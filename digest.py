"""
ai-digest — Stage 1: The plumbing.

Reads RSS feeds, remembers what it has seen, emails new items.
No LLM yet. Just the skeleton every agent needs:
  perception (fetch) → memory (dedupe) → action (email).
"""
import json
import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import feedparser

# --- File paths ---
FEEDS_FILE = Path("feeds.txt")
SEEN_FILE = Path("seen.json")


# --- Feed list ---
def load_feeds():
    """Read feed URLs from feeds.txt. Skip blank lines and # comments."""
    with open(FEEDS_FILE) as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]


# --- Memory: which items have we already seen? ---
def load_seen():
    """Load the set of item IDs we've already processed."""
    if SEEN_FILE.exists():
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    """Persist the set so the next run knows what's new."""
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def item_id(entry):
    """Stable unique ID for a feed entry."""
    return entry.get("id") or entry.get("link") or entry.get("title")


# --- Perception: fetch and diff ---
def fetch_new_items():
    """Return only entries we haven't seen before, across all feeds."""
    feeds = load_feeds()
    seen = load_seen()
    new_items = []

    for url in feeds:
        print(f"Fetching {url} ...")
        try:
            parsed = feedparser.parse(url)
            if parsed.bozo:
                print(f"  ⚠️  Feed parse warning: {parsed.bozo_exception}")
            source = parsed.feed.get("title", url)
            entry_count = len(parsed.entries)
            print(f"  → {entry_count} entries found (source: {source!r})")
            for entry in parsed.entries:
                eid = item_id(entry)
                if not eid or eid in seen:
                    continue
                new_items.append(
                    {
                        "source": source,
                        "title": entry.get("title", "(no title)"),
                        "link": entry.get("link", ""),
                        "summary": entry.get("summary", "")[:500],
                        "published": entry.get("published", ""),
                    }
                )
                seen.add(eid)
        except Exception as e:
            print(f"  ❌ ERROR fetching {url}: {e}")

    save_seen(seen)
    return new_items


# --- Action: render the digest ---
def format_digest(items):
    """Format new items as a plain-text digest, grouped by source."""
    if not items:
        return "No new items today."

    header = f"ai-digest — {datetime.now(timezone.utc).strftime('%Y-%m-%d')} UTC"
    lines = [header, "=" * len(header), "", f"{len(items)} new item(s)", ""]

    by_source = {}
    for item in items:
        by_source.setdefault(item["source"], []).append(item)

    for source, source_items in by_source.items():
        lines.append(f"--- {source} ({len(source_items)}) ---")
        for item in source_items:
            lines.append(f"  • {item['title']}")
            lines.append(f"    {item['link']}")
            lines.append("")

    return "\n".join(lines)


# --- Action: email delivery ---
def send_email(subject, body):
    """Send the digest via Gmail SMTP. Skips if credentials aren't set."""
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_pass:
        print("⚠️  GMAIL_USER or GMAIL_APP_PASSWORD not set — skipping email.")
        return

    to_addr = os.environ.get("DIGEST_TO", gmail_user)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = to_addr
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(gmail_user, gmail_pass)
        smtp.send_message(msg)
    print(f"📧 Sent digest to {to_addr}")


# --- Entry point ---
def main():
    items = fetch_new_items()
    digest = format_digest(items)
    print()
    print(digest)

    if items:
        subject = f"ai-digest — {len(items)} new items — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        send_email(subject, digest)
    else:
        print("Nothing new — skipping email.")


if __name__ == "__main__":
    main()