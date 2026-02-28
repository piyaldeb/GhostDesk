"""
GhostPC Notifications Module
Send Windows toast notifications and listen for system notifications.
"""

import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def send_notification(title: str, message: str, icon: str = "info") -> dict:
    """Send a Windows toast notification."""
    try:
        # Try win10toast first
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=5, threaded=True)
        return {"success": True, "text": f"✅ Notification sent: {title}"}
    except ImportError:
        pass

    try:
        # Fallback: PowerShell toast
        ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$template = @"
<toast>
  <visual>
    <binding template="ToastGeneric">
      <text>{title}</text>
      <text>{message}</text>
    </binding>
  </visual>
</toast>
"@
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = New-Object Windows.UI.Notifications.ToastNotification($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("GhostPC").Show($toast)
"""
        subprocess.run(["powershell", "-Command", ps_script], timeout=5, capture_output=True)
        return {"success": True, "text": f"✅ Notification sent: {title}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_clipboard() -> dict:
    """Get the current clipboard text content."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        data = win32clipboard.GetClipboardData()
        win32clipboard.CloseClipboard()
        return {"success": True, "content": data, "text": f"📋 Clipboard: {data[:200]}"}
    except ImportError:
        try:
            result = subprocess.run(
                ["powershell", "-Command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=5
            )
            content = result.stdout.strip()
            return {"success": True, "content": content, "text": f"📋 Clipboard: {content[:200]}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_clipboard(text: str) -> dict:
    """Set clipboard text content."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text)
        win32clipboard.CloseClipboard()
        return {"success": True, "text": "✅ Clipboard updated"}
    except ImportError:
        try:
            ps = f'Set-Clipboard -Value "{text.replace(chr(34), chr(39))}"'
            subprocess.run(["powershell", "-Command", ps], timeout=5)
            return {"success": True, "text": "✅ Clipboard updated"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}
