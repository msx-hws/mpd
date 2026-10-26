#!/usr/bin/env python3
"""
manage_app.py - MSX Pico DEVserver CLI Management Utility

Provides full API integration with mpd:
  - list: List files and directory structure
  - upload: Upload file(s) or entire directories (with recursive support)
  - download: Download a file from the server
  - delete: Delete a file or directory from the server
  - status: Query server status/health
"""

import argparse
import os
import sys
import json
import urllib.request
import urllib.error
import urllib.parse
import mimetypes
import uuid


def build_url(base_url, endpoint):
    return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"


def request_json(url, method="GET", data=None, headers=None):
    if headers is None:
        headers = {}
    
    encoded_data = None
    if data is not None:
        if isinstance(data, (dict, list)):
            encoded_data = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif isinstance(data, bytes):
            encoded_data = data
        elif isinstance(data, str):
            encoded_data = data.encode("utf-8")

    req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode("utf-8")
            status = response.status
            try:
                parsed = json.loads(res_body)
                return status, parsed
            except Exception:
                return status, res_body
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            parsed = json.loads(err_body)
            return e.code, parsed
        except Exception:
            return e.code, err_body
    except urllib.error.URLError as e:
        print(f"[!] Network error connecting to {url}: {e.reason}", file=sys.stderr)
        sys.exit(1)


def upload_single_file(base_url, filepath, target_dir=""):
    """Uploads a file using multipart/form-data via standard library urllib."""
    if not os.path.exists(filepath):
        print(f"[!] File not found: {filepath}", file=sys.stderr)
        return False

    filename = os.path.basename(filepath)
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    
    with open(filepath, "rb") as f:
        file_bytes = f.read()

    content_type = mimetypes.guess_type(filepath)[0] or "application/octet-stream"

    body = bytearray()
    
    # target_dir field
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b'Content-Disposition: form-data; name="target_dir"\r\n\r\n')
    body.extend(target_dir.encode("utf-8"))
    body.extend(b"\r\n")

    # file field
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"))
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_bytes)
    body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    upload_url = build_url(base_url, "/api/upload")
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body))
    }

    status, resp = request_json(upload_url, method="POST", data=bytes(body), headers=headers)
    if status in (200, 201):
        rel_path = resp.get("path", filename) if isinstance(resp, dict) else filename
        print(f"[✓] Uploaded: {filepath} -> {rel_path}")
        return True
    else:
        err = resp.get("error") if isinstance(resp, dict) else resp
        print(f"[✗] Failed uploading {filepath} (HTTP {status}): {err}", file=sys.stderr)
        return False


def cmd_upload(args):
    source = os.path.abspath(args.source)
    if not os.path.exists(source):
        print(f"[!] Path does not exist: {source}", file=sys.stderr)
        sys.exit(1)

    base_target = args.target_dir.strip("/\\")

    if os.path.isfile(source):
        success = upload_single_file(args.server, source, target_dir=base_target)
        sys.exit(0 if success else 1)

    if os.path.isdir(source):
        success_count = 0
        fail_count = 0
        for root, dirs, files in os.walk(source):
            rel_dir = os.path.relpath(root, source)
            target_sub = base_target
            if rel_dir != ".":
                target_sub = os.path.join(base_target, rel_dir).replace("\\", "/")

            for file in sorted(files):
                if file.startswith("."):
                    continue
                file_full = os.path.join(root, file)
                if upload_single_file(args.server, file_full, target_dir=target_sub):
                    success_count += 1
                else:
                    fail_count += 1

        print(f"\n[i] Upload Summary: {success_count} succeeded, {fail_count} failed.")
        sys.exit(0 if fail_count == 0 else 1)


def cmd_list(args):
    url = build_url(args.server, "/api/files")
    status, data = request_json(url)
    if status != 200:
        print(f"[!] Error listing files (HTTP {status}): {data}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(data, indent=2))
        return

    files = data.get("files", [])
    if not files:
        print("No files found on server.")
        return

    print(f"{'TYPE':<6} {'SIZE':>10}  {'NAME'}")
    print("-" * 60)
    for item in files:
        itype = "DIR" if item.get("is_dir") else "FILE"
        isize = "-" if item.get("is_dir") else str(item.get("size", 0))
        name = item.get("path") or item.get("name", "")
        print(f"{itype:<6} {isize:>10}  {name}")


def cmd_download(args):
    url = build_url(args.server, f"/api/download?path={urllib.parse.quote(args.remote_path)}")
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read()
            out_file = args.output or os.path.basename(args.remote_path)
            with open(out_file, "wb") as f:
                f.write(content)
            print(f"[✓] Downloaded {args.remote_path} -> {out_file} ({len(content)} bytes)")
    except urllib.error.HTTPError as e:
        print(f"[!] Download failed (HTTP {e.code}): {e.read().decode('utf-8')}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[!] Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def cmd_delete(args):
    url = build_url(args.server, "/api/delete")
    status, data = request_json(url, method="POST", data={"path": args.remote_path})
    if status == 200:
        msg = data.get("message") if isinstance(data, dict) else data
        print(f"[✓] {msg}")
    else:
        err = data.get("error") if isinstance(data, dict) else data
        print(f"[!] Delete failed (HTTP {status}): {err}", file=sys.stderr)
        sys.exit(1)


def cmd_status(args):
    url = build_url(args.server, "/health/getstatus")
    status, data = request_json(url)
    if status == 200:
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            service = data.get("service") if isinstance(data, dict) else "unknown"
            stat = data.get("status") if isinstance(data, dict) else "unknown"
            print(f"[✓] Status: {stat} | Service: {service}")
    else:
        print(f"[!] Server returned HTTP {status}: {data}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="MSX Pico DEVserver CLI Management Tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--server", "-s",
        default=os.getenv("MPD_SERVER_URL", "http://127.0.0.1:80"),
        help="mpd server base URL"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: upload
    p_upload = subparsers.add_parser("upload", help="Upload a file or folder")
    p_upload.add_argument("source", help="Local file or directory path to upload")
    p_upload.add_argument("--target-dir", "-t", default="", help="Remote directory path")
    p_upload.set_defaults(func=cmd_upload)

    # Subcommand: list
    p_list = subparsers.add_parser("list", help="List files on server")
    p_list.add_argument("--json", action="store_true", help="Output raw JSON")
    p_list.set_defaults(func=cmd_list)

    # Subcommand: download
    p_down = subparsers.add_parser("download", help="Download a file from server")
    p_down.add_argument("remote_path", help="Path of the file on the server")
    p_down.add_argument("-o", "--output", help="Local output destination filename")
    p_down.set_defaults(func=cmd_download)

    # Subcommand: delete
    p_del = subparsers.add_parser("delete", help="Delete a file or folder from server")
    p_del.add_argument("remote_path", help="Path on server to delete")
    p_del.set_defaults(func=cmd_delete)

    # Subcommand: status
    p_stat = subparsers.add_parser("status", help="Check server health/status")
    p_stat.add_argument("--json", action="store_true", help="Output raw JSON")
    p_stat.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
