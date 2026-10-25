import os
import shutil
import sqlite3
import html
from werkzeug.utils import secure_filename

# Configure the directory to serve (project root is parent of app package)
APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIRECTORY = os.path.dirname(APP_DIR)
SERVE_DIRECTORY = os.path.join(BASE_DIRECTORY, "files")

def safe_relative_path(user_path):
    if user_path is None:
        return ""
    normalized = user_path.strip().replace("\\", "/")
    if normalized in ("", "."):
        return ""
    normalized = os.path.normpath(normalized)
    if normalized.startswith("..") or normalized.startswith("/"):
        raise ValueError("Invalid path")
    return normalized

def safe_path(relative_path):
    relative_path = safe_relative_path(relative_path)
    destination = os.path.normpath(os.path.join(SERVE_DIRECTORY, relative_path))
    if os.path.commonpath([os.path.abspath(SERVE_DIRECTORY), os.path.abspath(destination)]) != os.path.abspath(SERVE_DIRECTORY):
        raise ValueError("Path outside serve directory")
    return destination

def timestamp_filename(filename, dt=None):
    """Prefix a filename with datetime stamp (YYYYMMDD_HHMMSS_filename)."""
    if dt is None:
        from datetime import datetime
        dt = datetime.now()
    timestamp = dt.strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{filename}"

def list_directory_structured():
    """Returns a list of dictionaries representing the file structure, sorted by path."""
    items = []
    if not os.path.exists(SERVE_DIRECTORY):
        os.makedirs(SERVE_DIRECTORY, exist_ok=True)
        return items

    # Add root files first
    for entry in os.scandir(SERVE_DIRECTORY):
        if entry.is_file():
            items.append({
                "name": entry.name,
                "path": entry.name,
                "type": "file",
                "display_path": "/",
                "size": entry.stat().st_size
            })

    # Now walk subdirectories
    for root, dirs, files in os.walk(SERVE_DIRECTORY):
        rel_root = os.path.relpath(root, SERVE_DIRECTORY)
        if rel_root == ".":
            continue

        clean_rel_root = rel_root.replace(os.sep, "/")
        display_path = "/" + clean_rel_root

        # Add the directory itself
        items.append({
            "name": os.path.basename(root),
            "path": clean_rel_root,
            "type": "dir",
            "display_path": os.path.dirname(display_path)
        })

        # Add files in this directory
        for filename in sorted(files):
            items.append({
                "name": filename,
                "path": clean_rel_root + "/" + filename,
                "type": "file",
                "display_path": display_path,
                "size": os.path.getsize(os.path.join(root, filename))
            })

    # Sort by directory path (combining dirs with their contents), then by type (dirs first), then name
    return sorted(items, key=lambda x: (("/" + x["path"]) if x["type"] == "dir" else x["display_path"], x["type"] == "file", x["name"]))

# --- Download Statistics Database ---

STATS_DB = os.path.join(BASE_DIRECTORY, "logs", "stats.db")

def init_stats_db():
    os.makedirs(os.path.dirname(STATS_DB), exist_ok=True)
    conn = sqlite3.connect(STATS_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            path TEXT PRIMARY KEY,
            download_count INTEGER DEFAULT 0,
            last_downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_ip TEXT
        )
    """)
    conn.commit()
    conn.close()

def record_download(rel_path, ip_address):
    init_stats_db()
    conn = sqlite3.connect(STATS_DB)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO downloads (path, download_count, last_downloaded_at, last_ip)
        VALUES (?, 1, CURRENT_TIMESTAMP, ?)
        ON CONFLICT(path) DO UPDATE SET
            download_count = download_count + 1,
            last_downloaded_at = CURRENT_TIMESTAMP,
            last_ip = EXCLUDED.last_ip
    """, (rel_path, ip_address))
    conn.commit()
    conn.close()

def get_download_stats():
    init_stats_db()
    conn = sqlite3.connect(STATS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT path, download_count, last_downloaded_at FROM downloads")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: {"count": row[1], "last_downloaded_at": row[2]} for row in rows}
