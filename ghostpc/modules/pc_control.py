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
            # Use --id if name looks like a winget package ID
            if _winget_is_id(name):
                search_cmd = ["winget", "search", "--id", name, "--exact", "--accept-source-agreements"]
            else:
                search_cmd = ["winget", "search", "--name", name, "--exact", "--accept-source-agreements"]
            result = subprocess.run(search_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0 or not result.stdout.strip():
                # Fallback: broad search
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


def _winget_is_id(name: str) -> bool:
    """
    Return True if `name` looks like a winget/Store package ID rather than a display name.
    Winget IDs: 'Publisher.AppName', 'Microsoft.VisualStudioCode', 'XP8BSBGQW2DKS0', etc.
    They contain no spaces and either have dots or are all-caps alphanumeric (Store IDs).
    """
    import re
    name = name.strip()
    if " " in name:
        return False
    # Publisher.App format (e.g. Git.Git, Microsoft.PowerShell)
    if "." in name:
        return True
    # Microsoft Store IDs: all uppercase alphanumeric, 12+ chars
    if re.fullmatch(r"[A-Z0-9]{10,}", name):
        return True
    return False


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
                + "Reply ✅ `install it` to confirm, or `cancel`."
            ),
        }

    try:
        if IS_WINDOWS:
            # Choose --id or --name depending on whether the input looks like a winget ID
            if _winget_is_id(name):
                id_flag = ["--id", name, "--exact"]
            else:
                id_flag = ["--name", name]
            result = subprocess.run(
                ["winget", "install"] + id_flag +
                ["--silent", "--accept-package-agreements", "--accept-source-agreements"],
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

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        combined = (stdout + stderr).lower()

        if result.returncode == 0:
            return {"success": True, "text": f"✅ *{name}* installed successfully."}
        # winget exit code 0x8A150011 (-1978335215) = already installed
        if "already installed" in combined or result.returncode == -1978335215:
            return {"success": True, "text": f"✅ *{name}* is already installed."}
        # Show stderr if stdout is empty
        detail = (stdout or stderr)[-400:].strip()
        return {
            "success": False,
            "error": f"Install failed (code {result.returncode}):\n{detail}",
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


def check_for_updates() -> dict:
    """Check if a newer version of GhostDesk is available (git-based)."""
    pkg_dir = Path(__file__).parent.parent.parent  # GhostDesk root
    git_dir = pkg_dir / ".git"

    if not git_dir.exists():
        return {
            "success": False,
            "text": "❌ Not a git repo — cannot check for updates automatically.",
        }
    try:
        subprocess.run(
            ["git", "fetch"], cwd=str(pkg_dir),
            capture_output=True, timeout=15,
        )
        status = subprocess.run(
            ["git", "status", "-uno"], cwd=str(pkg_dir),
            capture_output=True, text=True, timeout=10,
        )
        if "Your branch is behind" in status.stdout:
            behind = subprocess.run(
                ["git", "rev-list", "HEAD..@{u}", "--count"],
                cwd=str(pkg_dir), capture_output=True, text=True,
            )
            count = behind.stdout.strip()
            return {
                "success": True, "update_available": True,
                "text": (
                    f"🔄 Update available: *{count}* new commit(s).\n"
                    "Say `update ghostdesk` or run `/update` to install."
                ),
            }
        return {
            "success": True, "update_available": False,
            "text": "✅ GhostDesk is up to date.",
        }
    except Exception as e:
        return {"success": False, "text": f"❌ Update check failed: {e}"}


def update_ghostdesk(restart: bool = True) -> dict:
    """
    Pull latest code and reinstall GhostDesk.
    If restart=True, the process restarts automatically after 2 seconds.
    """
    import threading

    pkg_dir = Path(__file__).parent.parent.parent
    git_dir = pkg_dir / ".git"
    lines   = []

    # Clean up corrupted ~ partial installs left by interrupted pip runs
    try:
        import site, shutil
        for sp in site.getsitepackages():
            for broken in Path(sp).glob("~*"):
                try:
                    shutil.rmtree(broken) if broken.is_dir() else broken.unlink()
                except Exception:
                    pass
    except Exception:
        pass

    if git_dir.exists():
        # git pull
        pull = subprocess.run(
            ["git", "pull"], cwd=str(pkg_dir),
            capture_output=True, text=True, timeout=60,
        )
        if pull.returncode != 0:
            return {
                "success": False,
                "text": f"❌ git pull failed:\n```{pull.stderr[:300]}```",
            }
        lines.append(f"✅ git pull: {pull.stdout.strip() or 'Already up to date.'}")

        # Install/update dependencies only — avoids touching ghostdesk.exe
        # (which is locked while the process is running on Windows)
        req_file = pkg_dir / "ghostpc" / "requirements.txt"
        pip_cmd = (
            [sys.executable, "-m", "pip", "install", "-r", str(req_file), "-q"]
            if req_file.exists()
            else [sys.executable, "-m", "pip", "install", "-e", ".", "--no-deps", "-q"]
        )
        pip = subprocess.run(pip_cmd, cwd=str(pkg_dir), capture_output=True, text=True, timeout=180)
        if pip.returncode != 0:
            return {
                "success": False,
                "text": f"❌ pip install failed:\n```{pip.stderr[:300]}```",
            }
        lines.append("✅ Dependencies updated.")
    else:
        # PyPI upgrade
        pip = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "ghostdesk"],
            capture_output=True, text=True, timeout=120,
        )
        if pip.returncode != 0:
            return {
                "success": False,
                "text": f"❌ pip upgrade failed:\n```{pip.stderr[:300]}```",
            }
        lines.append("✅ pip upgrade complete.")

    if restart:
        lines.append("🔄 Restarting GhostDesk in 3 seconds...")

        def _do_restart():
            import time
            time.sleep(3)

            # Build the right restart command depending on how we were launched
            argv0 = sys.argv[0] if sys.argv else ""

            if argv0.endswith((".py",)):
                # Launched as: python main.py
                cmd = [sys.executable] + sys.argv
            elif "ghostdesk" in argv0.lower() and not argv0.endswith(".py"):
                # Launched as: ghostdesk  (console script — .exe on Windows or shebang on Unix)
                # Re-run the same entry-point script via sys.executable so it works cross-platform
                cmd = [sys.executable, "-m", "ghostpc.main"]
            else:
                # Fallback: re-run as module
                cmd = [sys.executable, "-m", "ghostpc.main"]

            import subprocess
            creationflags = 0
            if os.name == "nt":
                # Detach from current console so the new process lives independently
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

            subprocess.Popen(cmd, cwd=str(pkg_dir), creationflags=creationflags)
            os._exit(0)  # Hard-exit current process; new one is already starting

        threading.Thread(target=_do_restart, daemon=False).start()

    return {"success": True, "text": "\n".join(lines), "restarting": restart}


# ─── Autostart ────────────────────────────────────────────────────────────────

_AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "GhostDesk"


def is_autostart_enabled() -> bool:
    """Return True if GhostDesk is registered for Windows autostart."""
    if not IS_WINDOWS:
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, _AUTOSTART_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def _build_autostart_cmd() -> str:
    """Build the command string that Windows should run on login."""
    argv0 = sys.argv[0] if sys.argv else ""
    if argv0.endswith(".py"):
        return f'"{sys.executable}" "{argv0}"'
    # Installed via pip (ghostdesk entry-point .exe) or -m invocation
    return f'"{sys.executable}" -m ghostpc.main'


def enable_autostart() -> dict:
    """Register GhostDesk to start automatically when Windows boots."""
    if not IS_WINDOWS:
        return {"success": False, "error": "Autostart via registry is Windows-only."}
    try:
        import winreg
        cmd = _build_autostart_cmd()
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, _AUTOSTART_NAME, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        return {"success": True, "text": f"✅ GhostDesk will now start automatically on Windows login.\nCommand: {cmd}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def disable_autostart() -> dict:
    """Remove GhostDesk from Windows startup."""
    if not IS_WINDOWS:
        return {"success": False, "error": "Windows only."}
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, _AUTOSTART_NAME)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
        return {"success": True, "text": "✅ GhostDesk removed from Windows startup."}
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


# ─── Shell / Terminal Execution ───────────────────────────────────────────────

def run_command(
    command: str,
    shell: str = "powershell",
    timeout: int = 30,
    confirm: bool = False,
) -> dict:
    """
    Execute any shell command on the PC and return the output.
    shell: 'powershell' (default), 'cmd', or 'bash' (WSL/Mac/Linux)
    timeout: seconds to wait (max 120)
    confirm: must be True for destructive commands; bot will ask first if False
    """
    # Light safety gate: require confirmation for obviously destructive patterns
    _destructive = ("format ", "rm -rf", "del /f", "rd /s", "diskpart",
                    "net user", "reg delete", "bcdedit", "cipher /w")
    needs_confirm = any(d in command.lower() for d in _destructive)
    if needs_confirm and not confirm:
        return {
            "success": False,
            "confirm": True,
            "text": (
                f"⚠️ This command looks destructive:\n```\n{command}\n```\n\n"
                "Reply `run it` to confirm, or `cancel`."
            ),
        }

    timeout = min(int(timeout), 120)
    try:
        if IS_WINDOWS:
            if shell == "cmd":
                cmd = ["cmd", "/c", command]
            else:
                cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
        elif IS_MAC:
            cmd = ["bash", "-c", command]
        else:
            cmd = ["bash", "-c", command]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        output = stdout or stderr or "(no output)"
        success = result.returncode == 0

        return {
            "success": success,
            "returncode": result.returncode,
            "output": output,
            "text": (
                f"{'✅' if success else '⚠️'} Command finished (exit {result.returncode})\n"
                f"```\n{output[:3000]}\n```"
            ),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Command timed out after {timeout}s."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Process Management ───────────────────────────────────────────────────────

def get_processes(filter_name: str = "", top_n: int = 20) -> dict:
    """
    List running processes sorted by CPU usage.
    filter_name: optionally filter by process name substring.
    top_n: how many to return (default 20).
    """
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status"]):
            try:
                info = p.info
                if filter_name and filter_name.lower() not in info["name"].lower():
                    continue
                mem_mb = round(info["memory_info"].rss / 1024 / 1024, 1) if info["memory_info"] else 0
                procs.append({
                    "pid": info["pid"],
                    "name": info["name"],
                    "cpu": info["cpu_percent"],
                    "mem_mb": mem_mb,
                    "status": info["status"],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        procs.sort(key=lambda x: x["cpu"], reverse=True)
        procs = procs[:top_n]

        lines = [f"⚙️ *Running processes (top {len(procs)} by CPU)*\n"]
        for p in procs:
            lines.append(f"• [{p['pid']}] *{p['name']}* — CPU {p['cpu']}% | RAM {p['mem_mb']}MB")

        return {"success": True, "processes": procs, "text": "\n".join(lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def kill_process(name_or_pid: str, confirm: bool = False) -> dict:
    """
    Kill a process by name or PID.
    name_or_pid: process name (e.g. 'notepad.exe') or numeric PID.
    confirm: must be True.
    """
    if not confirm:
        return {
            "success": False,
            "confirm": True,
            "text": f"⚠️ Kill process `{name_or_pid}`?\n\nReply `kill it` to confirm.",
        }
    try:
        import psutil
        killed = []
        # Try as PID first
        try:
            pid = int(name_or_pid)
            p = psutil.Process(pid)
            name = p.name()
            p.terminate()
            killed.append(f"{name} (PID {pid})")
        except ValueError:
            # It's a name
            for p in psutil.process_iter(["pid", "name"]):
                if name_or_pid.lower() in p.info["name"].lower():
                    try:
                        p.terminate()
                        killed.append(f"{p.info['name']} (PID {p.info['pid']})")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

        if not killed:
            return {"success": False, "error": f"No process found matching '{name_or_pid}'."}
        return {"success": True, "text": f"✅ Killed: {', '.join(killed)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Clipboard ────────────────────────────────────────────────────────────────

def get_clipboard() -> dict:
    """Read the current clipboard content."""
    try:
        import pyautogui
        text = pyautogui.hotkey  # just to ensure pyautogui imported
        # Use pyperclip if available, otherwise pyautogui/win32
        try:
            import pyperclip
            content = pyperclip.paste()
        except ImportError:
            if IS_WINDOWS:
                import win32clipboard
                win32clipboard.OpenClipboard()
                try:
                    content = win32clipboard.GetClipboardData()
                finally:
                    win32clipboard.CloseClipboard()
            else:
                result = subprocess.run(["pbpaste"], capture_output=True, text=True)
                content = result.stdout
        return {
            "success": True,
            "content": content,
            "text": f"📋 *Clipboard:*\n```\n{content[:2000]}\n```",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_clipboard(text: str) -> dict:
    """Write text to the clipboard."""
    try:
        try:
            import pyperclip
            pyperclip.copy(text)
        except ImportError:
            if IS_WINDOWS:
                import win32clipboard
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
                finally:
                    win32clipboard.CloseClipboard()
            else:
                subprocess.run(["pbcopy"], input=text.encode(), check=True)
        return {"success": True, "text": f"📋 Clipboard set to:\n`{text[:200]}`"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Power Management ─────────────────────────────────────────────────────────

def sleep_pc(confirm: bool = False) -> dict:
    """Put the PC to sleep."""
    if not confirm:
        return {"success": False, "confirm": True, "text": "😴 Put PC to sleep? Reply `sleep it`."}
    try:
        if IS_WINDOWS:
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=True)
        elif IS_MAC:
            subprocess.run(["pmset", "sleepnow"], check=True)
        else:
            subprocess.run(["systemctl", "suspend"], check=True)
        return {"success": True, "text": "😴 PC going to sleep..."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def hibernate_pc(confirm: bool = False) -> dict:
    """Hibernate the PC."""
    if not confirm:
        return {"success": False, "confirm": True, "text": "💤 Hibernate PC? Reply `hibernate it`."}
    try:
        if IS_WINDOWS:
            subprocess.run(["shutdown", "/h"], check=True)
        elif IS_MAC:
            subprocess.run(["pmset", "hibernatemode", "25"], check=True)
            subprocess.run(["pmset", "sleepnow"], check=True)
        else:
            subprocess.run(["systemctl", "hibernate"], check=True)
        return {"success": True, "text": "💤 PC hibernating..."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Disk Information ─────────────────────────────────────────────────────────

def get_disk_info() -> dict:
    """Return disk/drive usage for all partitions."""
    try:
        import psutil
        partitions = psutil.disk_partitions(all=False)
        lines = ["💾 *Disk Usage*\n"]
        disks = []
        for p in partitions:
            try:
                usage = psutil.disk_usage(p.mountpoint)
                total_gb  = round(usage.total  / 1024**3, 1)
                used_gb   = round(usage.used   / 1024**3, 1)
                free_gb   = round(usage.free   / 1024**3, 1)
                pct       = usage.percent
                bar_filled = int(pct / 10)
                bar = "█" * bar_filled + "░" * (10 - bar_filled)
                lines.append(
                    f"• *{p.device}* ({p.fstype})\n"
                    f"  [{bar}] {pct}%\n"
                    f"  Used: {used_gb}GB / {total_gb}GB | Free: {free_gb}GB"
                )
                disks.append({"device": p.device, "total_gb": total_gb, "used_gb": used_gb, "free_gb": free_gb, "percent": pct})
            except PermissionError:
                continue
        return {"success": True, "disks": disks, "text": "\n".join(lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Network Information ──────────────────────────────────────────────────────

def get_network_info() -> dict:
    """Return network adapter info: IPs, MAC addresses, connection status."""
    try:
        import psutil, socket
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        io    = psutil.net_io_counters(pernic=False)

        lines = ["🌐 *Network Info*\n"]
        adapters = []
        for iface, addr_list in addrs.items():
            stat = stats.get(iface)
            if not stat or not stat.isup:
                continue
            for addr in addr_list:
                import psutil as _p
                if addr.family == 2:   # AF_INET = IPv4
                    lines.append(f"• *{iface}*: `{addr.address}` (mask: {addr.netmask})")
                    adapters.append({"iface": iface, "ip": addr.address, "mask": addr.netmask})
                elif addr.family == 23: # AF_INET6
                    lines.append(f"  IPv6: `{addr.address[:40]}`")
                elif addr.family == -1 or addr.family == 18:  # MAC
                    lines.append(f"  MAC: `{addr.address}`")

        # Public IP via quick DNS trick
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
            lines.append(f"\n📡 Primary outbound IP: `{local_ip}`")
        except Exception:
            pass

        sent_mb = round(io.bytes_sent / 1024**2, 1)
        recv_mb = round(io.bytes_recv / 1024**2, 1)
        lines.append(f"📊 Session I/O: ↑{sent_mb}MB sent | ↓{recv_mb}MB received")

        return {"success": True, "adapters": adapters, "text": "\n".join(lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def ping(host: str, count: int = 4) -> dict:
    """Ping a host and return latency stats."""
    try:
        count = min(int(count), 10)
        if IS_WINDOWS:
            result = subprocess.run(
                ["ping", "-n", str(count), host],
                capture_output=True, text=True, timeout=30,
            )
        else:
            result = subprocess.run(
                ["ping", "-c", str(count), host],
                capture_output=True, text=True, timeout=30,
            )
        output = result.stdout.strip()
        success = result.returncode == 0
        return {
            "success": success,
            "text": f"🏓 *Ping {host}*\n```\n{output[-800:]}\n```",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Ping timed out — {host} may be unreachable."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Battery ─────────────────────────────────────────────────────────────────

def get_battery_info() -> dict:
    """Return battery status (for laptops)."""
    try:
        import psutil
        batt = psutil.sensors_battery()
        if batt is None:
            return {"success": True, "text": "🔌 No battery detected (desktop PC or not supported)."}
        pct    = round(batt.percent, 1)
        status = "🔌 Charging" if batt.power_plugged else "🔋 On battery"
        secs   = batt.secsleft
        if secs == psutil.POWER_TIME_UNLIMITED:
            time_str = "fully charged"
        elif secs < 0:
            time_str = "calculating..."
        else:
            h, m = divmod(secs // 60, 60)
            time_str = f"{h}h {m}m remaining"
        return {
            "success": True,
            "percent": pct,
            "plugged": batt.power_plugged,
            "text": f"🔋 *Battery*: {pct}% — {status} — {time_str}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Windows Services ─────────────────────────────────────────────────────────

def list_services(filter_name: str = "", status_filter: str = "") -> dict:
    """
    List Windows services.
    filter_name: filter by name substring.
    status_filter: 'running', 'stopped', or '' for all.
    """
    if not IS_WINDOWS:
        return {"success": False, "error": "Service management is Windows-only."}
    try:
        import psutil
        svcs = []
        for svc in psutil.win_service_iter():
            try:
                info = svc.as_dict()
                if filter_name and filter_name.lower() not in info["name"].lower() \
                        and filter_name.lower() not in info["display_name"].lower():
                    continue
                if status_filter and info["status"] != status_filter:
                    continue
                svcs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        svcs.sort(key=lambda x: x["name"])
        lines = [f"⚙️ *Services ({len(svcs)} found)*\n"]
        for s in svcs[:25]:
            icon = "🟢" if s["status"] == "running" else "🔴"
            lines.append(f"{icon} *{s['display_name']}* (`{s['name']}`)")

        return {"success": True, "services": svcs, "text": "\n".join(lines)}
    except ImportError:
        return {"success": False, "error": "psutil required. Run: pip install psutil"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def manage_service(name: str, action: str, confirm: bool = False) -> dict:
    """
    Start, stop, or restart a Windows service.
    action: 'start' | 'stop' | 'restart'
    """
    if not IS_WINDOWS:
        return {"success": False, "error": "Service management is Windows-only."}
    if action not in ("start", "stop", "restart"):
        return {"success": False, "error": "action must be 'start', 'stop', or 'restart'."}
    if action in ("stop", "restart") and not confirm:
        return {
            "success": False,
            "confirm": True,
            "text": f"⚠️ {action.title()} service `{name}`? Reply `do it` to confirm.",
        }
    try:
        result = subprocess.run(
            ["sc", action, name] if action != "restart"
            else ["net", "stop", name],
            capture_output=True, text=True, timeout=30,
        )
        if action == "restart":
            subprocess.run(["net", "start", name], capture_output=True, text=True, timeout=30)
        output = (result.stdout or result.stderr or "").strip()
        success = result.returncode == 0
        return {
            "success": success,
            "text": f"{'✅' if success else '❌'} Service `{name}` {action}ed.\n{output[:300]}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Environment Variables ────────────────────────────────────────────────────

def get_env_var(name: str) -> dict:
    """Get the value of an environment variable."""
    value = os.environ.get(name)
    if value is None:
        return {"success": False, "error": f"Environment variable '{name}' not found."}
    return {"success": True, "name": name, "value": value, "text": f"🔧 `{name}` = `{value}`"}


def set_env_var(name: str, value: str, scope: str = "user") -> dict:
    """
    Set an environment variable.
    scope: 'process' (current session only), 'user' (Windows user, persistent), 'system' (Windows system, requires admin)
    """
    os.environ[name] = value  # Always set for current process
    if IS_WINDOWS and scope in ("user", "system"):
        try:
            import winreg
            root = winreg.HKEY_CURRENT_USER if scope == "user" else winreg.HKEY_LOCAL_MACHINE
            key_path = "Environment" if scope == "user" else r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
            with winreg.OpenKey(root, key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            # Broadcast WM_SETTINGCHANGE so new processes pick it up
            import ctypes
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 2, 5000, None)
            return {"success": True, "text": f"✅ `{name}` set to `{value}` ({scope} scope, persistent)."}
        except Exception as e:
            return {"success": True, "text": f"✅ `{name}` set for current session (persistent write failed: {e})."}
    return {"success": True, "text": f"✅ `{name}` = `{value}` (current session only)."}


# ─── Window Management ────────────────────────────────────────────────────────

def list_windows() -> dict:
    """List all visible windows with their titles."""
    try:
        import pygetwindow as gw
        windows = gw.getAllWindows()
        visible = [w for w in windows if w.title.strip()]
        lines = [f"🪟 *Open Windows ({len(visible)})*\n"]
        for w in visible[:30]:
            lines.append(f"• `{w.title[:60]}`")
        return {"success": True, "windows": [w.title for w in visible], "text": "\n".join(lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def focus_window(title: str) -> dict:
    """Bring a window to the foreground by title substring."""
    try:
        import pygetwindow as gw
        matches = [w for w in gw.getAllWindows() if title.lower() in w.title.lower() and w.title.strip()]
        if not matches:
            return {"success": False, "error": f"No window found matching '{title}'."}
        w = matches[0]
        w.activate()
        return {"success": True, "text": f"🪟 Focused: *{w.title}*"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def minimize_window(title: str) -> dict:
    """Minimize a window by title substring."""
    try:
        import pygetwindow as gw
        matches = [w for w in gw.getAllWindows() if title.lower() in w.title.lower()]
        if not matches:
            return {"success": False, "error": f"No window matching '{title}'."}
        matches[0].minimize()
        return {"success": True, "text": f"🪟 Minimized: *{matches[0].title}*"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def maximize_window(title: str) -> dict:
    """Maximize a window by title substring."""
    try:
        import pygetwindow as gw
        matches = [w for w in gw.getAllWindows() if title.lower() in w.title.lower()]
        if not matches:
            return {"success": False, "error": f"No window matching '{title}'."}
        matches[0].maximize()
        return {"success": True, "text": f"🪟 Maximized: *{matches[0].title}*"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Misc Utilities ───────────────────────────────────────────────────────────

def empty_recycle_bin(confirm: bool = False) -> dict:
    """Empty the Windows Recycle Bin."""
    if not IS_WINDOWS:
        return {"success": False, "error": "Recycle Bin is Windows-only."}
    if not confirm:
        return {"success": False, "confirm": True, "text": "🗑️ Empty Recycle Bin? Reply `empty it`."}
    try:
        import winshell
        winshell.recycle_bin().empty(confirm=False, show_progress=False, sound=False)
        return {"success": True, "text": "🗑️ Recycle Bin emptied."}
    except ImportError:
        # Fallback via PowerShell
        subprocess.run(
            ["powershell", "-Command", "Clear-RecycleBin -Confirm:$false"],
            capture_output=True, timeout=30,
        )
        return {"success": True, "text": "🗑️ Recycle Bin emptied."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def open_folder(path: str) -> dict:
    """Open a folder in Windows Explorer / Finder."""
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return {"success": False, "error": f"Path not found: {path}"}
        if IS_WINDOWS:
            subprocess.Popen(["explorer", str(p)])
        elif IS_MAC:
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return {"success": True, "text": f"📂 Opened: `{p}`"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_system_info() -> dict:
    """Return detailed hardware and OS information."""
    try:
        import psutil, platform, socket
        cpu_info   = platform.processor()
        cpu_cores  = psutil.cpu_count(logical=False)
        cpu_threads = psutil.cpu_count(logical=True)
        cpu_freq   = psutil.cpu_freq()
        ram        = psutil.virtual_memory()
        ram_gb     = round(ram.total / 1024**3, 1)
        hostname   = socket.gethostname()
        os_info    = f"{platform.system()} {platform.release()} ({platform.version()[:30]})"
        uptime_s   = int(psutil.boot_time())
        from datetime import datetime
        boot_time  = datetime.fromtimestamp(uptime_s).strftime("%Y-%m-%d %H:%M")

        text = (
            f"🖥️ *System Info*\n\n"
            f"*Host:* {hostname}\n"
            f"*OS:* {os_info}\n"
            f"*CPU:* {cpu_info}\n"
            f"  Cores: {cpu_cores} physical / {cpu_threads} logical\n"
            + (f"  Freq: {round(cpu_freq.current)}MHz (max {round(cpu_freq.max)}MHz)\n" if cpu_freq else "")
            + f"*RAM:* {ram_gb}GB total ({ram.percent}% used)\n"
            f"*Boot time:* {boot_time}\n"
        )
        return {"success": True, "text": text}
    except Exception as e:
        return {"success": False, "error": str(e)}
