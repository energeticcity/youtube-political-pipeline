"""Choose the one episode assigned to this week in Dawson Creek."""
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo

CATALOG = Path(__file__).with_name("weekly")


def choose(catalog, now, requested):
    if requested and requested != "weekly":
        if not re.fullmatch(r"[a-z0-9-]+", requested):
            raise ValueError("Invalid episode slug")
        path = catalog / f"{requested}.json"
        if not path.is_file():
            raise ValueError("Episode specification file does not exist")
        return path.stem

    date = now.astimezone(ZoneInfo("America/Dawson_Creek")).date()
    monday = (date - timedelta(days=date.weekday())).isoformat()
    matches = [path.stem for path in catalog.glob("*.json")
               if json.loads(path.read_text()).get("preview_week") == monday]
    if len(matches) > 1:
        raise ValueError(f"Multiple episodes assigned to the week of {monday}")
    return matches[0] if matches else ""


if __name__ == "__main__":
    episode = choose(CATALOG, datetime.now(ZoneInfo("UTC")), os.environ.get("EPISODE"))
    published_video = ""
    if episode:
        spec = json.loads((CATALOG / f"{episode}.json").read_text())
        published_video = spec.get("published_youtube_id", "")
        if published_video and not re.fullmatch(r"[A-Za-z0-9_-]{11}", published_video):
            raise ValueError("Invalid published YouTube video ID in weekly catalog")
    render = bool(episode and not (published_video and os.environ.get("REUSE_PUBLICATION") == "true"))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
        print(f"episode={episode}", file=stream)
        print(f"published_video={published_video}", file=stream)
        print(f"render={str(render).lower()}", file=stream)
    print(f"Weekly episode: {episode}" if episode else "No episode assigned to this week.")
