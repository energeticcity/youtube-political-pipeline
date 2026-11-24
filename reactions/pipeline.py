"""Produce trending reactions and deliver them only to configured reaction accounts."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from gta6_cloud import model_name, issues, save_issue
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
            continue
        # Keep the verified cut and public provenance rather than redistributing source media.
        for name in ("source.webm", "source.mp4", "source-review.mp4", "reaction.gif", "reaction-review.mp4",
                     "speech.wav", "captions.ass"):
            (slot / name).unlink(missing_ok=True)
        results.append((media, result))
        recent.add(result["reaction_id"])
        if len(results) == batch_size:
            break
    if len(results) != batch_size:
        raise RuntimeError(f"Verified {len(results)} of {batch_size} requested eligible videos")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preview",))
    parser.add_argument("inputs", type=Path)
    args = parser.parse_args()
    prior = history()
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    recent = {row["reaction_id"] for _, row in prior if datetime.fromisoformat(row["created_at"]) >= cutoff}
    results = prepare(2, args.inputs, {row["id"] for _, row in prior}, recent)
    print(json.dumps([item for _, item in results], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
