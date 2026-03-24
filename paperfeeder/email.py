"""
Send digest email via Resend, SendGrid, console, or file preview.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import aiohttp


class BaseEmailer(ABC):
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
            async with session.post(self.API_URL, headers=headers, json=payload) as response:
                if response.status == 200:
                    return True
                error = await response.text()
                print(f"Resend error: {response.status} - {error}")
                return False


class SendGridEmailer(BaseEmailer):
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
                    "content": attachment.get("content", ""),
                    "filename": attachment.get("filename", "attachment.bin"),
                    "type": attachment.get("content_type", "application/octet-stream"),
                    "disposition": "attachment",
                }
                for attachment in attachments
            ]
        async with aiohttp.ClientSession() as session:
            async with session.post(self.API_URL, headers=headers, json=payload) as response:
                if response.status in (200, 202):
                    return True
                error = await response.text()
                print(f"SendGrid error: {response.status} - {error}")
                return False


class ConsoleEmailer(BaseEmailer):
    async def send(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
    ) -> bool:
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
        try:
            with open(self.output_path, "w") as handle:
                handle.write(f"<!-- TO: {to} -->\n")
                handle.write(f"<!-- SUBJECT: {subject} -->\n")
                handle.write(html_content)
            print(f"Email saved to {self.output_path}")
            return True
        except Exception as exc:
            print(f"Error saving email: {exc}")
            return False

