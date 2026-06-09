"""Tests for elixifree.domains.sip builders."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from elixifree.builder import BuildResult, BuildError
from elixifree.domains.sip import Wall


def test_wall_returns_build_result():
    result = Wall(span=4000, height=2440, stock="SIP-100").build()
    assert isinstance(result, BuildResult)


def test_wall_shape_is_not_none():
    result = Wall(span=4000, height=2440, stock="SIP-100").build()
    assert result.shape is not None


def test_wall_span():
    result = Wall(span=4000, height=2440, stock="SIP-100").build()
    assert abs(result.shape.BoundBox.XLength - 4000) < 0.1


def test_wall_height():
    result = Wall(span=4000, height=2440, stock="SIP-100").build()
    assert abs(result.shape.BoundBox.ZLength - 2440) < 0.1


def test_wall_thickness_matches_stock():
    result = Wall(span=4000, height=2440, stock="SIP-100").build()
    assert abs(result.shape.BoundBox.YLength - 122) < 0.1


def test_wall_default_stock_is_sip200():
    result = Wall(span=4000, height=2440).build()
    assert abs(result.shape.BoundBox.YLength - 222) < 0.1


def test_wall_params_captured():
    result = Wall(span=4000, height=2440, stock="SIP-100").build()
    assert result.params["span"] == 4000
    assert result.params["height"] == 2440
    assert result.params["stock"] == "SIP-100"


def test_wall_invalid_stock_raises():
    with pytest.raises(BuildError):
        Wall(span=4000, height=2440, stock="SIP-999").build()


def test_wall_zero_span_raises():
    with pytest.raises(BuildError):
        Wall(span=0, height=2440).build()


def test_wall_negative_height_raises():
    with pytest.raises(BuildError):
        Wall(span=4000, height=-1).build()


def test_wall_shape_is_valid():
    result = Wall(span=4000, height=2440, stock="SIP-150").build()
    assert result.shape.isValid()


def test_wall_spline_grooves_reduce_volume():
    result = Wall(span=4000, height=2440, stock="SIP-100").build()
    bb = result.shape.BoundBox
    bounding_vol = bb.XLength * bb.YLength * bb.ZLength
    assert result.shape.Volume < bounding_vol


def test_wall_no_gaps_for_plain_wall():
    result = Wall(span=4000, height=2440, stock="SIP-100").build()
    assert result.gaps == []
