#!/usr/bin/env python3
"""
Run this script ONCE on your own computer to generate an Instagram session file.
The session file can then be uploaded as a GitHub secret so the pipeline
doesn't need to log in from scratch (which gets blocked by Instagram).

Usage:
    pip install instagrapi
    python export_ig_session.py

It will prompt you for your Instagram username and password,
log in, and save the session as a base64 string you can copy
into a GitHub secret called IG_SESSION.
"""
import base64
import getpass
import json
import sys

def main():
    try:
        from instagrapi import Client
    except ImportError:
        print("ERROR: instagrapi not installed. Run: pip install instagrapi")
        sys.exit(1)

    print("=" * 50)
    print("Instagram Session Exporter")
    print("=" * 50)
    print()

    username = input("Instagram username: ").strip()
    password = getpass.getpass("Instagram password: ")

    print()
    print("Logging in...")

    cl = Client()
    cl.set_user_agent(
        "Instagram 269.0.0.18.75 Android (33/13; 420dpi; 1080x2400; "
        "samsung; SM-G991B; o1s; exynos2100)"
    )

    try:
        cl.login(username, password)
    except Exception as e:
        print(f"Login failed: {e}")
        print()
        print("If Instagram is asking for a verification code,")
        print("check your email/SMS and try again.")
        sys.exit(1)

    print("Login successful!")
    print()

    # Save settings to a temp file, read it, base64 encode
    import tempfile, os
    tmp = tempfile.mktemp(suffix=".json")
    cl.dump_settings(tmp)

    with open(tmp, "r") as f:
        session_json = f.read()
    os.remove(tmp)

    session_b64 = base64.b64encode(session_json.encode()).decode()

    print("=" * 50)
    print("SUCCESS! Copy the text below and save it as a")
    print("GitHub secret named: IG_SESSION")
    print("=" * 50)
    print()
    print(session_b64)
    print()
    print("=" * 50)
    print(f"(Length: {len(session_b64)} characters)")
    print()
    print("Steps:")
    print("1. Go to your GitHub repo -> Settings -> Secrets -> Actions")
    print("2. Click 'New repository secret'")
    print("3. Name: IG_SESSION")
    print("4. Value: paste the text above")
    print("5. Click 'Add secret'")

if __name__ == "__main__":
    main()
