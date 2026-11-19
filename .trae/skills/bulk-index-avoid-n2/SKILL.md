---
name: bulk-index-avoid-n2
description: Catch the O(n²) anti-pattern where bulk create of derived index entries rewrites the whole index per item. Use when adding or refactoring any _build_*_store, bulk_create, or warm-up routine that creates many records each of which triggers an incremental index update. Do not use for single-record write paths or read paths.
---

# Bulk Derived Index — Avoid O(n²) Rewrite

## Problem

When a write path maintains a derived index (e.g. `tasks/_index.json` mapping fname → mtime/size/meta),
the natural incremental pattern is:

```python
def _write_task(self, id, task):
    json_write(self._task_path(id), task)
    self._update_index_entry(id, task)   # rewrites the entire index file every time
```

This is correct for the steady state (single create/update), but catastrophic for bulk creation.
2000 tasks at ~5ms per index rewrite takes 10 seconds; 100k at that rate takes hours.

## Correct Pattern

Single-record paths keep the incremental pattern (they pay O(log n) or O(n) once, rare enough).
Bulk paths **must** bypass incremental updates and do a single O(n) build + write at the end:

```python
# Bulk warm-up / _build_*_store — one pass, one index write
def _build_bulk_store(data_dir, n_tasks):
    tracker = TaskTracker(data_dir)
    for i in range(n_tasks):
        # Write the .json directly — DO NOT call tracker._write_task()
        _write_json(f"tasks/task-{i:04d}.json", {...})
    # One-shot rebuild from directory stat (O(n) stat + O(n) json parse)
    entries = _tasks_dir_entries(tasks_dir)
    idx = tracker._build_index(entries)
    tracker._write_tasks_index(idx)
```

## Mailbus-Specific Anchors

Use these when auditing a suspected anti-pattern in this repo:

- `python/lib/application/orchestration/tracker.py` — `_write_task` + `_update_index_entry` + `_build_index` + `_write_tasks_index`
- `python/lib/infra/inbox_store/jsonl_store.py` — `_note_task` (task_index 增量，**append 热路径正确**), `_rebuild_index_locked` (O(n) 重建)
- `tools/perf_baseline.py::_build_bulk_store` — example of the fix (批量创建 2000 任务后一次性 build + write)

## Red Flags

Audit any new or modified code that:

1. Creates many records in a loop and each body calls a helper whose name contains `update_index`, `sync_index`,
   or writes an `_index.json` / `index.json`.
2. Mixes bulk creation with incremental index helpers — `tracker._write_task()` inside a `for i in range(n)` loop.
3. Leaves a stale or missing index file after a bulk build — subsequent `list_all` will fall into the
   "file set mismatch" branch and do a full rebuild, which is O(n) per invocation.

## Validation

After applying the pattern, time the bulk creation end-to-end. For 2000 tasks:

- Bad: 10–60s (per-item index rewrite)
- Good: <3s (one-shot stat + one-shot write)

Also sanity-check the index file: `json.load(open("tasks/_index.json"))["files"]` should have exactly the
expected count of entries (excluding the `_index.json` marker itself — `_tasks_dir_entries` already skips it).
