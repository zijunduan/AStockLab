from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class CacheRecord:
    frame: pd.DataFrame
    created_at: datetime
    key: str


class ParquetCache:
    """Small endpoint cache. DuckDB remains the durable system of record."""

    def __init__(self, directory: str | Path, default_ttl_seconds: int = 3600):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.default_ttl = timedelta(seconds=default_ttl_seconds)

    @staticmethod
    def _digest(key: str, params: dict[str, Any] | None = None) -> str:
        payload = json.dumps({"key": key, "params": params or {}}, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    def _paths(self, key: str, params: dict[str, Any] | None = None) -> tuple[Path, Path]:
        digest = self._digest(key, params)
        return self.directory / f"{digest}.parquet", self.directory / f"{digest}.json"

    def get(
        self,
        key: str,
        params: dict[str, Any] | None = None,
        *,
        ttl_seconds: int | None = None,
        allow_stale: bool = False,
    ) -> CacheRecord | None:
        data_path, meta_path = self._paths(key, params)
        if not data_path.exists() or not meta_path.exists():
            return None
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            created_at = datetime.fromisoformat(metadata["created_at"])
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            ttl = timedelta(seconds=ttl_seconds) if ttl_seconds is not None else self.default_ttl
            if not allow_stale and datetime.now(timezone.utc) - created_at > ttl:
                return None
            return CacheRecord(pd.read_parquet(data_path), created_at, key)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return None

    def set(self, key: str, frame: pd.DataFrame, params: dict[str, Any] | None = None) -> CacheRecord:
        data_path, meta_path = self._paths(key, params)
        now = datetime.now(timezone.utc)
        tmp_data = data_path.with_suffix(".parquet.tmp")
        tmp_meta = meta_path.with_suffix(".json.tmp")
        frame.to_parquet(tmp_data, index=False)
        tmp_meta.write_text(
            json.dumps({"created_at": now.isoformat(), "key": key, "params": params or {}}, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_data, data_path)
        os.replace(tmp_meta, meta_path)
        return CacheRecord(frame.copy(), now, key)

    def clear_expired(self, older_than_days: int = 30) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        removed = 0
        for meta_path in self.directory.glob("*.json"):
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                created_at = datetime.fromisoformat(metadata["created_at"])
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at < cutoff:
                    data_path = meta_path.with_suffix(".parquet")
                    meta_path.unlink(missing_ok=True)
                    data_path.unlink(missing_ok=True)
                    removed += 1
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return removed

