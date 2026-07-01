#!/usr/bin/env python3
"""Sync Feishu Bitable image records into the local YQS raw image queue."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from env_loader import load_env
from feishu_bitable_client import FeishuBitableClient, bitable_status


PYTHON_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PYTHON_DIR.parent
IMAGES_RAW_DIR = PROJECT_DIR / "image_compressor" / "images_raw"
RUNTIME_DIR = PROJECT_DIR / "runtime"
BITABLE_FILE_MAP_PATH = RUNTIME_DIR / "bitable_file_map.json"
BITABLE_RECORDS_PATH = RUNTIME_DIR / "bitable_records.json"
BITABLE_STATE_PATH = RUNTIME_DIR / "bitable_sync_state.json"
ALERTS_PATH = RUNTIME_DIR / "alerts.json"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".heif"}
IMAGE_MAGIC_PREFIXES = (
    b"\xff\xd8\xff",  # jpg
    b"\x89PNG\r\n\x1a\n",
    b"GIF87a",
    b"GIF89a",
    b"BM",
    b"RIFF",  # webp starts with RIFF....WEBP
)


@dataclass
class BitableFieldConfig:
    name: str = "名字"
    description: str = "描述"
    file: str = "文件"
    source: str = "来源"
    usable: str = "是否可商用"


@dataclass
class ParsedRecord:
    record_id: str
    name: str
    description: str
    source: str
    usable: str
    attachments: list[dict[str, Any]]


def now_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def field_config_from_env() -> BitableFieldConfig:
    load_env(PROJECT_DIR)
    return BitableFieldConfig(
        name=os.getenv("FEISHU_BITABLE_FIELD_NAME", "名字"),
        description=os.getenv("FEISHU_BITABLE_FIELD_DESCRIPTION", "描述"),
        file=os.getenv("FEISHU_BITABLE_FIELD_FILE", "文件"),
        source=os.getenv("FEISHU_BITABLE_FIELD_SOURCE", "来源"),
        usable=os.getenv("FEISHU_BITABLE_FIELD_COMMERCIAL", os.getenv("FEISHU_BITABLE_FIELD_USABLE", "是否可商用")),
    )


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


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("name") or item.get("value") or "").strip())
            else:
                parts.append(str(item).strip())
        return "".join(part for part in parts if part).strip()
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value.get("value") or "").strip()
    return str(value).strip()


def attachment_values(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def parse_record(record: dict[str, Any], config: BitableFieldConfig) -> ParsedRecord:
    fields = record.get("fields", {}) if isinstance(record.get("fields"), dict) else {}
    commercial_value = fields.get(config.usable)
    if commercial_value is None and config.usable != "是否可用":
        commercial_value = fields.get("是否可用")
    return ParsedRecord(
        record_id=str(record.get("record_id") or record.get("id") or "").strip(),
        name=text_value(fields.get(config.name)),
        description=text_value(fields.get(config.description)),
        source=text_value(fields.get(config.source)),
        usable=text_value(commercial_value).lower(),
        attachments=attachment_values(fields.get(config.file)),
    )


def is_pending(record: ParsedRecord) -> bool:
    return True


def is_usable(record: ParsedRecord) -> bool:
    return record.usable.strip().lower() in {"有", "y", "yes", "true", "1", "可商用", "可用", "是"}


def commercial_label(record: ParsedRecord) -> str:
    return "有" if is_usable(record) else "无"


def safe_filename(text: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", text.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "image"


def target_filename(record: ParsedRecord, attachment: dict[str, Any]) -> str:
    source_name = str(attachment.get("name") or attachment.get("filename") or "image.png").strip()
    suffix = Path(source_name).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        suffix = ".png"
    stem = safe_filename(Path(source_name).stem)
    return f"{safe_filename(record.record_id)}_{stem}{suffix}"


def is_existing_image(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    try:
        header = path.read_bytes()[:16]
    except OSError:
        return False
    if header.startswith(b"RIFF"):
        return b"WEBP" in header
    return any(header.startswith(prefix) for prefix in IMAGE_MAGIC_PREFIXES)


def add_alert(level: str, message: str) -> None:
    alerts = read_json(ALERTS_PATH, [])
    if not isinstance(alerts, list):
        alerts = []
    alerts.append({"level": level, "message": message, "created_at": now_label()})
    write_json(ALERTS_PATH, alerts[-100:])


def check_capacity_alerts(record_count: int) -> list[str]:
    load_env(PROJECT_DIR)
    max_records = int(os.getenv("FEISHU_BITABLE_MAX_RECORDS", "20000") or "20000")
    ratios = [float(item) for item in os.getenv("FEISHU_BITABLE_WARN_RATIOS", "0.5,0.75,0.9").split(",") if item.strip()]
    messages = []
    for ratio in ratios:
        threshold = int(max_records * ratio)
        if record_count >= threshold:
            message = f"飞书多维表格记录数 {record_count}，已达到 {int(ratio * 100)}% 容量阈值 {threshold}。"
            add_alert("warning", message)
            messages.append(message)
    return messages


def metadata_for(record: ParsedRecord, attachment: dict[str, Any], local_path: Path) -> dict[str, Any]:
    return {
        "record_id": record.record_id,
        "名字": record.name,
        "描述": record.description,
        "来源": record.source,
        "是否可商用": commercial_label(record),
        "是否可用": record.usable,
        "原始附件名": str(attachment.get("name") or attachment.get("filename") or ""),
        "本地原图路径": str(local_path.relative_to(PROJECT_DIR) if local_path.is_absolute() else local_path),
        "synced_at": now_label(),
    }


def sync_bitable_to_raw(
    client: FeishuBitableClient | Any | None = None,
    config: BitableFieldConfig | None = None,
) -> dict[str, Any]:
    load_env(PROJECT_DIR)
    client = client or FeishuBitableClient()
    config = config or field_config_from_env()

    if not client.configured():
        result = {"ok": True, "skipped": True, "message": "未配置飞书多维表格，跳过同步。", "bitable": bitable_status()}
        write_json(BITABLE_STATE_PATH, {**result, "updated_at": now_label()})
        return result

    records = client.list_records(page_size=int(os.getenv("YQS_BITABLE_BATCH_LIMIT", "100") or "100"))
    check_capacity_alerts(len(records))
    if len(records) > int(os.getenv("YQS_BITABLE_BATCH_LIMIT", "100") or "100"):
        add_alert("warning", f"本次飞书多维表格拉取记录 {len(records)} 条，超过单次建议处理量。")

    file_map = read_json(BITABLE_FILE_MAP_PATH, {})
    record_map = read_json(BITABLE_RECORDS_PATH, {})
    if not isinstance(file_map, dict):
        file_map = {}
    if not isinstance(record_map, dict):
        record_map = {}

    summary = {
        "ok": True,
        "records": len(records),
        "pending": 0,
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "bitable": bitable_status(),
    }
    IMAGES_RAW_DIR.mkdir(parents=True, exist_ok=True)

    for raw_record in records:
        parsed = parse_record(raw_record, config)
        if not parsed.record_id or not is_pending(parsed):
            continue
        summary["pending"] += 1
        if not is_usable(parsed):
            summary["skipped"] += 1
            record_map[parsed.record_id] = {"record_id": parsed.record_id, "status": "已跳过", "updated_at": now_label()}
            continue
        if not parsed.attachments:
            summary["failed"] += 1
            message = "文件字段没有图片附件。"
            summary["errors"].append({"record_id": parsed.record_id, "error": message})
            continue
        for attachment in parsed.attachments:
            target = IMAGES_RAW_DIR / target_filename(parsed, attachment)
            if target.name in file_map and (not target.exists() or is_existing_image(target)):
                summary["skipped"] += 1
                continue
            if target.exists() and not is_existing_image(target):
                target.unlink()
            try:
                client.download_attachment(attachment, target)
                item = metadata_for(parsed, attachment, target)
                file_map[target.name] = item
                record_map[parsed.record_id] = item
                summary["downloaded"] += 1
            except Exception as exc:
                summary["failed"] += 1
                message = str(exc)
                summary["errors"].append({"record_id": parsed.record_id, "file": attachment.get("name"), "error": message})

    write_json(BITABLE_FILE_MAP_PATH, file_map)
    write_json(BITABLE_RECORDS_PATH, record_map)
    write_json(BITABLE_STATE_PATH, {**summary, "updated_at": now_label()})
    summary["ok"] = summary["failed"] == 0
    return summary


def load_metadata_for_image(image_name: str) -> dict[str, Any]:
    file_map = read_json(BITABLE_FILE_MAP_PATH, {})
    return file_map.get(image_name, {}) if isinstance(file_map, dict) else {}


def build_write_back_fields(
    config: BitableFieldConfig,
    status: str,
    record: dict[str, Any] | None = None,
    recognized_path: str = "",
    compressed_path: str = "",
    error: str = "",
) -> dict[str, Any]:
    return {}


def write_back_result(
    record_id: str,
    status: str,
    record: dict[str, Any] | None = None,
    recognized_path: str = "",
    compressed_path: str = "",
    error: str = "",
    client: FeishuBitableClient | Any | None = None,
    config: BitableFieldConfig | None = None,
) -> dict[str, Any]:
    if not record_id:
        return {"ok": True, "skipped": True, "message": "无多维表格 record_id，跳过写回。"}
    return {"ok": True, "skipped": True, "record_id": record_id, "message": "飞书多维表格只保留输入字段，处理结果仅写入本地。"}


def main() -> None:
    print(json.dumps(sync_bitable_to_raw(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
