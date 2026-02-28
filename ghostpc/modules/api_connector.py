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
