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
    list_file_entries,
    list_directory_structured,
    get_download_stats,
    record_download,
)
from app.translations import TRANSLATIONS

app = Flask(__name__)
app.secret_key = os.urandom(24)
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
app.logger.info('msx-pico-station startup')

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
        "service": "msx-pico-station",
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
        return jsonify({"status": "forbidden", "service": "msx-pico-station"}), 403
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
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>MSX-Flask API - Swagger UI</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
    <link rel="icon" type="image/png" href="https://unpkg.com/swagger-ui-dist@5/favicon-32x32.png" sizes="32x32" />
    <style>
        html { box-sizing: border-box; overflow: -moz-scrollbars-vertical; overflow-y: scroll; }
        *, *:before, *:after { box-sizing: inherit; }
        body { margin: 0; background: #fafafa; }
        .topbar { display: none; }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
    <script>
    window.onload = function() {
        window.ui = SwaggerUIBundle({
            url: "/docs/openapi.yaml",
            dom_id: '#swagger-ui',
            deepLinking: true,
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIStandalonePreset
            ],
            layout: "BaseLayout"
        });
    };
    </script>
</body>
</html>"""
    return Response(html_content, mimetype="text/html")

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

@app.route("/index2.php")
@app.route("/index2.php/")
def directory_listing():
    """Return directory listing based on type parameter (ROM, DSK, or ALL)"""
    app.logger.info(f"API Request: {request.url} from {request.remote_addr} (UA: {request.user_agent})")
    request_type = request.args.get("type", "ROM").upper()
    request_char = request.args.get("char", "a")
    download_index = request.args.get("download", None)

    if request_type == "ROM":
        extensions = [".rom", ".ROM", ".com", ".COM"]
    elif request_type == "DSK":
        extensions = [".dsk", ".DSK"]
    elif request_type == "ALL":
        extensions = [".rom", ".ROM", ".com", ".COM", ".dsk", ".DSK"]
    else:
        app.logger.warning(f"Unsupported type: {request_type}")
        return f"Error: Unsupported type '{request_type}'. Use ROM, DSK, or ALL.", 400

    files = list_file_entries(extensions, request_char=request_char)

    if download_index is not None:
        if not download_index.isdigit():
            return f"Error: Invalid download index {download_index}.", 400
        download_idx = int(download_index)
        if not 0 <= download_idx < len(files):
            return f"Error: Invalid download index {download_idx}.", 400

        game_name, size, rel_path, mtime = files[download_idx]
        item_path = safe_path(rel_path)
        app.logger.info(f"Downloading file: {rel_path} for {request.remote_addr}")
        try:
            with open(item_path, "rb") as f:
                file_content = f.read()
            
            # Record download statistics
            try:
                record_download(rel_path, request.remote_addr)
            except Exception as ex:
                app.logger.error(f"Failed to record download stats: {ex}")
            
            if request_type == "ROM":
                remainder = len(file_content) % 4096
                if remainder != 0 or len(file_content) == 0:
                    pad_size = 4096 - remainder if len(file_content) > 0 else 4096
                    file_content += b'\0' * pad_size
            
            # Use only the base filename in the header to avoid path issues on devices
            safe_filename = os.path.basename(rel_path)
            if request_type == "ROM" and safe_filename.lower().endswith(".com"):
                safe_filename = safe_filename[:-4] + ".rom"
                
            header = f"{'size:' if request_type == 'DSK' else 'type:,start:,size:'}{len(file_content)}{',disks:1' if request_type == 'DSK' else ''},name:{safe_filename}"

            def generate():
                yield header.encode("utf-8")
                yield b"\n"
                yield file_content

            response = Response(generate())
            response.headers["Content-type"] = "text/html; charset=UTF-8"
            response.headers["Expires"] = "0"
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Server"] = "Abyss/2.16.20.2-X2-Win32 AbyssLib/2.16.20.2"
            response.headers["X-Powered-By"] = "PHP/8.5.5"
            return response
        except (OSError, IOError) as e:
            app.logger.error(f"Error reading file {item_path}: {e}")
            return f"Error reading file: {str(e)}", 500

    if request.args.get("web") == "1" or request.args.get("format") == "json":
        stats = get_download_stats()
        json_data = []
        for game_name, size, rel_path, mtime in files:
            file_stats = stats.get(rel_path, {"count": 0, "last_downloaded_at": None})
            uploaded_at_str = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            json_data.append({
                "name": game_name,
                "size": size,
                "path": rel_path,
                "downloads": file_stats["count"],
                "last_downloaded": file_stats["last_downloaded_at"],
                "uploaded_at": uploaded_at_str
            })
        response = Response(json.dumps(json_data), mimetype="application/json")
        response.headers["Expires"] = "0"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response

    result = "".join(f"{game_name}\t{size}\n" for game_name, size, _, _ in files) if files else "No files found\t0\n"

    def generate_listing():
        yield result.encode("utf-8")

    response = Response(generate_listing())
    response.headers["Content-type"] = "text/html; charset=UTF-8"
    response.headers["Expires"] = "0"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Server"] = "Abyss/2.16.20.2-X2-Win32 AbyssLib/2.16.20.2"
    response.headers["X-Powered-By"] = "PHP/8.5.5"
    return response

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
