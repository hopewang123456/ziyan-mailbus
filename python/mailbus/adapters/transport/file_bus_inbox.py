"""file_bus 入站：扫描 inbound/*.json，处理后移入 processed / rejected。"""

from __future__ import annotations

import json
from pathlib import Path

from mailbus.core.shared.events import InboundEnvelope


class FileBusInbox:
    def __init__(self, base_dir: Path) -> None:
        self._inbound = base_dir / "inbound"
        self._processed = base_dir / "processed"
        self._rejected = base_dir / "rejected"

    def pending(self) -> list[InboundEnvelope]:
        self._inbound.mkdir(parents=True, exist_ok=True)
        envelopes: list[InboundEnvelope] = []
        for path in sorted(self._inbound.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._move(path, self._rejected, suffix="invalid_json")
                continue
            if not isinstance(payload, dict):
                self._move(path, self._rejected, suffix="invalid_payload")
                continue
            envelopes.append(InboundEnvelope(name=path.name, payload=payload))
        return envelopes

    def complete(self, name: str) -> None:
        self._move(self._inbound / name, self._processed)

    def fail(self, name: str, error_code: str) -> None:
        self._move(self._inbound / name, self._rejected, suffix=error_code)

    @staticmethod
    def _move(path: Path, folder: Path, suffix: str | None = None) -> None:
        if path.name != path.name.strip() or Path(path.name).name != path.name:
            return
        folder.mkdir(parents=True, exist_ok=True)
        stem = f"{path.stem}.{suffix}" if suffix else path.stem
        target = folder / f"{stem}{path.suffix}"
        index = 1
        while target.exists():
            target = folder / f"{stem}-{index}{path.suffix}"
            index += 1
        if path.exists():
            path.replace(target)
