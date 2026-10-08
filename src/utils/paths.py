from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_project_path(value: str | Path) -> Path:
    """Resolve project-relative config paths without depending on the CWD."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def ensure_runtime_directories() -> None:
    for relative in (
        "data/raw",
        "data/processed",
        "data/parquet",
        "data/cache",
        "models",
        "reports",
        "experiments",
        "logs",
    ):
        (PROJECT_ROOT / relative).mkdir(parents=True, exist_ok=True)

