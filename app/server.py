#!/usr/bin/env python3
"""
Flask webserver that returns plain text directory listing from files/ directory
"""

import os
import sys
import json
import shutil
import logging
import ipaddress
import socket
import subprocess
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from flask import Flask, request, Response, render_template, redirect, url_for, session, send_file, jsonify
from werkzeug.utils import secure_filename

from app.utils import (
    SERVE_DIRECTORY,
    safe_path,
    timestamp_filename,
    list_directory_structured,
    get_download_stats,
    record_download,
)
from app.translations import TRANSLATIONS
from app.index2 import create_index2_blueprint

app = Flask(__name__)

def _get_or_create_secret_key():
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)
    key_file = os.path.join(project_root, '.secret_key')
    if os.path.exists(key_file):
        try:
            with open(key_file, 'rb') as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass
    new_key = os.urandom(24)
    try:
        with open(key_file, 'wb') as f:
            f.write(new_key)
    except Exception:
        pass
    return new_key

app.secret_key = _get_or_create_secret_key()
APP_START_TIME = time.monotonic()

# --- Logging Configuration ---

if not os.path.exists('logs'):
    os.makedirs('logs')

file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s'
))
stream_handler.setLevel(logging.INFO)

app.logger.addHandler(file_handler)
app.logger.addHandler(stream_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('mpd startup')

# --- DRY Helpers ---

def get_msg(key):
    """Get translated message based on current session language."""
    lang = session.get('lang', 'nl')
    return TRANSLATIONS.get(lang, {}).get(key, key)

def render_manage(message=None):
    """Helper to consistently render the manage page with listing."""
    return render_template("manage.html", message=message, items=list_directory_structured())


def _is_internal_request() -> bool:
    remote_addr = request.remote_addr
    if not remote_addr:
        return False
    try:
        ip = ipaddress.ip_address(remote_addr)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified


def _get_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--always", "--long"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except Exception:
        return "unknown"


def _health_payload() -> dict:
    return {
        "status": "ok",
        "service": "mpd",
        "version": _get_version(),
        "hostname": socket.gethostname(),
        "environment": os.getenv("FLASK_ENV", "production"),
        "uptime_seconds": round(time.monotonic() - APP_START_TIME, 3),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

# --- Context Processors ---

@app.context_processor
def inject_translate():
    lang = session.get('lang', 'nl')
    return dict(_=lambda key: TRANSLATIONS.get(lang, {}).get(key, key), current_lang=lang)

# --- Logging Hooks ---

@app.before_request
def log_request():
    """Log every single request, even if it doesn't match a route."""
    app.logger.info(f"Incoming: {request.method} {request.url} from {request.remote_addr} (UA: {request.user_agent})")
    app.logger.debug(f"Headers: {dict(request.headers)}")

# --- Routes ---

@app.route("/set_lang/<lang>")
def set_lang(lang):
    if lang in TRANSLATIONS:
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health/getstatus")
def health():
    if not _is_internal_request():
        return jsonify({"status": "forbidden", "service": "mpd"}), 403
    return jsonify(_health_payload())

@app.route("/manage")
def manage():
    message = session.pop('manage_message', None)
    return render_manage(message)

@app.route("/manage/upload", methods=["POST"])
def upload_file():
    upload = request.files.get("file")
    if not upload or upload.filename == "":
        session['manage_message'] = get_msg("msg_select_file")
        return redirect(url_for('manage'))
    
    filename = secure_filename(upload.filename)
    if not filename:
        session['manage_message'] = get_msg("msg_invalid_filename")
        return redirect(url_for('manage'))
    filename = timestamp_filename(filename)
    
    target_dir = request.form.get("target_dir", "")
    try:
        dest_dir = safe_path(target_dir)
    except ValueError:
        session['manage_message'] = get_msg("msg_invalid_path")
        return redirect(url_for('manage'))
    
    os.makedirs(dest_dir, exist_ok=True)
    destination = os.path.join(dest_dir, filename)
    destination = safe_path(os.path.relpath(destination, SERVE_DIRECTORY))
    upload.save(destination)
    
    rel_path = os.path.relpath(destination, SERVE_DIRECTORY).replace('\\', '/')
    app.logger.info(f"File uploaded: {rel_path} from {request.remote_addr}")
    session['manage_message'] = f"{get_msg('msg_upload_success')} /{rel_path}."
    return redirect(url_for('manage'))

@app.route("/manage/delete", methods=["POST"])
def delete_item():
    target = request.form.get("path", "")
    if not target:
        session['manage_message'] = get_msg("msg_provide_path")
        return redirect(url_for('manage'))
    
    try:
        target_path = safe_path(target)
    except ValueError:
        session['manage_message'] = get_msg("msg_invalid_path")
        return redirect(url_for('manage'))
    
    if not os.path.exists(target_path):
        session['manage_message'] = get_msg("msg_not_found")
        return redirect(url_for('manage'))
    
    if os.path.abspath(target_path) == os.path.abspath(SERVE_DIRECTORY):
        session['manage_message'] = get_msg("msg_root_delete_denied")
        return redirect(url_for('manage'))
    
    if os.path.isdir(target_path):
        shutil.rmtree(target_path)
    else:
        os.remove(target_path)
    
    rel_path = os.path.relpath(target_path, SERVE_DIRECTORY).replace('\\', '/')
    app.logger.info(f"Item deleted: {rel_path} by {request.remote_addr}")
    session['manage_message'] = f"{get_msg('msg_deleted')} /{rel_path}."
    return redirect(url_for('manage'))

# --- API Documentation & Swagger ---

DOCS_DIRECTORY = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs"))

@app.route("/docs/openapi.yaml")
def openapi_spec():
    yaml_path = os.path.join(DOCS_DIRECTORY, "openapi.yaml")
    if not os.path.exists(yaml_path):
        return "Specification not found", 404
    return send_file(yaml_path, mimetype="text/yaml")

@app.route("/docs")
@app.route("/docs/")
@app.route("/swagger")
@app.route("/swagger/")
def swagger_ui():
    return render_template("docs.html")

@app.route("/about")
@app.route("/about/")
def about():
    system_info = _health_payload()
    return render_template("about.html", system_info=system_info)

# --- API Routes ---

@app.route("/api/files", methods=["GET"])
def api_list_files():
    items = list_directory_structured()
    return {"success": True, "files": items}

@app.route("/api/upload", methods=["POST"])
@app.route("/api/files/upload", methods=["POST"])
def api_upload_file():
    upload = request.files.get("file")
    if not upload or upload.filename == "":
        return {"success": False, "error": get_msg("msg_select_file")}, 400
    
    filename = secure_filename(upload.filename)
    if not filename:
        return {"success": False, "error": get_msg("msg_invalid_filename")}, 400
    filename = timestamp_filename(filename)
    
    target_dir = request.form.get("target_dir", "") or request.form.get("path", "")
    if request.is_json and request.json and not target_dir:
        target_dir = request.json.get("target_dir", "") or request.json.get("path", "")
        
    try:
        dest_dir = safe_path(target_dir)
    except ValueError:
        return {"success": False, "error": get_msg("msg_invalid_path")}, 400
    
    if os.path.isfile(dest_dir):
        return {"success": False, "error": get_msg("msg_invalid_path")}, 400

    os.makedirs(dest_dir, exist_ok=True)
    destination = os.path.join(dest_dir, filename)
    try:
        destination = safe_path(os.path.relpath(destination, SERVE_DIRECTORY))
    except ValueError:
        return {"success": False, "error": get_msg("msg_invalid_path")}, 400
        
    upload.save(destination)
    
    rel_path = os.path.relpath(destination, SERVE_DIRECTORY).replace('\\', '/')
    app.logger.info(f"File uploaded via API: {rel_path} from {request.remote_addr}")
    return {
        "success": True, 
        "message": f"{get_msg('msg_upload_success')} /{rel_path}.",
        "path": rel_path,
        "filename": filename
    }, 201

@app.route("/api/download", methods=["GET"])
@app.route("/api/download/<path:filepath>", methods=["GET"])
@app.route("/api/files/download", methods=["GET"])
@app.route("/api/files/download/<path:filepath>", methods=["GET"])
def api_download_file(filepath=None):
    if not filepath:
        filepath = request.args.get("path", "") or request.args.get("file", "")
    if not filepath:
        return {"success": False, "error": get_msg("msg_provide_path")}, 400
    
    try:
        target_path = safe_path(filepath)
    except ValueError:
        return {"success": False, "error": get_msg("msg_invalid_path")}, 400
    
    if not os.path.exists(target_path) or not os.path.isfile(target_path):
        return {"success": False, "error": get_msg("msg_not_found")}, 404
    
    rel_path = os.path.relpath(target_path, SERVE_DIRECTORY).replace('\\', '/')
    app.logger.info(f"Downloading file via API: {rel_path} for {request.remote_addr}")
    
    try:
        record_download(rel_path, request.remote_addr)
    except Exception as ex:
        app.logger.error(f"Failed to record download stats: {ex}")
    
    return send_file(target_path, as_attachment=True, download_name=os.path.basename(target_path))

@app.route("/api/delete", methods=["POST", "DELETE"])
@app.route("/api/files/delete", methods=["POST", "DELETE"])
def api_delete_file():
    target = ""
    if request.is_json and request.json:
        target = request.json.get("path", "")
    elif request.form:
        target = request.form.get("path", "")
    elif request.args:
        target = request.args.get("path", "")
        
    if not target:
        return {"success": False, "error": get_msg("msg_provide_path")}, 400
    
    try:
        target_path = safe_path(target)
    except ValueError:
        return {"success": False, "error": get_msg("msg_invalid_path")}, 400
    
    if not os.path.exists(target_path):
        return {"success": False, "error": get_msg("msg_not_found")}, 404
    
    if os.path.abspath(target_path) == os.path.abspath(SERVE_DIRECTORY):
        return {"success": False, "error": get_msg("msg_root_delete_denied")}, 403
    
    if os.path.isdir(target_path):
        shutil.rmtree(target_path)
    else:
        os.remove(target_path)
        
    rel_path = os.path.relpath(target_path, SERVE_DIRECTORY).replace('\\', '/')
    app.logger.info(f"Item deleted via API: {rel_path} by {request.remote_addr}")
    return {"success": True, "message": f"{get_msg('msg_deleted')} /{rel_path}."}

@app.route("/manage/rename", methods=["POST"])
def rename_item():
    old_path = request.form.get("old_path", "")
    new_path = request.form.get("new_path", "")
    if not old_path or not new_path:
        session['manage_message'] = get_msg("msg_provide_both_paths")
        return redirect(url_for('manage'))
    
    try:
        source_path = safe_path(old_path)
        destination_path = safe_path(new_path)
    except ValueError:
        session['manage_message'] = get_msg("msg_invalid_path")
        return redirect(url_for('manage'))
    
    if not os.path.exists(source_path):
        session['manage_message'] = get_msg("msg_source_not_found")
        return redirect(url_for('manage'))
    
    if os.path.exists(destination_path):
        session['manage_message'] = get_msg("msg_dest_exists")
        return redirect(url_for('manage'))
    
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    os.rename(source_path, destination_path)
    
    rel_old = os.path.relpath(source_path, SERVE_DIRECTORY).replace('\\', '/')
    rel_new = os.path.relpath(destination_path, SERVE_DIRECTORY).replace('\\', '/')
    app.logger.info(f"Item renamed: {rel_old} to {rel_new} by {request.remote_addr}")
    session['manage_message'] = f"{get_msg('msg_moved')} /{rel_old} {get_msg('msg_to')} /{rel_new}."
    return redirect(url_for('manage'))

@app.route("/manage/mkdir", methods=["POST"])
def make_dir():
    dir_path = request.form.get("dir_path", "")
    if not dir_path:
        session['manage_message'] = get_msg("msg_provide_dirname")
        return redirect(url_for('manage'))
    
    try:
        destination = safe_path(dir_path)
    except ValueError:
        session['manage_message'] = get_msg("msg_invalid_path")
        return redirect(url_for('manage'))
    
    if os.path.isfile(destination):
        session['manage_message'] = get_msg("msg_file_exists")
        return redirect(url_for('manage'))
    
    os.makedirs(destination, exist_ok=True)
    rel_path = os.path.relpath(destination, SERVE_DIRECTORY).replace('\\', '/')
    app.logger.info(f"Directory created: {rel_path} by {request.remote_addr}")
    session['manage_message'] = f"{get_msg('msg_mkdir_success')} /{rel_path}."
    return redirect(url_for('manage'))

def _index2_json_listing(files):
    stats = get_download_stats()
    json_data = []
    for game_name, size, rel_path, mtime in files:
        file_stats = stats.get(rel_path, {"count": 0, "last_downloaded_at": None})
        json_data.append({
            "name": game_name,
            "size": size,
            "path": rel_path,
            "downloads": file_stats["count"],
            "last_downloaded": file_stats["last_downloaded_at"],
            "uploaded_at": datetime.fromtimestamp(mtime, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        })
    return json_data


def _index2_record_download(rel_path, remote_addr):
    app.logger.info(f"Downloading file: {rel_path} for {remote_addr}")
    try:
        record_download(rel_path, remote_addr)
    except Exception as ex:
        app.logger.error(f"Failed to record download stats: {ex}")


app.register_blueprint(create_index2_blueprint(
    get_root_dir=lambda: SERVE_DIRECTORY,
    on_request=lambda req: app.logger.info(
        f"API Request: {req.url} from {req.remote_addr} (UA: {req.user_agent})"),
    on_download=_index2_record_download,
    json_listing=_index2_json_listing,
))

@app.route("/<path:path>")
def catch_all(path):
    # Ignore index2.php requests that might end up here due to trailing slash issues
    if path.startswith("index2.php"):
        return directory_listing()

    app.logger.warning(f"404 Path not found: /{path} from {request.remote_addr} (Args: {dict(request.args)})")
    return f"404 - Path not found: /{path}\nOnly /index2.php is supported", 404

if __name__ == "__main__":
    os.makedirs(SERVE_DIRECTORY, exist_ok=True)
    app.run(debug=True, host="0.0.0.0", port=5001)
