"""源机：按 manifest 打包目录树为 tar.gz。"""

from __future__ import annotations

import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from paths import MAILBUS_CORE, load_manifest, manifest_entries


def export_bundle(
    output: Path,
    install_prefix: Path,
    *,
    include_infra: bool = True,
) -> dict:
    prefix = install_prefix.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    included: list[str] = []
    skipped: list[str] = []

    def maybe_add(rel: str, src: Path, optional: bool) -> None:
        if not src.exists():
            if optional:
                skipped.append(str(src))
            else:
                raise FileNotFoundError(f"required path missing: {src}")
            return
        included.append(rel)

    items: list[tuple[str, Path, bool]] = []
    for section in ("required",):
        for item in manifest.get(section) or []:
            items.append((item["path"], prefix / item["path"], False))
    if include_infra:
        for item in manifest.get("infra") or []:
            items.append((item["path"], prefix / item["path"], item.get("optional", True)))

    with tarfile.open(output, "w:gz") as tar:
        meta = {
            "created": datetime.now(timezone.utc).isoformat(),
            "install_prefix": str(prefix),
            "included": [],
        }
        for rel, src, optional in items:
            if not src.exists():
                if optional:
                    skipped.append(str(src))
                    continue
                raise FileNotFoundError(f"required path missing: {src}")
            tar.add(src, arcname=rel)
            meta["included"].append(rel)
        import io

        data = json.dumps(meta, indent=2).encode("utf-8")
        info = tarfile.TarInfo(name="migrate-manifest.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    return {"output": str(output), "included": meta["included"], "skipped": skipped}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Export mailbus migrate bundle")
    ap.add_argument("--prefix", default=str(MAILBUS_CORE.parent))
    ap.add_argument("--output", default="mailbus-bundle.tar.gz")
    ap.add_argument("--no-infra", action="store_true")
    args = ap.parse_args()
    info = export_bundle(
        Path(args.output),
        Path(args.prefix),
        include_infra=not args.no_infra,
    )
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
