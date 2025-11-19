# meeting_tools.py
from langchain_core.tools import tool
import csv
import json
from agents import AGENTS, notify_agent
import random
from email import send_email
from datetime import datetime
from typing import Optional

BOOKINGS_FILE = "bookings.csv"
CANCELLATIONS_FILE = "cancellations.log"

def initialize_files():
    """Initialize required files with headers"""
    try:
        with open(BOOKINGS_FILE, mode='x', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Date", "Hour", "Booked_By", "Client_Email", "Meeting_ID"])
    except FileExistsError:
        pass
        
    try:
        with open(CANCELLATIONS_FILE, mode='x') as file:
            file.write("timestamp,meeting_id,action_by,reason\n")
    except FileExistsError:
        pass

def generate_meeting_id(date: str, hour: str) -> str:
    """Generate unique meeting ID"""
    return f"{date.replace('-','')}{hour.replace(':','')}"

@tool
def book_meeting(
    date: str, 
    hour: str, 
    booked_by: str,
    client_email: str,
    reason: Optional[str] = None,
    max_future_days: int = 3  # Maximum days in future allowed for booking
) -> str:
    """Book a new meeting with real-time date validation. 
    Required: date (YYYY-MM-DD), hour (HH:MM), booked_by (name), client_email.
    Optional: reason.
    
    Validates:
    - Date is not in the past
    - Date is within max_future_days (default: 90 days)
    - Time slot is available"""
    
    initialize_files()
    try:
        # Parse and validate datetime format
        booking_datetime = datetime.strptime(f"{date} {hour}", "%Y-%m-%d %H:%M")
        current_datetime = datetime.now()
        
        # Real-time date validation
        if booking_datetime < current_datetime:
            return "❌ Cannot book meetings in the past"
            
        if (booking_datetime - current_datetime).days > max_future_days:
            return f"❌ Cannot book more than {max_future_days} days in advance"
        
        # Check availability
        with open(BOOKINGS_FILE, mode='r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row["Date"] == date and row["Hour"] == hour:
                    return (f"❌ Timeslot already booked\n"
                            f"Existing booking ID: {row['Meeting_ID']}\n"
                            f"Contact: {row['Client_Email']}")
        
        # Generate ID and book
        meeting_id = generate_meeting_id(date, hour)
        
        with open(BOOKINGS_FILE, mode='a', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=["Date", "Hour", "Booked_By", "Client_Email", "Meeting_ID"])
            if file.tell() == 0:
                writer.writeheader()
            writer.writerow({
                "Date": date,
                "Hour": hour,
                "Booked_By": booked_by,
                "Client_Email": client_email,
                "Meeting_ID": meeting_id
            })
            
        # Prepare confirmation
        confirmation = (f"✅ Meeting booked successfully\n"
                       f"ID: {meeting_id}\n"
                       f"Date: {date} at {hour}\n"
                       f"Client: {client_email}")
        
        if reason:
            confirmation += f"\nReason: {reason}"
            
        return confirmation
        
    except ValueError:
        return "⚠ Invalid format. Use YYYY-MM-DD and HH:MM (24h)"
    except Exception as e:
        return f"⚠ Booking failed: {str(e)}"
    
    
@tool
def book_meeting_with_agent(
    date: str,
    hour: str,
    client_name: str,
    client_email: str,
    client_phone: str,
    reason: Optional[str] = None
) -> str:
    """Book a meeting and notify a random sales agent.
    Required: date (YYYY-MM-DD), hour (HH:MM), client_name, 
    client_email, client_phone. Optional: reason."""
    
    # Book the meeting
    booking_result = book_meeting.invoke({
        "date": date,
        "hour": hour,
        "booked_by": "AI Assistant",
        "client_email": client_email,
        "reason": reason
    })
    
    if not booking_result.startswith("✅"):
        return booking_result
    
    # Select random agent
    agent = random.choice(AGENTS)
    
    # Notify agent
    notify_agent(agent.email, {
        "client_name": client_name,
        "client_phone": client_phone,
        "meeting_time": f"{date} {hour}",
        "reason": reason
    })
    
    return (
        f"{booking_result}\n\n"
        f"🔧 A car evaluation specialist ({agent.name}) will contact you soon.\n"
        f"Direct WhatsApp: {agent.whatsapp}\n"
        f"Email: {agent.email}"
    )


@tool
def cancel_meeting(
    client_email: str,
    meeting_date: Optional[str] = None,
    reason: Optional[str] = None
) -> str:
    """Cancel an existing meeting using the client's email and optional meeting date.
    Returns confirmation of cancellation or error if no meeting found.
    
    Args:
        client_email: Email address used to book the meeting (from Client_Email field)
        meeting_date: (Optional) Specific date to cancel (YYYY-MM-DD format)
        reason: (Optional) Reason for cancellation
    """
    
    initialize_files()
    try:
        # Find and remove booking
        rows = []
        cancelled = False
        meeting_details = None
        
        with open(BOOKINGS_FILE, mode='r') as file:
            reader = csv.DictReader(file)
            rows = list(reader)
            
        with open(BOOKINGS_FILE, mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=reader.fieldnames)
            writer.writeheader()
            
            for row in rows:
                # Match by client_email (case-insensitive) and optional date
                if (row["Client_Email"].lower() == client_email.lower() and 
                    (not meeting_date or row["Date"] == meeting_date)):
                    cancelled = True
                    meeting_details = row
                    # Log cancellation
                    with open(CANCELLATIONS_FILE, mode='a') as log:
                        log.write(f"{datetime.now().isoformat()},"
                                 f"{row['Meeting_ID']},"
                                 f"{row['Client_Email']},"
                                 f"{reason or 'No reason provided'}\n")
                else:
                    writer.writerow(row)
                    
        if cancelled:
            return (f"✅ Meeting cancelled successfully\n"
                    f"Client: {meeting_details['Booked_By']}\n"
                    f"Date: {meeting_details['Date']} at {meeting_details['Hour']}\n"
                    f"Meeting ID: {meeting_details['Meeting_ID']}\n"
                    f"Reason: {reason or 'Not specified'}")
        else:
            if meeting_date:
                return f"⚠ No meeting found for {client_email} on {meeting_date}"
            return f"⚠ No meetings found for {client_email}"
                
    except Exception as e:
        return f"⚠ Cancellation failed: {str(e)}"

@tool
def list_bookings(with_client_info: bool = False) -> str:
    """List all bookings. Set with_client_info=True to show client details."""
    
    initialize_files()
    try:
        with open(BOOKINGS_FILE, mode='r') as file:
            reader = csv.DictReader(file)
            bookings = list(reader)
            
        if not bookings:
            return "No upcoming bookings"
            
        return "\n".join(
            [f"{b['Date']} {b['Hour']} - ID: {b['Meeting_ID']}\n"
             f"{'Client: ' + b['Client_Email'] + ' | ' if with_client_info else ''}"
             f"Booked by: {b['Booked_By']}"
             for b in bookings]
        )
    except Exception as e:
        return f"Error retrieving bookings: {str(e)}"

@tool
def check_availability(date: str, hour: str) -> str:
    """Check meeting slot availability. Date format: YYYY-MM-DD, hour: HH:MM"""
    
    initialize_files()
    try:
        datetime.strptime(f"{date} {hour}", "%Y-%m-%d %H:%M")
        
        with open(BOOKINGS_FILE, mode='r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row["Date"] == date and row["Hour"] == hour:
                    return (f"❌ Booked (ID: {row['Meeting_ID']})\n"
                            f"Client: {row['Client_Email']}")
                            
        return f"✅ Available"
    except ValueError:
        return "⚠ Invalid date/time format"
    except Exception as e:
        return f"⚠ Check failed: {str(e)}"

# Export all tools
meeting_tools = [
    book_meeting,
    cancel_meeting,
    check_availability,
    list_bookings
]
print(check_availability.invoke({'date': '2023-10-11', 'hour': '15:00'}))
print(book_meeting.invoke({'date':"2025-05-28", 'hour':"04:00", 'booked_by':"Edwin", 'client_email':"past@example.com"}))
#print(cancel_meeting.invoke('edwinmade54@gmail.com', reason='l am caught in traffic'))
