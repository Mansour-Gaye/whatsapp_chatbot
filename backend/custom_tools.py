from langchain.tools import StructuredTool
from backend.tool_schemas import AppointmentSchema, TicketSchema

def schedule_appointment_tool_func(appointment: AppointmentSchema) -> str:
    """
    Placeholder function to simulate scheduling an appointment.
    In a real scenario, this would interact with a calendar API (Google Calendar, Cal.com, etc.).
    """
    print(f"[TOOL_STUB] Scheduling appointment: {appointment.model_dump()}")
    # Simulate API call success
    return f"Appointment confirmed for {appointment.service_type} on {appointment.date} at {appointment.time}. Details: {appointment.details or 'N/A'}."

def create_ticket_tool_func(ticket: TicketSchema) -> str:
    """
    Placeholder function to simulate creating a support ticket.
    In a real scenario, this would interact with a ticketing system (Jira, Zendesk, etc.).
    """
    print(f"[TOOL_STUB] Creating ticket: {ticket.model_dump()}")
    # Simulate API call success
    ticket_id = "TICKET-12345" # Example ticket ID
    return f"Ticket {ticket_id} created for issue: {ticket.issue_type} with priority {ticket.priority}. Description: {ticket.description}. You will be contacted shortly."

# Convert functions to LangChain StructuredTools
schedule_appointment_tool = StructuredTool.from_function(
    func=schedule_appointment_tool_func,
    name="ScheduleAppointment",
    description="Schedules a new appointment. Use this to book services, meetings, or consultations.",
    args_schema=AppointmentSchema
)

create_ticket_tool = StructuredTool.from_function(
    func=create_ticket_tool_func,
    name="CreateSupportTicket",
    description="Creates a new support ticket for issues, requests, or problems.",
    args_schema=TicketSchema
)

if __name__ == '__main__':
    # Example usage:
    print("--- Testing ScheduleAppointment Tool ---")
    appointment_data = {
        "service_type": "interpretation_conférence",
        "date": "2024-10-01",
        "time": "10:00",
        "details": "Conference call with 3 international participants."
    }
    try:
        # Tools are typically invoked with a single dictionary argument for their inputs.
        result_appointment = schedule_appointment_tool.invoke(appointment_data)
        print(f"Appointment tool raw output type: {type(result_appointment)}")
        print(f"Appointment tool output: {result_appointment}")
    except Exception as e:
        print(f"Error invoking appointment tool: {e}")

    print("\n--- Testing CreateSupportTicket Tool ---")
    ticket_data = {
        "issue_type": "quote_request",
        "description": "Need a quote for translating a 50-page manual from English to German.",
        "priority": "high"
    }
    try:
        result_ticket = create_ticket_tool.invoke(ticket_data)
        print(f"Ticket tool raw output type: {type(result_ticket)}")
        print(f"Ticket tool output: {result_ticket}")
    except Exception as e:
        print(f"Error invoking ticket tool: {e}")

    print("\nAvailable tools:")
    print(f"- {schedule_appointment_tool.name}: {schedule_appointment_tool.description}")
    print(f"- {create_ticket_tool.name}: {create_ticket_tool.description}")
