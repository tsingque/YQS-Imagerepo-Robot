#!/usr/bin/env python3
"""Batch AI recognition worker for YQS-Imagerepo."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

import glm_client
import kimi_client
import bitable_sync
import feishu_client
import material_writers
from env_loader import load_env


PYTHON_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PYTHON_DIR.parent
IMAGES_COMPRESSED_DIR = PROJECT_DIR / "image_compressor" / "images_compressed"
RULES_PATH = PROJECT_DIR / "rules" / "image_recognition.md"
RUNTIME_DIR = PROJECT_DIR / "runtime"
STATE_PATH = RUNTIME_DIR / "recognition_state.json"
PROCESSED_PATH = RUNTIME_DIR / "processed_files.json"
TOKEN_USAGE_PATH = RUNTIME_DIR / "ai_token_usage.json"
ALERTS_PATH = RUNTIME_DIR / "alerts.json"
CASE_MATERIALS_DIR = PROJECT_DIR / "case_materials"
GENERAL_MATERIALS_FOLDER = "通用素材库"

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch recognize images in image_compressor/images_compressed with the configured AI provider.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of unprocessed images to recognize. 0 means all.")
    parser.add_argument("--dry-run", action="store_true", help="Scan and report only; do not call the configured AI provider or write files.")
    return parser.parse_args()


def now_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def current_provider() -> str:
    load_env(PROJECT_DIR)
    return os.getenv("AI_PROVIDER", "glm").strip().lower() or "glm"


def provider_label() -> str:
    provider = current_provider()
    if provider in {"kimi", "moonshot"}:
        return "Kimi"
    return "GLM"


def recognize_with_provider(image_path: Path, rules_prompt: str, metadata: dict[str, str]) -> dict:
    provider = current_provider()
    if provider in {"kimi", "moonshot"}:
        return kimi_client.recognize_image(image_path, rules_prompt, metadata)
    if provider == "glm":
        return glm_client.recognize_image(image_path, rules_prompt, metadata)
    raise ValueError(f"不支持的 AI_PROVIDER: {provider}。可选值: glm, kimi")


def read_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def update_state(**updates) -> None:
    state = read_json(STATE_PATH, {})
    state.update(updates)
    state["updated_at"] = now_label()
    write_json(STATE_PATH, state)


def load_processed() -> dict:
    return read_json(PROCESSED_PATH, {})


def save_processed(processed: dict) -> None:
    write_json(PROCESSED_PATH, processed)


def list_images() -> list[Path]:
    if not IMAGES_COMPRESSED_DIR.is_dir():
        return []
    return sorted(
        path
        for path in IMAGES_COMPRESSED_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def recognized_output_exists(record: dict) -> bool:
    recognized_path = str(record.get("recognized_path", "")).strip()
    if not recognized_path:
        return False
    path = Path(recognized_path)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    return path.is_file()


def cleanup_processed_compressed_images(images: list[Path], processed: dict) -> tuple[list[str], list[str]]:
    """Remove stale compressed copies, and restore records whose output is missing."""
    deleted: list[str] = []
    restored: list[str] = []
    for image_path in images:
        if image_path.name not in processed:
            continue
        try:
            image_path.relative_to(IMAGES_COMPRESSED_DIR)
        except ValueError:
            continue
        if not recognized_output_exists(processed[image_path.name]):
            processed.pop(image_path.name, None)
            restored.append(image_path.name)
            continue
        image_path.unlink()
        deleted.append(image_path.name)
    return deleted, restored


def image_resolution(image_path: Path) -> str:
    with Image.open(image_path) as image:
        return f"{image.width}x{image.height}"


def file_size_label(image_path: Path) -> str:
    size = image_path.stat().st_size
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} B"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def safe_folder_name(text: str) -> str:
    cleaned = "".join("_" if char in '\\/:*?"<>|' else char for char in text.strip())
    cleaned = "_".join(part for part in cleaned.split() if part)
    return cleaned.strip("._ ") or GENERAL_MATERIALS_FOLDER


def split_project_and_name(raw_name: str) -> tuple[str, str]:
    name = raw_name.strip()
    for separator in ("-", "－", "—", "–"):
        if separator not in name:
            continue
        project, material_name = name.split(separator, 1)
        project = project.strip()
        material_name = material_name.strip()
        if project and material_name:
            return project, material_name
    return "", name


def target_material_folder(metadata: dict[str, str]) -> Path:
    project, _ = split_project_and_name(metadata.get("名字", ""))
    folder = safe_folder_name(project) if project else GENERAL_MATERIALS_FOLDER
    return CASE_MATERIALS_DIR / folder


def move_to_case_materials(image_path: Path, suggested_filename: str, metadata: dict[str, str]) -> Path:
    target_dir = target_material_folder(metadata)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = unique_path(target_dir / suggested_filename)
    shutil.move(str(image_path), str(target))
    return target


def token_number(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def normalize_token_usage(raw_usage: dict | None, provider: str) -> dict[str, int | str]:
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    prompt_tokens = token_number(usage.get("prompt_tokens") or usage.get("input_tokens"))
    completion_tokens = token_number(usage.get("completion_tokens") or usage.get("output_tokens"))
    total_tokens = token_number(usage.get("total_tokens") or usage.get("total"))
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    return {
        "provider": provider,
        "model": str(usage.get("model") or ""),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def add_alert(level: str, message: str) -> None:
    alerts = read_json(ALERTS_PATH, [])
    if not isinstance(alerts, list):
        alerts = []
    alerts.append({"level": level, "message": message, "created_at": now_label()})
    write_json(ALERTS_PATH, alerts[-100:])


def record_token_usage(image_name: str, raw_usage: dict | None, provider: str) -> dict[str, int | str]:
    usage = normalize_token_usage(raw_usage, provider)
    payload = read_json(TOKEN_USAGE_PATH, {})
    if not isinstance(payload, dict):
        payload = {}
    totals = payload.get("totals")
    if not isinstance(totals, dict):
        totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0}
    totals["prompt_tokens"] = token_number(totals.get("prompt_tokens")) + token_number(usage["prompt_tokens"])
    totals["completion_tokens"] = token_number(totals.get("completion_tokens")) + token_number(usage["completion_tokens"])
    totals["total_tokens"] = token_number(totals.get("total_tokens")) + token_number(usage["total_tokens"])
    totals["calls"] = token_number(totals.get("calls")) + 1
    events = payload.get("events")
    if not isinstance(events, list):
        events = []
    event = {**usage, "image": image_name, "created_at": now_label()}
    events.append(event)
    payload = {"totals": totals, "events": events[-1000:], "updated_at": now_label()}
    write_json(TOKEN_USAGE_PATH, payload)

    threshold = token_number(os.getenv("AI_TOKEN_WARN_TOTAL", "0"))
    if threshold > 0 and totals["total_tokens"] >= threshold:
        add_alert("warning", f"AI token 累计用量 {totals['total_tokens']}，已达到阈值 {threshold}。")
    return usage


def build_metadata(image_path: Path) -> dict[str, str]:
    metadata = {
        "source_path": str(image_path.relative_to(PROJECT_DIR)),
        "resolution": image_resolution(image_path),
        "file_size": file_size_label(image_path),
    }
    bitable_metadata = bitable_sync.load_metadata_for_image(image_path.name)
    for key in ["record_id", "名字", "描述", "来源", "是否可用", "原始附件名", "本地原图路径"]:
        if bitable_metadata.get(key):
            metadata[key] = str(bitable_metadata[key])
    project, material_name = split_project_and_name(metadata.get("名字", ""))
    if project:
        metadata["项目"] = project
    if material_name:
        metadata["素材名"] = material_name
    return metadata


def run(limit: int = 0, dry_run: bool = False) -> dict:
    load_env(PROJECT_DIR)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    rules_prompt = RULES_PATH.read_text(encoding="utf-8")
    processed = load_processed()
    all_compressed_images = list_images()
    deleted_processed, restored_missing = ([], []) if dry_run else cleanup_processed_compressed_images(all_compressed_images, processed)
    if deleted_processed or restored_missing:
        save_processed(processed)
    images = [image for image in all_compressed_images if image.name not in processed and image.exists()]
    if limit > 0:
        images = images[:limit]

    summary = {
        "total": len(images),
        "completed": 0,
        "failed": 0,
        "skipped": len(processed),
        "deleted_processed_compressed": len(deleted_processed),
        "restored_missing_output": len(restored_missing),
        "started_at": now_label(),
        "finished_at": "",
        "errors": [],
        "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0},
    }
    update_state(
        running=not dry_run,
        provider=current_provider(),
        total=summary["total"],
        completed=0,
        failed=0,
        skipped=summary["skipped"],
        deleted_processed_compressed=summary["deleted_processed_compressed"],
        restored_missing_output=summary["restored_missing_output"],
        current_file="",
        message="dry-run: 已扫描待识图图片。" if dry_run else f"{provider_label()} 批量识图已开始。",
        errors=[],
    )

    if dry_run:
        summary["finished_at"] = now_label()
        update_state(running=False, message=f"dry-run 完成，待识图 {len(images)} 张。", finished_at=summary["finished_at"])
        return summary

    for index, image_path in enumerate(images, start=1):
        update_state(current_file=image_path.name, message=f"正在识图 {index}/{len(images)}: {image_path.name}")
        try:
            metadata = build_metadata(image_path)
            result = recognize_with_provider(image_path, rules_prompt, metadata)
            usage = record_token_usage(image_path.name, result.pop("_token_usage", None), current_provider())
            summary["token_usage"]["prompt_tokens"] += token_number(usage["prompt_tokens"])
            summary["token_usage"]["completion_tokens"] += token_number(usage["completion_tokens"])
            summary["token_usage"]["total_tokens"] += token_number(usage["total_tokens"])
            summary["token_usage"]["calls"] += 1
            record, appended = material_writers.write_recognition_result(result, metadata["resolution"])
            asset_path = move_to_case_materials(image_path, record["文件名"], metadata)
            bitable_sync.write_back_result(
                metadata.get("record_id", ""),
                "已完成",
                record=record,
                recognized_path=str(asset_path.relative_to(PROJECT_DIR)),
                compressed_path=metadata.get("source_path", ""),
            )
            processed[image_path.name] = {
                "recognized_at": now_label(),
                "record_id": metadata.get("record_id", ""),
                "suggested_filename": record["文件名"],
                "recognized_path": str(asset_path.relative_to(PROJECT_DIR)),
                "asset_path": str(asset_path.relative_to(PROJECT_DIR)),
                "target_folder": str(asset_path.parent.relative_to(PROJECT_DIR)),
                "appended_to_md": appended,
                "token_usage": usage,
            }
            save_processed(processed)
            summary["completed"] += 1
        except Exception as exc:
            summary["failed"] += 1
            summary["errors"].append({"file": image_path.name, "error": str(exc)})
            try:
                metadata = build_metadata(image_path)
                bitable_sync.write_back_result(
                    metadata.get("record_id", ""),
                    "失败",
                    compressed_path=metadata.get("source_path", ""),
                    error=str(exc),
                )
            except Exception:
                pass
        update_state(
            completed=summary["completed"],
            failed=summary["failed"],
            errors=summary["errors"][-20:],
            token_usage=summary["token_usage"],
        )
        time.sleep(float(os.getenv("GLM_BATCH_INTERVAL_SECONDS", "0.5")))

    summary["finished_at"] = now_label()
    update_state(
        running=False,
        current_file="",
        finished_at=summary["finished_at"],
        message=f"{provider_label()} 识图完成：成功 {summary['completed']} 张，失败 {summary['failed']} 张。",
    )
    try:
        feishu_client.notify_recognition_finished(summary)
    except Exception as exc:
        update_state(message=f"{provider_label()} 识图完成，但飞书通知失败: {exc}")
    return summary


def main() -> None:
    args = parse_args()
    summary = run(limit=args.limit, dry_run=args.dry_run)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
