#!/usr/bin/env python3
"""Collect daily security and AI headlines from public RSS feeds."""
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "news.json"
VIDEO_FILE = ROOT / "videos.json"
FEEDS = [
    ("CISA advisories", "vuln", "https://www.cisa.gov/cybersecurity-advisories/all.xml"),
    ("BleepingComputer", "cyber", "https://www.bleepingcomputer.com/feed/"),
    ("The Hacker News", "cyber", "https://feeds.feedburner.com/TheHackersNews"),
    ("OpenAI News", "ai", "https://openai.com/news/rss.xml"),
    ("Google AI", "ai", "https://blog.google/technology/ai/rss/"),
]
YOUTUBE_CHANNELS = [
    ("Google DeepMind", "ai", "UCP7jMXSY2xbc3KCAE0MHQ-A"),
    ("IBM Technology", "ai", "UCKWaEZ-_VweaEx1j62do_vQ"),
    ("John Hammond", "cyber", "UCVeW9qkBjo3zosnqUbG7CFw"),
    ("LiveOverflow", "cyber", "UClcE-kVhqyiHCcjYwcpfj9w"),
    ("Computerphile", "mixed", "UC9-y-6csu5WGm29I7JiwpnA"),
]
VIDEO_KEYWORDS = re.compile(
    r"\b(ai|artificial intelligence|machine learning|cyber|security|privacy|"
    r"malware|hacking|vulnerabilit|phishing|ransomware|deepfake|llm|"
    r"large language model|encryption|exploit|threat|data breach)\b",
    re.IGNORECASE,
)
UTC = dt.timezone.utc


def plain_text(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value or "")
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def parse_date(item: ET.Element) -> dt.datetime | None:
    for key in ("pubDate", "published", "updated", "date"):
        node = item.find(key)
        if node is None:
            node = item.find(f"{{http://www.w3.org/2005/Atom}}{key}")
        if node is None or not (node.text or "").strip():
            continue
        raw = node.text.strip()
        try:
            parsed = email.utils.parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            try:
                parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def item_text(item: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        node = item.find(name)
        if node is None:
            node = item.find(f"{{http://www.w3.org/2005/Atom}}{name}")
        if node is not None:
            if name == "link" and node.attrib.get("href"):
                return node.attrib["href"].strip()
            if node.text:
                return node.text.strip()
    return ""


def safe_image_url(value: str) -> str:
    value = html.unescape((value or "").strip())
    if value.startswith("//"):
        value = "https:" + value
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.netloc:
        return value
    return ""


def item_image(item: ET.Element) -> str:
    """Return a secure image URL exposed by the story's RSS/Atom metadata."""
    for node in item.iter():
        name = node.tag.rsplit("}", 1)[-1].lower()
        mime = node.attrib.get("type", "").lower()
        medium = node.attrib.get("medium", "").lower()
        candidate = node.attrib.get("url") or node.attrib.get("href") or ""
        is_image_field = name in {"thumbnail", "image"} or (
            name in {"content", "enclosure"}
            and (mime.startswith("image/") or medium == "image")
        ) or (
            name == "link"
            and node.attrib.get("rel", "").lower() in {"enclosure", "thumbnail"}
            and mime.startswith("image/")
        )
        if candidate and is_image_field:
            image = safe_image_url(candidate)
            if image:
                return image

    # Some feeds put the article's image in the HTML description instead of
    # RSS media metadata. Read the image URL only; never render feed HTML.
    for node in item.iter():
        if node.tag.rsplit("}", 1)[-1].lower() not in {"description", "summary", "encoded", "content"}:
            continue
        markup = node.text or ""
        for match in re.finditer(r"(?is)<img\b[^>]*?\bsrc\s*=\s*(['\"])(.*?)\1", markup):
            image = safe_image_url(match.group(2))
            if image:
                return image
    return ""


def fetch_feed(name: str, category: str, url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "TeklonNewsBot/1.0 (+daily public RSS collector)", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
    with urllib.request.urlopen(req, timeout=25) as response:
        root = ET.fromstring(response.read())
    results = []
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1] not in ("item", "entry"):
            continue
        title = plain_text(item_text(item, ("title",)))
        link = item_text(item, ("link", "guid"))
        published = parse_date(item)
        desc = plain_text(item_text(item, ("description", "summary", "content")))
        if not title or not published or not link:
            continue
        parsed = urlparse(link)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        if len(title) > 240:
            title = title[:237].rstrip() + "…"
        if not desc:
            desc = f"{name} published a new update. Open the original report for details."
        image = item_image(item)
        identity = hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]
        story = {
            "id": identity,
            "category": category,
            "label": {"cyber": "CYBERSECURITY", "ai": "AI & RESEARCH", "vuln": "VULNERABILITY"}[category],
            "time": published.strftime("%H:%M UTC"),
            "publishedAt": published.isoformat(),
            "source": name,
            "title": title,
            "description": desc[:300],
            "summary": desc[:900],
            "detail": desc[:1600] or title,
            "url": link,
        }
        if image:
            story["image"] = image
        results.append(story)
    return results


def video_summary(description: str, title: str, channel: str) -> str:
    """Make a readable short overview from the channel's public video description."""
    cleaned = re.sub(r"https?://\S+", "", description or "")
    cleaned = re.sub(r"(?m)#\w+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–|")
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    summary = " ".join(sentence for sentence in sentences if sentence)[:850].strip()
    return summary or f"{channel} shares a recent video about {title}."


def fetch_youtube_channel(name: str, category: str, channel_id: str) -> list[dict]:
    """Read recent public uploads from a curated channel's YouTube Atom feed."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TeklonVideoBot/1.0 (+public channel feed reader)",
                 "Accept": "application/atom+xml, application/xml, text/xml"},
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        root = ET.fromstring(response.read())
    results = []
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1] != "entry":
            continue
        title = plain_text(item_text(item, ("title",)))
        video_id = ""
        description = ""
        thumbnail = ""
        for node in item.iter():
            local = node.tag.rsplit("}", 1)[-1].lower()
            if local == "videoid":
                video_id = (node.text or "").strip()
            elif local in {"description", "summary", "content"} and node.text:
                description = plain_text(node.text)
            elif local == "thumbnail" and node.attrib.get("url"):
                thumbnail = safe_image_url(node.attrib["url"])
        published = parse_date(item)
        if not video_id or not title or not published:
            continue
        if category == "mixed" and not VIDEO_KEYWORDS.search(f"{title} {description}"):
            continue
        video_category = category
        if category == "mixed":
            video_category = "cyber" if re.search(
                r"\b(cyber|security|privacy|malware|hacking|vulnerabilit|phishing|ransomware|encryption|exploit|threat|data breach)\b",
                f"{title} {description}", re.IGNORECASE,
            ) else "ai"
        summary = video_summary(description, title, name)
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        results.append({
            "id": video_id,
            "category": video_category,
            "source": name,
            "channelUrl": f"https://www.youtube.com/channel/{channel_id}",
            "title": title[:240],
            "description": summary[:260],
            "summary": summary,
            "thumbnail": thumbnail or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            "url": watch_url,
            "publishedAt": published.isoformat(),
        })
    return results


def update_videos(today: dt.date) -> None:
    previous = json.loads(VIDEO_FILE.read_text(encoding="utf-8")) if VIDEO_FILE.exists() else {}
    by_id: dict[str, dict] = {
        item["id"]: item for item in previous.get("videos", []) if item.get("id")
    }
    errors = []
    for name, category, channel_id in YOUTUBE_CHANNELS:
        try:
            for item in fetch_youtube_channel(name, category, channel_id):
                published = dt.datetime.fromisoformat(item["publishedAt"]).date()
                if published >= today - dt.timedelta(days=30):
                    by_id[item["id"]] = item
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError, ValueError) as exc:
            errors.append(f"{name}: {exc}")
    videos = sorted(by_id.values(), key=lambda item: item.get("publishedAt", ""), reverse=True)
    videos = [item for item in videos if dt.datetime.fromisoformat(item["publishedAt"]).date() >= today - dt.timedelta(days=30)][:24]
    if not videos and not previous.get("videos"):
        print("No YouTube videos were retrieved; the video section will show its empty state.", file=sys.stderr)
    VIDEO_FILE.write_text(json.dumps({
        "updatedAt": dt.datetime.now(UTC).replace(microsecond=0).isoformat(),
        "videos": videos,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Collected {len(videos)} recent YouTube videos from curated channels.")
    if errors:
        print("Some YouTube channels could not be refreshed:\n" + "\n".join(errors), file=sys.stderr)


def main() -> None:
    today = dt.datetime.now(UTC).date()
    update_videos(today)
    previous = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else {}
    fetched: list[dict] = []
    errors = []
    for name, category, url in FEEDS:
        try:
            fetched.extend(fetch_feed(name, category, url))
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError, ValueError) as exc:
            errors.append(f"{name}: {exc}")
    if not fetched:
        print("No feed items were retrieved; leaving the existing edition untouched.", file=sys.stderr)
        if errors:
            print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)

    by_url: dict[str, dict] = {}
    for story in fetched:
        old = by_url.get(story["url"])
        if old is None or story["publishedAt"] > old["publishedAt"]:
            by_url[story["url"]] = story
    all_stories = sorted(by_url.values(), key=lambda story: story["publishedAt"], reverse=True)
    archive: dict[str, dict[str, dict]] = {}
    for day, items in (previous.get("archive") or {}).items():
        if day < today.isoformat() and (today - dt.date.fromisoformat(day)).days <= 90:
            archive[day] = {item["url"]: item for item in items if item.get("url")}
    previous_day = previous.get("date")
    if previous_day and previous_day < today.isoformat():
        archive.setdefault(previous_day, {})
        for item in previous.get("stories", []):
            if item.get("url"):
                archive[previous_day][item["url"]] = item
    current, historical = [], []
    cutoff = today - dt.timedelta(days=30)
    for story in all_stories:
        day = dt.datetime.fromisoformat(story["publishedAt"]).date()
        if day == today:
            current.append(story)
        elif cutoff <= day < today:
            archive.setdefault(day.isoformat(), {})[story["url"]] = story
    current = current[:40]
    if current:
        current[0]["featured"] = True
    data = {
        "date": today.isoformat(),
        "updatedAt": dt.datetime.now(UTC).replace(microsecond=0).isoformat(),
        "stories": current,
        "archive": {day: sorted(items.values(), key=lambda item: item.get("publishedAt", ""), reverse=True)[:80]
                    for day, items in sorted(archive.items(), reverse=True) if items},
    }
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Collected {len(current)} stories for {today}; archived {sum(map(len, data['archive'].values()))} older stories.")
    if errors:
        print("Some sources could not be refreshed:\n" + "\n".join(errors), file=sys.stderr)


if __name__ == "__main__":
    main()
