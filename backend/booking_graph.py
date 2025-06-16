import os
from typing import List, Optional, TypedDict, Annotated, Union
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from backend.tool_schemas import AppointmentSchema, TicketSchema
from backend.custom_tools import schedule_appointment_tool, create_ticket_tool
from backend.lead_graph import llm as chat_llm, get_rag_chain

# --- State Definition (ensure it's consistent with previous versions) ---
class BookingGraphState(TypedDict):
    conversation_history: Annotated[List[BaseMessage], lambda x, y: x + y]
    user_request_type: Optional[str]
    appointment_details: Optional[AppointmentSchema]
    appointment_slot_service_type_asked: bool
    appointment_slot_date_asked: bool
    appointment_slot_time_asked: bool
    appointment_slot_details_asked: bool
    ticket_details: Optional[TicketSchema]
    ticket_slot_issue_type_asked: bool
    ticket_slot_description_asked: bool
    ticket_slot_priority_asked: bool
    confirmation_summary: Optional[str]
    final_tool_response: Optional[str]
    interaction_count: int
    current_ai_response: Optional[str]

# --- Helper function for LLM extraction (consistent with previous versions) ---
def extract_info_with_llm(field_name: str, user_message: str, context: Optional[str] = None) -> Optional[str]:
    if not user_message: return None
    field_prompts = {
        "service_type": "Extract the type of service requested for an appointment. Examples: 'translation', 'interpretation', 'consultation'. If multiple, pick the most prominent or first mentioned.",
        "date": "Extract the date for the appointment. Try to format as YYYY-MM-DD if possible, but also accept relative dates like 'tomorrow', 'next Monday'. Context: {context}",
        "time": "Extract the time for the appointment. Try to format as HH:MM or include AM/PM. Context: {context}",
        "details": "Extract any additional details, notes, or specific requests for the appointment. If the user says 'no', 'none', 'not applicable', or similar, consider it as no details and respond with 'None'. Context: {context}",
        "issue_type": "Extract the type or category of the issue for a support ticket. Examples: 'technical problem', 'billing inquiry', 'service question', 'account access'. Context: {context}",
        "description": "Extract the detailed description of the issue for a support ticket. This should be a comprehensive explanation of the problem or request. Context: {context}",
        "priority": "Extract the priority for a support ticket (e.g., 'low', 'medium', 'high'). If not mentioned, or if unclear, it's okay to respond 'None'. Context: {context}",
        "confirmation": "The user is being asked to confirm details previously summarized. Does the user's message mean 'yes', 'confirm', 'ok', 'proceed', 'correct', 'yep', 'yeah', 'sounds good', 'y'? Respond only with 'yes' or 'no'."
    }
    instruction = field_prompts.get(field_name)
    if not instruction:
        print(f"Warning: Unknown field_name '{field_name}' for LLM extraction.")
        return None
    instruction = instruction.format(context=context or "not specified")

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=f"You are an information extraction assistant. {instruction} Respond with only the extracted information, or 'None' if not found (unless it's 'yes'/'no' for confirmation)."),
        HumanMessage(content=user_message)
    ])
    chain = prompt | chat_llm
    try:
        extracted = chain.invoke({}).content.strip()
    except Exception as e:
        print(f"LLM call failed for field {field_name} extraction: {e}")
        return None

    if field_name == "confirmation":
        return extracted.lower() if extracted.lower() in ["yes", "no"] else "no"
    return extracted if extracted.lower() != "none" else None

# --- Helper function to generate questions using LLM ---
def generate_question_with_llm(target_field: str, context_info: Optional[dict] = None) -> str:
    context_info = context_info or {}
    system_message_base = "You are a helpful assistant. Your goal is to ask a polite and clear question to get specific information from a user for their current request."

    question_prompt_instruction = "" # This will be the specific instruction for the LLM
    if target_field == "service_type":
        question_prompt_instruction = "The user wants to book an appointment. Ask them what type of service they are interested in (e.g., translation, interpretation)."
    elif target_field == "date":
        service = context_info.get("service_type", "the service")
        question_prompt_instruction = f"The user wants to book an appointment for '{service}'. Ask them for the desired date."
    elif target_field == "time":
        service = context_info.get("service_type", "the service")
        date = context_info.get("date", "the chosen date")
        question_prompt_instruction = f"The user wants to book an appointment for '{service}' on '{date}'. Ask them for the desired time."
    elif target_field == "details":
        question_prompt_instruction = "The user has provided the main details for their appointment (service, date, time). Ask them if they have any additional details or specific requests. Mention this is optional and they can say 'no' or 'none'."
    elif target_field == "issue_type":
        question_prompt_instruction = "The user wants to create a support ticket. Ask them for the type or category of their issue (e.g., technical problem, billing inquiry, account access)."
    elif target_field == "description":
        issue = context_info.get("issue_type", "the issue")
        question_prompt_instruction = f"The user wants to create a support ticket regarding '{issue}'. Ask them to describe this issue in more detail."
    elif target_field == "priority":
        issue = context_info.get("issue_type", "the issue")
        description = context_info.get("description", "the previously described issue")
        question_prompt_instruction = f"The user has described an issue ('{issue}': '{description[:50]}...'). Ask them for the priority level for this ticket (e.g., low, medium, high). Mention that 'medium' is the default if they don't specify."
    else:
        print(f"Warning: Unknown target_field '{target_field}' for question generation.")
        return "I'm not sure what information to ask for next. Can you clarify?"

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=system_message_base),
        HumanMessage(content=question_prompt_instruction)
    ])
    chain = prompt | chat_llm
    try:
        generated_question = chain.invoke({}).content.strip()
    except Exception as e:
        print(f"LLM call failed for question generation (field: {target_field}): {e}")
        # Fallback to a simpler hardcoded question if LLM fails
        if target_field == "service_type": return "What type of service are you interested in?"
        if target_field == "date": return f"What date would you like for the {context_info.get('service_type','service')}?"
        # Add other fallbacks as needed
        return "Could you provide more information?"

    return generated_question

# --- Node Implementations (Full Versions from previous steps, with question generation updated) ---

def classify_intent_node(state: BookingGraphState) -> BookingGraphState:
    print(f"--- NODE: classify_intent_node (Interaction: {state.get('interaction_count', 0)}) ---")
    user_input_content = ""
    if state.get("conversation_history") and isinstance(state["conversation_history"][-1], HumanMessage):
        user_input_content = state["conversation_history"][-1].content
    else:
        print("Warning: No human message found for intent classification.")
        return {**state, "user_request_type": "general", "current_ai_response": "I'm not sure how to respond. Could you try rephrasing?"}

    current_intent = state.get("user_request_type")
    appt_details = state.get("appointment_details")
    ticket_details = state.get("ticket_details")

    default_appt_flags = {"appointment_slot_service_type_asked": False, "appointment_slot_date_asked": False, "appointment_slot_time_asked": False, "appointment_slot_details_asked": False}
    default_ticket_flags = {"ticket_slot_issue_type_asked": False, "ticket_slot_description_asked": False, "ticket_slot_priority_asked": False}

    appt_flags = {k: state.get(k, v) for k, v in default_appt_flags.items()}
    ticket_flags = {k: state.get(k, v) for k, v in default_ticket_flags.items()}

    prompt_template = ChatPromptTemplate.from_messages([
        SystemMessage(content=(
            "You are an intent classification assistant. Based on the user's latest message, "
            "classify the intent as one of the following: 'appointment', 'ticket', or 'general'. "
            "If the user is providing information that seems to be part of an ongoing appointment or ticket collection (e.g. providing a date after being asked), "
            "maintain the current intent. Provide only the classification word."
        )),
        HumanMessage(content="{user_message}")
    ])
    intent_classification_chain = prompt_template | chat_llm
    raw_llm_intent = intent_classification_chain.invoke({"user_message": user_input_content}).content.strip().lower()

    determined_intent = "general"
    if "appointment" in raw_llm_intent: determined_intent = "appointment"
    elif "ticket" in raw_llm_intent: determined_intent = "ticket"
    elif current_intent in ["appointment", "ticket"] and user_input_content:
        if not any(kw in user_input_content.lower() for kw in ["appointment", "ticket", "book", "schedule", "issue", "problem", "cancel", "stop"]): # if not a clear new intent keyword
             determined_intent = current_intent

    print(f"LLM raw intent: '{raw_llm_intent}', Current intent: '{current_intent}', Determined intent: '{determined_intent}'")

    updated_state = {**state, "user_request_type": determined_intent, "current_ai_response": None, "confirmation_summary": None, "final_tool_response": None}

    if determined_intent == "appointment":
        if current_intent != "appointment" or not isinstance(appt_details, AppointmentSchema):
            updated_state.update({"appointment_details": AppointmentSchema(service_type="", date="", time="", details=None), **default_appt_flags, "ticket_details": None})
        else:
            updated_state.update({"appointment_details": appt_details, **appt_flags}) # Preserve existing details & flags
    elif determined_intent == "ticket":
        if current_intent != "ticket" or not isinstance(ticket_details, TicketSchema):
            updated_state.update({"ticket_details": TicketSchema(issue_type="", description="", priority="medium"), **default_ticket_flags, "appointment_details": None})
        else:
            updated_state.update({"ticket_details": ticket_details, **ticket_flags}) # Preserve existing details & flags
    else: # General intent
        if current_intent == "appointment": updated_state.update({"appointment_details": None, **default_appt_flags})
        if current_intent == "ticket": updated_state.update({"ticket_details": None, **default_ticket_flags})

    return updated_state


def collect_appointment_details_node(state: BookingGraphState) -> BookingGraphState:
    print("--- NODE: collect_appointment_details_node ---")
    appointment_data_from_state = state.get("appointment_details")

    if not isinstance(appointment_data_from_state, AppointmentSchema):
        if state.get("user_request_type") == "appointment":
            print("Warning: appointment_details not AppointmentSchema. Initializing.")
            current_details = AppointmentSchema(service_type="", date="", time="", details=None)
            question = generate_question_with_llm("service_type")
            return {**state, "appointment_details": current_details, "appointment_slot_service_type_asked": True, "appointment_slot_date_asked": False, "appointment_slot_time_asked": False, "appointment_slot_details_asked": False, "current_ai_response": question}
        else:
            return {**state, "current_ai_response": "Error processing appointment. Please clarify you want an appointment.", "user_request_type": "general"}

    current_details = appointment_data_from_state.model_copy(deep=True)
    history = state.get("conversation_history", [])
    last_user_message = history[-1].content if history and isinstance(history[-1], HumanMessage) else ""
    state_update: dict = {"appointment_details": current_details}
    context_for_q = {"service_type": current_details.service_type, "date": current_details.date, "time": current_details.time}


    if not current_details.service_type:
        if not state.get("appointment_slot_service_type_asked"):
            state_update["current_ai_response"] = generate_question_with_llm("service_type", context_for_q)
            state_update["appointment_slot_service_type_asked"] = True
        else:
            extracted = extract_info_with_llm("service_type", last_user_message)
            if extracted: current_details.service_type = extracted
            state_update["appointment_slot_service_type_asked"] = False
            state_update["current_ai_response"] = None if extracted else generate_question_with_llm("service_type", context_for_q)
        return {**state, **state_update}

    if not current_details.date:
        if not state.get("appointment_slot_date_asked"):
            context_for_q["service_type"] = current_details.service_type # Update context
            state_update["current_ai_response"] = generate_question_with_llm("date", context_for_q)
            state_update["appointment_slot_date_asked"] = True
        else:
            extracted = extract_info_with_llm("date", last_user_message, current_details.service_type)
            if extracted: current_details.date = extracted
            state_update["appointment_slot_date_asked"] = False
            context_for_q["service_type"] = current_details.service_type # Update context
            state_update["current_ai_response"] = None if extracted else generate_question_with_llm("date", context_for_q)
        return {**state, **state_update}

    if not current_details.time:
        if not state.get("appointment_slot_time_asked"):
            context_for_q.update({"service_type": current_details.service_type, "date": current_details.date})
            state_update["current_ai_response"] = generate_question_with_llm("time", context_for_q)
            state_update["appointment_slot_time_asked"] = True
        else:
            extracted = extract_info_with_llm("time", last_user_message, current_details.service_type)
            if extracted: current_details.time = extracted
            state_update["appointment_slot_time_asked"] = False
            context_for_q.update({"service_type": current_details.service_type, "date": current_details.date})
            state_update["current_ai_response"] = None if extracted else generate_question_with_llm("time", context_for_q)
        return {**state, **state_update}

    if current_details.details is None:
        if not state.get("appointment_slot_details_asked"):
            state_update["current_ai_response"] = generate_question_with_llm("details", context_for_q)
            state_update["appointment_slot_details_asked"] = True
        else:
            extracted = extract_info_with_llm("details", last_user_message, current_details.service_type)
            current_details.details = extracted if extracted else "N/A"
            state_update["appointment_slot_details_asked"] = False
            state_update["current_ai_response"] = None
        return {**state, **state_update}

    if current_details.service_type and current_details.date and current_details.time and (current_details.details is not None):
        print(f"All appointment details collected: {current_details.model_dump_json(indent=2)}")
        state_update["current_ai_response"] = None
        return {**state, **state_update}

    print(f"Warning: Fallback in collect_appointment_details_node. State: {{k:v for k,v in state.items() if k != 'conversation_history'}}")
    state_update.update({
        "current_ai_response": generate_question_with_llm("service_type"), # Re-ask first question
        "appointment_details": AppointmentSchema(service_type="",date="",time="",details=None),
        "appointment_slot_service_type_asked": True, "appointment_slot_date_asked": False,
        "appointment_slot_time_asked": False, "appointment_slot_details_asked": False
    })
    return {**state, **state_update}


def collect_ticket_details_node(state: BookingGraphState) -> BookingGraphState:
    print("--- NODE: collect_ticket_details_node ---")
    ticket_data_from_state = state.get("ticket_details")

    if not isinstance(ticket_data_from_state, TicketSchema):
        if state.get("user_request_type") == "ticket":
            print("Warning: ticket_details not TicketSchema. Initializing.")
            current_details = TicketSchema(issue_type="", description="", priority="medium")
            question = generate_question_with_llm("issue_type")
            return {**state, "ticket_details": current_details, "ticket_slot_issue_type_asked": True, "ticket_slot_description_asked": False, "ticket_slot_priority_asked": False, "current_ai_response": question}
        else:
             return {**state, "current_ai_response": "Error processing ticket. Please clarify you need a support ticket.", "user_request_type": "general"}

    current_details = ticket_data_from_state.model_copy(deep=True)
    history = state.get("conversation_history", [])
    last_user_message = history[-1].content if history and isinstance(history[-1], HumanMessage) else ""
    state_update: dict = {"ticket_details": current_details}
    context_for_q = {"issue_type": current_details.issue_type, "description": current_details.description}


    if not current_details.issue_type:
        if not state.get("ticket_slot_issue_type_asked"):
            state_update["current_ai_response"] = generate_question_with_llm("issue_type", context_for_q)
            state_update["ticket_slot_issue_type_asked"] = True
        else:
            extracted = extract_info_with_llm("issue_type", last_user_message)
            if extracted: current_details.issue_type = extracted
            state_update["ticket_slot_issue_type_asked"] = False
            state_update["current_ai_response"] = None if extracted else generate_question_with_llm("issue_type", context_for_q)
        return {**state, **state_update}

    if not current_details.description:
        if not state.get("ticket_slot_description_asked"):
            context_for_q["issue_type"] = current_details.issue_type # Update context
            state_update["current_ai_response"] = generate_question_with_llm("description", context_for_q)
            state_update["ticket_slot_description_asked"] = True
        else:
            extracted = extract_info_with_llm("description", last_user_message, current_details.issue_type)
            if extracted: current_details.description = extracted
            state_update["ticket_slot_description_asked"] = False
            context_for_q["issue_type"] = current_details.issue_type # Update context
            state_update["current_ai_response"] = None if extracted else generate_question_with_llm("description", context_for_q)
        return {**state, **state_update}

    if current_details.priority == "medium" and not state.get("ticket_slot_priority_asked"):
        if current_details.issue_type and current_details.description:
            context_for_q.update({"issue_type": current_details.issue_type, "description": current_details.description})
            state_update["current_ai_response"] = generate_question_with_llm("priority", context_for_q)
            state_update["ticket_slot_priority_asked"] = True
            return {**state, **state_update}
    elif state.get("ticket_slot_priority_asked"):
        extracted = extract_info_with_llm("priority", last_user_message, current_details.issue_type)
        if extracted and extracted.lower() in ["low", "medium", "high"]:
            current_details.priority = extracted.lower()
        state_update["ticket_slot_priority_asked"] = False
        state_update["current_ai_response"] = None
        return {**state, **state_update}

    if current_details.issue_type and current_details.description and not state.get("ticket_slot_priority_asked"):
        print(f"All ticket details collected: {current_details.model_dump_json(indent=2)}")
        state_update["current_ai_response"] = None
        return {**state, **state_update}

    if "current_ai_response" not in state_update or state_update["current_ai_response"] is None :
         state_update["current_ai_response"] = generate_question_with_llm("issue_type") # Re-ask first question
         print(f"Warning: Fallback in collect_ticket_details_node. Current details: {current_details.model_dump()}")
    return {**state, **state_update}


def generate_summary_node(state: BookingGraphState) -> BookingGraphState:
    # (Implementation from previous step - unchanged)
    print("--- NODE: generate_summary_node ---")
    request_type = state.get("user_request_type")
    summary_text = ""
    if request_type == "appointment":
        details = state.get("appointment_details")
        if not (isinstance(details, AppointmentSchema) and all([details.service_type, details.date, details.time, details.details is not None])):
            return {**state, "current_ai_response": "It seems some appointment details are missing. Let's try collecting them again.", "user_request_type": "appointment"}
        summary_text = (f"Okay, I have the following appointment details for you:\n"
                       f"- Service: {details.service_type}\n- Date: {details.date}\n- Time: {details.time}")
        if details.details and details.details.lower() not in ["none", "n/a", ""]: summary_text += f"\n- Additional Details: {details.details}"
    elif request_type == "ticket":
        details = state.get("ticket_details")
        if not (isinstance(details, TicketSchema) and all([details.issue_type, details.description, details.priority is not None])):
            return {**state, "current_ai_response": "It seems some ticket details are missing. Let's try collecting them again.", "user_request_type": "ticket"}
        summary_text = (f"Here's a summary of your support ticket request:\n"
                       f"- Issue Type: {details.issue_type}\n- Description: {details.description}\n- Priority: {details.priority or 'medium'}")
    else:
        return {**state, "current_ai_response": "I'm not sure what I'm confirming. Could you please clarify your request?", "user_request_type": "general"}
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content="You are a helpful assistant. Rephrase the following summary into a natural confirmation question for the user. Ask them to confirm if the details are correct and if they want to proceed. End with a clear question asking for 'yes' or 'no' (or similar confirmation)."),
        HumanMessage(content=f"Here is the summary:\n{summary_text}")
    ])
    chain = prompt | chat_llm
    try: confirmation_question = chain.invoke({}).content
    except Exception as e:
        print(f"Error using LLM for rephrasing summary: {e}")
        confirmation_question = f"{summary_text}\n\nIs this information correct and would you like to proceed? (Please reply with 'yes' or 'no')"
    return {**state, "confirmation_summary": summary_text, "current_ai_response": confirmation_question}

def execute_tool_node(state: BookingGraphState) -> BookingGraphState:
    # (Implementation from previous step - unchanged)
    print("--- NODE: execute_tool_node ---")
    request_type = state.get("user_request_type")
    tool_output = f"Error: No action taken for '{request_type}' or details missing."
    try:
        if request_type == "appointment" and isinstance(state.get("appointment_details"), AppointmentSchema):
            tool_output = schedule_appointment_tool.invoke(state["appointment_details"].model_dump())
        elif request_type == "ticket" and isinstance(state.get("ticket_details"), TicketSchema):
            tool_output = create_ticket_tool.invoke(state["ticket_details"].model_dump())
        else: tool_output = "No valid details found to execute a tool."
    except Exception as e:
        print(f"Error during tool execution: {e}")
        tool_output = f"Sorry, there was an error processing your {request_type} request. Please try again later."
    return {**state, "final_tool_response": tool_output, "current_ai_response": tool_output, "user_request_type": "general", "appointment_details": None, "ticket_details": None, "confirmation_summary": None, "appointment_slot_service_type_asked": False, "appointment_slot_date_asked": False, "appointment_slot_time_asked": False, "appointment_slot_details_asked": False, "ticket_slot_issue_type_asked": False, "ticket_slot_description_asked": False, "ticket_slot_priority_asked": False }

def general_chat_node(state: BookingGraphState) -> BookingGraphState:
    # (Implementation from previous step - unchanged)
    print("--- NODE: general_chat_node ---")
    rag_chain = None
    try: rag_chain = get_rag_chain()
    except Exception as e: print(f"Error getting RAG chain: {e}. Proceeding without RAG.")
    history = state.get("conversation_history", [])
    user_input = history[-1].content if history and isinstance(history[-1], HumanMessage) else "Hello"
    response_content = f"I'm sorry, I couldn't find information on that. How else can I assist you?"
    if rag_chain:
        try:
            response = rag_chain.invoke({"question": user_input, "history": history[:-1]})
            response_content = response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            print(f"Error invoking RAG chain: {e}. Falling back to basic LLM.")
            try: response_content = chat_llm.invoke(history).content
            except Exception as e2: print(f"Error invoking basic LLM in general_chat_node: {e2}")
    else:
        print("RAG chain not available. Using basic LLM for general_chat_node.")
        try: response_content = chat_llm.invoke(history).content
        except Exception as e: print(f"Error invoking basic LLM in general_chat_node: {e}")
    return {**state, "current_ai_response": response_content}


# --- Graph Workflow Definition & Compilation (consistent with previous versions) ---
workflow = StateGraph(BookingGraphState)
# ... (Graph definition and compilation from previous step, unchanged)
workflow.add_node("classify_intent", classify_intent_node)
workflow.add_node("collect_appointment_details", collect_appointment_details_node)
workflow.add_node("collect_ticket_details", collect_ticket_details_node)
workflow.add_node("generate_summary", generate_summary_node)
workflow.add_node("execute_tool", execute_tool_node)
workflow.add_node("general_chat", general_chat_node)

def route_after_intent_classification(state: BookingGraphState):
    intent = state.get("user_request_type")
    print(f"ROUTE: After Intent. Intent: '{intent}'")
    if intent == "appointment": return "collect_appointment_details"
    if intent == "ticket": return "collect_ticket_details"
    return "general_chat"

def route_after_detail_collection(state: BookingGraphState):
    ai_response = state.get("current_ai_response")
    current_intent = state.get("user_request_type")
    print(f"ROUTE: After Detail Collection for '{current_intent}'. AI needs more info: '{ai_response is not None}'")
    if ai_response is None:
        if current_intent == "appointment":
            appt = state.get("appointment_details")
            if not (appt and appt.service_type and appt.date and appt.time and appt.details is not None):
                return "collect_appointment_details"
        elif current_intent == "ticket":
            ticket = state.get("ticket_details")
            if not (ticket and ticket.issue_type and ticket.description and ticket.priority is not None):
                return "collect_ticket_details"
        return "generate_summary"
    else:
        if current_intent == "appointment": return "collect_appointment_details"
        if current_intent == "ticket": return "collect_ticket_details"
        return "classify_intent"

def route_after_summary_prompt(state: BookingGraphState):
    last_message_content = ""
    if state.get("conversation_history") and isinstance(state["conversation_history"][-1], HumanMessage):
        last_message_content = state["conversation_history"][-1].content
    confirmation = extract_info_with_llm("confirmation", last_message_content, context=state.get("confirmation_summary"))
    print(f"ROUTE: After Summary. User Confirmed with '{last_message_content[:30]}...': Extracted as '{confirmation}'")
    if confirmation == "yes":
        return "execute_tool"
    else: # "no" or unclear
        current_intent = state.get("user_request_type")
        print(f"User did not confirm summary for {current_intent}. Routing back to collection to allow corrections or clarification.")
        state["confirmation_summary"] = None
        if current_intent == "appointment":
            state.update({k: False for k in ["appointment_slot_service_type_asked", "appointment_slot_date_asked", "appointment_slot_time_asked", "appointment_slot_details_asked"]})
            return "collect_appointment_details"
        if current_intent == "ticket":
            state.update({k: False for k in ["ticket_slot_issue_type_asked", "ticket_slot_description_asked", "ticket_slot_priority_asked"]})
            return "collect_ticket_details"
        state["current_ai_response"] = "Okay, I've cancelled that. How can I help you now?"
        return "general_chat"

workflow.set_entry_point("classify_intent")
workflow.add_conditional_edges("classify_intent", route_after_intent_classification)
workflow.add_conditional_edges("collect_appointment_details", route_after_detail_collection)
workflow.add_conditional_edges("collect_ticket_details", route_after_detail_collection)
workflow.add_conditional_edges("generate_summary", route_after_summary_prompt)
workflow.add_edge("execute_tool", "general_chat")
workflow.add_edge("general_chat", "classify_intent")

db_path_dir = os.path.dirname(os.path.abspath(__file__))
if not os.path.exists(db_path_dir):
    os.makedirs(db_path_dir) # Ensure directory exists for the SQLite DB
db_path = os.path.join(db_path_dir, "booking_checkpoints.sqlite")
memory_checkpointer = SqliteSaver.from_conn_string(db_path)
app_graph = workflow.compile(checkpointer=memory_checkpointer)
print(f"Graph compiled successfully with SQLite checkpointer at {db_path}")


def invoke_booking_graph(session_id: str, user_input: str) -> dict:
    # (Implementation from previous step - unchanged)
    config = {"configurable": {"thread_id": session_id}}
    current_state_snapshot = app_graph.get_state(config)
    interaction_count = current_state_snapshot.values.get("interaction_count", 0) + 1 if current_state_snapshot else 1
    inputs = {"conversation_history": [HumanMessage(content=user_input)], "interaction_count": interaction_count}
    ai_response_to_user = "Error: No response generated."
    for event_chunk in app_graph.stream(inputs, config, stream_mode="updates"):
        for node_name, node_output_update in event_chunk.items():
            if isinstance(node_output_update, dict) and "current_ai_response" in node_output_update and node_output_update["current_ai_response"] is not None:
                ai_response_to_user = node_output_update["current_ai_response"]
    final_state_values = app_graph.get_state(config).values if app_graph.get_state(config) else {}
    return {"session_id": session_id, "ai_response": ai_response_to_user, "full_graph_state": final_state_values }

if __name__ == '__main__':
    # (Test conversation from previous step - unchanged)
    print("\n--- Testing LLM-Generated Questions in Full Graph Flow ---")
    print("Ensure GROQ_API_KEY is set for LLM calls.")
    session_id = f"test_session_llm_questions_main_{os.getpid()}"
    print(f"Using Session ID: {session_id}")
    test_conversation = [
        ("Hi", "general"), ("I need to book an appointment", "appointment"), ("translation service", "appointment"),
        ("For next Monday", "appointment"), ("10 AM should be fine", "appointment"), ("No, that's all for details", "appointment"),
        ("Yes, looks good", "execute_tool"), ("Thanks!", "general"),
        ("I have an issue with my login", "ticket"),("It's a technical problem", "ticket"),
        ("I cannot access my account, it says 'invalid credentials'.", "ticket"),("High", "ticket"),
        ("Yes", "execute_tool"),("Goodbye", "general")
    ]
    for i, (user_msg, expected_intent_category) in enumerate(test_conversation):
        print(f"--- Turn {i+1} ---"); print(f"User: {user_msg}")
        response_data = invoke_booking_graph(session_id, user_msg)
        print(f"AI: {response_data['ai_response']}")
        if os.getenv("CI_RUN"): pass
        else: input("Press Enter for next turn...")
    print("LLM question generation test conversation complete.")
