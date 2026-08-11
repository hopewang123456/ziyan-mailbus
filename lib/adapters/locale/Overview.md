# lib.adapters.locale

Chinese error messages, role labels, and `LocalePort` adapter.

## Role

Localize stable error codes and role_type labels.

## Dependency direction

`interfaces.LocalePort` ← `dict_locale` → `errors_zh` / `role_labels` / `domain.error_codes`

## Forbidden imports

`lib.application.*`

## Files

| File | Purpose |
|------|---------|
| `errors_zh.py` | Error code → zh |
| `role_labels.py` | role_type ↔ zh |
| `dict_locale.py` | `DictLocale` / `build_locale` |
