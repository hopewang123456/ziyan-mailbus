"""Shared load-time plugin discovery (no hot-reload).

Used by frameworks and integrations extension hooks.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
from typing import Any, Iterable, Sequence


def parse_spec(spec: str) -> tuple[str, str | None]:
    raw = (spec or "").strip()
    if not raw:
        raise ValueError("empty plugin spec")
    if ":" in raw:
        mod, _, attr = raw.partition(":")
        mod, attr = mod.strip(), attr.strip()
        if not mod:
            raise ValueError(f"bad plugin spec: {spec!r}")
        return mod, attr or None
    return raw, None


def specs_from_nested(config: dict | None, paths: Sequence[Sequence[str]]) -> list[str]:
    if not isinstance(config, dict):
        return []
    out: list[str] = []
    for path in paths:
        cur: Any = config
        for key in path:
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(key)
        if isinstance(cur, list):
            out.extend(str(x).strip() for x in cur if str(x).strip())
        elif isinstance(cur, str) and cur.strip():
            out.extend(p.strip() for p in cur.split(",") if p.strip())
    return out


def specs_from_env(env_var: str) -> list[str]:
    raw = (os.environ.get(env_var) or "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def specs_from_entry_points(group: str) -> list[str]:
    try:
        from importlib.metadata import entry_points
    except ImportError:
        return []
    try:
        eps = entry_points()
        if hasattr(eps, "select"):
            selected = list(eps.select(group=group))
        else:
            selected = list(eps.get(group, []))  # type: ignore[arg-type]
    except Exception:
        return []
    return [f"ep:{ep.name}" for ep in selected]


def load_entry_point(group: str, name: str) -> Any:
    from importlib.metadata import entry_points

    eps = entry_points()
    if hasattr(eps, "select"):
        selected = list(eps.select(group=group))
    else:
        selected = list(eps.get(group, []))  # type: ignore[arg-type]
    for ep in selected:
        if ep.name == name:
            return ep.load()
    raise LookupError(f"entry point not found: {group}/{name}")


def merge_specs(*groups: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for spec in group:
            if spec not in seen:
                seen.add(spec)
                out.append(spec)
    return out


def load_config_json(data_dir: str) -> dict | None:
    path = os.path.join(data_dir, "config.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


class PluginDiscovery:
    """Idempotent discover+load for one extension family."""

    def __init__(
        self,
        *,
        name: str,
        entry_point_group: str,
        config_paths: Sequence[Sequence[str]],
        env_var: str,
        strict_env: str,
    ) -> None:
        self.name = name
        self.entry_point_group = entry_point_group
        self.config_paths = config_paths
        self.env_var = env_var
        self.strict_env = strict_env
        self.log = logging.getLogger(f"mailbus.plugins.{name}")
        self._loaded: set[str] = set()
        self._results: list[dict[str, Any]] = []

    def reset_for_tests(self) -> None:
        self._loaded.clear()
        self._results.clear()

    def results(self) -> list[dict[str, Any]]:
        return list(self._results)

    def collect(self, config: dict | None = None) -> list[str]:
        return merge_specs(
            specs_from_nested(config, self.config_paths),
            specs_from_env(self.env_var),
            specs_from_entry_points(self.entry_point_group),
        )

    def load_spec(self, spec: str) -> dict[str, Any]:
        key = spec.strip()
        if key in self._loaded:
            return {"spec": key, "ok": True, "skipped": True, "reason": "already_loaded"}
        try:
            if key.startswith("ep:"):
                obj = load_entry_point(self.entry_point_group, key[3:])
                if callable(obj):
                    obj()
            else:
                mod_name, attr = parse_spec(key)
                mod = importlib.import_module(mod_name)
                if attr:
                    fn = getattr(mod, attr)
                    if not callable(fn):
                        raise TypeError(f"{key} is not callable")
                    fn()
                elif hasattr(mod, "register") and callable(mod.register):
                    mod.register()
            self._loaded.add(key)
            row = {"spec": key, "ok": True, "skipped": False}
            self._results.append(row)
            return row
        except Exception as exc:
            row = {"spec": key, "ok": False, "skipped": False, "error": str(exc)}
            self._results.append(row)
            self.log.warning("%s plugin load failed: %s (%s)", self.name, key, exc)
            return row

    def discover(
        self,
        *,
        data_dir: str = "",
        config: dict | None = None,
    ) -> list[dict[str, Any]]:
        cfg = config
        if cfg is None and data_dir:
            cfg = load_config_json(data_dir)
        results: list[dict[str, Any]] = []
        strict = os.environ.get(self.strict_env, "0") == "1"
        for spec in self.collect(cfg):
            row = self.load_spec(spec)
            results.append(row)
            if strict and not row.get("ok"):
                raise RuntimeError(f"{self.name} plugin failed: {spec}: {row.get('error')}")
        return results
