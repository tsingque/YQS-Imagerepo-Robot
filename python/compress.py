"""
Image Compressor for PPT Material Preparation

Strategy:
  JPG/JPEG -> quality 85, subsampling 4:2:0, optimize=True
  WebP     -> quality 85, method=6
  PNG      -> lossless optimize first; if > 500 KB, quantize to 256 colors (keeps alpha)
  All      -> resize if longest edge > 2560 px (maintains aspect ratio)

Output:
  image_compressor/images_compressed/   — compressed copies
  image_compressor/images_raw/          — originals are deleted after successful compression
  image_compressor/compression_report.md — per-file before/after report
"""

import os
import sys
from datetime import datetime
from PIL import Image

PYTHON_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PYTHON_DIR)
IMAGE_COMPRESSOR_DIR = os.path.join(PROJECT_DIR, "image_compressor")
INPUT_DIR = os.path.join(IMAGE_COMPRESSOR_DIR, "images_raw")
OUTPUT_DIR = os.path.join(IMAGE_COMPRESSOR_DIR, "images_compressed")
REPORT_PATH = os.path.join(IMAGE_COMPRESSOR_DIR, "compression_report.md")

MAX_DIM = 2560
JPG_QUALITY = 85
WEBP_QUALITY = 85
PNG_QUANTIZE_THRESHOLD = 500 * 1024  # 500 KB

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp"}


def format_size(n):
    if n >= 1024 * 1024:
        return f"{n / (1024*1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def compress_image(src_path, dst_path):
    """Compress one image. Returns (src_size, dst_size, actions)."""
    src_size = os.path.getsize(src_path)
    ext = os.path.splitext(src_path)[1].lower()

    with Image.open(src_path) as img:
        actions = []

        # Convert RGBA -> RGB for JPEG output (JPEG has no alpha)
        if ext in (".jpg", ".jpeg") and img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = bg
            actions.append("alpha→white")

        # Resize if needed
        w, h = img.size
        longest = max(w, h)
        if longest > MAX_DIM:
            ratio = MAX_DIM / longest
            new_size = (int(w * ratio), int(h * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            actions.append(f"resize {w}×{h}→{new_size[0]}×{new_size[1]}")

        # Save
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)

        if ext in (".jpg", ".jpeg"):
            img.save(dst_path, "JPEG", quality=JPG_QUALITY,
                     optimize=True, subsampling="4:2:0")
            actions.append(f"JPEG q{JPG_QUALITY}")

        elif ext == ".webp":
            img.save(dst_path, "WEBP", quality=WEBP_QUALITY, method=6)
            actions.append(f"WebP q{WEBP_QUALITY}")

        elif ext == ".png":
            # Pass 1: lossless optimize
            img.save(dst_path, "PNG", optimize=True)
            dst_size = os.path.getsize(dst_path)

            if dst_size > PNG_QUANTIZE_THRESHOLD and img.mode != "P":
                # Pass 2: quantize to 256 colors.
                # RGBA requires FASTOCTREE; RGB/Mono can use MEDIANCUT.
                method = Image.Quantize.FASTOCTREE if img.mode == "RGBA" else Image.Quantize.MEDIANCUT
                q_img = img.quantize(colors=256, method=method)
                q_img.save(dst_path, "PNG", optimize=True)
                dst_size = os.path.getsize(dst_path)
                actions.append("lossless → quantized 256c")
            else:
                actions.append("lossless optimize")

    dst_size = os.path.getsize(dst_path)
    return src_size, dst_size, ", ".join(actions)


def main():
    if not os.path.isdir(INPUT_DIR):
        print(f"错误: 未找到输入目录: {INPUT_DIR}")
        print("请创建 'image_compressor/images_raw/' 文件夹并放入图片。")
        sys.exit(1)

    files = sorted([
        f for f in os.listdir(INPUT_DIR)
        if os.path.splitext(f)[1].lower() in SUPPORTED
    ])

    if not files:
        print("image_compressor/images_raw/ 中未找到支持的图片文件。")
        print(f"支持格式: {', '.join(SUPPORTED)}")
        sys.exit(0)

    # Clean output folder
    if os.path.isdir(OUTPUT_DIR):
        for f in os.listdir(OUTPUT_DIR):
            os.remove(os.path.join(OUTPUT_DIR, f))
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"{'='*60}")
    print(f"图片压缩工具 — PPT 素材模式")
    print(f"源目录: {INPUT_DIR}")
    print(f"目标目录: {OUTPUT_DIR}")
    print(f"文件数: {len(files)}")
    print(f"{'='*60}\n")

    results = []
    total_src = 0
    total_dst = 0
    skipped = 0
    deleted_raw = 0
    errors = []

    for f in files:
        src = os.path.join(INPUT_DIR, f)
        dst = os.path.join(OUTPUT_DIR, f)

        try:
            src_size, dst_size, actions = compress_image(src, dst)
            ratio = (1 - dst_size / src_size) * 100 if src_size > 0 else 0
            results.append((f, src_size, dst_size, ratio, actions))
            total_src += src_size
            total_dst += dst_size
            os.remove(src)
            deleted_raw += 1
            status = "✓" if ratio > 0 else "="
            print(f"  {status} {f:40s} {format_size(src_size):>10s} → {format_size(dst_size):>10s}  ({ratio:5.1f}%)  [{actions}] 已删除原图")
        except Exception as e:
            errors.append((f, str(e)))
            print(f"  ✗ {f:40s} ERROR: {e}")
            skipped += 1

    # Write report
    overall_ratio = (1 - total_dst / total_src) * 100 if total_src > 0 else 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# 图片压缩报告",
        f"",
        f"> 生成时间: {now}  ",
        f"> 输入目录: `image_compressor/images_raw/` ({len(files)} 个文件)  ",
        f"> 输出目录: `image_compressor/images_compressed/`  ",
        f"> 压缩设置: JPG 质量{JPG_QUALITY} / WebP 质量{WEBP_QUALITY} / PNG 优先无损→大于{PNG_QUANTIZE_THRESHOLD//1024}KB 时量化 / 最长边限制 {MAX_DIM}px",
        f"",
        f"## 汇总",
        f"",
        f"| 指标 | 数值 |",
        f"|---|---|",
        f"| 原始总大小 | {format_size(total_src)} |",
        f"| 压缩后总大小 | {format_size(total_dst)} |",
        f"| 整体压缩率 | {overall_ratio:.1f}% |",
        f"| 已处理文件 | {len(results)} |",
        f"| 已删除原图 | {deleted_raw} |",
        f"| 跳过（错误） | {skipped} |",
        f"",
        f"## 逐文件明细",
        f"",
        f"| 文件名 | 原大小 | 压缩后 | 压缩率 | 操作 |",
        f"|--------|--------|--------|--------|------|",
    ]
    for f, src_sz, dst_sz, ratio, actions in results:
        sign = "-" if ratio < 0 else ""
        lines.append(
            f"| {f} | {format_size(src_sz)} | {format_size(dst_sz)} | {sign}{ratio:.1f}% | {actions} |"
        )

    if errors:
        lines.append("")
        lines.append("## 错误")
        lines.append("")
        for f, err in errors:
            lines.append(f"- **{f}**: {err}")

    with open(REPORT_PATH, "w", encoding="utf-8") as r:
        r.write("\n".join(lines) + "\n")

    print(f"\n{'='*60}")
    print(f"完成: {len(results)} 张已压缩, 已删除 {deleted_raw} 张原图, {skipped} 张跳过")
    print(f"总计: {format_size(total_src)} → {format_size(total_dst)} (减少 {overall_ratio:.1f}%)")
    print(f"报告: {REPORT_PATH}")


if __name__ == "__main__":
    main()
