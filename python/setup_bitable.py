#!/usr/bin/env python3
"""Create or validate the Feishu Bitable schema used by YQS Imagerepo."""

from __future__ import annotations

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
        config.file: ATTACHMENT_FIELD,
        config.source: TEXT_FIELD,
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


def setup_bitable() -> dict:
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
    cleanup = prune_extra_fields(client, set(fields.keys()))
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
    return {
        "ok": True,
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
        },
    }


def main() -> None:
    print(json.dumps(setup_bitable(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
