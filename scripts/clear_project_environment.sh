#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
BACKUP_ROOT="${YQS_CLEAN_BACKUP_DIR:-"$ROOT_DIR/.cleanup_backups"}"
TIMESTAMP="${YQS_CLEAN_TIMESTAMP:-"$(date +%Y%m%d_%H%M%S)"}"
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"

ASSUME_YES=0
DRY_RUN=0
INCLUDE_ENV=0
INCLUDE_FEISHU_ECHO_FOLDER=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/clear_project_environment.sh [options]

Options:
  -y, --yes       Run without interactive confirmation.
  --dry-run       Print what would be cleared without changing files.
  --include-env   Also clear local environment/config files such as .env and config.yaml.
  --include-feishu-echo-folder
                  Also delete the Feishu Drive echo folder recorded in runtime state.
  -h, --help      Show this help.

Default behavior clears local workflow data only:
  - runtime state
  - uploaded/compressed/recognized images
  - classified case_materials images
  - generated material export rows

The script moves removable data into .cleanup_backups/<timestamp>/ before clearing.
Set YQS_CLEAN_BACKUP_DIR to put backups outside the project directory.
Template files such as .env.example and config.example.yaml are never removed.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes)
      ASSUME_YES=1
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    --include-env)
      INCLUDE_ENV=1
      ;;
    --include-feishu-echo-folder)
      INCLUDE_FEISHU_ECHO_FOLDER=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

FLOW_DIRS=(
  ".deer-flow"
  "runtime"
  "case_materials"
  "image_compressor/images_raw"
  "image_compressor/images_compressed"
  "image_compressor/images_recognized"
  "feishu_trans_repo"
  "feishu-trans-repo"
  "md_trans_repo"
  "logs"
  "deer-flow/backend/.deer-flow"
  "deer-flow/logs"
)

FLOW_FILES=(
  "image_compressor/compression_report.md"
  ".~案例素材清单.xlsx"
)

ENV_FILES=(
  ".env"
  "config.yaml"
  "deer-flow/.env"
  "deer-flow/config.yaml"
  "deer-flow/extensions_config.json"
  "deer-flow/frontend/.env"
  "deer-flow/backend/.env"
)

EMPTY_DIRS=(
  "runtime"
  "case_materials"
  "image_compressor/images_raw"
  "image_compressor/images_compressed"
  "image_compressor/images_recognized"
)

exists_rel() {
  local rel="$1"
  [[ -e "$ROOT_DIR/$rel" || -L "$ROOT_DIR/$rel" ]]
}

unique_backup_target() {
  local rel="$1"
  local target="$BACKUP_DIR/$rel"
  local counter=1
  while [[ -e "$target" || -L "$target" ]]; do
    target="$BACKUP_DIR/$rel.$counter"
    counter=$((counter + 1))
  done
  printf '%s\n' "$target"
}

move_to_backup() {
  local rel="$1"
  local source="$ROOT_DIR/$rel"
  if ! exists_rel "$rel"; then
    return
  fi

  local target
  target="$(unique_backup_target "$rel")"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] move $rel -> ${target#$ROOT_DIR/}"
    return
  fi

  mkdir -p "$(dirname "$target")"
  mv "$source" "$target"
  echo "moved $rel -> ${target#$ROOT_DIR/}"
}

ensure_empty_dirs() {
  local rel
  for rel in "${EMPTY_DIRS[@]}"; do
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "[dry-run] ensure empty dir $rel"
      continue
    fi
    mkdir -p "$ROOT_DIR/$rel"
  done
}

reset_material_exports() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] reset 案例素材清单_表格.md, 素材分辨率.csv, 案例素材清单.xlsx"
    return
  fi

  python3 - "$ROOT_DIR" "$BACKUP_DIR" <<'PY'
from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
backup_dir = Path(sys.argv[2])

md_headers = [
    "分类",
    "文件名",
    "案例名称",
    "图片内容",
    "想放在哪（章节/论点）",
    "配图说明文字（图注/要点）",
    "关键数据",
    "来源/版权",
    "状态",
]


def backup_copy(rel: str) -> None:
    source = root / rel
    if not source.exists():
        return
    target = backup_dir / rel
    counter = 1
    while target.exists():
        target = backup_dir / f"{rel}.{counter}"
        counter += 1
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def reset_markdown() -> None:
    rel = "案例素材清单_表格.md"
    backup_copy(rel)
    header = "| " + " | ".join(md_headers) + " |"
    separator = "|" + "|".join(["---"] * len(md_headers)) + "|"
    (root / rel).write_text(header + "\n" + separator + "\n", encoding="utf-8")


def reset_csv() -> None:
    rel = "素材分辨率.csv"
    backup_copy(rel)
    with (root / rel).open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["filename", "resolution"])
        writer.writeheader()


def reset_workbook() -> None:
    rel = "案例素材清单.xlsx"
    workbook_path = root / rel
    if not workbook_path.exists():
        return
    backup_copy(rel)
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError as exc:
        raise SystemExit("openpyxl is required to reset 案例素材清单.xlsx") from exc

    workbook = load_workbook(workbook_path)
    for sheet in workbook.worksheets:
        if sheet.max_row > 1:
            sheet.delete_rows(2, sheet.max_row - 1)
    workbook.save(workbook_path)


reset_markdown()
reset_csv()
reset_workbook()
PY
  echo "reset material export files"
}

confirm() {
  if [[ "$DRY_RUN" -eq 1 || "$ASSUME_YES" -eq 1 ]]; then
    return
  fi

  echo "This will clear local YQS workflow data under:"
  echo "  $ROOT_DIR"
  echo "A backup will be written to:"
  echo "  $BACKUP_DIR"
  if [[ "$INCLUDE_ENV" -eq 1 ]]; then
    echo "Environment/config files will also be moved into the backup."
  fi
  if [[ "${INCLUDE_FEISHU_ECHO_FOLDER:-0}" -eq 1 ]]; then
    echo "The Feishu Drive echo folder recorded in runtime state will also be deleted."
  fi
  local answer
  if ! read -r -p "Continue? [y/N] " answer; then
    exit 1
  fi
  case "$answer" in
    y|Y|yes|YES)
      ;;
    *)
      echo "Canceled."
      exit 1
      ;;
  esac
}

delete_feishu_echo_folder() {
  if [[ "${INCLUDE_FEISHU_ECHO_FOLDER:-0}" -ne 1 ]]; then
    return
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] delete Feishu echo folder recorded in runtime/feishu_echo_drive_folder.json"
    return
  fi
  if [[ ! -f "$ROOT_DIR/runtime/feishu_echo_drive_folder.json" ]]; then
    echo "skip Feishu echo folder delete: runtime/feishu_echo_drive_folder.json not found"
    return
  fi
  python3 "$ROOT_DIR/python/feishu_knowledge_base.py" \
    --echo-folder-state "$ROOT_DIR/runtime/feishu_echo_drive_folder.json" \
    --delete-echo-folder \
    --clear-echo-folder-state
}

main() {
  echo "YQS project cleanup"
  echo "root: $ROOT_DIR"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "mode: dry-run"
  elif [[ "$INCLUDE_ENV" -eq 1 ]]; then
    echo "mode: workflow data + environment config"
  else
    echo "mode: workflow data only"
  fi
  echo "backup: $BACKUP_DIR"

  confirm

  delete_feishu_echo_folder

  local rel
  for rel in "${FLOW_DIRS[@]}"; do
    move_to_backup "$rel"
  done
  for rel in "${FLOW_FILES[@]}"; do
    move_to_backup "$rel"
  done

  reset_material_exports
  ensure_empty_dirs

  if [[ "$INCLUDE_ENV" -eq 1 ]]; then
    for rel in "${ENV_FILES[@]}"; do
      move_to_backup "$rel"
    done
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "Dry-run complete. No files were changed."
  else
    echo "Cleanup complete."
    echo "Backup directory: $BACKUP_DIR"
    echo "Next environment setup: bash scripts/configure_env_ubuntu.sh"
  fi
}

main
