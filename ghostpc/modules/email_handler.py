"""
GhostPC Email Module
IMAP (read) + SMTP (send) email integration.
"""

import email
import imaplib
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _get_config():
    from config import EMAIL_IMAP, EMAIL_SMTP, EMAIL_ADDRESS, EMAIL_PASSWORD
    return EMAIL_IMAP, EMAIL_SMTP, EMAIL_ADDRESS, EMAIL_PASSWORD


def _imap_connect():
    imap_host, _, address, password = _get_config()
    if not imap_host or not address or not password:
        raise ValueError("Email not configured. Run setup.py and enable email.")
    conn = imaplib.IMAP4_SSL(imap_host)
    conn.login(address, password)
    return conn


# ─── Read Emails ─────────────────────────────────────────────────────────────

def get_emails(folder: str = "INBOX", limit: int = 10, unread_only: bool = False) -> dict:
    """Fetch emails from a folder."""
    try:
        conn = _imap_connect()
        conn.select(folder)

        search_criteria = "UNSEEN" if unread_only else "ALL"
        _, data = conn.search(None, search_criteria)
        email_ids = data[0].split()

        # Take the most recent N
        recent_ids = email_ids[-limit:][::-1]

        emails = []
        for eid in recent_ids:
            _, msg_data = conn.fetch(eid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = email.header.decode_header(msg["Subject"] or "")[0]
            subject = subject[0].decode(subject[1] or "utf-8") if isinstance(subject[0], bytes) else subject[0]

            sender = msg.get("From", "")
            date = msg.get("Date", "")

            # Extract plain text body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                        body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="replace")

            emails.append({
                "id": eid.decode(),
                "subject": subject,
                "from": sender,
                "date": date,
                "body": body[:500],
            })

        conn.logout()

        lines = [f"📧 {folder} ({len(emails)} emails):\n"]
        for e in emails:
            lines.append(f"• From: {e['from'][:40]}\n  Subject: {e['subject']}\n  {e['body'][:80]}...")

        return {
            "success": True,
            "emails": emails,
            "text": "\n".join(lines),
        }

    except Exception as ex:
        logger.error(f"get_emails error: {ex}")
        return {"success": False, "error": str(ex)}


def get_unread_count() -> dict:
    """Get the count of unread emails."""
    try:
        conn = _imap_connect()
        conn.select("INBOX")
        _, data = conn.search(None, "UNSEEN")
        count = len(data[0].split())
        conn.logout()
        return {"success": True, "count": count, "text": f"📧 {count} unread email(s) in INBOX"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Send Email ──────────────────────────────────────────────────────────────

def send_email(
    to: str,
    subject: str,
    body: str,
    attachment_path: Optional[str] = None,
    html: bool = False,
) -> dict:
    """Send an email."""
    try:
        _, smtp_host, address, password = _get_config()
        if not smtp_host or not address or not password:
            raise ValueError("Email not configured.")

        msg = MIMEMultipart()
        msg["From"] = address
        msg["To"] = to
        msg["Subject"] = subject

        content_type = "html" if html else "plain"
        msg.attach(MIMEText(body, content_type))

        if attachment_path:
            p = Path(attachment_path)
            if p.exists():
                with open(p, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={p.name}")
                msg.attach(part)

        # Try SSL first (port 465), then TLS (port 587)
        try:
            with smtplib.SMTP_SSL(smtp_host, 465) as server:
                server.login(address, password)
                server.send_message(msg)
        except Exception:
            with smtplib.SMTP(smtp_host, 587) as server:
                server.starttls()
                server.login(address, password)
                server.send_message(msg)

        return {"success": True, "text": f"✅ Email sent to {to}: {subject}"}

    except Exception as e:
        logger.error(f"send_email error: {e}")
        return {"success": False, "error": str(e)}


def reply_email(email_id: str, body: str, folder: str = "INBOX") -> dict:
    """Reply to an email by its ID."""
    try:
        conn = _imap_connect()
        conn.select(folder)

        _, msg_data = conn.fetch(email_id.encode(), "(RFC822)")
        raw = msg_data[0][1]
        original = email.message_from_bytes(raw)

        # Get reply-to or from
        reply_to = original.get("Reply-To") or original.get("From", "")
        subject = original.get("Subject", "")
        if not subject.startswith("Re:"):
            subject = f"Re: {subject}"

        conn.logout()

        return send_email(reply_to, subject, body)

    except Exception as e:
        return {"success": False, "error": str(e)}
