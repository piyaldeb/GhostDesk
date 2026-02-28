"""
GhostPC PC Control Module
Screenshots, app management, system stats, keyboard/mouse control.
"""

import logging
import os
import subprocess
import sys
from config import IS_WINDOWS, IS_MAC
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _temp_dir() -> Path:
    from config import TEMP_DIR
    return TEMP_DIR


# ─── Screenshot ──────────────────────────────────────────────────────────────

def screenshot(save_path: Optional[str] = None) -> dict:
    """Capture the full screen and save to a temp file."""
    try:
        import pyautogui
        from PIL import Image

        img = pyautogui.screenshot()

        if not save_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = str(_temp_dir() / f"screenshot_{ts}.png")

        img.save(save_path)
        logger.info(f"Screenshot saved: {save_path}")
        return {"success": True, "file_path": save_path, "caption": "Screenshot"}

    except Exception as e:
        logger.error(f"Screenshot error: {e}")
        return {"success": False, "error": str(e)}


# ─── App Management ──────────────────────────────────────────────────────────

def get_open_apps() -> dict:
    """Return list of open application window titles."""
    try:
        import pygetwindow as gw
        windows = gw.getAllTitles()
        # Filter empty titles
        apps = [w for w in windows if w.strip()]
        text = "Open applications:\n" + "\n".join(f"• {a}" for a in apps)
        return {"success": True, "apps": apps, "text": text}
    except Exception as e:
        logger.error(f"get_open_apps error: {e}")
        return {"success": False, "error": str(e)}


def open_app(name: str) -> dict:
    """Open an application by name (Windows & Mac)."""
    try:
        key = name.lower()

        if sys.platform == "win32":
            shortcuts = {
                "chrome": "chrome", "google chrome": "chrome",
                "firefox": "firefox", "edge": "msedge",
                "notepad": "notepad", "calculator": "calc",
                "excel": "excel", "word": "winword",
                "powerpoint": "powerpnt", "outlook": "outlook",
                "explorer": "explorer", "cmd": "cmd",
                "powershell": "powershell", "paint": "mspaint",
                "vlc": "vlc", "spotify": "spotify",
                "vscode": "code", "vs code": "code",
                "task manager": "taskmgr",
            }
            cmd = shortcuts.get(key, name)
            try:
                os.startfile(cmd)
            except Exception:
                subprocess.Popen(cmd, shell=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            # Mac: use `open -a "App Name"`
            mac_shortcuts = {
                "chrome": "Google Chrome", "google chrome": "Google Chrome",
                "firefox": "Firefox", "safari": "Safari",
                "calculator": "Calculator", "terminal": "Terminal",
                "finder": "Finder", "vscode": "Visual Studio Code",
                "vs code": "Visual Studio Code", "excel": "Microsoft Excel",
                "word": "Microsoft Word", "spotify": "Spotify", "vlc": "VLC",
            }
            app_name = mac_shortcuts.get(key, name)
            subprocess.Popen(["open", "-a", app_name],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        return {"success": True, "text": f"✅ Opened: {name}"}

    except Exception as e:
        logger.error(f"open_app error: {e}")
        return {"success": False, "error": str(e)}


def close_app(name: str) -> dict:
    """Close an application window by its title (partial match)."""
    try:
        import pygetwindow as gw
        windows = gw.getWindowsWithTitle(name)
        if not windows:
            # Try partial match
            all_wins = gw.getAllWindows()
            windows = [w for w in all_wins if name.lower() in w.title.lower()]

        if not windows:
            return {"success": False, "error": f"No window found matching: {name}"}

        closed = []
        for w in windows:
            try:
                w.close()
                closed.append(w.title)
            except Exception as e:
                logger.warning(f"Could not close {w.title}: {e}")

        return {"success": True, "text": f"✅ Closed: {', '.join(closed)}"}

    except Exception as e:
        logger.error(f"close_app error: {e}")
        return {"success": False, "error": str(e)}


# ─── System Stats ─────────────────────────────────────────────────────────────

def get_system_stats() -> dict:
    """Return CPU, RAM, disk, and network stats via psutil."""
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        import sys
        disk_root = "C:\\" if sys.platform == "win32" else "/"
        disk = psutil.disk_usage(disk_root)

        # Top 5 CPU processes
        procs = sorted(
            psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
            key=lambda p: p.info.get("cpu_percent") or 0,
            reverse=True
        )[:5]

        proc_lines = []
        for p in procs:
            try:
                proc_lines.append(
                    f"  {p.info['name'][:20]:<20} CPU:{p.info.get('cpu_percent', 0):.1f}%  "
                    f"RAM:{p.info.get('memory_percent', 0):.1f}%"
                )
            except Exception:
                pass

        text = (
            f"🖥️ System Stats\n"
            f"──────────────────\n"
            f"CPU:    {cpu:.1f}%\n"
            f"RAM:    {ram.percent:.1f}% ({ram.used // 1024**3}GB / {ram.total // 1024**3}GB)\n"
            f"Disk:   {disk.percent:.1f}% used "
            f"({disk.free // 1024**3}GB free / {disk.total // 1024**3}GB)\n\n"
            f"Top Processes:\n" + "\n".join(proc_lines)
        )

        return {
            "success": True,
            "cpu_percent": cpu,
            "ram_percent": ram.percent,
            "disk_percent": disk.percent,
            "text": text,
        }

    except Exception as e:
        logger.error(f"get_system_stats error: {e}")
        return {"success": False, "error": str(e)}


# ─── Power / Lock ─────────────────────────────────────────────────────────────

def restart_pc(delay_minutes: int = 1, confirm: bool = False) -> dict:
    """Schedule a system restart (Windows & Mac)."""
    try:
        if not confirm:
            return {"success": False, "error": "Restart requires explicit confirmation (confirm=True)"}
        import sys
        delay_seconds = delay_minutes * 60
        if sys.platform == "win32":
            subprocess.run(f"shutdown /r /t {delay_seconds}", shell=True, check=True)
        else:
            subprocess.run(["sudo", "shutdown", "-r", f"+{delay_minutes}"], check=True)
        return {"success": True, "text": f"✅ PC will restart in {delay_minutes} minute(s)."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def shutdown_pc(delay_minutes: int = 1, confirm: bool = False) -> dict:
    """Schedule a system shutdown (Windows & Mac)."""
    try:
        if not confirm:
            return {"success": False, "error": "Shutdown requires explicit confirmation (confirm=True)"}
        import sys
        delay_seconds = delay_minutes * 60
        if sys.platform == "win32":
            subprocess.run(f"shutdown /s /t {delay_seconds}", shell=True, check=True)
        else:
            subprocess.run(["sudo", "shutdown", "-h", f"+{delay_minutes}"], check=True)
        return {"success": True, "text": f"✅ PC will shut down in {delay_minutes} minute(s)."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def lock_pc() -> dict:
    """Lock the workstation (Windows & Mac)."""
    try:
        import sys
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.LockWorkStation()
        elif sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to keystroke "q" using {command down, control down}'],
                check=True
            )
        else:
            subprocess.run(["loginctl", "lock-session"], check=True)
        return {"success": True, "text": "✅ PC locked."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def abort_shutdown() -> dict:
    """Abort a pending shutdown (Windows only)."""
    try:
        import sys
        if sys.platform == "win32":
            subprocess.run("shutdown /a", shell=True, check=True)
        else:
            subprocess.run(["sudo", "shutdown", "-c"], check=True)
        return {"success": True, "text": "✅ Shutdown aborted."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Keyboard / Mouse ────────────────────────────────────────────────────────

def type_text(text: str) -> dict:
    """Type text at the current cursor position using PyAutoGUI."""
    try:
        import pyautogui
        import time
        time.sleep(0.5)  # Brief pause so focus is set
        pyautogui.typewrite(text, interval=0.03)
        return {"success": True, "text": f"✅ Typed: {text[:50]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def press_key(key: str) -> dict:
    """Press a keyboard key or key combination (e.g. 'ctrl+c', 'enter', 'f5')."""
    try:
        import pyautogui
        if "+" in key:
            keys = [k.strip() for k in key.split("+")]
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(key)
        return {"success": True, "text": f"✅ Key pressed: {key}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def click(x: int, y: int, button: str = "left") -> dict:
    """Click at screen coordinates."""
    try:
        import pyautogui
        pyautogui.click(x, y, button=button)
        return {"success": True, "text": f"✅ Clicked at ({x}, {y})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def move_mouse(x: int, y: int) -> dict:
    """Move mouse to coordinates."""
    try:
        import pyautogui
        pyautogui.moveTo(x, y, duration=0.3)
        return {"success": True, "text": f"✅ Mouse moved to ({x}, {y})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── App Installer ───────────────────────────────────────────────────────────

def search_app(name: str) -> dict:
    """
    Search for an app in winget (Windows) or brew (Mac) and return info
    before installing — so the user can confirm what will be installed.
    """
    try:
        if IS_WINDOWS:
            result = subprocess.run(
                ["winget", "search", "--name", name, "--exact", "--accept-source-agreements"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0 or not result.stdout.strip():
                # Fallback: non-exact search, first 5 results
                result = subprocess.run(
                    ["winget", "search", name, "--accept-source-agreements"],
                    capture_output=True, text=True, timeout=30,
                )
            lines = [l for l in result.stdout.splitlines() if l.strip() and "---" not in l]
            if lines:
                return {"success": True, "text": "\n".join(lines[:8]), "raw": result.stdout}
            return {"success": False, "error": f"No results for '{name}' in winget."}
        elif IS_MAC:
            result = subprocess.run(
                ["brew", "search", name],
                capture_output=True, text=True, timeout=30,
            )
            return {"success": True, "text": result.stdout[:600]}
        else:
            result = subprocess.run(
                ["apt-cache", "search", name],
                capture_output=True, text=True, timeout=30,
            )
            return {"success": True, "text": result.stdout[:600]}
    except FileNotFoundError as e:
        return {"success": False, "error": f"Package manager not found: {e}. On Windows install winget (built into Windows 11)."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def install_app(name: str, confirm: bool = False) -> dict:
    """
    Install an application silently using the system package manager.
    On Windows uses winget; on Mac uses brew; on Linux uses apt.
    Always set confirm=True in the action plan so the user approves first.
    """
    if not confirm:
        # Return info about what would be installed so user can confirm
        search = search_app(name)
        info = search.get("text", "")
        return {
            "success": False,
            "confirm": True,
            "text": (
                f"📦 About to install: *{name}*\n\n"
                + (f"Found in package manager:\n```\n{info[:400]}\n```\n\n" if info else "")
                + "Reply ✅ Yes to confirm installation."
            ),
        }

    try:
        if IS_WINDOWS:
            result = subprocess.run(
                ["winget", "install", "--name", name,
                 "--silent", "--accept-package-agreements", "--accept-source-agreements"],
                capture_output=True, text=True, timeout=300,
            )
        elif IS_MAC:
            result = subprocess.run(
                ["brew", "install", name],
                capture_output=True, text=True, timeout=300,
            )
        else:
            result = subprocess.run(
                ["apt-get", "install", "-y", name],
                capture_output=True, text=True, timeout=300,
            )

        if result.returncode == 0:
            return {"success": True, "text": f"✅ {name} installed successfully."}
        # winget exit code 0x8A150011 = already installed
        if "already installed" in result.stdout.lower() or result.returncode == -1978335215:
            return {"success": True, "text": f"✅ {name} is already installed."}
        return {
            "success": False,
            "error": f"Install failed (code {result.returncode}):\n{result.stdout[-300:]}",
        }
    except FileNotFoundError as e:
        return {"success": False, "error": f"Package manager not found: {e}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Installation timed out (5 min). It may still be running in the background."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Volume / Brightness ─────────────────────────────────────────────────────

def set_volume(level: int) -> dict:
    """Set system volume (0–100). Windows only."""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        import math

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        # Convert 0-100 to scalar
        scalar = max(0.0, min(1.0, level / 100.0))
        volume.SetMasterVolumeLevelScalar(scalar, None)
        return {"success": True, "text": f"✅ Volume set to {level}%"}
    except ImportError:
        # Fallback via nircmd if available
        try:
            vol = int(65535 * level / 100)
            subprocess.run(f"nircmd.exe setsysvolume {vol}", shell=True)
            return {"success": True, "text": f"✅ Volume set to {level}%"}
        except Exception as e:
            return {"success": False, "error": f"pycaw not installed and nircmd not found: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Wake-on-LAN ──────────────────────────────────────────────────────────────

def wake_on_lan(mac_address: str, broadcast: str = "255.255.255.255", port: int = 9) -> dict:
    """
    Send a Wake-on-LAN magic packet to wake another PC on the network.
    mac_address: target PC's MAC address, e.g. 'AA:BB:CC:DD:EE:FF'
    broadcast: broadcast address (default works for most home networks)

    NOTE: To wake THIS PC when it's off, you need an always-on device
    (router, Raspberry Pi, VPS) to send the packet. GhostDesk must be running
    to receive commands. See 'remote access guide' for setup options.
    """
    import socket
    import re

    mac = re.sub(r'[^0-9a-fA-F]', '', mac_address)
    if len(mac) != 12:
        return {"success": False, "error": f"Invalid MAC address: '{mac_address}'. Use format AA:BB:CC:DD:EE:FF"}

    try:
        magic = bytes.fromhex('FF' * 6 + mac * 16)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(magic, (broadcast, port))
        return {
            "success": True,
            "text": f"✅ Wake-on-LAN packet sent to {mac_address}. The target PC should power on in ~10 seconds if WoL is enabled in its BIOS."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def enable_remote_desktop() -> dict:
    """
    Enable Windows Remote Desktop (RDP) so you can connect via any RDP client.
    Also shows your local IP for connection. Windows only.
    """
    if not IS_WINDOWS:
        return {"success": False, "error": "Remote Desktop is Windows-only. On Mac/Linux use SSH or VNC."}

    try:
        import socket

        # Enable RDP via registry
        subprocess.run(
            ['reg', 'add', r'HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server',
             '/v', 'fDenyTSConnections', '/t', 'REG_DWORD', '/d', '0', '/f'],
            capture_output=True, check=True,
        )
        # Enable firewall rule
        subprocess.run(
            ['netsh', 'advfirewall', 'firewall', 'set', 'rule',
             'group="remote desktop"', 'new', 'enable=Yes'],
            capture_output=True,
        )

        local_ip = socket.gethostbyname(socket.gethostname())
        return {
            "success": True,
            "text": (
                f"✅ Remote Desktop (RDP) enabled!\n\n"
                f"*Your local IP:* `{local_ip}`\n"
                f"*Port:* 3389\n\n"
                f"*To connect:*\n"
                f"• Windows: Start → Remote Desktop Connection → enter `{local_ip}`\n"
                f"• Mac: Microsoft Remote Desktop app → `{local_ip}`\n"
                f"• Phone: Microsoft RD app → `{local_ip}`\n\n"
                f"⚠️ For access from outside your home network:\n"
                f"  1. Set up port forwarding: router → port 3389 → `{local_ip}`\n"
                f"  2. Or use Cloudflare Tunnel / Tailscale (more secure, recommended)"
            ),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def disable_remote_desktop() -> dict:
    """Disable Windows Remote Desktop (RDP)."""
    if not IS_WINDOWS:
        return {"success": False, "error": "Windows only."}
    try:
        subprocess.run(
            ['reg', 'add', r'HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server',
             '/v', 'fDenyTSConnections', '/t', 'REG_DWORD', '/d', '1', '/f'],
            capture_output=True, check=True,
        )
        return {"success": True, "text": "✅ Remote Desktop disabled."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_remote_access_guide() -> dict:
    """Return a guide on how to remotely wake and access this PC."""
    import socket
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "your-local-ip"

    return {
        "success": True,
        "text": (
            "🖥️ *Remote PC Access Guide*\n\n"

            "─── Option 1: Already ON (easiest) ───\n"
            "GhostDesk is running → you already have full control via Telegram.\n"
            "For visual desktop:\n"
            "• Say `enable remote desktop` → connect from phone/laptop\n\n"

            "─── Option 2: PC is SLEEPING ───\n"
            "Wake-on-LAN works from another device on the same network:\n"
            "• Find your MAC: say `show my network info`\n"
            "• Say `wake PC at AA:BB:CC:DD:EE:FF` from another GhostDesk device\n\n"

            "─── Option 3: PC is OFF / WoL from internet ───\n"
            "Requires an always-on relay. Easiest options:\n\n"
            "*A) Tailscale (free, recommended):*\n"
            "  1. `install Tailscale` on this PC + your phone\n"
            "  2. They get private IPs that work from anywhere\n"
            "  3. Enable WoL in BIOS (look for 'Wake on LAN' in Power settings)\n"
            "  4. From phone: send magic packet to this PC's Tailscale IP\n\n"
            "*B) Always-on VPS relay:*\n"
            "  1. Get a $3/month VPS (DigitalOcean, Vultr)\n"
            "  2. Run GhostDesk there with your Telegram bot token\n"
            "  3. VPS receives 'wake PC' → sends WoL packet via VPN to your home\n\n"
            "*C) Router WoL (if supported):*\n"
            "  Check your router's web interface for 'Wake on LAN' feature.\n\n"

            "─── Enable WoL in BIOS ───\n"
            "1. Restart PC → press Del/F2 during boot to enter BIOS\n"
            "2. Find: Power Management → Wake on LAN → Enable\n"
            "3. Save and exit\n\n"

            f"*Your current local IP:* `{local_ip}`\n"
            "Say `enable remote desktop` to turn on RDP access now."
        ),
    }
