from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_step(name: str, script: str, arguments: list[str] | None = None, timeout: int = 3600) -> dict:
    command = [sys.executable, str(PROJECT_ROOT / "scripts" / script), *(arguments or [])]
    started = datetime.now().astimezone()
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "name": name,
            "status": "success" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode,
            "started_at": started.isoformat(),
            "finished_at": datetime.now().astimezone().isoformat(),
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name, "status": "failed", "returncode": None, "started_at": started.isoformat(),
            "finished_at": datetime.now().astimezone().isoformat(), "message": f"timeout after {timeout}s",
            "stdout_tail": str(exc.stdout or "")[-4000:], "stderr_tail": str(exc.stderr or "")[-4000:],
        }


def main() -> int:
    steps: list[dict] = []
    # A non-critical source failure must not suppress all remaining local analysis.
    steps.append(run_step("data_health", "health_check.py", timeout=300))
    steps.append(run_step("market_data", "update_data.py", timeout=1200))
    steps.append(run_step("factor_scan", "run_daily_analysis.py", ["--chunk-size", "100", "--lookback", "400"], timeout=7200))
    model_path = PROJECT_ROOT / "models" / "qlib_lightgbm.joblib"
    if model_path.exists():
        steps.append(run_step("qlib_inference", "run_qlib_inference.py", ["--chunk-size", "250"], timeout=7200))
    else:
        steps.append({"name": "qlib_inference", "status": "skipped", "message": "模型文件不存在"})
    steps.append(run_step("point_in_time_rescore", "rescore_factors.py", timeout=1200))
    steps.append(run_step("portfolio", "run_portfolio_analysis.py", timeout=1800))
    steps.append(run_step("model_health", "evaluate_model_health.py", timeout=600))
    steps.append(run_step("daily_report", "generate_daily_report.py", timeout=300))
    payload = {
        "status": "success" if all(step["status"] in {"success", "skipped"} for step in steps) else "partial_success",
        "steps": steps,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    # Partial success is a valid resilient run; detailed failed steps remain visible.
    return 0 if any(step["status"] == "success" for step in steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())

