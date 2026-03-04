#!/usr/bin/env python3
"""
One-time helper to generate a Google Ads OAuth2 refresh token.

Usage:
    1. Download client_secrets.json from Google Cloud Console
       (APIs & Services → Credentials → OAuth 2.0 Client IDs → Desktop app → Download)
    2. Place client_secrets.json in this directory (backend/)
    3. Run:  python generate_refresh_token.py
    4. Follow the browser prompt and paste the authorization code
    5. Copy the printed refresh token into google-ads.yaml
"""
import json
import os
import sys
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/adwords"]
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"  # Desktop app out-of-band

def main():
    secrets_file = Path(__file__).parent / "client_secrets.json"
    if not secrets_file.exists():
        print("ERROR: client_secrets.json not found.")
        print("Download it from: Google Cloud Console → APIs & Services → Credentials")
        sys.exit(1)

    with open(secrets_file) as f:
        secrets = json.load(f)

    installed = secrets.get("installed") or secrets.get("web")
    if not installed:
        print("ERROR: Unexpected client_secrets.json format.")
        sys.exit(1)

    client_id = installed["client_id"]
    client_secret = installed["client_secret"]

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Install: pip install google-auth-oauthlib")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), scopes=SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n" + "=" * 60)
    print("SUCCESS! Add the following to your google-ads.yaml:")
    print("=" * 60)
    print(f"developer_token: YOUR_DEVELOPER_TOKEN")
    print(f"client_id: {client_id}")
    print(f"client_secret: {client_secret}")
    print(f"refresh_token: {creds.refresh_token}")
    print(f"login_customer_id: YOUR_MCC_CUSTOMER_ID  # optional")
    print("=" * 60)


if __name__ == "__main__":
    main()
