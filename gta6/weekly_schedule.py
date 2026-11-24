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
    now = datetime.now(ZoneInfo("UTC"))
    requested = os.environ.get("EPISODE")
    if requested == "next-week":
        now += timedelta(days=7)
        requested = "weekly"
    episode = choose(CATALOG, now, requested)
    spec = json.loads((CATALOG / f"{episode}.json").read_text()) if episode else {}
    if not spec and os.environ.get("AUTO_PLAN") == "true":
        from gta6.weekly_autoplan import START, plan_week

        local = now.astimezone(ZoneInfo("America/Dawson_Creek")).date()
        monday = local - timedelta(days=local.weekday())
        if monday >= START:
            spec = plan_week(monday)
            episode = spec["id"]
    published_video = spec.get("published_youtube_id", "")
    if published_video and not re.fullmatch(r"[A-Za-z0-9_-]{11}", published_video):
        raise ValueError("Invalid published YouTube video ID in weekly catalog")
    if spec and os.environ.get("SPEC_OUTPUT"):
        spec_path = Path(os.environ["SPEC_OUTPUT"])
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    render = bool(episode and not (published_video and os.environ.get("REUSE_PUBLICATION") == "true"))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
        print(f"episode={episode}", file=stream)
        print(f"published_video={published_video}", file=stream)
        print(f"render={str(render).lower()}", file=stream)
    print(f"Weekly episode: {episode}" if episode else "No episode assigned to this week.")
