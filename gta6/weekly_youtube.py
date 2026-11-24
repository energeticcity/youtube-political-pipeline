"""Publish or verify the assigned long-form episode on the GTA VI channel."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

import requests

from gta6_cloud import youtube_api_client
from gta6_crosspost import DESTINATIONS

API = "https://www.googleapis.com/youtube/v3"
CHANNEL = DESTINATIONS["youtube"]["user_id"]
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
RECEIPT = Path("gta6-weekly-youtube.json")


def read_youtube(resource, headers, **params):
    response = requests.get(f"{API}/{resource}", headers=headers, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def videos(headers, ids):
    return read_youtube("videos", headers, part="snippet,status,contentDetails", id=",".join(ids))["items"]


def recent_episode(headers, tag, week):
    channel = read_youtube("channels", headers, part="contentDetails", mine="true")["items"][0]
    uploads = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    start = datetime.fromisoformat(week).replace(tzinfo=timezone.utc)
    params = {"part": "snippet,contentDetails", "playlistId": uploads, "maxResults": 50}
    matches = []
    while True:
        page = read_youtube("playlistItems", headers, **params)
        recent = [item["contentDetails"]["videoId"] for item in page["items"]
                  if datetime.fromisoformat(item["snippet"]["publishedAt"].replace("Z", "+00:00")) >= start]
        if recent:
            matches.extend(item for item in videos(headers, recent) if tag in item["snippet"].get("tags", []))
        if len(recent) < len(page["items"]) or not page.get("nextPageToken"):
            break
        params["pageToken"] = page["nextPageToken"]
    if len(matches) > 1:
        raise RuntimeError("Multiple YouTube uploads already match this weekly episode")
    return matches[0]["id"] if matches else None


def upload(media, title, description, tag, token, values):
    from oauth2client.client import GoogleCredentials

    with tempfile.TemporaryDirectory(prefix="gta6-weekly-youtube-") as directory:
        credentials = Path(directory) / "credentials.json"
        client = Path(directory) / "client.json"
        credentials.write_text(GoogleCredentials(
            token, values["CLIENT_ID"], values["CLIENT_SECRET"], values["REFRESH_TOKEN"], None,
            "https://oauth2.googleapis.com/token", "gta6-weekly-youtube"
        ).to_json())
        client.write_text(json.dumps({"installed": {
            "client_id": values["CLIENT_ID"], "client_secret": values["CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": ["http://localhost"],
        }}))
        credentials.chmod(0o600)
        client.chmod(0o600)
        result = subprocess.run([
            "youtube-upload", "--client-secrets", str(client), "--credentials-file", str(credentials),
            "--privacy=public", "--category=Gaming", f"--title={title}", f"--description={description}",
            f"--tags={tag}", str(media.resolve()),
        ], capture_output=True, text=True, timeout=420, stdin=subprocess.DEVNULL)
    ids = [line for line in result.stdout.splitlines() if VIDEO_ID.fullmatch(line)]
    if result.returncode or len(ids) != 1:
        raise RuntimeError("YouTube upload receipt unavailable. Check the tagged episode before resubmitting.")
    return ids[0]


def set_thumbnail(headers, video_id, data):
    for attempt in range(4):
        response = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
            params={"videoId": video_id, "uploadType": "media"}, data=data,
            headers={**headers, "Content-Type": "image/jpeg"}, timeout=45,
        )
        if response.ok and response.json().get("items"):
            return
        if response.status_code not in (404, 429, 500, 502, 503, 504) or attempt == 3:
            raise RuntimeError(f"Thumbnail update failed (HTTP {response.status_code}); retain video {video_id}")
        time.sleep(6 * (attempt + 1))


def verify_public(headers, video_id, title, description):
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("Invalid weekly YouTube video ID")
    for _ in range(20):
        entries = videos(headers, [video_id])
        if entries:
            item = entries[0]
            snippet, status = item["snippet"], item["status"]
            if (snippet["channelId"] != CHANNEL or snippet["title"] != title
                    or not snippet["description"].startswith(description)):
                raise RuntimeError("YouTube returned unexpected channel, title, or description")
            if status["privacyStatus"] != "public":
                raise RuntimeError(f"Weekly video {video_id} is not public")
            if status["uploadStatus"] == "processed" and snippet.get("thumbnails"):
                return item["contentDetails"]["duration"]
            if status["uploadStatus"] in ("failed", "rejected", "deleted"):
                raise RuntimeError(f"YouTube did not process weekly video {video_id}")
        time.sleep(9)
    raise RuntimeError(f"YouTube is still processing {video_id}; preserve the original video ID")


def publish(spec, folder):
    token, values = youtube_api_client()
    headers = {"Authorization": f"Bearer {token}"}
    title, description = spec["title"], spec["description"]
    video_id = spec.get("published_youtube_id")
    if video_id:
        duration = verify_public(headers, video_id, title, description)
        return {"status": "already_public", "video_id": video_id, "duration": duration}

    manifest = json.loads((folder / "manifest.json").read_text())
    episode = manifest["episode"]
    media = folder / "episode.mp4"
    cover = (folder / "episode.jpg").read_bytes()
    if (manifest["id"] != spec["id"] or manifest["title"] != title or manifest["description"] != description
            or manifest.get("background", {}).get("audio") != "muted"
            or episode["thumbnail"] != "episode.jpg" or not 180 <= episode["seconds"] <= 900
            or not cover.startswith(b"\xff\xd8") or len(cover) > 2_000_000):
        raise ValueError("Weekly render or thumbnail does not match the assigned episode")
    with media.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != episode["sha256"]:
            raise ValueError("Weekly episode checksum mismatch")

    chapters = "\n".join(f"{chapter['timestamp']} {chapter['title']}" for chapter in manifest["chapters"])
    description = f"{description}\n\n{chapters}\n\n{(folder / 'credits.txt').read_text().strip()}"
    week = spec["preview_week"]
    tag = f"gtaviclipfix-weekly-{week}-{spec['id']}"
    video_id = recent_episode(headers, tag, week)
    if not video_id:
        if os.environ.get("GITHUB_RUN_ATTEMPT", "1") != "1":
            raise RuntimeError("No prior weekly upload found on this retry; no new upload attempted")
        video_id = upload(media, title, description, tag, token, values)
    RECEIPT.write_text(json.dumps({"status": "uploaded", "video_id": video_id}) + "\n")
    set_thumbnail(headers, video_id, cover)
    duration = verify_public(headers, video_id, title, description)
    return {"status": "public", "video_id": video_id, "duration": duration, "thumbnail": "applied"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("render", type=Path)
    args = parser.parse_args()
    result = publish(json.loads(args.episode.read_text()), args.render)
    result["url"] = f"https://www.youtube.com/watch?v={result['video_id']}"
    RECEIPT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
