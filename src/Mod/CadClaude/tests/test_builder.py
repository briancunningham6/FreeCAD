"""Tests for elixifree.builder base classes."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
# Import builder directly to avoid triggering elixifree/__init__.py's FreeCAD import
import importlib.util
spec = importlib.util.spec_from_file_location(
    "builder",
    os.path.join(os.path.dirname(__file__), "..", "elixifree", "builder.py")
)
builder_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder_module)
BuildResult = builder_module.BuildResult
BuildError = builder_module.BuildError


def test_build_result_stores_params():
    result = BuildResult(shape=None, params={"span": 4000}, gaps=[])
    assert result.params["span"] == 4000


def test_build_result_gaps_default_empty():
    result = BuildResult(shape=None, params={}, gaps=[])
    assert result.gaps == []


def test_build_result_gaps_accumulate():
    result = BuildResult(shape=None, params={}, gaps=["tapered_top: not supported"])
    assert len(result.gaps) == 1
    assert "tapered_top" in result.gaps[0]


def test_build_error_is_exception():
    with pytest.raises(BuildError):
        raise BuildError("span must be positive")


def test_build_error_message():
    err = BuildError("span must be positive")
    assert "span must be positive" in str(err)
