#!/usr/bin/env python3
"""Export current env configuration to a local Markdown handoff document."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DESKTOP_DIR = Path.home() / "Desktop"
OUTPUT_PATH = DESKTOP_DIR / "YQS项目迁移_env配置备份.md"
ENV_FILES = [
    ".env",
    "deer-flow/.env",
    "deer-flow/frontend/.env",
]


def read_text(path: Path) -> str:
    if not path.exists():
        return "# 文件不存在\n"
    return path.read_text(encoding="utf-8")


def main() -> None:
    sections: list[str] = [
        "# YQS 项目迁移 env 配置备份",
        "",
        f"- 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 来源目录：`{PROJECT_DIR}`",
        "- 目标系统：Ubuntu 24.04 工作站",
        "",
        "> 重要：本文档包含可复用一次的密钥和 token。迁移完成并验证后，请删除此文件，旧密钥按计划废弃或轮换。",
        "",
        "## Ubuntu 工作站配置步骤",
        "",
        "1. 把项目复制到 Ubuntu 工作站。",
        "2. 安装基础依赖：Docker、Docker Compose、Python 3、make、git。",
        "3. 在项目根目录运行：`bash scripts/configure_env_ubuntu.sh`。",
        "4. 也可以直接把下方三段 dotenv 内容分别写入对应文件。",
        "5. 运行 `python3 python/setup_bitable.py` 校验飞书多维表格。",
        "6. 进入 `deer-flow` 后运行 `make docker-start` 启动服务。",
        "",
        "## 当前配置文件内容",
        "",
    ]
    for relative in ENV_FILES:
        sections.extend([
            f"### `{relative}`",
            "",
            "```dotenv",
            read_text(PROJECT_DIR / relative).rstrip(),
            "```",
            "",
        ])
    sections.extend([
        "## 迁移后建议检查",
        "",
        "- 飞书开放平台事件订阅和应用权限仍然有效。",
        "- 多维表格字段仍为：`项目`、`名字`、`描述`、`文件`、`来源`、`来源二级分类`、`是否可商用`。",
        "- `项目` 字段有值时会进入 `case_materials/项目/`，为空时进入 `case_materials/通用素材库/`；`项目-名字` 写法已废弃。",
        "- 飞书知识库回显配置：已有知识库填 `FEISHU_KNOWLEDGE_SPACE_ID`；需要自动创建时额外配置 `FEISHU_KNOWLEDGE_USER_ACCESS_TOKEN`。",
        "- Kimi/GLM token 监控文件：`runtime/ai_token_usage.json`。",
        "- 迁移验证完成后删除本备份文件，并按需轮换密钥。",
        "",
    ])
    OUTPUT_PATH.write_text("\n".join(sections), encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
