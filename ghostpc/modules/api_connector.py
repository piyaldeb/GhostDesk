"""
GhostPC Universal API Connector
Call any HTTP API with any method, headers, and auth.
API credentials are retrieved from SQLite memory automatically.
"""

import logging
from typing import Any, Optional

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

# Default timeout for all requests
DEFAULT_TIMEOUT = 30


def call_api(
    method: str,
    url: str,
    headers: Optional[dict] = None,
    body: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """
    Universal HTTP API caller.
    method: GET, POST, PUT, DELETE, PATCH
    Returns response as dict or string for AI to process.
    """
    try:
        resp = requests.request(
            method=method.upper(),
            url=url,
            headers=headers or {},
            json=body,
            params=params,
            timeout=timeout,
        )

        try:
            data = resp.json()
        except Exception:
            data = resp.text

        status = resp.status_code
        success = 200 <= status < 300

        result = {
            "success": success,
            "status_code": status,
            "data": data,
        }

        if not success:
            result["error"] = f"HTTP {status}: {str(data)[:500]}"
            result["text"] = f"❌ API call failed: HTTP {status}\n{str(data)[:500]}"
        else:
            # Format a readable summary
            if isinstance(data, dict):
                result["text"] = f"✅ API response ({status}):\n{_summarize_json(data)}"
            elif isinstance(data, list):
                result["text"] = f"✅ API returned {len(data)} items\n{_summarize_json(data[:3])}"
            else:
                result["text"] = f"✅ API response ({status}):\n{str(data)[:1000]}"

        return result

    except RequestException as e:
        logger.error(f"API call error: {e}")
        return {"success": False, "error": str(e), "text": f"❌ Request failed: {e}"}
    except Exception as e:
        logger.error(f"API connector unexpected error: {e}")
        return {"success": False, "error": str(e)}


def call_api_with_auth(
    method: str,
    url: str,
    auth_type: str,
    auth_value: str,
    headers: Optional[dict] = None,
    body: Optional[dict] = None,
    params: Optional[dict] = None,
) -> dict:
    """
    Call an API with authentication.
    auth_type: "bearer" | "basic" | "apikey" | "apikey_param"
    auth_value: the token/key string
    """
    headers = dict(headers or {})

    if auth_type == "bearer":
        headers["Authorization"] = f"Bearer {auth_value}"
    elif auth_type == "basic":
        import base64
        encoded = base64.b64encode(auth_value.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
    elif auth_type == "apikey":
        headers["x-api-key"] = auth_value
    elif auth_type == "apikey_param":
        params = dict(params or {})
        params["api_key"] = auth_value

    return call_api(method, url, headers=headers, body=body, params=params)


def call_saved_api(
    service_name: str,
    method: str,
    url: str,
    body: Optional[dict] = None,
    params: Optional[dict] = None,
    extra_headers: Optional[dict] = None,
) -> dict:
    """
    Call an API using a credential stored in GhostPC's memory.
    The agent uses this when the user says "use my GitHub token" etc.
    """
    try:
        from core.memory import get_api_credential
        cred = get_api_credential(service_name)
        if not cred:
            return {
                "success": False,
                "error": f"No credential found for service: {service_name}. "
                         f"Tell me: 'remember my {service_name} token is YOUR_TOKEN'"
            }

        return call_api_with_auth(
            method=method,
            url=url,
            auth_type=cred["credential_type"],
            auth_value=cred["credential_value"],
            headers=extra_headers,
            body=body,
            params=params,
        )
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Common API Helpers ──────────────────────────────────────────────────────

def get_weather(location: str, api_key: Optional[str] = None) -> dict:
    """
    Get weather for a location using OpenWeatherMap.
    Uses saved 'openweathermap' credential if api_key not provided.
    """
    if not api_key:
        try:
            from core.memory import get_api_credential
            cred = get_api_credential("openweathermap")
            api_key = cred["credential_value"] if cred else None
        except Exception:
            pass

    if not api_key:
        return {
            "success": False,
            "error": "No OpenWeatherMap API key. Say: 'remember my openweathermap key is YOUR_KEY'"
        }

    result = call_api(
        "GET",
        "https://api.openweathermap.org/data/2.5/weather",
        params={"q": location, "appid": api_key, "units": "metric"}
    )

    if result.get("success") and isinstance(result.get("data"), dict):
        data = result["data"]
        temp = data.get("main", {}).get("temp", "?")
        feels = data.get("main", {}).get("feels_like", "?")
        desc = data.get("weather", [{}])[0].get("description", "?")
        wind = data.get("wind", {}).get("speed", "?")
        city = data.get("name", location)

        result["text"] = (
            f"🌤 Weather in {city}:\n"
            f"Temperature: {temp}°C (feels like {feels}°C)\n"
            f"Condition: {desc.title()}\n"
            f"Wind: {wind} m/s"
        )

    return result


def search_web_serpapi(query: str, api_key: Optional[str] = None, num_results: int = 5) -> dict:
    """Search web via SerpAPI (requires API key stored as 'serpapi')."""
    if not api_key:
        try:
            from core.memory import get_api_credential
            cred = get_api_credential("serpapi")
            api_key = cred["credential_value"] if cred else None
        except Exception:
            pass

    if not api_key:
        return {"success": False, "error": "No SerpAPI key found."}

    result = call_api(
        "GET",
        "https://serpapi.com/search",
        params={"q": query, "api_key": api_key, "num": num_results}
    )

    if result.get("success") and isinstance(result.get("data"), dict):
        organic = result["data"].get("organic_results", [])
        lines = [f"🔍 Search results for: {query}\n"]
        for r in organic[:num_results]:
            lines.append(f"• {r.get('title', '')}\n  {r.get('link', '')}\n  {r.get('snippet', '')[:100]}")
        result["text"] = "\n".join(lines)

    return result


# ─── Service Integration Catalog ─────────────────────────────────────────────
# Each entry defines: auth type, base URL, setup steps, known actions, examples.
# The agent uses connect_service() to guide users and run_service_action() to call them.

SERVICE_CATALOG: dict = {
    "spotify": {
        "name": "Spotify",
        "auth_type": "bearer",
        "base_url": "https://api.spotify.com/v1",
        "setup_url": "https://developer.spotify.com/dashboard",
        "setup_steps": [
            "1. Go to https://developer.spotify.com/dashboard and log in",
            "2. Create an App → copy the Access Token (or use OAuth flow)",
            "3. Tell me: `my Spotify token is YOUR_ACCESS_TOKEN`",
        ],
        "actions": {
            "current_track": ("GET", "/me/player/currently-playing"),
            "pause":         ("PUT", "/me/player/pause"),
            "play":          ("PUT", "/me/player/play"),
            "next":          ("POST", "/me/player/next"),
            "previous":      ("POST", "/me/player/previous"),
            "search":        ("GET", "/search"),
            "queue":         ("GET", "/me/player/queue"),
        },
        "examples": [
            "what's playing on Spotify",
            "pause Spotify",
            "next song on Spotify",
            "search Spotify for Coldplay",
        ],
    },
    "github": {
        "name": "GitHub",
        "auth_type": "bearer",
        "base_url": "https://api.github.com",
        "setup_url": "https://github.com/settings/tokens",
        "setup_steps": [
            "1. Go to https://github.com/settings/tokens",
            "2. Generate new token (classic) — select scopes: repo, user, notifications",
            "3. Copy the token (starts with ghp_...)",
            "4. Tell me: `my GitHub token is ghp_XXXXXXXX`",
        ],
        "actions": {
            "repos":         ("GET", "/user/repos"),
            "notifications": ("GET", "/notifications"),
            "user":          ("GET", "/user"),
        },
        "examples": [
            "show my GitHub repos",
            "show my GitHub notifications",
            "my GitHub profile",
        ],
    },
    "notion": {
        "name": "Notion",
        "auth_type": "bearer",
        "base_url": "https://api.notion.com/v1",
        "setup_url": "https://www.notion.so/my-integrations",
        "extra_headers": {"Notion-Version": "2022-06-28"},
        "setup_steps": [
            "1. Go to https://www.notion.so/my-integrations",
            "2. Click '+ New integration' → name it GhostDesk → Submit",
            "3. Copy the Internal Integration Token (secret_...)",
            "4. Share your Notion pages with the integration (page → Share → invite GhostDesk)",
            "5. Tell me: `my Notion token is secret_XXXXXXXX`",
        ],
        "actions": {
            "search":      ("POST", "/search"),
            "page":        ("GET", "/pages/{page_id}"),
            "create_page": ("POST", "/pages"),
        },
        "examples": [
            "search Notion for meeting notes",
            "create a Notion page: My Note",
        ],
    },
    "openweathermap": {
        "name": "OpenWeatherMap",
        "auth_type": "apikey_param",
        "base_url": "https://api.openweathermap.org/data/2.5",
        "setup_url": "https://home.openweathermap.org/api_keys",
        "setup_steps": [
            "1. Sign up at https://openweathermap.org/api",
            "2. Go to https://home.openweathermap.org/api_keys → copy your API key",
            "3. Tell me: `my OpenWeatherMap key is XXXXXXXX`",
        ],
        "actions": {
            "weather":  ("GET", "/weather"),
            "forecast": ("GET", "/forecast"),
        },
        "examples": [
            "what's the weather in Dhaka",
            "weather forecast for London",
        ],
    },
    "discord": {
        "name": "Discord",
        "auth_type": "webhook",
        "base_url": "",
        "setup_url": "https://discord.com/developers/applications",
        "setup_steps": [
            "1. Open Discord → go to your server → Edit Channel → Integrations → Webhooks",
            "2. Click 'New Webhook', name it GhostDesk, copy the Webhook URL",
            "3. Tell me: `my Discord webhook is https://discord.com/api/webhooks/...`",
        ],
        "actions": {
            "send": ("POST", "{webhook_url}"),
        },
        "examples": [
            "send Discord message: server is down!",
            "post to Discord: meeting in 5 minutes",
        ],
    },
    "trello": {
        "name": "Trello",
        "auth_type": "apikey_param",
        "base_url": "https://api.trello.com/1",
        "setup_url": "https://trello.com/app-key",
        "setup_steps": [
            "1. Go to https://trello.com/app-key — copy your API Key",
            "2. Click the 'Token' link → allow access → copy the token",
            "3. Tell me: `my Trello key is XXXX` then `my Trello token is YYYY`",
        ],
        "actions": {
            "boards":      ("GET", "/members/me/boards"),
            "create_card": ("POST", "/cards"),
        },
        "examples": [
            "show my Trello boards",
            "create Trello card: Fix bug",
        ],
    },
    "slack": {
        "name": "Slack",
        "auth_type": "bearer",
        "base_url": "https://slack.com/api",
        "setup_url": "https://api.slack.com/apps",
        "setup_steps": [
            "1. Go to https://api.slack.com/apps → Create New App → From scratch",
            "2. Add OAuth scopes: chat:write, channels:read → Install to workspace",
            "3. Copy Bot User OAuth Token (xoxb-...)",
            "4. Tell me: `my Slack token is xoxb-XXXXXXXX`",
        ],
        "actions": {
            "post":     ("POST", "/chat.postMessage"),
            "channels": ("GET", "/conversations.list"),
        },
        "examples": [
            "send Slack message to #general: server is up",
            "show my Slack channels",
        ],
    },
    "youtube": {
        "name": "YouTube",
        "auth_type": "apikey_param",
        "base_url": "https://www.googleapis.com/youtube/v3",
        "setup_url": "https://console.cloud.google.com/apis/credentials",
        "setup_steps": [
            "1. Go to https://console.cloud.google.com/ → create a project",
            "2. Enable 'YouTube Data API v3'",
            "3. Create credentials → API Key → copy it",
            "4. Tell me: `my YouTube API key is AIzaXXXXXX`",
        ],
        "actions": {
            "search":        ("GET", "/search"),
            "video_details": ("GET", "/videos"),
        },
        "examples": [
            "search YouTube for Python tutorials",
            "get info about YouTube video dQw4w9WgXcQ",
        ],
    },
    "telegram_bot": {
        "name": "Telegram Bot API",
        "auth_type": "bearer",
        "base_url": "https://api.telegram.org",
        "setup_url": "https://t.me/BotFather",
        "setup_steps": [
            "1. Open Telegram → message @BotFather → /newbot",
            "2. Copy the bot token",
            "3. Tell me: `my Telegram bot token is 123456:XXXXXXXX`",
        ],
        "actions": {
            "send_message": ("POST", "/bot{token}/sendMessage"),
            "get_updates":  ("GET", "/bot{token}/getUpdates"),
        },
        "examples": [
            "send Telegram bot message to chat 123: hello",
        ],
    },
}


def list_services() -> dict:
    """List all supported service integrations with examples."""
    lines = ["🔌 *Supported Service Integrations:*\n"]
    for key, svc in SERVICE_CATALOG.items():
        ex = svc.get("examples", [])
        example = f" — e.g. `{ex[0]}`" if ex else ""
        lines.append(f"• *{svc['name']}* (`{key}`){example}")
    lines.append(
        "\nSay `connect Spotify` or `connect GitHub` to get step-by-step setup instructions.\n"
        "Once connected, just ask naturally: `what's playing on Spotify?`"
    )
    return {"success": True, "text": "\n".join(lines)}


def connect_service(service_name: str) -> dict:
    """
    Return step-by-step instructions for connecting a service's API.
    Checks if already connected and confirms, otherwise gives full setup guide.
    """
    key = service_name.lower().strip().replace(" ", "")
    svc = SERVICE_CATALOG.get(key)

    # Fuzzy match
    if not svc:
        for k, s in SERVICE_CATALOG.items():
            if k in key or key in k or key in s["name"].lower():
                svc = s
                key = k
                break

    if not svc:
        supported = ", ".join(SERVICE_CATALOG.keys())
        return {
            "success": False,
            "text": (
                f"❌ Service '{service_name}' not in catalog.\n\n"
                f"Supported: {supported}\n\n"
                f"For any other service use: `call api GET https://api.example.com/endpoint`"
            ),
        }

    # Check if already connected
    try:
        from core.memory import get_api_credential
        cred = get_api_credential(key)
        if cred:
            examples = "\n".join(f"  • `{e}`" for e in svc.get("examples", []))
            return {
                "success": True,
                "text": (
                    f"✅ *{svc['name']}* is already connected.\n\n"
                    f"*Things you can ask:*\n{examples}\n\n"
                    f"To reconnect with a new token say: `my {svc['name']} token is NEW_TOKEN`"
                ),
            }
    except Exception:
        pass

    steps = "\n".join(svc["setup_steps"])
    examples = "\n".join(f"  • `{e}`" for e in svc.get("examples", []))
    return {
        "success": True,
        "text": (
            f"🔌 *Connecting {svc['name']}*\n\n"
            f"*Setup steps:*\n{steps}\n\n"
            f"*What you can do after connecting:*\n{examples}"
        ),
        "service": key,
    }


def run_service_action(service_name: str, action: str, params: Optional[dict] = None) -> dict:
    """
    Execute a known action for a connected service using stored credentials.
    Falls back to connect_service() instructions if not yet connected.
    """
    from core.memory import get_api_credential

    key = service_name.lower().strip().replace(" ", "")
    svc = SERVICE_CATALOG.get(key)
    if not svc:
        # Try fuzzy
        for k, s in SERVICE_CATALOG.items():
            if k in key or key in k or key in s["name"].lower():
                svc = s
                key = k
                break
    if not svc:
        return connect_service(service_name)

    cred = get_api_credential(key)
    if not cred:
        return {
            "success": False,
            "text": (
                f"❌ {svc['name']} is not connected yet.\n\n"
                f"Say `connect {svc['name']}` to get setup instructions."
            ),
        }

    actions = svc.get("actions", {})
    if action not in actions:
        avail = ", ".join(actions.keys())
        return {
            "success": False,
            "error": f"Unknown action '{action}' for {svc['name']}. Available: {avail}",
        }

    method, path = actions[action]
    params = params or {}

    # Fill path params like {page_id}, {webhook_url}
    try:
        path = path.format(**params, **{"webhook_url": cred["credential_value"]})
    except KeyError:
        pass

    extra_headers = dict(svc.get("extra_headers", {}))

    # Webhook services: POST directly to stored URL
    if svc["auth_type"] == "webhook":
        return call_api(method, cred["credential_value"], body=params.get("body"))

    url = svc["base_url"] + path
    query_params = {k: v for k, v in params.items() if k not in ("body",)}

    return call_api_with_auth(
        method=method,
        url=url,
        auth_type=cred["credential_type"],
        auth_value=cred["credential_value"],
        headers=extra_headers or None,
        body=params.get("body"),
        params=query_params if method == "GET" else None,
    )


def _summarize_json(data: Any, max_keys: int = 8, indent: int = 0) -> str:
    """Create a readable summary of a JSON response."""
    if isinstance(data, dict):
        lines = []
        for i, (k, v) in enumerate(data.items()):
            if i >= max_keys:
                lines.append(f"  ... (+{len(data) - max_keys} more)")
                break
            if isinstance(v, (dict, list)):
                lines.append(f"  {k}: [{type(v).__name__}]")
            else:
                lines.append(f"  {k}: {str(v)[:100]}")
        return "\n".join(lines)
    elif isinstance(data, list):
        if not data:
            return "  (empty list)"
        return f"  [{len(data)} items, first: {_summarize_json(data[0])}]"
    else:
        return str(data)[:200]
