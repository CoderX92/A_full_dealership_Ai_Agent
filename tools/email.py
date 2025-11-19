from langchain_core.tools import tool
from pydantic import BaseModel, Field
import smtplib
import ssl

# Configuration using env
EMAIL_CONFIG = {
    "smtp_server": "smtp.gmail.com",
    "port": 465,
    "sender": os.environ.get["SENDER_EMAIL"],
    "password": os.environ.get['PASSWORD'] # Not your gmail login pass
}

class SendEmailArgsSchema(BaseModel):
    recipient: str = Field(..., description="Email address of the recipient")
    subject: str = Field(..., description="Subject line of the email")
    body: str = Field(..., description="Main content of the email")

@tool(args_schema=SendEmailArgsSchema)
def send_email(recipient: str, subject: str, body: str) -> str:
    """Send an email to a specified recipient using configured SMTP settings."""
    
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            EMAIL_CONFIG["smtp_server"],
            EMAIL_CONFIG["port"],
            context=context
        ) as server:
            server.login(EMAIL_CONFIG["sender"], EMAIL_CONFIG["password"])
            message = f"Subject: {subject}\n\n{body}"
            server.sendmail(
                EMAIL_CONFIG["sender"],
                recipient,
                message
            )
        return "Email sent successfully!"
    
    except smtplib.SMTPAuthenticationError:
        return "Error: Authentication failed. Check email credentials."
    except smtplib.SMTPException as e:
        return f"Error sending email: {str(e)}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"
    
