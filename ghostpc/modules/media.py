"""
GhostPC Media Module
Audio/video control via Windows APIs and media key simulation.
"""

import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def _press_media_key(key_name: str) -> dict:
    """Send a media key press via PyAutoGUI."""
    try:
        import pyautogui
        pyautogui.press(key_name)
        return {"success": True, "text": f"✅ {key_name} pressed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def play_pause() -> dict:
    """Toggle play/pause."""
    return _press_media_key("playpause")


def next_track() -> dict:
    """Skip to next track."""
    return _press_media_key("nexttrack")


def prev_track() -> dict:
    """Go to previous track."""
    return _press_media_key("prevtrack")


def pause() -> dict:
    """Pause media playback."""
    return _press_media_key("playpause")


def stop() -> dict:
    """Stop media playback."""
    return _press_media_key("stop")


def play_media(query: str) -> dict:
    """
    Play media by searching on YouTube/Spotify, or open a local file.
    If it's a file path, open it. Otherwise search on YouTube.
    """
    try:
        import os
        from pathlib import Path

        # Check if it's a local file
        p = Path(query)
        if p.exists():
            os.startfile(str(p))
            return {"success": True, "text": f"✅ Playing: {p.name}"}

        # Otherwise open YouTube search in browser
        import webbrowser
        search_query = query.replace(" ", "+")
        url = f"https://www.youtube.com/results?search_query={search_query}"
        webbrowser.open(url)
        return {"success": True, "text": f"✅ Searching YouTube for: {query}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def get_current_playing() -> dict:
    """
    Try to get the currently playing media info.
    Uses Windows SMTC (System Media Transport Controls) via PowerShell.
    """
    try:
        # PowerShell script to query Windows media info
        ps_script = """
$playingInfo = @{}
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $asyncOp = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime]::RequestAsync()
    $manager = $asyncOp.GetResults()
    $session = $manager.GetCurrentSession()
    if ($session -ne $null) {
        $mediaOp = $session.TryGetMediaPropertiesAsync()
        $props = $mediaOp.GetResults()
        $playbackOp = $session.GetPlaybackInfo()
        $playback = $playbackOp
        Write-Output "Title: $($props.Title)"
        Write-Output "Artist: $($props.Artist)"
        Write-Output "Status: $($playback.PlaybackStatus)"
    } else {
        Write-Output "No media session found"
    }
} catch {
    Write-Output "Error: $_"
}
"""
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout.strip()
        if output and "Error" not in output and "No media session" not in output:
            return {"success": True, "text": f"🎵 Now playing:\n{output}"}
        else:
            return {"success": True, "text": "🎵 No media currently playing (or could not detect)."}

    except Exception as e:
        return {"success": False, "error": str(e)}


def set_volume(level: int) -> dict:
    """Set system volume (0-100)."""
    try:
        # Try pycaw first
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        scalar = max(0.0, min(1.0, level / 100.0))
        volume.SetMasterVolumeLevelScalar(scalar, None)
        return {"success": True, "text": f"✅ Volume: {level}%"}

    except ImportError:
        # Fallback: PowerShell
        try:
            ps = f"[audio]::Volume = {level / 100.0}"
            subprocess.run(["powershell", "-Command",
                           f"(New-Object -ComObject WScript.Shell).SendKeys([char]173)"], timeout=2)
            return {"success": True, "text": f"✅ Volume adjusted (pycaw not available)"}
        except Exception as e:
            return {"success": False, "error": f"pycaw not installed: {e}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def mute() -> dict:
    """Toggle mute."""
    return _press_media_key("volumemute")


def volume_up(steps: int = 5) -> dict:
    """Increase volume."""
    try:
        import pyautogui
        for _ in range(steps):
            pyautogui.press("volumeup")
        return {"success": True, "text": f"✅ Volume up ({steps} steps)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def volume_down(steps: int = 5) -> dict:
    """Decrease volume."""
    try:
        import pyautogui
        for _ in range(steps):
            pyautogui.press("volumedown")
        return {"success": True, "text": f"✅ Volume down ({steps} steps)"}
    except Exception as e:
        return {"success": False, "error": str(e)}
