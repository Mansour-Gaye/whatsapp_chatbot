from typing import Optional
from pydantic import BaseModel, Field

class AppointmentSchema(BaseModel):
    """Schema for scheduling an appointment."""
    service_type: str = Field(..., description="The type of service requested for the appointment. e.g., 'interpretation', 'translation'")
    date: str = Field(..., description="The requested date for the appointment, preferably in YYYY-MM-DD format.")
    time: str = Field(..., description="The requested time for the appointment, preferably in HH:MM format.")
    details: Optional[str] = Field(None, description="Any additional details or notes for the appointment.")

class TicketSchema(BaseModel):
    """Schema for creating a support ticket."""
    issue_type: str = Field(..., description="The type or category of the issue. e.g., 'technical_problem', 'billing_inquiry', 'service_request'")
    description: str = Field(..., description="A detailed description of the issue or request.")
    priority: Optional[str] = Field("medium", description="The priority of the ticket. e.g., 'low', 'medium', 'high'")

if __name__ == '__main__':
    # Example usage:
    appointment_example = AppointmentSchema(
        service_type="translation_project",
        date="2024-09-15",
        time="14:30",
        details="Need translation of a 10-page document from French to English."
    )
    print("Appointment Example:", appointment_example.model_dump_json(indent=2))

    ticket_example = TicketSchema(
        issue_type="service_request",
        description="I would like to inquire about the availability of Japanese interpreters for a conference.",
        priority="high"
    )
    print("\nTicket Example:", ticket_example.model_dump_json(indent=2))
