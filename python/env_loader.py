"""Small .env loader for local scripts."""

from __future__ import annotations

import os
from pathlib import Path


def load_env(project_dir: Path) -> None:
    env_paths = [project_dir / ".env", project_dir / "deer-flow" / ".env"]

    for env_path in env_paths:
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
