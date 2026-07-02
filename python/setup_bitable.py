#!/usr/bin/env python3
"""Validate or explicitly apply the Feishu Bitable schema used by YQS Imagerepo."""

from __future__ import annotations

import argparse
import json

from bitable_sync import BitableFieldConfig
from feishu_bitable_client import FeishuBitableClient


TEXT_FIELD = 1
ATTACHMENT_FIELD = 17


def required_fields() -> dict[str, int]:
    config = BitableFieldConfig()
    return {
        config.name: TEXT_FIELD,
        config.description: TEXT_FIELD,
        config.project: TEXT_FIELD,
        config.file: ATTACHMENT_FIELD,
        config.source: TEXT_FIELD,
        config.source_subcategory: TEXT_FIELD,
        config.usable: TEXT_FIELD,
    }


def prune_extra_fields(client: FeishuBitableClient, keep_fields: set[str]) -> dict:
    deleted = []
    failed = []
    for field in client.list_fields():
        field_name = str(field.get("field_name") or "")
        field_id = str(field.get("field_id") or "")
        if not field_name or field_name in keep_fields:
            continue
        try:
            client.delete_field(field_id)
            deleted.append(field_name)
        except Exception as exc:
            failed.append({"field_name": field_name, "error": str(exc)})
    return {"deleted": deleted, "failed": failed}


def normalize_primary_name_field(client: FeishuBitableClient, primary_name: str = "名字") -> dict:
    fields = client.list_fields()
    primary = next((field for field in fields if field.get("is_primary")), None)
    if not primary or primary.get("field_name") == primary_name:
        return {"changed": False}

    deleted_duplicate = None
    for field in fields:
        if field.get("field_name") == primary_name and not field.get("is_primary"):
            client.delete_field(str(field.get("field_id")))
            deleted_duplicate = primary_name
            break

    updated = client.update_field(str(primary.get("field_id")), primary_name)
    return {"changed": True, "deleted_duplicate": deleted_duplicate, "updated": updated}


def _existing_field_names(fields: list[dict]) -> set[str]:
    return {str(field.get("field_name") or "") for field in fields if field.get("field_name")}


def _find_form_views(views: list[dict]) -> list[dict]:
    return [view for view in views if view.get("view_type") == "form"]


def validate_bitable(client: FeishuBitableClient | None = None) -> dict:
    client = client or FeishuBitableClient()
    fields = required_fields()
    existing_fields = client.list_fields()
    existing_names = _existing_field_names(existing_fields)
    views = client.list_views() if client.configured() else []
    missing = [field_name for field_name in fields if field_name not in existing_names]
    extra = sorted(name for name in existing_names if name not in fields)
    form_views = _find_form_views(views)
    return {
        "ok": client.configured() and not missing,
        "mode": "validate",
        "configured": client.configured(),
        "missing_fields": missing,
        "extra_fields": extra,
        "fields": sorted(existing_names),
        "form_views": form_views,
        "message": (
            "只读校验完成；未修改多维表格。"
            if client.configured()
            else "缺少 FEISHU_BITABLE_APP_TOKEN 或 FEISHU_BITABLE_TABLE_ID，未执行写入操作。"
        ),
        "env": {
            "FEISHU_BITABLE_APP_TOKEN": client.app_token,
            "FEISHU_BITABLE_TABLE_ID": client.table_id,
            "FEISHU_BITABLE_VIEW_ID": client.view_id,
            "FEISHU_BITABLE_FORM_VIEW_ID": str(form_views[0].get("view_id") or "") if form_views else "",
        },
    }


def setup_bitable(*, apply_changes: bool = False, prune_extra: bool = False) -> dict:
    if not apply_changes:
        return validate_bitable()

    client = FeishuBitableClient()
    created_app = None
    created_table = None
    if not client.app_token:
        created_app = client.create_app()
    if not client.table_id:
        created_table = client.create_table()
    primary = normalize_primary_name_field(client)
    fields = required_fields()
    schema = client.ensure_schema(fields)
    cleanup = (
        prune_extra_fields(client, set(fields.keys()))
        if prune_extra
        else {"deleted": [], "failed": [], "skipped": True}
    )
    permission = None
    try:
        permission = client.grant_tenant_editable()
    except Exception as exc:
        permission = {"ok": False, "error": str(exc)}
    form_view = None
    try:
        form_view = client.create_form_view()
    except Exception as exc:
        form_view = {"ok": False, "error": str(exc)}
    form_view_id = ""
    if isinstance(form_view, dict):
        view = form_view.get("view")
        if isinstance(view, dict):
            form_view_id = str(view.get("view_id") or "")
    return {
        "ok": True,
        "mode": "apply",
        "created_app": created_app,
        "created_table": created_table,
        "primary": primary,
        "schema": schema,
        "cleanup": cleanup,
        "permission": permission,
        "form_view": form_view,
        "env": {
            "FEISHU_BITABLE_APP_TOKEN": client.app_token,
            "FEISHU_BITABLE_TABLE_ID": client.table_id,
            "FEISHU_BITABLE_VIEW_ID": client.view_id,
            "FEISHU_BITABLE_FORM_VIEW_ID": form_view_id,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate or apply the YQS Feishu Bitable schema.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create/update table, fields, permissions and form view. Default is read-only validation.",
    )
    parser.add_argument(
        "--prune-extra",
        action="store_true",
        help="When used with --apply, delete fields that are not part of the expected schema.",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            setup_bitable(apply_changes=args.apply, prune_extra=args.prune_extra),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
