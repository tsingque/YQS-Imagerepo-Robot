#!/usr/bin/env python3
"""Local web wizard for writing YQS .env files on Ubuntu workstations."""

from __future__ import annotations

import html
import os
import secrets
import stat
import sys
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
HOST = os.getenv("YQS_ENV_WIZARD_HOST", "127.0.0.1")
PORT = int(os.getenv("YQS_ENV_WIZARD_PORT", "8787"))


FIELDS = [
    {
        "title": "1/4 AI 识图配置",
        "description": "配置图片识别使用的模型供应商。GLM 和 Kimi 可以都填，实际使用由 AI_PROVIDER 决定。",
        "fields": [
            ("AI_PROVIDER", "识图供应商", "kimi", "select", "glm,kimi"),
            ("GLM_API_KEY", "GLM API Key", "", "password", ""),
            ("GLM_MODEL", "GLM 模型", "glm-5v-turbo", "text", ""),
            ("GLM_API_BASE", "GLM Chat Completions 地址", "https://open.bigmodel.cn/api/paas/v4/chat/completions", "text", ""),
            ("GLM_OPENAI_BASE_URL", "GLM OpenAI 兼容地址", "https://open.bigmodel.cn/api/paas/v4", "text", ""),
            ("GLM_TIMEOUT_SECONDS", "GLM 超时时间", "120", "number", ""),
            ("GLM_BATCH_INTERVAL_SECONDS", "GLM 批处理间隔", "0.5", "text", ""),
            ("KIMI_API_KEY", "Kimi / Moonshot API Key", "", "password", ""),
            ("KIMI_MODEL", "Kimi 模型", "kimi-k2.6", "text", ""),
            ("KIMI_API_BASE", "Kimi Chat Completions 地址", "https://api.moonshot.cn/v1/chat/completions", "text", ""),
            ("KIMI_TIMEOUT_SECONDS", "Kimi 超时时间", "120", "number", ""),
            ("AI_TOKEN_WARN_TOTAL", "AI token 累计告警阈值，0 表示不告警", "0", "number", ""),
        ],
    },
    {
        "title": "2/4 YQS / 飞书多维表格配置",
        "description": "配置素材处理、Dashboard、飞书机器人和多维表格主输入源。",
        "fields": [
            ("YQS_DEERFLOW_MODE", "DeerFlow 执行模式", "direct", "select", "direct,agent"),
            ("YQS_DEERFLOW_MODEL", "DeerFlow 模型名", "glm-agent", "text", ""),
            ("YQS_DASHBOARD_TOKEN", "Dashboard 写操作口令", "", "password", ""),
            ("YQS_DASHBOARD_HOST", "Dashboard 监听地址", "127.0.0.1", "text", ""),
            ("YQS_DASHBOARD_PORT", "Dashboard 端口", "8765", "number", ""),
            ("YQS_AI_TIMEOUT_SECONDS", "单张 AI 识图超时时间", "120", "number", ""),
            ("FEISHU_APP_ID", "飞书应用 App ID", "", "password", ""),
            ("FEISHU_APP_SECRET", "飞书应用 App Secret", "", "password", ""),
            ("FEISHU_RECEIVE_ID_TYPE", "飞书通知 receive_id 类型", "chat_id", "select", "chat_id,open_id,user_id,email"),
            ("FEISHU_RECEIVE_ID", "飞书通知 receive_id，可留空", "", "text", ""),
            ("FEISHU_NOTIFY_ON_RECOGNITION", "识图完成后发送飞书通知", "true", "select", "true,false"),
            ("FEISHU_BITABLE_APP_TOKEN", "多维表格 app_token", "", "password", ""),
            ("FEISHU_BITABLE_TABLE_ID", "多维表格 table_id", "", "text", ""),
            ("FEISHU_BITABLE_VIEW_ID", "多维表格 view_id / 表单 view_id", "", "text", ""),
            ("FEISHU_BITABLE_FIELD_NAME", "字段名：名字", "名字", "text", ""),
            ("FEISHU_BITABLE_FIELD_DESCRIPTION", "字段名：描述", "描述", "text", ""),
            ("FEISHU_BITABLE_FIELD_FILE", "字段名：文件", "文件", "text", ""),
            ("FEISHU_BITABLE_FIELD_SOURCE", "字段名：来源", "来源", "text", ""),
            ("FEISHU_BITABLE_FIELD_USABLE", "字段名：是否可用", "是否可用", "text", ""),
            ("FEISHU_BITABLE_MAX_RECORDS", "多维表格容量上限", "20000", "number", ""),
            ("FEISHU_BITABLE_WARN_RATIOS", "容量告警比例", "0.5,0.75,0.9", "text", ""),
            ("YQS_BITABLE_BATCH_LIMIT", "单次处理建议上限", "100", "number", ""),
        ],
    },
    {
        "title": "3/4 DeerFlow 后端模型与认证配置",
        "description": "配置 DeerFlow 普通聊天模型、搜索工具和后端认证密钥。",
        "fields": [
            ("DEEPSEEK_API_KEY", "DeepSeek API Key", "", "password", ""),
            ("SERPER_API_KEY", "Serper API Key，可留空", "", "password", ""),
            ("TAVILY_API_KEY", "Tavily API Key，可留空", "", "password", ""),
            ("JINA_API_KEY", "Jina API Key，可留空", "", "password", ""),
            ("INFOQUEST_API_KEY", "InfoQuest API Key，可留空", "", "password", ""),
            ("GATEWAY_CORS_ORIGINS", "Gateway CORS Origins，可留空", "", "text", ""),
            ("GATEWAY_ENABLE_DOCS", "是否开启 Gateway 文档", "true", "select", "true,false"),
            ("AUTH_JWT_SECRET", "JWT Secret", "__GENERATE__", "password", ""),
            ("DEER_FLOW_INTERNAL_AUTH_TOKEN", "DeerFlow 内部调用 Token", "__GENERATE__", "password", ""),
            ("DEER_FLOW_AUTH_DISABLED", "是否关闭 DeerFlow 登录，生产建议 0", "0", "select", "0,1"),
        ],
    },
    {
        "title": "4/4 前端 / SSR 配置",
        "description": "如果使用统一 nginx，前两个 public 地址通常可以留空。",
        "fields": [
            ("NEXT_PUBLIC_BACKEND_BASE_URL", "前端访问后端地址，可留空", "", "text", ""),
            ("NEXT_PUBLIC_LANGGRAPH_BASE_URL", "前端访问 LangGraph 地址，可留空", "", "text", ""),
            ("DEER_FLOW_INTERNAL_GATEWAY_BASE_URL", "容器内部 Gateway 地址", "http://gateway:8001", "text", ""),
            ("DEER_FLOW_TRUSTED_ORIGINS", "可信来源", "http://localhost:2026,http://127.0.0.1:2026", "text", ""),
        ],
    },
]


ROOT_ENV_KEYS = [
    "AI_PROVIDER",
    "GLM_API_KEY",
    "GLM_MODEL",
    "GLM_API_BASE",
    "GLM_OPENAI_BASE_URL",
    "GLM_TIMEOUT_SECONDS",
    "GLM_BATCH_INTERVAL_SECONDS",
    "KIMI_API_KEY",
    "KIMI_MODEL",
    "KIMI_API_BASE",
    "KIMI_TIMEOUT_SECONDS",
    "AI_TOKEN_WARN_TOTAL",
    "YQS_DEERFLOW_MODE",
    "YQS_DEERFLOW_MODEL",
    "YQS_DASHBOARD_TOKEN",
    "YQS_DASHBOARD_HOST",
    "YQS_DASHBOARD_PORT",
    "YQS_AI_TIMEOUT_SECONDS",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_RECEIVE_ID_TYPE",
    "FEISHU_RECEIVE_ID",
    "FEISHU_NOTIFY_ON_RECOGNITION",
    "FEISHU_BITABLE_APP_TOKEN",
    "FEISHU_BITABLE_TABLE_ID",
    "FEISHU_BITABLE_VIEW_ID",
    "FEISHU_BITABLE_FIELD_NAME",
    "FEISHU_BITABLE_FIELD_DESCRIPTION",
    "FEISHU_BITABLE_FIELD_FILE",
    "FEISHU_BITABLE_FIELD_SOURCE",
    "FEISHU_BITABLE_FIELD_USABLE",
    "FEISHU_BITABLE_MAX_RECORDS",
    "FEISHU_BITABLE_WARN_RATIOS",
    "YQS_BITABLE_BATCH_LIMIT",
]

DEER_ENV_KEYS = [
    "SERPER_API_KEY",
    "TAVILY_API_KEY",
    "JINA_API_KEY",
    "INFOQUEST_API_KEY",
    "DEEPSEEK_API_KEY",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "AUTH_JWT_SECRET",
    "DEER_FLOW_INTERNAL_AUTH_TOKEN",
    "DEER_FLOW_AUTH_DISABLED",
    "DEER_FLOW_INTERNAL_GATEWAY_BASE_URL",
    "DEER_FLOW_TRUSTED_ORIGINS",
    "GATEWAY_CORS_ORIGINS",
    "GATEWAY_ENABLE_DOCS",
]

FRONTEND_ENV_KEYS = [
    "NEXT_PUBLIC_BACKEND_BASE_URL",
    "NEXT_PUBLIC_LANGGRAPH_BASE_URL",
    "DEER_FLOW_INTERNAL_GATEWAY_BASE_URL",
    "DEER_FLOW_TRUSTED_ORIGINS",
]


def random_secret() -> str:
    return secrets.token_urlsafe(32)


def all_field_defaults() -> dict[str, str]:
    defaults: dict[str, str] = {}
    for section in FIELDS:
        for key, _label, default, _kind, _options in section["fields"]:
            defaults[key] = random_secret() if default == "__GENERATE__" else default
    return defaults


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def load_current_values() -> dict[str, str]:
    values = all_field_defaults()
    for rel_path in (".env", "deer-flow/.env", "deer-flow/frontend/.env"):
        values.update(load_env_file(ROOT_DIR / rel_path))
    if not values.get("KIMI_API_KEY") and values.get("MOONSHOT_API_KEY"):
        values["KIMI_API_KEY"] = values["MOONSHOT_API_KEY"]
    if not values.get("FEISHU_RECEIVE_ID") and values.get("FEISHU_CHAT_ID"):
        values["FEISHU_RECEIVE_ID"] = values["FEISHU_CHAT_ID"]
    return values


def timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def write_env_file(rel_path: str, keys: list[str], values: dict[str, str]) -> Path:
    path = ROOT_DIR / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + f".bak.{timestamp()}")
        backup.write_bytes(path.read_bytes())
        os.chmod(backup, stat.S_IRUSR | stat.S_IWUSR)
    content = "\n".join(f"{key}={values.get(key, '')}" for key in keys) + "\n"
    path.write_text(content, encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


def save_all(values: dict[str, str]) -> list[Path]:
    return [
        write_env_file(".env", ROOT_ENV_KEYS, values),
        write_env_file("deer-flow/.env", DEER_ENV_KEYS, values),
        write_env_file("deer-flow/frontend/.env", FRONTEND_ENV_KEYS, values),
    ]


def h(value: str) -> str:
    return html.escape(value, quote=True)


def render_field(key: str, label: str, value: str, kind: str, options: str) -> str:
    escaped_key = h(key)
    if kind == "select":
        option_html = []
        for option in options.split(","):
            selected = " selected" if option == value else ""
            option_html.append(f'<option value="{h(option)}"{selected}>{h(option)}</option>')
        control = f'<select id="{escaped_key}" name="{escaped_key}">{"".join(option_html)}</select>'
    else:
        input_type = "password" if kind == "password" else kind
        control = (
            f'<input id="{escaped_key}" name="{escaped_key}" type="{input_type}" '
            f'value="{h(value)}" autocomplete="off" />'
        )
        if kind == "password":
            control += f'<button class="ghost" type="button" data-toggle="{escaped_key}">显示</button>'
    return (
        '<label class="field">'
        f'<span>{h(label)}</span>'
        f'<code>{escaped_key}</code>'
        f'<div class="control">{control}</div>'
        '</label>'
    )


def render_page(values: dict[str, str], message: str = "") -> bytes:
    sections = []
    for section in FIELDS:
        fields = []
        for key, label, _default, kind, options in section["fields"]:
            fields.append(render_field(key, label, values.get(key, ""), kind, options))
        sections.append(
            '<section>'
            f'<h2>{h(section["title"])}</h2>'
            f'<p>{h(section["description"])}</p>'
            f'{"".join(fields)}'
            '</section>'
        )
    message_html = f'<div class="notice">{h(message)}</div>' if message else ""
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>YQS .env 网页配置向导</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f4f6f8;
      color: #20262d;
    }}
    body {{ margin: 0; }}
    header {{
      position: sticky;
      top: 0;
      z-index: 2;
      background: #ffffff;
      border-bottom: 1px solid #d8dee6;
      padding: 18px 32px;
    }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 24px 24px 48px; }}
    h1 {{ font-size: 24px; margin: 0 0 6px; }}
    h2 {{ font-size: 18px; margin: 0 0 8px; }}
    p {{ margin: 0 0 18px; color: #59636f; line-height: 1.6; }}
    section {{
      background: #fff;
      border: 1px solid #d8dee6;
      border-radius: 8px;
      padding: 22px;
      margin: 18px 0;
    }}
    .field {{
      display: grid;
      grid-template-columns: minmax(180px, 260px) minmax(180px, 260px) 1fr;
      gap: 14px;
      align-items: center;
      border-top: 1px solid #eef1f4;
      padding: 12px 0;
    }}
    .field:first-of-type {{ border-top: 0; }}
    code {{ color: #4b5563; font-size: 12px; overflow-wrap: anywhere; }}
    .control {{ display: flex; gap: 8px; min-width: 0; }}
    input, select {{
      width: 100%;
      min-width: 0;
      box-sizing: border-box;
      border: 1px solid #c8d0da;
      border-radius: 6px;
      padding: 9px 10px;
      font-size: 14px;
      background: #fff;
      color: #20262d;
    }}
    button {{
      border: 0;
      border-radius: 6px;
      padding: 10px 16px;
      font-size: 14px;
      cursor: pointer;
      background: #175cd3;
      color: white;
      white-space: nowrap;
    }}
    button.ghost {{ background: #e8edf5; color: #233044; }}
    .actions {{
      position: sticky;
      bottom: 0;
      background: rgba(244, 246, 248, 0.92);
      backdrop-filter: blur(8px);
      border-top: 1px solid #d8dee6;
      padding: 16px 0;
      display: flex;
      gap: 12px;
      justify-content: flex-end;
    }}
    .notice {{
      border: 1px solid #9fd6b0;
      background: #effaf2;
      color: #1d6b35;
      border-radius: 8px;
      padding: 14px 16px;
      margin: 0 0 18px;
    }}
    .hint {{ font-size: 13px; color: #66717e; margin-top: 4px; }}
    @media (max-width: 820px) {{
      header {{ padding: 16px 20px; }}
      main {{ padding: 18px 16px 40px; }}
      .field {{ grid-template-columns: 1fr; gap: 6px; }}
      .actions {{ justify-content: stretch; }}
      .actions button {{ flex: 1; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>YQS .env 网页配置向导</h1>
    <div class="hint">项目目录：{h(str(ROOT_DIR))}</div>
  </header>
  <main>
    {message_html}
    <form method="post" action="/save">
      {''.join(sections)}
      <div class="actions">
        <button class="ghost" type="button" id="fill-local">填入局域网常用值</button>
        <button type="submit">保存配置文件</button>
      </div>
    </form>
  </main>
  <script>
    document.querySelectorAll("[data-toggle]").forEach((button) => {{
      button.addEventListener("click", () => {{
        const input = document.getElementById(button.dataset.toggle);
        input.type = input.type === "password" ? "text" : "password";
        button.textContent = input.type === "password" ? "显示" : "隐藏";
      }});
    }});
    document.getElementById("fill-local").addEventListener("click", () => {{
      const dashboardHost = document.getElementById("YQS_DASHBOARD_HOST");
      if (dashboardHost && dashboardHost.value === "127.0.0.1") dashboardHost.value = "0.0.0.0";
      const trusted = document.getElementById("DEER_FLOW_TRUSTED_ORIGINS");
      if (trusted && !trusted.value.includes("工作站IP")) {{
        trusted.value = trusted.value + ",http://工作站IP:2026";
      }}
    }});
  </script>
</body>
</html>"""
    return page.encode("utf-8")


class WizardHandler(BaseHTTPRequestHandler):
    server_version = "YQSEnvWizard/1.0"

    def do_GET(self) -> None:
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        self.respond(render_page(load_current_values()))

    def do_POST(self) -> None:
        if self.path != "/save":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8")
        submitted = {key: values[-1] for key, values in urllib.parse.parse_qs(body, keep_blank_values=True).items()}
        values = load_current_values()
        for section in FIELDS:
            for key, _label, _default, _kind, _options in section["fields"]:
                values[key] = submitted.get(key, "")
        paths = save_all(values)
        message = "已保存配置文件：" + "，".join(str(path.relative_to(ROOT_DIR)) for path in paths)
        self.respond(render_page(values, message))

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[env-wizard] {self.address_string()} - {fmt % args}")

    def respond(self, content: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main() -> int:
    os.chdir(ROOT_DIR)
    server = ThreadingHTTPServer((HOST, PORT), WizardHandler)
    url = f"http://{HOST}:{PORT}"
    print("YQS Material Repository - .env 网页配置向导")
    print(f"项目目录: {ROOT_DIR}")
    print(f"请在浏览器打开: {url}")
    print("填写并点击“保存配置文件”后会写入 .env、deer-flow/.env、deer-flow/frontend/.env。")
    print("按 Ctrl+C 退出。")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出配置向导。")
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
