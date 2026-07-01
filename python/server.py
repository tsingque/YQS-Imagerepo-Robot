#!/usr/bin/env python3
"""
Local dashboard server for the material repository.

Run from the project root:
  python3 python/server.py
"""

from __future__ import annotations

import json
import mimetypes
import os
import hmac
import threading
import contextlib
import io
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import feishu_client
import compress
import deerflow_runner
import recognition_worker
import similar_images


PYTHON_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PYTHON_DIR.parent
DASHBOARD_DIR = PROJECT_DIR / "dashboard"

IMAGES_RAW_DIR = PROJECT_DIR / "image_compressor" / "images_raw"
IMAGES_RECOGNIZED_DIR = PROJECT_DIR / "image_compressor" / "images_recognized"
IMAGES_COMPRESSED_DIR = PROJECT_DIR / "image_compressor" / "images_compressed"
CASE_MATERIALS_DIR = PROJECT_DIR / "case_materials"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".heif"}
SUPPORTED_PREVIEW_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
STATIC_EXTENSIONS = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}
HOST = os.getenv("YQS_DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.getenv("YQS_DASHBOARD_PORT", "8765"))
recognition_thread: threading.Thread | None = None
agent_thread: threading.Thread | None = None


def format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} B"


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def iter_images(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.rglob("*") if is_image(path))


def dir_size(paths: list[Path]) -> int:
    return sum(path.stat().st_size for path in paths if path.exists())


def directory_summary(key: str, label: str, path: Path) -> dict:
    images = iter_images(path)
    previewable = [path for path in images if path.suffix.lower() in SUPPORTED_PREVIEW_EXTENSIONS]
    return {
        "key": key,
        "label": label,
        "path": str(path.relative_to(PROJECT_DIR)),
        "exists": path.is_dir(),
        "count": len(images),
        "size": dir_size(images),
        "sizeLabel": format_size(dir_size(images)),
        "preview": [
            {
                "name": image.name,
                "path": str(image.relative_to(PROJECT_DIR)),
                "url": f"/api/file?path={quote(image.relative_to(PROJECT_DIR).as_posix())}",
            }
            for image in previewable[:12]
        ],
    }


def build_status() -> dict:
    raw_images = iter_images(IMAGES_RAW_DIR)
    recognized_images = iter_images(IMAGES_RECOGNIZED_DIR)
    compressed_images = iter_images(IMAGES_COMPRESSED_DIR)
    case_images = iter_images(CASE_MATERIALS_DIR)

    return {
        "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "totals": {
            "allImages": len(raw_images) + len(recognized_images) + len(compressed_images) + len(case_images),
            "raw": len(raw_images),
            "recognized": len(recognized_images),
            "compressed": len(compressed_images),
            "finished": len(case_images),
        },
        "directories": [
            directory_summary("raw", "images_raw 待处理", IMAGES_RAW_DIR),
            directory_summary("recognized", "AI 识图完成", IMAGES_RECOGNIZED_DIR),
            directory_summary("compressed", "压缩输出", IMAGES_COMPRESSED_DIR),
            directory_summary("finished", "Codex 成品素材", CASE_MATERIALS_DIR),
        ],
    }


def build_recognition_status() -> dict:
    state = recognition_worker.read_json(recognition_worker.STATE_PATH, {})
    token_usage = recognition_worker.read_json(recognition_worker.TOKEN_USAGE_PATH, {})
    compressed_images = recognition_worker.list_images()
    processed = recognition_worker.load_processed()
    return {
        "running": bool(state.get("running", False)),
        "total": state.get("total", 0),
        "completed": state.get("completed", 0),
        "failed": state.get("failed", 0),
        "skipped": state.get("skipped", len(processed)),
        "currentFile": state.get("current_file", ""),
        "message": state.get("message", "尚未启动 AI 识图。"),
        "provider": state.get("provider", ""),
        "updatedAt": state.get("updated_at", ""),
        "finishedAt": state.get("finished_at", ""),
        "pendingCompressed": len(compressed_images),
        "pendingRaw": 0,
        "errors": state.get("errors", []),
        "tokenUsage": token_usage,
    }


def build_feishu_status() -> dict:
    return feishu_client.feishu_config_status()


def build_agent_status() -> dict:
    return deerflow_runner.read_state()


def build_similarity_status() -> dict:
    return similar_images.read_report()


def dashboard_token() -> str:
    return os.getenv("YQS_DASHBOARD_TOKEN", "").strip()


def is_write_authorized(headers) -> bool:
    token = dashboard_token()
    if not token:
        return True
    provided = headers.get("X-YQS-Dashboard-Token", "").strip()
    return hmac.compare_digest(provided, token)


def start_recognition_job() -> tuple[bool, str]:
    global recognition_thread
    if recognition_thread is not None and recognition_thread.is_alive():
        return False, "AI 识图任务正在运行。"
    if not recognition_worker.list_images():
        return False, "暂无图片，请先压缩。"

    def target() -> None:
        try:
            recognition_worker.run()
        except Exception as exc:
            recognition_worker.update_state(
                running=False,
                message=f"AI 识图任务异常: {exc}",
                errors=[{"file": "", "error": str(exc)}],
            )

    recognition_thread = threading.Thread(target=target, daemon=True)
    recognition_thread.start()
    return True, "AI 识图任务已启动。"


def start_agent_workflow() -> tuple[bool, str]:
    global agent_thread
    state = deerflow_runner.read_state()
    if bool(state.get("running", False)):
        return False, "DeerFlow 托管任务正在运行。"
    if agent_thread is not None and agent_thread.is_alive():
        return False, "DeerFlow 托管任务正在运行。"

    def target() -> None:
        try:
            deerflow_runner.run_managed_workflow(force_direct=True)
        except Exception as exc:
            deerflow_runner.write_state(
                running=False,
                message=f"DeerFlow 托管任务异常: {exc}",
                error=str(exc),
            )

    agent_thread = threading.Thread(target=target, daemon=True)
    agent_thread.start()
    return True, "DeerFlow 托管处理已启动。"


def clear_directory_files(directory: Path) -> int:
    if not directory.is_dir():
        return 0

    removed = 0
    for path in sorted(directory.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
            removed += 1
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    return removed


def compress_images_raw() -> tuple[bool, str]:
    if not iter_images(IMAGES_RAW_DIR):
        return False, "images_raw 暂无图片。飞书机器人发图后，先点更新 images_raw。"

    output = io.StringIO()
    exit_code = 0
    with contextlib.redirect_stdout(output):
        try:
            compress.main()
        except SystemExit as exc:
            exit_code = int(exc.code or 0)
    if exit_code != 0:
        text = output.getvalue().strip()
        return False, text or "压缩失败。"
    compressed_count = len(iter_images(IMAGES_COMPRESSED_DIR))
    raw_count = len(iter_images(IMAGES_RAW_DIR))
    return True, f"压缩完成：compressed 当前 {compressed_count} 张，raw 剩余 {raw_count} 张。"


def safe_project_path(relative_path: str) -> Path | None:
    path = (PROJECT_DIR / unquote(relative_path)).resolve()
    allowed_roots = (
        IMAGES_RAW_DIR.resolve(),
        IMAGES_RECOGNIZED_DIR.resolve(),
        IMAGES_COMPRESSED_DIR.resolve(),
        CASE_MATERIALS_DIR.resolve(),
    )
    if any(path == root or root in path.parents for root in allowed_roots):
        return path
    return None


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self.send_json(build_status())
            return
        if parsed.path == "/api/recognition-status":
            self.send_json(build_recognition_status())
            return
        if parsed.path == "/api/feishu-status":
            self.send_json(build_feishu_status())
            return
        if parsed.path == "/api/agent-status":
            self.send_json(build_agent_status())
            return
        if parsed.path == "/api/similarity-status":
            self.send_json(build_similarity_status())
            return
        if parsed.path == "/api/file":
            params = parse_qs(parsed.query)
            self.send_project_file(params.get("path", [""])[0])
            return
        self.send_static(parsed.path)

    def do_POST(self) -> None:
        if not is_write_authorized(self.headers):
            self.send_json({
                "ok": False,
                "message": "Dashboard 写操作需要访问口令。请设置正确的 YQS_DASHBOARD_TOKEN。",
            }, status=401)
            return

        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/load-images":
                IMAGES_RAW_DIR.mkdir(parents=True, exist_ok=True)
                raw_count = len(iter_images(IMAGES_RAW_DIR))
                self.send_json({
                    "ok": True,
                    "message": f"images_raw 已更新，当前 {raw_count} 张图片。",
                    "status": build_status(),
                })
                return
            if parsed.path == "/api/clear-images-raw":
                removed_count = clear_directory_files(IMAGES_RAW_DIR)
                IMAGES_RAW_DIR.mkdir(parents=True, exist_ok=True)
                self.send_json({
                    "ok": True,
                    "message": f"已清空 images_raw，删除 {removed_count} 个文件。",
                    "status": build_status(),
                })
                return
            if parsed.path == "/api/compress-images":
                ok, message = compress_images_raw()
                self.send_json({
                    "ok": ok,
                    "message": message,
                    "status": build_status(),
                    "recognition": build_recognition_status(),
                }, status=200 if ok else 409)
                return
            if parsed.path == "/api/start-recognition":
                started, message = start_recognition_job()
                self.send_json({
                    "ok": started,
                    "message": message,
                    "recognition": build_recognition_status(),
                    "status": build_status(),
                }, status=200 if started else 409)
                return
            if parsed.path == "/api/start-agent-workflow":
                started, message = start_agent_workflow()
                self.send_json({
                    "ok": started,
                    "message": message,
                    "agent": build_agent_status(),
                    "status": build_status(),
                }, status=200 if started else 409)
                return
            if parsed.path == "/api/check-similarity":
                similarity = similar_images.scan_similar_images()
                self.send_json({
                    "ok": True,
                    "message": f"相似图片检查完成，发现 {similarity['pairCount']} 组疑似相似图片。",
                    "similarity": similarity,
                    "status": build_status(),
                })
                return
            if parsed.path == "/api/delete-similar-image":
                payload = self.read_json_body()
                result = similar_images.delete_compressed_image(str(payload.get("path", "")))
                if not result.get("ok"):
                    self.send_json(result, status=400)
                    return
                self.send_json({
                    **result,
                    "status": build_status(),
                })
                return
            if parsed.path == "/api/test-feishu":
                feishu_client.send_text_message(
                    "YQS-Imagerepo 飞书通知测试成功。\nDashboard 已完成飞书消息通道接入。"
                )
                self.send_json({
                    "ok": True,
                    "message": "飞书测试消息已发送。",
                    "feishu": build_feishu_status(),
                    "status": build_status(),
                })
                return
            self.send_error(404, "Not found")
        except Exception as exc:
            self.send_json({"ok": False, "message": str(exc)}, status=500)

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body)

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_project_file(self, relative_path: str) -> None:
        path = safe_project_path(relative_path)
        if path is None or not path.is_file():
            self.send_error(404, "File not found")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, request_path: str) -> None:
        relative_path = "index.html" if request_path in ("", "/") else request_path.lstrip("/")
        path = (DASHBOARD_DIR / relative_path).resolve()
        if DASHBOARD_DIR.resolve() not in path.parents and path != DASHBOARD_DIR.resolve():
            self.send_error(404, "Not found")
            return
        if path.is_dir():
            path = path / "index.html"
        if not path.is_file():
            self.send_error(404, "Not found")
            return
        body = path.read_bytes()
        content_type = STATIC_EXTENSIONS.get(path.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    os.chdir(PROJECT_DIR)
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"素材可视化页面: http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
