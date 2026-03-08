"""
Email sending module.
Supports Resend and SendGrid.
"""

import aiohttp
from abc import ABC, abstractmethod
from typing import Optional


class BaseEmailer(ABC):
    """Abstract base class for email services."""
    
    @abstractmethod
    async def send(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
    ) -> bool:
        pass


class ResendEmailer(BaseEmailer):
    """Send emails using Resend API."""
    
    API_URL = "https://api.resend.com/emails"
    
    def __init__(self, api_key: str, from_email: str = "paperfeeder@resend.dev"):
        self.api_key = api_key
        self.from_email = from_email
    
    async def send(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
    ) -> bool:
        """Send an email using Resend."""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "from": self.from_email,
            "to": [to] if isinstance(to, str) else to,
            "subject": subject,
            "html": html_content,
        }
        
        if text_content:
            payload["text"] = text_content
        if attachments:
            payload["attachments"] = attachments
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.API_URL,
                headers=headers,
                json=payload,
            ) as response:
                if response.status == 200:
                    return True
                else:
                    error = await response.text()
                    print(f"Resend error: {response.status} - {error}")
                    return False


class SendGridEmailer(BaseEmailer):
    """Send emails using SendGrid API."""
    
    API_URL = "https://api.sendgrid.com/v3/mail/send"
    
    def __init__(self, api_key: str, from_email: str):
        self.api_key = api_key
        self.from_email = from_email
    
    async def send(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
    ) -> bool:
        """Send an email using SendGrid."""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": self.from_email},
            "subject": subject,
            "content": [{"type": "text/html", "value": html_content}],
        }
        
        if text_content:
            payload["content"].insert(0, {"type": "text/plain", "value": text_content})
        if attachments:
            payload["attachments"] = [
                {
                    "content": a.get("content", ""),
                    "filename": a.get("filename", "attachment.bin"),
                    "type": a.get("content_type", "application/octet-stream"),
                    "disposition": "attachment",
                }
                for a in attachments
            ]
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.API_URL,
                headers=headers,
                json=payload,
            ) as response:
                if response.status in (200, 202):
                    return True
                else:
                    error = await response.text()
                    print(f"SendGrid error: {response.status} - {error}")
                    return False


class ConsoleEmailer(BaseEmailer):
    """Mock emailer that prints to console (for testing)."""
    
    async def send(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
    ) -> bool:
        """Print email to console."""
        print("\n" + "=" * 60)
        print(f"TO: {to}")
        print(f"SUBJECT: {subject}")
        print("=" * 60)
        print(html_content[:2000])
        if len(html_content) > 2000:
            print(f"\n... [{len(html_content) - 2000} more characters]")
        print("=" * 60 + "\n")
        return True


class FileEmailer(BaseEmailer):
    """Save email to file (for testing/preview)."""
    
    def __init__(self, output_path: str = "email_preview.html"):
        self.output_path = output_path
    
    async def send(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
    ) -> bool:
        """Save email to file."""
        try:
            with open(self.output_path, "w") as f:
                f.write(f"<!-- TO: {to} -->\n")
                f.write(f"<!-- SUBJECT: {subject} -->\n")
                f.write(html_content)
            print(f"Email saved to {self.output_path}")
            return True
        except Exception as e:
            print(f"Error saving email: {e}")
            return False
