"""Wave7: LocalePort / DictLocale baseline."""
from __future__ import annotations

import pytest

from lib.adapters.locale import DictLocale, build_locale
from lib.composition import build_locale_port, get_locale, reset_context


@pytest.fixture(autouse=True)
def _reset_locale_context():
    yield
    reset_context()


def test_dict_locale_message_zh():
    loc = DictLocale(lang="zh")
    assert loc.get("totally_missing_key_xyz", fallback="fb") == "fb"
    table = loc.load("zh")
    assert isinstance(table, dict)
    assert len(table) >= 1


def test_composition_locale_port():
    port = build_locale_port("store", lang="zh")
    assert hasattr(port, "get")
    assert hasattr(port, "message_zh")
    got = get_locale("store")
    assert got is not None


def test_role_type_keys():
    loc = build_locale(lang="zh")
    roles = list(loc.valid_role_types())
    assert isinstance(roles, list)
