"""Thin async wrapper around the Google Calendar API.

The google-api-python-client is synchronous, so every network call is run in a
worker thread via asyncio.to_thread to avoid blocking the bot's event loop.
Credentials are built from the OAuth refresh token in config; the library
refreshes the short-lived access token automatically.
"""

import asyncio
import uuid

from config import config

TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/calendar"]

_service = None


def _get_service():
    global _service
    if _service is None:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=config.google_refresh_token,
            client_id=config.google_client_id,
            client_secret=config.google_client_secret,
            token_uri=TOKEN_URI,
            scopes=SCOPES,
        )
        _service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return _service


def _create_sync(
    title: str,
    start_iso: str,
    end_iso: str,
    tz: str,
    is_online: bool,
    location: str,
    attendees: list[str],
) -> dict:
    body: dict = {
        "summary": title,
        "start": {"dateTime": start_iso, "timeZone": tz},
        "end": {"dateTime": end_iso, "timeZone": tz},
    }
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [{"email": e} for e in attendees]

    params: dict = {
        "calendarId": config.google_calendar_id,
        "body": body,
        "sendUpdates": "all",  # email invites to attendees
    }
    if is_online:
        body["conferenceData"] = {
            "createRequest": {
                "requestId": uuid.uuid4().hex,
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
        params["conferenceDataVersion"] = 1

    ev = _get_service().events().insert(**params).execute()

    meet = ""
    for ep in ev.get("conferenceData", {}).get("entryPoints", []):
        if ep.get("entryPointType") == "video":
            meet = ep.get("uri", "")
            break

    return {
        "event_id": ev["id"],
        "html_link": ev.get("htmlLink", ""),
        "meet_link": meet,
    }


async def create_event(
    title: str,
    start_iso: str,
    end_iso: str,
    tz: str,
    is_online: bool,
    location: str = "",
    attendees: list[str] | None = None,
) -> dict:
    """Create a calendar event. start_iso/end_iso are local ISO datetimes
    (without offset) interpreted in the given tz. Returns event_id, html_link
    and meet_link (empty for offline). Raises on API failure."""
    return await asyncio.to_thread(
        _create_sync, title, start_iso, end_iso, tz, is_online, location, attendees or []
    )


def _delete_sync(event_id: str) -> None:
    _get_service().events().delete(
        calendarId=config.google_calendar_id,
        eventId=event_id,
        sendUpdates="all",
    ).execute()


async def delete_event(event_id: str) -> None:
    """Delete a calendar event and notify attendees. Raises on API failure."""
    await asyncio.to_thread(_delete_sync, event_id)
