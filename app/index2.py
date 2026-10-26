"""MSX Pico /index2.php protocol (listing + download), shared between MSX Pico servers.

SOURCE OF TRUTH: the `mpd` repository (app/index2.py). Other servers (e.g. daystrom83)
receive a copy via `manage_ws sync-shared <site>`. Do not edit the copies; change this
file in mpd and sync. This module must stay free of imports from the host application.
"""

import os
import re

from flask import Blueprint, Response, request

# MSX Pico firmware only understands ROM and DSK: .COM files are listed as ROM.
EXTENSIONS_BY_TYPE = {
    "ROM": (".rom", ".com"),
    "COM": (".rom", ".com"),
    "DSK": (".dsk",),
    "ALL": (".rom", ".com", ".dsk"),
}
ROM_PAD_BLOCK = 4096
ROM_LIST_BLOCK = 8192


def list_entries(root_dir, extensions, request_char=""):
    """Return (display_name, size, rel_path, mtime) tuples below root_dir, newest first."""
    if not root_dir or not os.path.isdir(root_dir):
        return []
    normalized = tuple(ext.lower() for ext in extensions)
    entries = []
    for root, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if not filename.lower().endswith(normalized):
                continue
            file_path = os.path.join(root, filename)
            if not os.path.isfile(file_path):
                continue
            rel_path = os.path.relpath(file_path, root_dir).replace(os.sep, "/")
            try:
                size = os.path.getsize(file_path)
                mtime = os.path.getmtime(file_path)
            except OSError:
                continue
            if filename.lower().endswith(".rom"):
                remainder = size % ROM_LIST_BLOCK
                if remainder != 0 or size == 0:
                    size += (ROM_LIST_BLOCK - remainder) if size > 0 else ROM_LIST_BLOCK

            display_name = os.path.splitext(filename)[0]
            display_name = re.sub(r"^\d{8}_\d{6}_", "", display_name)
            display_name = re.sub(r"_\d{8}_\d{6}$", "", display_name)
            display_name = display_name.replace(" [original]", "")
            display_name = re.sub(r"(\]\s)(\[\d+\])$", r"]\2", display_name)

            term = request_char.lower()
            name_lower = display_name.lower()
            if term and term != "a":
                if len(term) == 1 and term.isalnum():
                    if not name_lower.startswith(term):
                        continue
                elif term not in name_lower:
                    continue
            entries.append((display_name, size, rel_path, mtime))

    unique = []
    seen = set()
    for entry in sorted(entries, key=lambda item: (-item[3], item[0], item[2])):
        key = (entry[0], entry[1], entry[2])
        if key not in seen:
            unique.append(entry)
            seen.add(key)
    return unique


def _pico_response(body):
    response = Response(body)
    response.headers["Content-type"] = "text/html; charset=UTF-8"
    response.headers["Expires"] = "0"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Server"] = "Abyss/2.16.20.2-X2-Win32 AbyssLib/2.16.20.2"
    response.headers["X-Powered-By"] = "PHP/8.5.5"
    return response


def _rom_download(header, content):
    def generate():
        yield header.encode("utf-8")
        yield b"\n"
        yield content

    return _pico_response(generate())


def _pad(content):
    remainder = len(content) % ROM_PAD_BLOCK
    if remainder != 0 or len(content) == 0:
        content += b"\0" * (ROM_PAD_BLOCK - remainder if content else ROM_PAD_BLOCK)
    return content


def create_index2_blueprint(get_root_dir, on_request=None, on_download=None,
                            json_listing=None):
    """Build the /index2.php blueprint.

    get_root_dir(): directory that is served.
    on_request(request): optional hook for request logging.
    on_download(rel_path, remote_addr): optional hook (statistics, logging).
    json_listing(files): optional; returns a JSON-serializable list for ?web=1 / ?format=json.
    """
    bp = Blueprint("index2", __name__)

    @bp.route("/index2.php", methods=["GET"])
    @bp.route("/index2.php/", methods=["GET"])
    def directory_listing():
        if on_request:
            on_request(request)
        request_type = request.args.get("type", "ROM").upper()
        request_char = request.args.get("char", "")
        download_index = request.args.get("download", None)

        extensions = EXTENSIONS_BY_TYPE.get(request_type)
        if extensions is None:
            return f"Error: Unsupported type '{request_type}'. Use ROM, COM, DSK, or ALL.", 400

        root_dir = get_root_dir()
        files = list_entries(root_dir, extensions, request_char=request_char)

        wants_json = request.args.get("web") == "1" or request.args.get("format") == "json"
        if wants_json and json_listing:
            import json
            response = Response(json.dumps(json_listing(files)), mimetype="application/json")
            response.headers["Expires"] = "0"
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            return response

        if download_index is not None:
            if not download_index.isdigit():
                return f"Error: Invalid download index {download_index}.", 400
            download_idx = int(download_index)
            if not 0 <= download_idx < len(files):
                return f"Error: Invalid download index {download_idx}.", 400

            _, _, rel_path, _ = files[download_idx]
            item_path = os.path.abspath(os.path.join(root_dir, rel_path))
            if os.path.commonpath([os.path.abspath(root_dir), item_path]) != os.path.abspath(root_dir):
                return "Error: Invalid path", 400
            try:
                with open(item_path, "rb") as f:
                    content = f.read()
            except OSError as e:
                return f"Error reading file: {e}", 500
            if on_download:
                on_download(rel_path, request.remote_addr)

            safe_filename = os.path.basename(rel_path)
            if request_type == "DSK":
                header = f"size:{len(content)},disks:1,name:{safe_filename}"
            else:
                if request_type in ("ROM", "COM"):
                    content = _pad(content)
                    if safe_filename.lower().endswith(".com"):
                        safe_filename = safe_filename[:-4] + ".rom"
                header = f"type:,start:,size:{len(content)},name:{safe_filename}"
            return _rom_download(header, content)

        result = "".join(f"{name}\t{size}\n" for name, size, _, _ in files)
        return _pico_response(result.encode("utf-8"))

    return bp
