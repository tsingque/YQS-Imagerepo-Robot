#!/usr/bin/env python3
"""Find visually similar images in image_compressor/images_compressed."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageOps


PYTHON_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PYTHON_DIR.parent
IMAGES_COMPRESSED_DIR = PROJECT_DIR / "image_compressor" / "images_compressed"
RUNTIME_DIR = PROJECT_DIR / "runtime"
REPORT_CSV_PATH = RUNTIME_DIR / "similar_images_report.csv"
REPORT_JSON_PATH = RUNTIME_DIR / "similar_images_report.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}

HASH_SIZE = 8
SAME_THRESHOLD = 3
HIGH_THRESHOLD = 8
MAYBE_THRESHOLD = 14


def relative_label(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def iter_images(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dhash(path: Path, hash_size: int = HASH_SIZE) -> int:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        pixels = list(image.getdata())

    value = 0
    for row in range(hash_size):
        offset = row * (hash_size + 1)
        for column in range(hash_size):
            left = pixels[offset + column]
            right = pixels[offset + column + 1]
            value = (value << 1) | int(left > right)
    return value


def hamming_distance(left: int, right: int) -> int:
    return bin(left ^ right).count("1")


def classify(distance: int, exact_duplicate: bool) -> tuple[str, str]:
    if exact_duplicate:
        return "完全重复", "建议只保留一张"
    if distance <= SAME_THRESHOLD:
        return "几乎同图", "建议只保留一张"
    if distance <= HIGH_THRESHOLD:
        return "高度相似", "建议人工确认是否重复"
    if distance <= MAYBE_THRESHOLD:
        return "可能相似", "可抽查确认"
    return "不同", ""


def image_url(path: Path) -> str:
    from urllib.parse import quote

    return f"/api/file?path={quote(relative_label(path))}"


def scan_similar_images(directory: Optional[Path] = None) -> dict[str, Any]:
    if directory is None:
        directory = IMAGES_COMPRESSED_DIR
    images = iter_images(directory)
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for path in images:
        try:
            records.append({
                "path": path,
                "name": path.name,
                "relative": relative_label(path),
                "directory": relative_label(path.parent),
                "sha256": file_sha256(path),
                "dhash": dhash(path),
                "size": path.stat().st_size,
            })
        except Exception as exc:
            errors.append({"file": path.name, "error": str(exc)})

    pairs: list[dict[str, Any]] = []
    for left, right in combinations(records, 2):
        exact_duplicate = left["sha256"] == right["sha256"]
        distance = 0 if exact_duplicate else hamming_distance(left["dhash"], right["dhash"])
        if not exact_duplicate and distance > MAYBE_THRESHOLD:
            continue
        level, suggestion = classify(distance, exact_duplicate)
        pairs.append({
            "left": left["relative"],
            "leftName": left["name"],
            "leftDir": left["directory"],
            "leftUrl": image_url(left["path"]),
            "right": right["relative"],
            "rightName": right["name"],
            "rightDir": right["directory"],
            "rightUrl": image_url(right["path"]),
            "distance": distance,
            "level": level,
            "suggestion": suggestion,
        })

    level_order = {"完全重复": 0, "几乎同图": 1, "高度相似": 2, "可能相似": 3}
    pairs.sort(key=lambda item: (level_order.get(item["level"], 9), item["distance"], item["leftName"], item["rightName"]))

    counts = {
        "exact": sum(1 for pair in pairs if pair["level"] == "完全重复"),
        "same": sum(1 for pair in pairs if pair["level"] == "几乎同图"),
        "high": sum(1 for pair in pairs if pair["level"] == "高度相似"),
        "maybe": sum(1 for pair in pairs if pair["level"] == "可能相似"),
    }
    summary = {
        "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "directory": relative_label(directory),
        "scanScope": "compressed",
        "imageCount": len(records),
        "pairCount": len(pairs),
        "counts": counts,
        "pairs": pairs[:100],
        "errors": errors,
        "csvPath": REPORT_CSV_PATH.relative_to(PROJECT_DIR).as_posix(),
    }
    write_reports(summary, pairs)
    return summary


def compressed_image_path(relative_path: str) -> Path | None:
    path = (PROJECT_DIR / relative_path).resolve()
    root = IMAGES_COMPRESSED_DIR.resolve()
    if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS and (path == root or root in path.parents):
        return path
    return None


def delete_compressed_image(relative_path: str) -> dict[str, Any]:
    path = compressed_image_path(relative_path)
    if path is None:
        return {"ok": False, "message": "只能删除 images_compressed 里的图片。"}

    deleted = relative_label(path)
    path.unlink()
    summary = scan_similar_images()
    return {
        "ok": True,
        "message": f"已删除压缩图：{Path(deleted).name}",
        "deleted": deleted,
        "similarity": summary,
    }


def write_reports(summary: dict[str, Any], pairs: list[dict[str, Any]]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with REPORT_CSV_PATH.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["图片A", "图片B", "相似等级", "哈希距离", "建议操作"])
        writer.writeheader()
        for pair in pairs:
            writer.writerow({
                "图片A": pair["left"],
                "图片B": pair["right"],
                "相似等级": pair["level"],
                "哈希距离": pair["distance"],
                "建议操作": pair["suggestion"],
            })


def read_report() -> dict[str, Any]:
    if not REPORT_JSON_PATH.is_file():
        return {
            "updatedAt": "",
            "directory": relative_label(IMAGES_COMPRESSED_DIR),
            "scanScope": "compressed",
            "imageCount": 0,
            "pairCount": 0,
            "counts": {"exact": 0, "same": 0, "high": 0, "maybe": 0},
            "pairs": [],
            "errors": [],
            "csvPath": REPORT_CSV_PATH.relative_to(PROJECT_DIR).as_posix(),
            "message": "尚未检查相似图片。",
        }
    return json.loads(REPORT_JSON_PATH.read_text(encoding="utf-8"))


def main() -> None:
    summary = scan_similar_images()
    print(f"扫描图片: {summary['imageCount']}")
    print(f"疑似相似: {summary['pairCount']} 组")
    print(f"报告: {summary['csvPath']}")


if __name__ == "__main__":
    main()
