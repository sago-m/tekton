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
FEEDS = [
    ("CISA advisories", "vuln", "https://www.cisa.gov/cybersecurity-advisories/all.xml"),
    ("BleepingComputer", "cyber", "https://www.bleepingcomputer.com/feed/"),
    ("The Hacker News", "cyber", "https://feeds.feedburner.com/TheHackersNews"),
    ("OpenAI News", "ai", "https://openai.com/news/rss.xml"),
    ("Google AI", "ai", "https://blog.google/technology/ai/rss/"),
]
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
        identity = hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]
        results.append({
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
        })
    return results


def main() -> None:
    today = dt.datetime.now(UTC).date()
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
