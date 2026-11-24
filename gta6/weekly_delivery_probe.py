"""Submit one private YouTube proof for the reviewed weekly episode."""
import hashlib
import json
from pathlib import Path
import re
import sys
import time

import requests

from gta6_crosspost import DESTINATIONS, api, validate_account

DESTINATION = DESTINATIONS["youtube"]
EXTERNAL_ID = "gtaviclipfix-weekly-recording-audio-private-proof"
TITLE = "Private weekly upload test — GTA VI Creator Audio"
REPORT = Path("weekly-delivery-proof.json")


def save(**details):
    REPORT.write_text(json.dumps({
        "platform": "youtube", "channel_id": DESTINATION["user_id"],
        "requested_visibility": "private", **details,
    }, indent=2) + "\n")


def rows(response):
    return response if isinstance(response, list) else response["data"]


def private_watch_page(video_id):
    page = requests.get(f"https://www.youtube.com/watch?v={video_id}", timeout=20)
    if not page.ok:
        return False
    match = re.search(r"ytInitialPlayerResponse\s*=\s*", page.text)
    if not match:
        return False
    status = json.JSONDecoder().raw_decode(page.text[match.end():])[0].get("playabilityStatus", {})
    return status.get("status") == "LOGIN_REQUIRED" and "private" in status.get("reason", "").lower()


def main(folder):
    manifest = json.loads((folder / "manifest.json").read_text())
    asset = manifest["episode"]
    if (manifest["id"] != "recording-audio" or manifest["visuals"] != "Original diagrams"
            or manifest.get("background") or not 180 <= asset["seconds"] <= 900
            or asset["dimensions"] != [1280, 720] or asset["filename"] != "episode.mp4"):
        raise ValueError("Unexpected weekly proof media")
    video = folder / asset["filename"]
    with video.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != asset["sha256"]:
            raise ValueError("Weekly proof media changed")

    account = validate_account("youtube", api("GET", "/social-accounts/" + DESTINATION["id"]))
    if account["status"] != "connected":
        raise ValueError("YouTube connection requires repair")
    matches = [item for item in rows(api("GET", "/social-posts", params={"external_id": EXTERNAL_ID, "limit": 10}))
               if item.get("external_id") == EXTERNAL_ID]
    if len(matches) > 1:
        raise ValueError("Multiple test submissions exist; stop")
    if matches:
        prior = matches[0]
        if [account["id"] for account in prior.get("social_accounts", [])] != [DESTINATION["id"]]:
            raise ValueError("Existing test submission does not match intended account")
        configuration = (prior.get("platform_configurations") or {}).get("youtube") or {}
        if configuration.get("privacy_status") != "private":
            raise ValueError("Existing test submission does not match intended visibility")
        post_id = prior["id"]
    else:
        upload = api("POST", "/media/create-upload-url")
        if not all(upload.get(k, "").startswith("https://") for k in ("upload_url", "media_url")):
            raise ValueError("Invalid upload destination")
        with video.open("rb") as stream:
            response = requests.put(upload["upload_url"], data=stream,
                                    headers={"Content-Type": "video/mp4"}, timeout=120)
        if not response.ok:
            raise RuntimeError(f"Media transfer HTTP {response.status_code}")
        post_id = api("POST", "/social-posts", json={
            "external_id": EXTERNAL_ID, "caption": TITLE, "social_accounts": [DESTINATION["id"]],
            "media": [{"url": upload["media_url"]}],
            "platform_configurations": {"youtube": {
                "title": TITLE, "description": manifest["description"] + "\n\n" +
                (folder / "credits.txt").read_text(),
                "privacy_status": "private", "made_for_kids": False}},
        })["id"]
    save(stage="submitted", provider_post=post_id, duration=asset["seconds"])
    video_id = None
    for _ in range(20):
        results = rows(api("GET", "/social-post-results", params={"post_id": post_id, "limit": 10}))
        matching = [r for r in results if r.get("post_id") == post_id
                    and r.get("social_account_id") == DESTINATION["id"]]
        if matching and matching[-1].get("success") is False:
            from archive_recovery_check import quota_evidence
            save(stage="rejected", provider_post=post_id, result_id=matching[-1].get("id"),
                 quota=quota_evidence(matching[-1].get("error")))
            raise RuntimeError("YouTube upload rejected; existing receipt retained")
        if matching and matching[-1].get("success") is True:
            platform_data = matching[-1].get("platform_data") or {}
            url = platform_data.get("url") or ""
            match = re.fullmatch(r"https://(?:www\.)?youtube\.com/watch\?v=([\w-]{11})", url)
            if match:
                video_id = match[1]
            elif re.fullmatch(r"[\w-]{11}", str(platform_data.get("id", ""))):
                video_id = platform_data["id"]
            save(stage="platform_receipt", provider_post=post_id, video_id=video_id,
                 duration=asset["seconds"], reported_visibility=platform_data.get("privacy_status"))
            if video_id and private_watch_page(video_id):
                save(stage="verified_private", provider_post=post_id, video_id=video_id,
                     duration=asset["seconds"], anonymous_watch_page="reported_private")
                return
        time.sleep(10)
    raise RuntimeError("Awaiting YouTube privacy confirmation; do not resubmit")


if __name__ == "__main__":
    try:
        main(Path(sys.argv[1]))
    except (KeyError, requests.RequestException, ValueError, RuntimeError):
        if not REPORT.exists():
            save(stage="preflight_or_submission_failed")
        raise SystemExit("Weekly proof stopped. See the diagnostic receipt; do not retry blindly.") from None
