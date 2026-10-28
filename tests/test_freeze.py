"""Benchmark split and freeze: reproducible split, one dev task per category, and edits are detected."""
from __future__ import annotations

import json

import scripts.freeze_benchmark as fb
from shared.benchmarks.task_package import load_all_public_tasks


def test_split_is_reproducible_and_covers_every_task_once():
    a, b = fb.draw_split(), fb.draw_split()
    assert a == b
    all_ids = {t.task_id for t in load_all_public_tasks()}
    assert set(a["dev"]) | set(a["test"]) == all_ids
    assert not set(a["dev"]) & set(a["test"])


def test_one_dev_task_per_category():
    split = fb.draw_split()
    categories = {t.task_id: t.category for t in load_all_public_tasks()}
    dev_categories = [categories[t] for t in split["dev"]]
    assert sorted(dev_categories) == sorted(set(categories.values()))


def test_committed_split_matches_the_seeded_draw():
    committed = json.loads(fb.SPLIT_PATH.read_text(encoding="utf-8"))
    assert committed["dev"] == fb.draw_split()["dev"]


def test_snapshot_detects_a_changed_file(tmp_path, monkeypatch):
    root = tmp_path / "bench"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(fb, "FROZEN_ROOTS", [root])
    monkeypatch.setattr(fb, "SVAGA_ROOT", tmp_path)
    before = fb.snapshot()
    (root / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert fb.snapshot() != before


def test_line_endings_do_not_change_the_hash(tmp_path, monkeypatch):
    root = tmp_path / "bench"
    root.mkdir()
    monkeypatch.setattr(fb, "FROZEN_ROOTS", [root])
    monkeypatch.setattr(fb, "SVAGA_ROOT", tmp_path)
    (root / "a.py").write_bytes(b"x = 1\n")
    unix = fb.snapshot()
    (root / "a.py").write_bytes(b"x = 1\r\n")
    assert fb.snapshot() == unix
