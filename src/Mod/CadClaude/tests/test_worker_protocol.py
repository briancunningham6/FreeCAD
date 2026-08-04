"""Tests for the READY-line build-identity payload (design spec 2026-08-04).

Runs under plain pytest — cadclaude_worker has no top-level FreeCAD import,
and _collect_build_info degrades to None when FreeCAD is unavailable.
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cadclaude_worker as w


def test_ready_line_bare_when_no_info():
    assert w._ready_line(None) == "READY\n"


def test_ready_line_embeds_single_line_json():
    info = {
        "freecad": "26.3.0",
        "git": "f7605d21c9",
        "branch": "sync/upstream-2026-08",
        "occt": "8.0.0.rc4-e72d772e70",
        "python": "3.13.5",
    }
    line = w._ready_line(info)
    assert line.startswith("READY ")
    assert line.endswith("\n")
    assert line.count("\n") == 1
    assert json.loads(line[len("READY "):]) == info


def test_ready_line_falls_back_on_unserializable_info():
    assert w._ready_line({"bad": object()}) == "READY\n"


def test_collect_build_info_none_without_freecad():
    if "FreeCAD" in sys.modules:
        import pytest
        pytest.skip("running inside FreeCAD; collection would succeed")
    assert w._collect_build_info() is None
