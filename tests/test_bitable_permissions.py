import unittest
from pathlib import Path

import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
PYTHON_DIR = PROJECT_DIR / "python"
sys.path.insert(0, str(PYTHON_DIR))

from feishu_bitable_client import FeishuBitableClient


class FakeBitableClient(FeishuBitableClient):
    def __init__(self):
        super().__init__(app_token="app-token", table_id="tbl")
        self.calls = []

    def request(self, method, path, payload=None, query=None, timeout=30):
        self.calls.append({"method": method, "path": path, "payload": payload, "query": query})
        if method == "GET" and path.endswith("/views"):
            return {"code": 0, "data": {"items": []}}
        if method == "POST" and path.endswith("/views"):
            return {"code": 0, "data": {"view": {"view_id": "vew1", "view_name": payload["view_name"], "view_type": payload["view_type"]}}}
        return {"code": 0, "data": {"ok": True}}


class BitablePermissionTests(unittest.TestCase):
    def test_grant_tenant_readable_updates_public_permission(self):
        client = FakeBitableClient()
        result = client.grant_tenant_readable()

        self.assertEqual(result["ok"], True)
        self.assertEqual(client.calls[0]["method"], "PATCH")
        self.assertEqual(client.calls[0]["path"], "/drive/v2/permissions/app-token/public")
        self.assertEqual(client.calls[0]["query"], {"type": "bitable"})
        self.assertEqual(client.calls[0]["payload"]["link_share_entity"], "tenant_readable")

    def test_grant_tenant_editable_updates_public_permission(self):
        client = FakeBitableClient()
        result = client.grant_tenant_editable()

        self.assertEqual(result["ok"], True)
        self.assertEqual(client.calls[0]["method"], "PATCH")
        self.assertEqual(client.calls[0]["path"], "/drive/v2/permissions/app-token/public")
        self.assertEqual(client.calls[0]["query"], {"type": "bitable"})
        self.assertEqual(client.calls[0]["payload"]["link_share_entity"], "tenant_editable")

    def test_add_reader_member_uses_view_permission(self):
        client = FakeBitableClient()
        result = client.add_reader_member("ou_xxx", member_type="openid")

        self.assertEqual(result["ok"], True)
        self.assertEqual(client.calls[0]["method"], "POST")
        self.assertEqual(client.calls[0]["path"], "/drive/v1/permissions/app-token/members")
        self.assertEqual(client.calls[0]["query"], {"type": "bitable"})
        self.assertEqual(client.calls[0]["payload"]["perm"], "view")
        self.assertEqual(client.calls[0]["payload"]["member_type"], "openid")
        self.assertEqual(client.calls[0]["payload"]["member_id"], "ou_xxx")

    def test_create_form_view_posts_view_schema(self):
        client = FakeBitableClient()
        result = client.create_form_view("图片上传表单视图")

        self.assertEqual(result["ok"], True)
        self.assertEqual(client.calls[0]["method"], "GET")
        self.assertEqual(client.calls[1]["method"], "POST")
        self.assertEqual(client.calls[1]["path"], "/bitable/v1/apps/app-token/tables/tbl/views")
        self.assertEqual(client.calls[1]["payload"]["view_name"], "图片上传表单视图")
        self.assertEqual(client.calls[1]["payload"]["view_type"], "form")
        self.assertEqual(result["view"]["view_type"], "form")


if __name__ == "__main__":
    unittest.main()
