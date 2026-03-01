"""
GhostDesk YouTube Insights

Reads your liked videos + subscriptions via YouTube Data API v3 to build
a taste profile, then periodically surfaces new content matching your interests.

Note: YouTube watch history is NOT accessible via the API (removed in 2016).
      Liked videos + subscriptions are used as the taste signal instead.

Setup:
  1. Enable YouTube Data API v3 in Google Cloud Console (same project as other Google APIs).
  2. Your existing ~/.ghostdesk/google_oauth_secret.json works — just re-auth once.
  3. Set YOUTUBE_ALERTS_ENABLED=true in .env, restart GhostDesk.
"""

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_YT_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

# Module-level bot context — set by register_yt_alerts()
_bot_app = None
_chat_id: int = 0
_scheduler = None


# ─── DB ───────────────────────────────────────────────────────────────────────

def _db() -> str:
    from config import DB_PATH
    return str(DB_PATH)


def _ensure_tables():
    with sqlite3.connect(_db()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS yt_taste_profile (
                id         INTEGER PRIMARY KEY,
                interests  TEXT NOT NULL DEFAULT '[]',
                topics     TEXT NOT NULL DEFAULT '[]',
                fav_channels TEXT NOT NULL DEFAULT '[]',
                summary    TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS yt_seen_videos (
                video_id TEXT PRIMARY KEY,
                title    TEXT,
                channel  TEXT,
                seen_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


# ─── Auth ─────────────────────────────────────────────────────────────────────

def _yt():
    """Build a YouTube Data API v3 client with its own OAuth2 token file."""
    from config import USER_DATA_DIR, GOOGLE_SHEETS_CREDS_PATH
    token_path   = Path(USER_DATA_DIR) / "youtube_token.json"
    oauth_secret = Path(USER_DATA_DIR) / "google_oauth_secret.json"

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "Install: pip install google-api-python-client google-auth-oauthlib"
        )

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _YT_SCOPES)
        if creds and creds.valid:
            pass
        elif creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
        else:
            creds = None

    if not creds:
        if not oauth_secret.exists():
            raise FileNotFoundError(
                "YouTube OAuth not configured.\n"
                "Download OAuth2 client JSON from Google Cloud Console\n"
                "(YouTube Data API v3 must be enabled) and save it to:\n"
                f"  {oauth_secret}\n"
                "Then say: *analyze my YouTube taste* to trigger the login."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(oauth_secret), _YT_SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return build("youtube", "v3", credentials=creds)


# ─── Data fetchers ────────────────────────────────────────────────────────────

def get_liked_videos(max_results: int = 50) -> dict:
    """Fetch the user's liked videos from YouTube."""
    try:
        _ensure_tables()
        yt = _yt()
        items, page_token = [], None

        while len(items) < max_results:
            batch = min(50, max_results - len(items))
            kw = dict(part="snippet", myRating="like", maxResults=batch)
            if page_token:
                kw["pageToken"] = page_token
            resp = yt.videos().list(**kw).execute()
            items.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        videos = []
        for item in items:
            s = item.get("snippet", {})
            videos.append({
                "id":           item.get("id", ""),
                "title":        s.get("title", ""),
                "channel":      s.get("channelTitle", ""),
                "description":  s.get("description", "")[:300],
                "tags":         s.get("tags", [])[:10],
                "published_at": s.get("publishedAt", ""),
            })

        lines = [f"👍 *Liked Videos ({len(videos)})*\n"]
        for v in videos[:25]:
            lines.append(f"• {v['title']} — _{v['channel']}_")
        if len(videos) > 25:
            lines.append(f"_…and {len(videos) - 25} more_")
        return {"success": True, "videos": videos, "text": "\n".join(lines)}

    except FileNotFoundError as e:
        return {"success": False, "error": str(e), "text": str(e)}
    except Exception as e:
        logger.error(f"get_liked_videos: {e}")
        return {"success": False, "error": str(e), "text": f"❌ {e}"}


def get_subscriptions(max_results: int = 50) -> dict:
    """Fetch the user's YouTube channel subscriptions."""
    try:
        _ensure_tables()
        yt = _yt()
        items, page_token = [], None

        while len(items) < max_results:
            batch = min(50, max_results - len(items))
            kw = dict(part="snippet", mine=True, maxResults=batch, order="relevance")
            if page_token:
                kw["pageToken"] = page_token
            resp = yt.subscriptions().list(**kw).execute()
            items.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        channels = [
            {
                "channel_id": i.get("snippet", {}).get("resourceId", {}).get("channelId", ""),
                "name":        i.get("snippet", {}).get("title", ""),
                "description": i.get("snippet", {}).get("description", "")[:200],
            }
            for i in items
        ]

        lines = [f"📺 *Subscriptions ({len(channels)})*\n"]
        for c in channels[:25]:
            lines.append(f"• {c['name']}")
        if len(channels) > 25:
            lines.append(f"_…and {len(channels) - 25} more_")
        return {"success": True, "channels": channels, "text": "\n".join(lines)}

    except FileNotFoundError as e:
        return {"success": False, "error": str(e), "text": str(e)}
    except Exception as e:
        logger.error(f"get_subscriptions: {e}")
        return {"success": False, "error": str(e), "text": f"❌ {e}"}


# ─── Taste analysis ───────────────────────────────────────────────────────────

def analyze_taste(max_results: int = 100) -> dict:
    """
    Fetch liked videos + subscriptions, use AI to extract interest categories,
    and persist the profile to SQLite.
    """
    try:
        _ensure_tables()
        liked = get_liked_videos(max_results)
        subs  = get_subscriptions(50)

        videos   = liked.get("videos", [])
        channels = subs.get("channels", [])

        if not videos and not channels:
            return {
                "success": False,
                "text": (
                    "⚠️ Could not fetch YouTube data.\n"
                    "Make sure YouTube Data API v3 is enabled in Google Cloud Console\n"
                    "and run the OAuth flow (the browser will open automatically)."
                ),
            }

        video_block = "\n".join(
            f"- {v['title']} by {v['channel']}"
            + (f" [tags: {', '.join(v['tags'][:5])}]" if v.get("tags") else "")
            for v in videos[:60]
        )
        channel_block = "\n".join(
            f"- {c['name']}: {c['description'][:80]}" for c in channels[:40]
        )

        prompt = (
            "Analyse this user's YouTube liked videos and subscriptions "
            "and identify their interests.\n\n"
            f"LIKED VIDEOS ({len(videos)} total):\n{video_block}\n\n"
            f"SUBSCRIBED CHANNELS ({len(channels)} total):\n{channel_block}\n\n"
            "Return ONLY a JSON object — no markdown, no explanation:\n"
            '{\n'
            '  "interests": ["broad interest 1", "broad interest 2"],\n'
            '  "topics": ["specific topic to search YouTube for"],\n'
            '  "fav_channels": ["Channel Name"],\n'
            '  "summary": "One-sentence personality summary."\n'
            '}'
        )

        from core.ai import get_ai
        raw = get_ai().call("You are a YouTube taste analyst. Be concise.", prompt, 1024)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
        profile = json.loads(raw.strip())

        with sqlite3.connect(_db()) as conn:
            conn.execute("DELETE FROM yt_taste_profile")
            conn.execute(
                "INSERT INTO yt_taste_profile (interests, topics, fav_channels, summary) "
                "VALUES (?,?,?,?)",
                (
                    json.dumps(profile.get("interests", [])),
                    json.dumps(profile.get("topics", [])),
                    json.dumps(profile.get("fav_channels", [])),
                    profile.get("summary", ""),
                ),
            )
            conn.commit()

        interests = profile.get("interests", [])
        topics    = profile.get("topics", [])
        summary   = profile.get("summary", "")
        text = (
            f"🎯 *YouTube Taste Profile Updated*\n\n"
            f"*Interests:* {', '.join(interests)}\n"
            f"*Topics:* {', '.join(topics[:8])}\n"
            f"*Summary:* _{summary}_\n\n"
            f"_Based on {len(videos)} liked videos and {len(channels)} subscriptions._\n\n"
            f"Say *enable YouTube alerts* to get notified when new content matches your taste."
        )
        return {"success": True, "profile": profile, "text": text}

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"AI returned invalid JSON: {e}"}
    except Exception as e:
        logger.error(f"analyze_taste: {e}")
        return {"success": False, "error": str(e), "text": f"❌ {e}"}


def get_taste_profile() -> dict:
    """Return the saved YouTube taste profile from the DB."""
    try:
        _ensure_tables()
        with sqlite3.connect(_db()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM yt_taste_profile ORDER BY id DESC LIMIT 1"
            ).fetchone()

        if not row:
            return {
                "success": True,
                "topics": [],
                "text": (
                    "📊 No YouTube taste profile yet.\n"
                    "Say: *analyze my YouTube taste* to build one."
                ),
            }

        row      = dict(row)
        interests    = json.loads(row.get("interests", "[]"))
        topics       = json.loads(row.get("topics", "[]"))
        fav_channels = json.loads(row.get("fav_channels", "[]"))
        updated      = row.get("updated_at", "")[:16]

        text = (
            f"📊 *Your YouTube Taste Profile*\n_(updated {updated})_\n\n"
            f"*Interests:* {', '.join(interests) or '—'}\n"
            f"*Topics you enjoy:* {', '.join(topics) or '—'}\n"
            f"*Favourite channels:* {', '.join(fav_channels[:10]) or '—'}\n\n"
            f"_{row.get('summary', '')}_"
        )
        return {
            "success": True, "profile": row,
            "interests": interests, "topics": topics, "text": text,
        }
    except Exception as e:
        logger.error(f"get_taste_profile: {e}")
        return {"success": False, "error": str(e), "text": f"❌ {e}"}


# ─── Content search & alerts ──────────────────────────────────────────────────

def search_new_content(query: str = "", max_results: int = 10) -> dict:
    """
    Search YouTube for recent videos matching a query.
    If query is blank, uses saved interest topics.
    Only returns videos not previously seen.
    """
    try:
        _ensure_tables()

        if not query:
            profile = get_taste_profile()
            topics  = profile.get("topics", [])
            if not topics:
                return {
                    "success": False,
                    "text": "No taste profile yet. Say: *analyze my YouTube taste* first.",
                }
            query = " OR ".join(topics[:3])

        yt = _yt()
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        resp = yt.search().list(
            part="snippet",
            q=query,
            type="video",
            order="date",
            maxResults=min(max_results, 50),
            publishedAfter=today.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ).execute()

        with sqlite3.connect(_db()) as conn:
            seen_ids = {
                r[0] for r in conn.execute("SELECT video_id FROM yt_seen_videos").fetchall()
            }

        videos = []
        for item in resp.get("items", []):
            vid_id = item.get("id", {}).get("videoId", "")
            if not vid_id or vid_id in seen_ids:
                continue
            s = item.get("snippet", {})
            videos.append({
                "id":           vid_id,
                "title":        s.get("title", ""),
                "channel":      s.get("channelTitle", ""),
                "published_at": s.get("publishedAt", ""),
                "url":          f"https://youtu.be/{vid_id}",
            })

        if not videos:
            return {
                "success": True, "videos": [],
                "text": f"No new YouTube videos today for: _{query}_",
            }

        lines = [f"🎬 *New Videos ({len(videos)}) — {query}*\n"]
        for v in videos:
            lines.append(f"• [{v['title']}]({v['url']}) — _{v['channel']}_")
        return {"success": True, "videos": videos, "text": "\n".join(lines)}

    except Exception as e:
        logger.error(f"search_new_content: {e}")
        return {"success": False, "error": str(e), "text": f"❌ {e}"}


def check_interest_alerts(bot_app=None, chat_id: int = 0) -> dict:
    """
    Check for new videos across all saved interest topics.
    Sends a Telegram notification if bot_app/chat_id are set.
    Called periodically by the APScheduler job.
    """
    try:
        _ensure_tables()
        profile = get_taste_profile()
        topics  = profile.get("topics", [])

        if not topics:
            return {"success": False, "text": "No taste profile. Run analyze_taste() first."}

        all_videos: list = []
        seen_in_run: set = set()

        for topic in topics[:5]:
            res = search_new_content(query=topic, max_results=5)
            for v in res.get("videos", []):
                if v["id"] not in seen_in_run:
                    seen_in_run.add(v["id"])
                    all_videos.append(v)

        if not all_videos:
            return {"success": True, "text": "No new YouTube content matching your interests today."}

        # Persist as seen so they won't re-appear in future alerts
        with sqlite3.connect(_db()) as conn:
            for v in all_videos:
                conn.execute(
                    "INSERT OR IGNORE INTO yt_seen_videos (video_id, title, channel) VALUES (?,?,?)",
                    (v["id"], v["title"], v["channel"]),
                )
            conn.commit()

        lines = ["📺 *New content matching your interests!*\n"]
        for v in all_videos[:10]:
            lines.append(f"• [{v['title']}]({v['url']}) — _{v['channel']}_")
        text = "\n".join(lines)

        app = bot_app or _bot_app
        cid = chat_id or _chat_id
        if app and cid:
            async def _send():
                await app.bot.send_message(
                    cid, text,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(_send())
                else:
                    loop.run_until_complete(_send())
            except Exception as ex:
                logger.warning(f"check_interest_alerts send failed: {ex}")

        return {"success": True, "videos": all_videos, "text": text}

    except Exception as e:
        logger.error(f"check_interest_alerts: {e}")
        return {"success": False, "error": str(e), "text": f"❌ {e}"}


# ─── Scheduler registration (called from main.py post_init) ──────────────────

def register_yt_alerts(bot_app, chat_id: int, scheduler):
    """Register the periodic interest-alert check with an existing APScheduler."""
    global _bot_app, _chat_id, _scheduler
    _bot_app   = bot_app
    _chat_id   = chat_id
    _scheduler = scheduler

    from config import YOUTUBE_ALERTS_ENABLED, YOUTUBE_ALERTS_INTERVAL_HOURS
    if not YOUTUBE_ALERTS_ENABLED:
        return

    try:
        from apscheduler.triggers.interval import IntervalTrigger
        hours = YOUTUBE_ALERTS_INTERVAL_HOURS
        scheduler.add_job(
            lambda: check_interest_alerts(bot_app, chat_id),
            trigger=IntervalTrigger(hours=hours),
            id="yt_interest_alerts",
            replace_existing=True,
        )
        logger.info(f"YouTube interest alerts registered (every {hours}h)")
    except Exception as e:
        logger.warning(f"Could not register YouTube alerts: {e}")


# ─── Agent-callable wrappers ──────────────────────────────────────────────────

def enable_interest_alerts(interval_hours: int = 24) -> dict:
    """Enable YouTube interest alerts (persists config and registers job live)."""
    try:
        from modules.config_manager import set_config
        set_config("YOUTUBE_ALERTS_ENABLED", "true")
        set_config("YOUTUBE_ALERTS_INTERVAL_HOURS", str(interval_hours))
    except Exception:
        pass

    # If the scheduler is already running, add/replace the job immediately
    if _scheduler and _bot_app and _chat_id:
        try:
            from apscheduler.triggers.interval import IntervalTrigger
            _scheduler.add_job(
                lambda: check_interest_alerts(_bot_app, _chat_id),
                trigger=IntervalTrigger(hours=interval_hours),
                id="yt_interest_alerts",
                replace_existing=True,
            )
            return {
                "success": True,
                "text": f"✅ YouTube interest alerts enabled — checking every {interval_hours}h.",
            }
        except Exception as e:
            logger.warning(f"enable_interest_alerts live register: {e}")

    return {
        "success": True,
        "text": (
            f"✅ YouTube interest alerts enabled (every {interval_hours}h).\n"
            "Restart GhostDesk to activate the alert schedule."
        ),
    }


def disable_interest_alerts() -> dict:
    """Disable YouTube interest alerts."""
    try:
        from modules.config_manager import set_config
        set_config("YOUTUBE_ALERTS_ENABLED", "false")
    except Exception:
        pass

    if _scheduler:
        try:
            if _scheduler.get_job("yt_interest_alerts"):
                _scheduler.remove_job("yt_interest_alerts")
        except Exception:
            pass

    return {"success": True, "text": "✅ YouTube interest alerts disabled."}
