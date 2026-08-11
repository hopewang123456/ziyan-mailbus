"""LocalePort adapter wrapping errors_zh + role_labels."""
from __future__ import annotations

from typing import Mapping, Sequence

from lib.adapters.locale.errors_zh import ERROR_ZH, message_zh
from lib.adapters.locale.role_labels import (
    role_type_candidates as _role_type_candidates,
    role_type_to_zh as _role_type_to_zh,
    valid_role_types as _valid_role_types,
)


class DictLocale:
    """In-process dict locale (zh-first). Implements LocalePort."""

    def __init__(self, data_dir: str = "", lang: str = "zh"):
        self.data_dir = data_dir
        self.lang = lang or "zh"
        self._cache: dict[str, str] | None = None

    def get(self, key: str, *, fallback: str = "", lang: str = "zh") -> str:
        use_lang = lang or self.lang
        table = self.load(use_lang)
        if key in table:
            return table[key]
        if key.startswith("role_type:"):
            try:
                rt = int(key.split(":", 1)[1])
            except ValueError:
                return fallback or key
            return self.role_type_to_zh(rt) or fallback or key
        if use_lang.startswith("zh"):
            return message_zh(key, fallback=fallback or key)
        return fallback or key

    def load(self, lang: str = "zh") -> Mapping[str, str]:
        if self._cache is not None and (lang or "zh") == self.lang:
            return self._cache
        out: dict[str, str] = {}
        if (lang or "zh").startswith("zh"):
            out.update(ERROR_ZH)
            for rt in self.valid_role_types():
                out[f"role_type:{rt}"] = self.role_type_to_zh(rt)
        self.lang = lang or "zh"
        self._cache = out
        return out

    def message_zh(self, code: str, fallback: str = "") -> str:
        return message_zh(code, fallback=fallback or code)

    def role_type_to_zh(self, role_type: int) -> str:
        return _role_type_to_zh(int(role_type), self.data_dir)

    def role_type_candidates(self, role_type: int) -> Sequence[str]:
        return _role_type_candidates(int(role_type), self.data_dir)

    def valid_role_types(self) -> Sequence[int]:
        return _valid_role_types(self.data_dir)


def build_locale(data_dir: str = "", lang: str = "zh") -> DictLocale:
    return DictLocale(data_dir=data_dir, lang=lang)
