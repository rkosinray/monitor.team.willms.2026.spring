#!/usr/bin/env python3
"""Monitor a public Google Doc for Willms game updates and notify on changes."""

import argparse
import json
import logging
import os
import smtplib
import sys
import time
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────
DOCUMENT_ID = "1T9feUs-P9KEvOUyT6W6d59DopJ9DNVsMOgBxPXcP4lU"
SEARCH_TERM = "willms"

BASE_DIR      = Path(__file__).parent
SNAPSHOT_FILE = BASE_DIR / "snapshot.json"
LOG_FILE      = BASE_DIR / "monitor.log"

# Email — env vars take precedence (used by GitHub Actions); hardcoded values
# are the local fallback. Leave EMAIL_TO empty ("") to disable notifications.
EMAIL_FROM     = os.getenv("EMAIL_FROM",     "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_TO       = os.getenv("EMAIL_TO",       "")
SMTP_HOST      = "smtp.gmail.com"
SMTP_PORT      = 587
# ───────────────────────────────────────────────────────────────────────────────

EXPORT_URL = f"https://docs.google.com/document/d/{DOCUMENT_ID}/export?format=txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ── Fetch & parse ──────────────────────────────────────────────────────────────

def _fetch_text() -> str:
    delays = [5, 15, 30]  # seconds between retries
    for attempt, delay in enumerate(delays + [None], start=1):
        try:
            with urllib.request.urlopen(EXPORT_URL, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 500 and delay is not None:
                log.warning("HTTP 500 on attempt %d — retrying in %ds…", attempt, delay)
                time.sleep(delay)
            else:
                log.error("Failed to fetch document after %d attempts: %s", attempt, exc)
                sys.exit(1)
        except Exception as exc:
            log.error("Failed to fetch document: %s", exc)
            sys.exit(1)


def _parse_all_games(text: str) -> list[dict]:
    """
    The doc exports as one tab-indented cell per line.
    Columns in order: DATE, TIME, FIELD, HOME TEAM, AWAY TEAM.
    We find the header block, then group every 5 data lines into a game row.
    """
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]

    try:
        header_idx = lines.index("DATE")
    except ValueError:
        log.error("Could not find schedule header in document.")
        return []

    # Skip the 5 header labels: DATE, TIME, FIELD, HOME TEAM, AWAY TEAM
    data = lines[header_idx + 5:]

    games = []
    for i in range(0, len(data) - 4, 5):
        chunk = data[i:i + 5]
        if len(chunk) < 5:
            break
        games.append({
            "date":  chunk[0],
            "time":  chunk[1],
            "field": chunk[2],
            "home":  chunk[3],
            "away":  chunk[4],
        })
    return games


def fetch_willms_games() -> list[dict]:
    """Return all games where Willms appears as home or away team."""
    games = _parse_all_games(_fetch_text())
    results = []
    for g in games:
        is_home = SEARCH_TERM in g["home"].lower()
        is_away = SEARCH_TERM in g["away"].lower()
        if not is_home and not is_away:
            continue
        results.append({
            "date":      g["date"],
            "time":      g["time"],
            "location":  g["field"],
            "home_away": "HOME" if is_home else "AWAY",
            "opponent":  g["away"] if is_home else g["home"],
        })
    return results


# ── Snapshot persistence ───────────────────────────────────────────────────────

def load_snapshot() -> list[dict]:
    if SNAPSHOT_FILE.exists():
        return json.loads(SNAPSHOT_FILE.read_text())
    return []


def save_snapshot(games: list[dict]) -> None:
    SNAPSHOT_FILE.write_text(json.dumps(games, indent=2))


# ── Formatting ─────────────────────────────────────────────────────────────────

def _format_game(g: dict) -> str:
    return (
        f"{g['date']}  {g['time']:>8}  |  {g['location']:<14}  "
        f"|  {g['home_away']}  vs  {g['opponent']}"
    )


# ── Email notification ─────────────────────────────────────────────────────────

def send_email(subject: str, body: str) -> None:
    if not EMAIL_TO or not EMAIL_FROM:
        return
    recipients = [addr.strip() for addr in EMAIL_TO.split(",") if addr.strip()]
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_FROM
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, recipients, msg.as_string())
        log.info("Email notification sent to %s", ", ".join(recipients))
    except Exception as exc:
        log.error("Failed to send email: %s", exc)


# ── Core check ────────────────────────────────────────────────────────────────

def _game_key(g: dict) -> tuple:
    return (g["date"], g["time"], g["location"], g["home_away"], g["opponent"])


def check_for_updates(test_mode: bool = False) -> None:
    current  = fetch_willms_games()
    previous = load_snapshot()

    current_keys  = {_game_key(g) for g in current}
    previous_keys = {_game_key(g) for g in previous}

    added   = [g for g in current  if _game_key(g) not in previous_keys]
    removed = [g for g in previous if _game_key(g) not in current_keys]

    if test_mode:
        header = f"{'DATE':<12} {'TIME':>8}    {'LOCATION':<14}    {'H/A':<4}  OPPONENT"
        divider = "-" * 70
        print(f"\n{'='*70}")
        print(f"  Willms schedule — {len(current)} game(s) found")
        print(f"{'='*70}")
        print(f"  {header}")
        print(f"  {divider}")
        for g in current:
            print(f"  {_format_game(g)}")
        print(f"\n  Added since last run  : {len(added)}")
        print(f"  Removed since last run: {len(removed)}")
        if added:
            print("\n  ADDED:")
            for g in added: print(f"    + {_format_game(g)}")
        if removed:
            print("\n  REMOVED:")
            for g in removed: print(f"    - {_format_game(g)}")
        print()
        return

    if added or removed:
        lines = ["Willms game schedule change detected!\n"]
        if added:
            lines.append("ADDED:")
            lines.extend(f"  + {_format_game(g)}" for g in added)
            lines.append("")
        if removed:
            lines.append("REMOVED:")
            lines.extend(f"  - {_format_game(g)}" for g in removed)
        body = "\n".join(lines)
        log.info("Changes detected:\n%s", body)
        send_email("Willms Game Schedule Update", body)
        save_snapshot(current)
    else:
        log.info("No changes in Willms schedule.")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor Google Doc for Willms games")
    parser.add_argument("--test", action="store_true",
                        help="Fetch current schedule and print a diff without saving")
    args = parser.parse_args()
    check_for_updates(test_mode=args.test)


if __name__ == "__main__":
    main()
