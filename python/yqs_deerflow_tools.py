#!/usr/bin/env python3
"""DeerFlow tools for the YQS material repository workflow."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(_name):
        def decorator(fn):
            return fn

        return decorator

PYTHON_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PYTHON_DIR.parent
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import compress
import bitable_sync
import feishu_bitable_client
import feishu_client
import md_table_to_material_xlsx
import recognition_worker


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".heif"}
IMAGES_RAW_DIR = PROJECT_DIR / "image_compressor" / "images_raw"
IMAGES_COMPRESSED_DIR = PROJECT_DIR / "image_compressor" / "images_compressed"
CASE_MATERIALS_DIR = PROJECT_DIR / "case_materials"


def _iter_images(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def _safe_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def repository_status() -> dict[str, Any]:
    """Return the current repository processing status."""
    return {
        "ok": True,
        "directories": {
            "raw": str(IMAGES_RAW_DIR.relative_to(PROJECT_DIR)),
            "compressed": str(IMAGES_COMPRESSED_DIR.relative_to(PROJECT_DIR)),
            "finished": str(CASE_MATERIALS_DIR.relative_to(PROJECT_DIR)),
        },
        "counts": {
            "raw": len(_iter_images(IMAGES_RAW_DIR)),
            "compressed": len(_iter_images(IMAGES_COMPRESSED_DIR)),
            "finished": len(_iter_images(CASE_MATERIALS_DIR)),
        },
        "recognition": recognition_worker.read_json(recognition_worker.STATE_PATH, {}),
        "token_usage": recognition_worker.read_json(recognition_worker.TOKEN_USAGE_PATH, {}),
        "feishu": feishu_client.feishu_config_status(),
        "bitable": feishu_bitable_client.bitable_status(),
        "bitable_sync": recognition_worker.read_json(bitable_sync.BITABLE_STATE_PATH, {}),
    }


def sync_bitable_to_raw() -> dict[str, Any]:
    """Sync Feishu Bitable image records into images_raw."""
    return bitable_sync.sync_bitable_to_raw()


def compress_raw_images() -> dict[str, Any]:
    """Compress images_raw into images_compressed using the existing compressor."""
    raw_before = len(_iter_images(IMAGES_RAW_DIR))
    compressed_before = len(_iter_images(IMAGES_COMPRESSED_DIR))
    output = io.StringIO()
    exit_code = 0
    with contextlib.redirect_stdout(output):
        try:
            compress.main()
        except SystemExit as exc:
            exit_code = int(exc.code or 0)
    raw_after = len(_iter_images(IMAGES_RAW_DIR))
    compressed_after = len(_iter_images(IMAGES_COMPRESSED_DIR))
    compressed_delta = max(compressed_after - compressed_before, compressed_after if raw_before else 0)
    if exit_code not in (0,):
        return {"ok": False, "exit_code": exit_code, "output": output.getvalue()}
    if raw_before > 0 and compressed_delta <= 0:
        return {
            "ok": False,
            "exit_code": exit_code,
            "raw_before": raw_before,
            "raw_after": raw_after,
            "compressed_before": compressed_before,
            "compressed_after": compressed_after,
            "compressed": 0,
            "output": output.getvalue()[-4000:],
            "status": repository_status(),
        }
    return {
        "ok": True,
        "exit_code": exit_code,
        "raw_before": raw_before,
        "raw_after": raw_after,
        "deleted_raw": max(raw_before - raw_after, 0),
        "compressed_before": compressed_before,
        "compressed_after": compressed_after,
        "compressed": compressed_delta,
        "output": output.getvalue()[-4000:],
        "status": repository_status(),
    }


def run_glm_recognition(limit: int = 0, dry_run: bool = False) -> dict[str, Any]:
    """Run configured AI recognition on compressed images."""
    summary = recognition_worker.run(limit=limit, dry_run=dry_run)
    return {
        "ok": summary.get("failed", 0) == 0,
        "provider": recognition_worker.current_provider(),
        "summary": summary,
        "outputs": {
            "markdown": str((PROJECT_DIR / "案例素材清单_表格.md").relative_to(PROJECT_DIR)),
            "workbook": str((PROJECT_DIR / "案例素材清单.xlsx").relative_to(PROJECT_DIR)),
            "resolution_csv": str((PROJECT_DIR / "素材分辨率.csv").relative_to(PROJECT_DIR)),
            "materials_dir": str(CASE_MATERIALS_DIR.relative_to(PROJECT_DIR)),
        },
        "status": repository_status(),
    }


def append_md_table_to_xlsx(dry_run: bool = False) -> dict[str, Any]:
    """Append the extracted Markdown table into the material workbook."""
    args = ["--dry-run"] if dry_run else []
    output = io.StringIO()
    exit_code = 0
    old_argv = sys.argv[:]
    sys.argv = ["md_table_to_material_xlsx.py", *args]
    try:
        with contextlib.redirect_stdout(output):
            try:
                md_table_to_material_xlsx.main()
            except SystemExit as exc:
                exit_code = int(exc.code or 0)
    finally:
        sys.argv = old_argv
    return {
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "output": output.getvalue()[-4000:],
        "status": repository_status(),
    }


def send_feishu_summary(message: str) -> dict[str, Any]:
    """Send a text summary to the configured Feishu receiver."""
    feishu_client.send_text_message(message)
    return {"ok": True, "message": "飞书通知已发送。", "feishu": feishu_client.feishu_config_status()}


@tool("get_repository_status")
def get_repository_status_tool() -> str:
    """查看 YQS 素材库当前图片数量、识图状态和飞书配置状态。"""
    return _safe_json(repository_status())


@tool("compress_raw_images")
def compress_raw_images_tool() -> str:
    """压缩 image_compressor/images_raw 中的图片，输出到 image_compressor/images_compressed。"""
    return _safe_json(compress_raw_images())


@tool("sync_bitable_to_raw")
def sync_bitable_to_raw_tool() -> str:
    """从飞书多维表格拉取待处理图片附件，下载到 image_compressor/images_raw。"""
    return _safe_json(sync_bitable_to_raw())


@tool("run_glm_recognition")
def run_glm_recognition_tool(limit: int = 0, dry_run: bool = False) -> str:
    """对 image_compressor/images_compressed 中的压缩图进行已配置 AI Provider 批量识图。limit 为 0 表示全部处理。"""
    return _safe_json(run_glm_recognition(limit=limit, dry_run=dry_run))


@tool("append_md_table_to_xlsx")
def append_md_table_to_xlsx_tool(dry_run: bool = False) -> str:
    """把案例素材清单_表格.md 追加到案例素材清单.xlsx。仅在需要补录 Markdown 表格时调用。"""
    return _safe_json(append_md_table_to_xlsx(dry_run=dry_run))


@tool("send_feishu_summary")
def send_feishu_summary_tool(message: str) -> str:
    """向已配置的飞书群或用户发送文本通知。"""
    return _safe_json(send_feishu_summary(message))
