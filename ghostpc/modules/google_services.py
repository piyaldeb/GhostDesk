"""
GhostPC Google Services Module
Unified backend for Google Drive, Calendar, Docs, Gmail, and Contacts.
Uses google-api-python-client with OAuth2 / service-account auth.
No browser / Selenium — all API calls only.
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ─── Scopes ───────────────────────────────────────────────────────────────────

_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/documents",
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/contacts.readonly",
]

# ─── Auth helper ──────────────────────────────────────────────────────────────

def _get_credentials():
    """
    Returns valid Google OAuth2 credentials.
    Priority:
      1. Cached token at ~/.ghostdesk/google_token.json
      2. Service account at GOOGLE_SHEETS_CREDS_PATH or ~/.ghostdesk/google_service_account.json
      3. OAuth2 flow using ~/.ghostdesk/google_oauth_secret.json → saves token on first run
    """
    from config import USER_DATA_DIR, GOOGLE_SHEETS_CREDS_PATH

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.oauth2 import service_account
    except ImportError:
        raise ImportError(
            "Install: pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2"
        )

    token_path   = Path(USER_DATA_DIR) / "google_token.json"
    sa_path      = Path(GOOGLE_SHEETS_CREDS_PATH) if GOOGLE_SHEETS_CREDS_PATH else Path(USER_DATA_DIR) / "google_service_account.json"
    oauth_secret = Path(USER_DATA_DIR) / "google_oauth_secret.json"

    # 1. Cached OAuth2 token
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
            return creds

    # 2. Service account
    if sa_path.exists():
        return service_account.Credentials.from_service_account_file(
            str(sa_path), scopes=_SCOPES
        )

    # 3. OAuth2 interactive flow
    if not oauth_secret.exists():
        raise FileNotFoundError(
            f"No Google credentials found.\n"
            f"Download OAuth2 client JSON from Google Cloud Console and save to:\n"
            f"  {oauth_secret}\n"
            f"Or place a service account JSON at:\n"
            f"  {sa_path}"
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(oauth_secret), _SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    return creds


def _build(service: str, version: str):
    """Build a Google API service client."""
    from googleapiclient.discovery import build as _build_client
    creds = _get_credentials()
    return _build_client(service, version, credentials=creds)


# ─── Google Drive ─────────────────────────────────────────────────────────────

def list_drive_files(
    query: str = "",
    folder_id: str = "",
    max_results: int = 20,
) -> dict:
    """
    List files in Google Drive.
    query: freetext search (e.g. 'name contains \"report\"')
    folder_id: limit to a specific folder
    """
    try:
        svc = _build("drive", "v3")
        q_parts = []
        if query:
            q_parts.append(f"fullText contains '{query}'")
        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")
        q_parts.append("trashed = false")
        q = " and ".join(q_parts)

        results = svc.files().list(
            q=q,
            pageSize=max_results,
            fields="files(id, name, mimeType, size, modifiedTime, webViewLink)",
        ).execute()

        files = results.get("files", [])
        if not files:
            return {"success": True, "files": [], "text": "📂 No files found."}

        lines = [f"📂 *Drive files ({len(files)})*\n"]
        for f in files:
            size  = int(f.get("size", 0))
            size_str = f"{size // 1024}KB" if size > 1024 else f"{size}B" if size else ""
            mod   = f.get("modifiedTime", "")[:10]
            lines.append(
                f"• [{f['name']}]({f.get('webViewLink', '#')}) — {f.get('mimeType','').split('.')[-1]} {size_str} ({mod})"
            )
        return {"success": True, "files": files, "text": "\n".join(lines)}

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"list_drive_files: {e}")
        return {"success": False, "error": str(e)}


def upload_to_drive(
    file_path: str,
    folder_id: str = "",
    mime_type: str = "",
) -> dict:
    """Upload a local file to Google Drive."""
    try:
        from googleapiclient.http import MediaFileUpload

        svc  = _build("drive", "v3")
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        metadata = {"name": path.name}
        if folder_id:
            metadata["parents"] = [folder_id]

        media = MediaFileUpload(str(path), mimetype=mime_type or "application/octet-stream")
        result = svc.files().create(
            body=metadata, media_body=media, fields="id, name, webViewLink"
        ).execute()

        return {
            "success": True,
            "file_id": result["id"],
            "text": f"✅ Uploaded *{result['name']}* to Drive.\n🔗 {result.get('webViewLink','')}",
        }

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"upload_to_drive: {e}")
        return {"success": False, "error": str(e)}


def download_from_drive(file_id: str, dest_path: str = "") -> dict:
    """Download a file from Google Drive by its file ID."""
    try:
        from googleapiclient.http import MediaIoBaseDownload
        import io

        svc  = _build("drive", "v3")
        meta = svc.files().get(fileId=file_id, fields="name, mimeType").execute()
        name = meta.get("name", file_id)

        from config import TEMP_DIR
        out  = Path(dest_path) if dest_path else Path(TEMP_DIR) / name

        request = svc.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        dl  = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = dl.next_chunk()

        out.write_bytes(buf.getvalue())
        return {"success": True, "path": str(out), "text": f"✅ Downloaded *{name}* → `{out}`"}

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"download_from_drive: {e}")
        return {"success": False, "error": str(e)}


def search_drive(query: str, max_results: int = 10) -> dict:
    """Search Google Drive files by name or content."""
    return list_drive_files(query=query, max_results=max_results)


def delete_drive_file(file_id: str) -> dict:
    """Move a Drive file to trash."""
    try:
        svc = _build("drive", "v3")
        meta = svc.files().get(fileId=file_id, fields="name").execute()
        svc.files().delete(fileId=file_id).execute()
        return {"success": True, "text": f"🗑️ *{meta.get('name', file_id)}* moved to trash."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Google Calendar ──────────────────────────────────────────────────────────

def list_calendar_events(
    calendar_id: str = "primary",
    days_ahead: int = 7,
    max_results: int = 15,
) -> dict:
    """List upcoming calendar events."""
    try:
        from googleapiclient.errors import HttpError

        svc = _build("calendar", "v3")
        now = datetime.now(timezone.utc).isoformat()

        events_result = svc.events().list(
            calendarId=calendar_id,
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = events_result.get("items", [])
        if not events:
            return {"success": True, "events": [], "text": "📅 No upcoming events."}

        lines = [f"📅 *Upcoming events ({len(events)})*\n"]
        for e in events:
            start = e["start"].get("dateTime", e["start"].get("date", ""))[:16].replace("T", " ")
            lines.append(f"• *{e.get('summary', 'No title')}* — {start}")
            loc = e.get("location", "")
            if loc:
                lines.append(f"  📍 {loc}")

        return {"success": True, "events": events, "text": "\n".join(lines)}

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"list_calendar_events: {e}")
        return {"success": False, "error": str(e)}


def create_calendar_event(
    title: str,
    start: str,
    end: str = "",
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
    attendees: list = None,
) -> dict:
    """
    Create a Google Calendar event.
    start/end: ISO8601 datetime string e.g. '2025-06-01T14:00:00+06:00'
               or date string '2025-06-01' for all-day events.
    """
    try:
        svc = _build("calendar", "v3")

        # Detect all-day vs timed
        if "T" in start:
            start_obj = {"dateTime": start, "timeZone": "UTC"}
            end_obj   = {"dateTime": end or start, "timeZone": "UTC"}
        else:
            start_obj = {"date": start}
            end_obj   = {"date": end or start}

        body: dict[str, Any] = {
            "summary": title,
            "start": start_obj,
            "end": end_obj,
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]

        event = svc.events().insert(calendarId=calendar_id, body=body).execute()
        return {
            "success": True,
            "event_id": event["id"],
            "link": event.get("htmlLink", ""),
            "text": f"✅ Event *{title}* created for {start}.\n🔗 {event.get('htmlLink','')}",
        }

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"create_calendar_event: {e}")
        return {"success": False, "error": str(e)}


def delete_calendar_event(event_id: str, calendar_id: str = "primary") -> dict:
    """Delete a calendar event by ID."""
    try:
        svc = _build("calendar", "v3")
        svc.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return {"success": True, "text": f"🗑️ Event deleted."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_calendar_event(event_id: str, calendar_id: str = "primary") -> dict:
    """Get details of a specific calendar event."""
    try:
        svc   = _build("calendar", "v3")
        event = svc.events().get(calendarId=calendar_id, eventId=event_id).execute()
        start = event["start"].get("dateTime", event["start"].get("date", ""))[:16]
        return {
            "success": True,
            "event": event,
            "text": (
                f"📅 *{event.get('summary','No title')}*\n"
                f"Start: {start}\n"
                f"Location: {event.get('location','—')}\n"
                f"Description: {event.get('description','—')}"
            ),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Google Docs ──────────────────────────────────────────────────────────────

def read_google_doc(doc_id_or_url: str) -> dict:
    """Read text content from a Google Doc."""
    try:
        svc = _build("docs", "v1")

        doc_id = doc_id_or_url
        if "docs.google.com" in doc_id_or_url:
            # Extract ID from URL like https://docs.google.com/document/d/DOC_ID/edit
            parts = doc_id_or_url.split("/d/")
            if len(parts) > 1:
                doc_id = parts[1].split("/")[0]

        doc = svc.documents().get(documentId=doc_id).execute()
        title = doc.get("title", "Untitled")

        # Extract plain text from content
        content = doc.get("body", {}).get("content", [])
        lines = []
        for elem in content:
            para = elem.get("paragraph")
            if not para:
                continue
            for pe in para.get("elements", []):
                tr = pe.get("textRun", {})
                if tr.get("content"):
                    lines.append(tr["content"])

        text = "".join(lines).strip()
        return {
            "success": True,
            "title": title,
            "doc_id": doc_id,
            "text_content": text,
            "text": f"📄 *{title}*\n\n{text[:3000]}{'…' if len(text) > 3000 else ''}",
        }

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"read_google_doc: {e}")
        return {"success": False, "error": str(e)}


def append_to_google_doc(doc_id_or_url: str, text: str) -> dict:
    """Append text to an existing Google Doc."""
    try:
        svc = _build("docs", "v1")

        doc_id = doc_id_or_url
        if "docs.google.com" in doc_id_or_url:
            parts = doc_id_or_url.split("/d/")
            if len(parts) > 1:
                doc_id = parts[1].split("/")[0]

        requests = [
            {
                "insertText": {
                    "location": {"index": 1},
                    "text": text + "\n",
                }
            }
        ]
        svc.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
        doc = svc.documents().get(documentId=doc_id).execute()
        return {
            "success": True,
            "text": f"✅ Text appended to *{doc.get('title','Doc')}*.",
        }

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"append_to_google_doc: {e}")
        return {"success": False, "error": str(e)}


def create_google_doc(title: str, content: str = "") -> dict:
    """Create a new Google Doc."""
    try:
        svc = _build("docs", "v1")
        doc = svc.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]

        if content:
            svc.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
            ).execute()

        return {
            "success": True,
            "doc_id": doc_id,
            "text": f"✅ Google Doc *{title}* created.\n🔗 https://docs.google.com/document/d/{doc_id}/edit",
        }

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"create_google_doc: {e}")
        return {"success": False, "error": str(e)}


# ─── Gmail API ────────────────────────────────────────────────────────────────

def get_gmail_messages(
    label: str = "INBOX",
    query: str = "",
    max_results: int = 10,
) -> dict:
    """
    Fetch Gmail messages via API.
    label: 'INBOX', 'SENT', 'UNREAD', etc.
    query: Gmail search query e.g. 'from:boss@company.com is:unread'
    """
    try:
        import base64
        svc = _build("gmail", "v1")

        q_parts = []
        if query:
            q_parts.append(query)
        if label and label not in ("ALL",):
            q_parts.append(f"label:{label.lower()}")
        q = " ".join(q_parts) if q_parts else ""

        result = svc.users().messages().list(
            userId="me", q=q, maxResults=max_results
        ).execute()

        msgs = result.get("messages", [])
        if not msgs:
            return {"success": True, "emails": [], "text": f"📭 No messages found ({label})."}

        emails = []
        lines  = [f"📬 *{label} — {len(msgs)} message(s)*\n"]
        for m in msgs:
            full = svc.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
            snippet = full.get("snippet", "")[:100]
            entry   = {
                "id": m["id"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": snippet,
            }
            emails.append(entry)
            lines.append(
                f"• *{entry['subject'] or '(no subject)'}*\n"
                f"  From: {entry['from']} | {entry['date'][:16]}\n"
                f"  {snippet}"
            )

        return {"success": True, "emails": emails, "text": "\n".join(lines)}

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"get_gmail_messages: {e}")
        return {"success": False, "error": str(e)}


def send_gmail(to: str, subject: str, body: str) -> dict:
    """Send an email via Gmail API."""
    try:
        import base64
        from email.mime.text import MIMEText

        svc = _build("gmail", "v1")
        msg = MIMEText(body)
        msg["to"]      = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        sent = svc.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        return {
            "success": True,
            "message_id": sent["id"],
            "text": f"✅ Email sent to *{to}*: _{subject}_",
        }

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"send_gmail: {e}")
        return {"success": False, "error": str(e)}


def reply_gmail(message_id: str, body: str) -> dict:
    """Reply to a Gmail message by message ID."""
    try:
        import base64
        from email.mime.text import MIMEText

        svc  = _build("gmail", "v1")
        orig = svc.users().messages().get(
            userId="me", id=message_id, format="metadata",
            metadataHeaders=["From", "Subject", "Message-ID", "References"],
        ).execute()

        headers = {h["name"]: h["value"] for h in orig.get("payload", {}).get("headers", [])}
        to      = headers.get("From", "")
        subject = "Re: " + headers.get("Subject", "")
        refs    = headers.get("Message-ID", "")

        msg = MIMEText(body)
        msg["to"]         = to
        msg["subject"]    = subject
        msg["references"] = refs
        msg["in-reply-to"] = refs

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        thread_id = orig.get("threadId", "")
        sent = svc.users().messages().send(
            userId="me", body={"raw": raw, "threadId": thread_id}
        ).execute()

        return {"success": True, "text": f"✅ Reply sent to *{to}*."}

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"reply_gmail: {e}")
        return {"success": False, "error": str(e)}


def get_gmail_full_body(message_id: str) -> dict:
    """Get the full body of a Gmail message."""
    try:
        import base64

        svc  = _build("gmail", "v1")
        full = svc.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

        payload  = full.get("payload", {})
        headers  = {h["name"]: h["value"] for h in payload.get("headers", [])}
        body_txt = ""

        def _extract(part):
            nonlocal body_txt
            mime = part.get("mimeType", "")
            if mime == "text/plain" and part.get("body", {}).get("data"):
                body_txt = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
            for sub in part.get("parts", []):
                _extract(sub)

        _extract(payload)

        return {
            "success": True,
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "body": body_txt,
            "text": (
                f"📧 *{headers.get('Subject','(no subject)')}*\n"
                f"From: {headers.get('From','')}\n"
                f"Date: {headers.get('Date','')}\n\n"
                f"{body_txt[:2000]}"
            ),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Google Contacts ──────────────────────────────────────────────────────────

def list_google_contacts(query: str = "", max_results: int = 20) -> dict:
    """Search or list Google Contacts."""
    try:
        svc = _build("people", "v1")
        if query:
            result = svc.people().searchContacts(
                query=query,
                readMask="names,emailAddresses,phoneNumbers",
                pageSize=max_results,
            ).execute()
            contacts = result.get("results", [])
            people   = [r.get("person", {}) for r in contacts]
        else:
            result = svc.people().connections().list(
                resourceName="people/me",
                pageSize=max_results,
                personFields="names,emailAddresses,phoneNumbers",
            ).execute()
            people = result.get("connections", [])

        if not people:
            return {"success": True, "contacts": [], "text": "📇 No contacts found."}

        lines = [f"📇 *Contacts ({len(people)})*\n"]
        for p in people:
            name   = (p.get("names", [{}])[0].get("displayName", "Unknown"))
            emails = [e["value"] for e in p.get("emailAddresses", [])]
            phones = [n["value"] for n in p.get("phoneNumbers", [])]
            lines.append(
                f"• *{name}*" +
                (f" — {', '.join(emails)}" if emails else "") +
                (f" | {', '.join(phones)}" if phones else "")
            )

        return {"success": True, "contacts": people, "text": "\n".join(lines)}

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"list_google_contacts: {e}")
        return {"success": False, "error": str(e)}
