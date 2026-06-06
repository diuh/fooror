"""One-time helper to obtain a Google OAuth refresh token for the bot.

This script is NOT imported by the bot — run it once on your own machine, then
copy the printed values into your Railway environment variables.

Setup before running:
  1. Go to https://console.cloud.google.com/ → create a project.
  2. APIs & Services → Library → enable "Google Calendar API".
  3. APIs & Services → OAuth consent screen → External; add your own Gmail as a
     test user (so the unverified app can be used).
  4. APIs & Services → Credentials → Create Credentials → OAuth client ID →
     Application type: "Desktop app". Download the client secret JSON.
  5. Save that file next to this script as `client_secret.json`
     (or set GOOGLE_OAUTH_CLIENT_FILE to its path).

Then:
  pip install google-auth-oauthlib
  python gcal_auth.py

A browser window opens; grant access. The script prints GOOGLE_CLIENT_ID,
GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN — paste them into Railway.
"""

import os

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main() -> None:
    client_file = os.environ.get("GOOGLE_OAUTH_CLIENT_FILE", "client_secret.json")
    if not os.path.exists(client_file):
        raise SystemExit(
            f"Client secret file not found: {client_file}\n"
            "Download it from Google Cloud Console (Desktop app OAuth client) "
            "and save it as client_secret.json next to this script."
        )

    flow = InstalledAppFlow.from_client_secrets_file(client_file, SCOPES)
    # access_type=offline + prompt=consent guarantees a refresh_token is returned.
    creds = flow.run_local_server(
        port=0, access_type="offline", prompt="consent"
    )

    print("\n✅ Authorized! Copy these into your Railway environment variables:\n")
    print(f"GOOGLE_CLIENT_ID={creds.client_id}")
    print(f"GOOGLE_CLIENT_SECRET={creds.client_secret}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print("\n(GOOGLE_CALENDAR_ID defaults to 'primary' — set it only to use another calendar.)")


if __name__ == "__main__":
    main()
