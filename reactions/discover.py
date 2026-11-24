"""Rank current Commons video traffic, then enforce verifiable reuse terms."""

from datetime import datetime, timedelta, timezone
from html import unescape
import re
from urllib.parse import quote, unquote, urlsplit

import requests

HEADERS = {"User-Agent": "EnergeticCityReactionPublisher/1.0 (https://github.com/energeticcity/reaction-video-assets)"}
METRICS = "https://wikimedia.org/api/rest_v1/metrics/mediarequests/top/all-referers/video"
COMMONS = "https://commons.wikimedia.org/w/api.php"
LICENSE = re.compile(r"https?://creativecommons\.org/(?:licenses/by/(?:2\.0|2\.5|3\.0|4\.0)|publicdomain/zero/1\.0)(?:/.*)?$")
UNSUITABLE = re.compile(
    r"\b(?:sex(?:ual|uality)?|porn\w*|nude|naked|breastfeeding|masturbat\w*|ejaculat\w*|penis|vagina|fetish|"
    r"2 girls 1 cup|rape|terror\w*|IED|explos\w*|shoot\w*|murder\w*|sniper\w*|massacre|attack\w*|helicopter crash|"
    r"suicide|death|killed|war|protest\w*|genocide|blood|gore|politic\w*|president|assault|trailer|"
    r"full episode|tsunami|landing on mars|apollo\s*11)\b", re.I,
)


def plain(value):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", value)).split())


def charts(now):
    days = []
    for offset in range(1, 6):
        day = now.date() - timedelta(days=offset)
        response = requests.get(f"{METRICS}/{day:%Y/%m/%d}", headers=HEADERS, timeout=15)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        chart = response.json()["items"][0]["files"]
        rows = {row["file_path"]: row["requests"] for row in chart
                if row["file_path"].startswith("/wikipedia/commons/")}
        if rows:
            days.append((day.isoformat(), rows))
        if len(days) == 2:
            return days
    raise RuntimeError("No two recent Commons video traffic charts are available")


def file_metadata(title_list):
    response = requests.get(COMMONS, headers=HEADERS, timeout=25, params={
        "action": "query", "format": "json", "formatversion": 2, "titles": "|".join(title_list),
        "prop": "imageinfo", "iiprop": "url|mime|extmetadata|sha1|size",
    })
    response.raise_for_status()
    return response.json()["query"]["pages"]


def discover(used=(), now=None):
    recent, previous = charts(now or datetime.now(timezone.utc))
    baseline = min(previous[1].values())
    ranked = []
    for path, count in recent[1].items():
        older = previous[1].get(path, baseline)
        name = "File:" + unquote(path.rsplit("/", 1)[-1]).replace("_", " ")
        if count >= 2800 and count - older >= 350 and count >= older * 1.12 and not UNSUITABLE.search(name):
            ranked.append((count - older, count, older, name))
    ranked.sort(reverse=True)
    records = {name: (growth, count, older) for growth, count, older, name in ranked[:100]}
    previous_names = {unquote(path.rsplit("/", 1)[-1]).replace("_", " ") for path in previous[1]}
    found = []
    names = list(records)
    for start in range(0, len(names), 30):
        for page in file_metadata(names[start:start + 30]):
            info = next(iter(page.get("imageinfo", [])), None)
            if not info or page.get("missing") or page["title"] not in records:
                continue
            if not 11 <= info.get("duration", 0) <= 90 or not 1000 < info["size"] <= 65_000_000:
                continue
            metadata = {key: plain(entry["value"]) for key, entry in info["extmetadata"].items()
                        if isinstance(entry.get("value"), str)}
            license_url = metadata.get("LicenseUrl", "")
            credits = metadata.get("Credit", "")
            artist = metadata.get("Artist", "")
            description = metadata.get("ImageDescription", "")
            license_name = metadata.get("LicenseShortName", "")
            if (not LICENSE.fullmatch(license_url) or not re.fullmatch(r"(?:CC0|CC BY [234]\.[05])", license_name)
                    or metadata.get("Restrictions") or not artist or not description or not credits
                    or UNSUITABLE.search(description)):
                continue
            if urlsplit(info["url"]).hostname != "upload.wikimedia.org" or urlsplit(info["descriptionurl"]).hostname != "commons.wikimedia.org":
                continue
            source_id = info["sha1"]
            if source_id in used or any(item["id"] == source_id for item in found):
                continue
            growth, count, older = records[page["title"]]
            found.append({
                "id": source_id, "title": page["title"].removeprefix("File:").rsplit(".", 1)[0],
                "creator": artist[:140], "source_description": description[:750], "source": info["descriptionurl"],
                "download_url": info["url"], "seconds": info["duration"], "size": info["size"],
                "license": license_name, "license_url": license_url,
                "traffic": {"date": recent[0], "requests": count,
                            "previous_date": previous[0], "comparison_requests": older, "increase": growth,
                            "comparison_is_upper_bound": page["title"].removeprefix("File:") not in previous_names},
            })
    return sorted(found, key=lambda row: row["traffic"]["increase"], reverse=True)


if __name__ == "__main__":
    import json
    print(json.dumps(discover(), ensure_ascii=False, indent=2))
