#!/usr/bin/env python3
"""
One-time helper to get a YouTube OAuth refresh token.
Run this locally on your computer (NOT in GitHub Actions).

Steps:
1. Go to https://console.cloud.google.com/apis/credentials
2. Create an OAuth 2.0 Client ID (Desktop app type)
3. Download the client secret JSON or copy the Client ID and Client Secret
4. Run this script: python get_youtube_token.py
5. It will open a browser for you to authorize
6. Copy the refresh token and add it as a GitHub Secret
"""

import json
import http.server
import urllib.parse
import webbrowser
import requests

# ── Fill these in from your Google Cloud Console ──
CLIENT_ID = input("Enter your YouTube OAuth Client ID: ").strip()
CLIENT_SECRET = input("Enter your YouTube OAuth Client Secret: ").strip()

REDIRECT_URI = "http://localhost:8090"
SCOPES = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube"

# Step 1: Open browser for authorization
auth_url = (
    "https://accounts.google.com/o/oauth2/v2/auth?"
    f"client_id={CLIENT_ID}&"
    f"redirect_uri={urllib.parse.quote(REDIRECT_URI)}&"
    "response_type=code&"
    f"scope={urllib.parse.quote(SCOPES)}&"
    "access_type=offline&"
    "prompt=consent"
)

print(f"\nOpening browser for authorization...")
print(f"If it doesn't open, visit: {auth_url}\n")
webbrowser.open(auth_url)

# Step 2: Listen for the callback
auth_code = None

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        auth_code = params.get("code", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Authorization successful!</h1><p>You can close this tab.</p>")

    def log_message(self, *args):
        pass  # Suppress server logs

server = http.server.HTTPServer(("localhost", 8090), Handler)
server.handle_request()

if not auth_code:
    print("ERROR: No authorization code received")
    exit(1)

# Step 3: Exchange code for tokens
print("Exchanging authorization code for tokens...")
resp = requests.post(
    "https://oauth2.googleapis.com/token",
    data={
        "code": auth_code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    },
)

if resp.status_code != 200:
    print(f"ERROR: {resp.text}")
    exit(1)

tokens = resp.json()
refresh_token = tokens.get("refresh_token", "")

print("\n" + "=" * 60)
print("SUCCESS! Here are your tokens:")
print("=" * 60)
print(f"\nRefresh Token (add as YOUTUBE_REFRESH_TOKEN secret):\n{refresh_token}")
print(f"\nClient ID (add as YOUTUBE_CLIENT_ID secret):\n{CLIENT_ID}")
print(f"\nClient Secret (add as YOUTUBE_CLIENT_SECRET secret):\n{CLIENT_SECRET}")
print("\n" + "=" * 60)
print("Add these as GitHub Secrets in your repo:")
print("  Settings > Secrets and variables > Actions > New repository secret")
print("=" * 60)
