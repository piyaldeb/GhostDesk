"""
GhostPC File System Module
Find, read, move, copy, delete, zip, and send files.
"""

import logging
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)


def _home() -> Path:
    return Path.home()


def _temp_dir() -> Path:
    from config import TEMP_DIR
    return TEMP_DIR


# ─── Find Files ──────────────────────────────────────────────────────────────

def find_file(filename: str, search_path: Optional[str] = None) -> dict:
    """
    Search for a file by name (supports wildcards like *.xlsx).
    Returns the most recently modified match.
    """
    try:
        if search_path:
            base = Path(search_path).expanduser()
        else:
            base = _home()

        import glob
        # Try exact match first
        pattern = str(base / "**" / filename)
        matches = glob.glob(pattern, recursive=True)

        if not matches:
            # Try case-insensitive on Windows
            lower = filename.lower()
            matches = [
                str(p) for p in base.rglob("*")
                if p.name.lower() == lower
            ]

        if not matches:
            return {"success": False, "error": f"File not found: {filename} in {base}"}

        # Return most recently modified
        matches.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)
        found = matches[0]
        return {
            "success": True,
            "file_path": found,
            "all_matches": matches[:10],
            "text": f"Found: {found}",
        }

    except Exception as e:
        logger.error(f"find_file error: {e}")
        return {"success": False, "error": str(e)}


def find_files(pattern: str, search_path: Optional[str] = None, limit: int = 20) -> dict:
    """Find multiple files matching a glob pattern."""
    try:
        import glob as glob_mod
        base = Path(search_path).expanduser() if search_path else _home()
        full_pattern = str(base / "**" / pattern)
        matches = glob_mod.glob(full_pattern, recursive=True)
        matches.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)
        matches = matches[:limit]

        if not matches:
            return {"success": False, "error": f"No files found matching: {pattern}"}

        lines = [f"• {m}" for m in matches]
        return {
            "success": True,
            "files": matches,
            "text": f"Found {len(matches)} file(s):\n" + "\n".join(lines),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── List Files ──────────────────────────────────────────────────────────────

def list_files(folder: str, pattern: str = "*") -> dict:
    """List files in a folder with optional glob pattern."""
    try:
        path = Path(folder).expanduser()
        if not path.exists():
            return {"success": False, "error": f"Folder not found: {folder}"}

        files = sorted(path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

        lines = []
        for f in files[:50]:
            size = f.stat().st_size
            size_str = f"{size // 1024}KB" if size >= 1024 else f"{size}B"
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            icon = "📁" if f.is_dir() else "📄"
            lines.append(f"{icon} {f.name:<40} {size_str:>8}  {mtime}")

        text = f"📂 {folder} ({len(files)} items)\n" + "\n".join(lines[:50])
        return {
            "success": True,
            "files": [str(f) for f in files],
            "text": text,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Read File ───────────────────────────────────────────────────────────────

def read_file(path: str, max_chars: int = 8000) -> dict:
    """Read a text file and return its content."""
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return {"success": False, "error": f"File not found: {path}"}

        # Handle different encodings
        for encoding in ["utf-8", "utf-8-sig", "cp1252", "latin-1"]:
            try:
                content = p.read_text(encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            return {"success": False, "error": "Cannot decode file (binary?)"}

        truncated = content[:max_chars]
        if len(content) > max_chars:
            truncated += f"\n\n... [truncated, {len(content) - max_chars} chars remaining]"

        return {
            "success": True,
            "content": truncated,
            "text": truncated,
            "file_size": p.stat().st_size,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Write File ──────────────────────────────────────────────────────────────

def write_file(path: str, content: str, mode: str = "w") -> dict:
    """Write content to a file."""
    try:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"success": True, "text": f"✅ Written to {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Move / Copy ─────────────────────────────────────────────────────────────

def move_file(src: str, dst: str) -> dict:
    """Move a file or folder."""
    try:
        src_p = Path(src).expanduser()
        dst_p = Path(dst).expanduser()
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_p), str(dst_p))
        return {"success": True, "text": f"✅ Moved {src} → {dst}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def copy_file(src: str, dst: str) -> dict:
    """Copy a file."""
    try:
        src_p = Path(src).expanduser()
        dst_p = Path(dst).expanduser()
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        if src_p.is_dir():
            shutil.copytree(str(src_p), str(dst_p))
        else:
            shutil.copy2(str(src_p), str(dst_p))
        return {"success": True, "text": f"✅ Copied {src} → {dst}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Delete ──────────────────────────────────────────────────────────────────

def delete_file(path: str, confirm: bool = False) -> dict:
    """Delete a file or folder. Requires confirm=True."""
    if not confirm:
        return {"success": False, "error": "Deletion requires confirm=True"}
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return {"success": False, "error": f"Not found: {path}"}
        if p.is_dir():
            shutil.rmtree(str(p))
        else:
            p.unlink()
        return {"success": True, "text": f"✅ Deleted: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Zip ─────────────────────────────────────────────────────────────────────

def zip_folder(path: str, output_path: Optional[str] = None) -> dict:
    """Zip a folder or file."""
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return {"success": False, "error": f"Not found: {path}"}

        if not output_path:
            output_path = str(_temp_dir() / f"{p.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if p.is_dir():
                for file in p.rglob("*"):
                    if file.is_file():
                        zf.write(file, file.relative_to(p.parent))
            else:
                zf.write(p, p.name)

        size_mb = Path(output_path).stat().st_size / (1024 * 1024)
        return {
            "success": True,
            "zip_path": output_path,
            "file_path": output_path,
            "size_mb": round(size_mb, 2),
            "text": f"✅ Zipped to {output_path} ({size_mb:.1f}MB)",
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def zip_file(path: str) -> dict:
    """Alias for zip_folder that works on single files too."""
    return zip_folder(path)


def unzip(zip_path: str, extract_to: Optional[str] = None) -> dict:
    """Extract a ZIP archive."""
    try:
        p = Path(zip_path).expanduser()
        if not extract_to:
            extract_to = str(p.parent / p.stem)

        Path(extract_to).mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(str(p), "r") as zf:
            zf.extractall(extract_to)

        return {"success": True, "extract_path": extract_to, "text": f"✅ Extracted to {extract_to}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Send to Telegram (placeholder, actual send is done by main.py) ──────────

def send_file_to_telegram(path: str, caption: str = "") -> dict:
    """
    Prepare a file for Telegram delivery.
    The actual sending is handled by the agent/main.py.
    """
    p = Path(path).expanduser()
    if not p.exists():
        return {"success": False, "error": f"File not found: {path}"}

    size_mb = p.stat().st_size / (1024 * 1024)
    return {
        "success": True,
        "file_path": str(p),
        "caption": caption or p.name,
        "size_mb": round(size_mb, 2),
    }


# ─── Get Recent Files ────────────────────────────────────────────────────────

def get_recent_files(folder: Optional[str] = None, n: int = 10, extension: str = "") -> dict:
    """Get the N most recently modified files in a folder."""
    try:
        base = Path(folder).expanduser() if folder else _home() / "Downloads"
        if not base.exists():
            return {"success": False, "error": f"Folder not found: {base}"}

        all_files = [f for f in base.rglob("*") if f.is_file()]
        if extension:
            ext = extension if extension.startswith(".") else f".{extension}"
            all_files = [f for f in all_files if f.suffix.lower() == ext.lower()]

        all_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        recent = all_files[:n]

        lines = []
        for f in recent:
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            size = f.stat().st_size // 1024
            lines.append(f"• {f.name} ({size}KB) — {mtime}")

        return {
            "success": True,
            "files": [str(f) for f in recent],
            "text": f"Recent files in {base}:\n" + "\n".join(lines),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Open File / Folder ──────────────────────────────────────────────────────

def open_file(path: str) -> dict:
    """Open a file with its default application."""
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return {"success": False, "error": f"Not found: {path}"}
        os.startfile(str(p))
        return {"success": True, "text": f"✅ Opened: {p.name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def open_folder(path: str) -> dict:
    """Open a folder in Windows Explorer."""
    try:
        import subprocess
        p = Path(path).expanduser()
        subprocess.Popen(f'explorer "{p}"')
        return {"success": True, "text": f"✅ Opened folder: {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
