from __future__ import annotations

import json


def explanation_markdown(explanation_json: str | None) -> str:
    try:
        payload = json.loads(explanation_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    positive = payload.get("positive") or ["暂无显著正贡献"]
    negative = payload.get("negative") or ["暂无显著负贡献"]
    lines = ["正贡献：", *[f"- {item}" for item in positive], "", "负贡献：", *[f"- {item}" for item in negative]]
    return "\n".join(lines)

