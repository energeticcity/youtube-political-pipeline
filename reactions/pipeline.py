"""Produce trending reactions and deliver them only to configured reaction accounts."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import re
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo

from gta6_cloud import (
    instagram_cli_check, instagram_cli_upload, issues, model_name, save_issue,
    tiktok_cli_upload, youtube_api_cli_upload, youtube_api_client,
)
from gta6_crosspost import gh
from gta6.produce import Rejected
from reactions.discover import discover
from reactions.render import compose

ROOT = Path("reaction-output")
PREFIX = "[viral-reaction] "
LOCAL = ZoneInfo("America/Dawson_Creek")


def history():
    return [(row["number"], json.loads(row["body"])) for row in issues() if row["title"].startswith(PREFIX)]


def prepare(batch_size, inputs, excluded, recent):
    from kokoro_onnx import Kokoro

    model = model_name(commentary=True)
    voice = Kokoro(str(inputs / "kokoro.onnx"), str(inputs / "voices.bin"))
    results = []
    for candidate in discover(excluded)[:12]:
        if any(result["source"] == candidate["source"] for _, result in results):
            continue
        slot = ROOT / f"clip-{len(results) + 1}"
        try:
            media, result = compose(candidate, model, voice, slot, recent)
        except Rejected as error:
            print(f"Skipped {candidate['title'][:70]}: {error}", flush=True)
            shutil.rmtree(slot, ignore_errors=True)
            continue
        # Keep the verified cut and public provenance rather than redistributing source media.
        for name in ("source.webm", "source.mp4", "source-review.mp4", "reaction.gif", "reaction-review.mp4",
                     "speech.wav", "caption-timeline.txt"):
            (slot / name).unlink(missing_ok=True)
        for image in slot.glob("caption-*.png"):
            image.unlink()
        results.append((media, result))
        recent.add(result["reaction_id"])
        if len(results) == batch_size:
            break
    if len(results) != batch_size:
        raise RuntimeError(f"Verified {len(results)} of {batch_size} requested eligible videos")
    return results


def destination_settings():
    config = json.loads(os.environ["REACTION_ACCOUNTS"])
    if set(config) != {"tiktok", "instagram", "youtube"}:
        raise ValueError("All three exact reaction destinations are required")
    for service in ("tiktok", "instagram"):
        account = config[service]
        if (not re.fullmatch(r"[a-zA-Z0-9_.]{2,30}", account["username"])
                or not re.fullmatch(r"[0-9]{8,24}", account["user_id"])):
            raise ValueError(f"Invalid expected {service} identity")
    if not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", config["youtube"]["user_id"]):
        raise ValueError("Invalid expected YouTube channel ID")
    config["tiktok"].update(account="viral_reactions", session_env="REACTION_TIKTOK_SESSION")
    config["instagram"].update(session_env="REACTION_INSTAGRAM_SESSION")
    config["youtube"].update(prefix="REACTION_YOUTUBE_API_")
    required = ("REACTION_TIKTOK_SESSION", "REACTION_INSTAGRAM_SESSION", "REACTION_YOUTUBE_API_CLIENT_ID",
                "REACTION_YOUTUBE_API_CLIENT_SECRET", "REACTION_YOUTUBE_API_REFRESH_TOKEN")
    if any(not os.environ.get(name) for name in required):
        raise ValueError("All three reaction account connections are required before posting")
    return config


def publish(media, clip, slot, config):
    title = f"{PREFIX}{slot}"
    row = {**clip, "created_at": datetime.now(timezone.utc).isoformat(), "delivery": {}}
    issue = gh("POST", "issues", json={"title": title, "body": json.dumps(row, ensure_ascii=False, indent=2)})
    Path("gta6-output").mkdir(exist_ok=True)
    attempts = {
        "tiktok": lambda: tiktok_cli_upload(media, clip["caption"], config["tiktok"]),
        "instagram": lambda: instagram_cli_upload(media, clip["caption"], config["instagram"]),
        "youtube": lambda: youtube_api_cli_upload(media, clip, config["youtube"]),
    }
    for platform, submit in attempts.items():
        row["delivery"][platform] = {"status": "uploading"}
        save_issue(issue["number"], row)
        try:
            if platform == "instagram":
                instagram_cli_check(config["instagram"])
            if platform == "youtube":
                youtube_api_client(config["youtube"]["user_id"], config["youtube"]["prefix"])
        except (RuntimeError, ValueError, OSError, KeyError):
            row["delivery"][platform] = {"status": "blocked_before_upload"}
        else:
            try:
                row["delivery"][platform] = submit()
            except (RuntimeError, ValueError, OSError, KeyError):
                row["delivery"][platform] = {"status": "unconfirmed", "reason": "verify platform before any retry"}
        save_issue(issue["number"], row)
    (media.parent / "delivery.json").write_text(json.dumps(row["delivery"], indent=2))
    print(json.dumps({"slot": slot, "issue": issue["number"], "delivery": row["delivery"]}), flush=True)
    if any(receipt["status"] not in ("published", "accepted") for receipt in row["delivery"].values()):
        raise RuntimeError("One or more platforms did not confirm delivery; successful posts will not be duplicated")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preview", "publish"))
    parser.add_argument("inputs", type=Path)
    args = parser.parse_args()
    prior = history()
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    recent = {row["reaction_id"] for _, row in prior if datetime.fromisoformat(row["created_at"]) >= cutoff}
    excluded = {row["id"] for _, row in prior}
    if args.mode == "preview":
        results = prepare(2, args.inputs, excluded, recent)
        print(json.dumps([item for _, item in results], ensure_ascii=False, indent=2))
        return
    config = destination_settings()
    slot_name = os.environ["REACTION_SLOT"]
    if slot_name not in ("midday", "evening") or os.environ.get("GITHUB_REF_NAME") != "main":
        raise ValueError("Only the two scheduled production slots can publish")
    slot = f"{datetime.now(LOCAL).date().isoformat()} {slot_name}"
    if any(row["title"] == PREFIX + slot for row in issues()):
        print(f"{slot} is already reserved. No new upload attempted.")
        return
    (media, clip), = prepare(1, args.inputs, excluded, recent)
    publish(media, clip, slot, config)


if __name__ == "__main__":
    main()
