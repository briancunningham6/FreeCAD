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
    assert result.shape.Volume > 0
    assert abs(result.shape.BoundBox.XLength - 3045) < 0.1


def test_wall_spline_grooves_reduce_volume():
    result = Wall(span=4000, height=2440, stock="SIP-100").build()
    bb = result.shape.BoundBox
    bounding_vol = bb.XLength * bb.YLength * bb.ZLength
    assert result.shape.Volume < bounding_vol


def test_wall_no_gaps_for_plain_wall():
    result = Wall(span=4000, height=2440, stock="SIP-100").build()
    assert result.gaps == []


# ── Wall — with openings ──────────────────────────────────────────────────────

def test_wall_with_door_opening_reduces_volume():
    plain = Wall(span=4000, height=2440, stock="SIP-100").build()
    with_door = (Wall(span=4000, height=2440, stock="SIP-100")
        .opening(x=1500, z=0, width=900, height=2100)
        .build())
    assert with_door.shape.Volume < plain.shape.Volume


def test_wall_opening_params_captured():
    result = (Wall(span=4000, height=2440, stock="SIP-100")
        .opening(x=1500, z=0, width=900, height=2100)
        .build())
    assert len(result.params["openings"]) == 1
    assert result.params["openings"][0]["width"] == 900


def test_wall_multiple_openings():
    result = (Wall(span=5000, height=2440, stock="SIP-100")
        .opening(x=500, z=800, width=1200, height=1000)
        .opening(x=3000, z=0, width=900, height=2100)
        .build())
    assert len(result.params["openings"]) == 2
    assert result.shape.Volume > 0
    assert abs(result.shape.BoundBox.XLength - 3045) < 0.1


def test_wall_opening_outside_span_raises():
    with pytest.raises(BuildError):
        (Wall(span=4000, height=2440)
            .opening(x=3500, z=0, width=900, height=2100)
            .build())


def test_wall_opening_outside_height_raises():
    with pytest.raises(BuildError):
        (Wall(span=4000, height=2440)
            .opening(x=1500, z=2000, width=900, height=600)
            .build())


# ── RoofPanel ─────────────────────────────────────────────────────────────────

from elixifree.domains.sip import Wall, RoofPanel


def test_roof_panel_returns_build_result():
    result = RoofPanel(span=4200, depth=3200, stock="SIP-150").build()
    assert isinstance(result, BuildResult)


def test_roof_panel_span():
    result = RoofPanel(span=4200, depth=3200, stock="SIP-150").build()
    assert abs(result.shape.BoundBox.XLength - 4200) < 0.1


def test_roof_panel_depth():
    result = RoofPanel(span=4200, depth=3200, stock="SIP-150").build()
    assert abs(result.shape.BoundBox.ZLength - 3200) < 0.1


def test_roof_panel_thickness_matches_stock():
    result = RoofPanel(span=4200, depth=3200, stock="SIP-150").build()
    assert abs(result.shape.BoundBox.YLength - 172) < 0.1


def test_roof_panel_params_captured():
    result = RoofPanel(span=4200, depth=3200, stock="SIP-150").build()
    assert result.params["span"] == 4200
    assert result.params["depth"] == 3200
    assert result.params["stock"] == "SIP-150"


def test_roof_panel_is_valid():
    result = RoofPanel(span=4200, depth=3200, stock="SIP-200").build()
    assert result.shape.Volume > 0
    assert abs(result.shape.BoundBox.XLength - 3045) < 0.1


def test_roof_panel_zero_span_raises():
    with pytest.raises(BuildError):
        RoofPanel(span=0, depth=3200).build()


def test_roof_panel_gap_logged_for_pitch():
    result = RoofPanel(span=4200, depth=3200, stock="SIP-150").pitch(degrees=15).build()
    assert len(result.gaps) == 1
    assert "pitch" in result.gaps[0].lower()


# ── Foundation ────────────────────────────────────────────────────────────────

from elixifree.domains.sip import Wall, RoofPanel, Foundation


def test_foundation_returns_build_result():
    result = Foundation(length=4200, width=3400, depth=200).build()
    assert isinstance(result, BuildResult)


def test_foundation_dimensions():
    result = Foundation(length=4200, width=3400, depth=200).build()
    assert abs(result.shape.BoundBox.XLength - 4200) < 0.1
    assert abs(result.shape.BoundBox.YLength - 3400) < 0.1
    assert abs(result.shape.BoundBox.ZLength - 200) < 0.1


def test_foundation_is_valid():
    result = Foundation(length=4200, width=3400, depth=200).build()
    assert result.shape.Volume > 0
    assert abs(result.shape.BoundBox.XLength - 3045) < 0.1


def test_foundation_params_captured():
    result = Foundation(length=4200, width=3400, depth=200).build()
    assert result.params["length"] == 4200
    assert result.params["width"] == 3400
    assert result.params["depth"] == 200


def test_foundation_default_type():
    result = Foundation(length=4200, width=3400, depth=200).build()
    assert result.params["type"] == "concrete_slab"


def test_foundation_zero_depth_raises():
    with pytest.raises(BuildError):
        Foundation(length=4200, width=3400, depth=0).build()


# ── Wall — corner splines ─────────────────────────────────────────────────────

def test_corner_spline_increases_volume():
    plain = Wall(span=3000, height=2440, stock="SIP-100").build()
    with_splines = (Wall(span=3000, height=2440, stock="SIP-100")
        .corner_spline(side="left")
        .corner_spline(side="right")
        .build())
    assert with_splines.shape.Volume > plain.shape.Volume


def test_corner_spline_extends_bounding_box():
    result = (Wall(span=3000, height=2440, stock="SIP-100")
        .corner_spline(side="left")
        .corner_spline(side="right")
        .build())
    # Splines add 45mm to each end → total span = 3000 + 45 + 45 = 3090
    assert abs(result.shape.BoundBox.XLength - 3090) < 0.1


def test_corner_spline_params_captured():
    result = (Wall(span=3000, height=2440, stock="SIP-100")
        .corner_spline(side="left")
        .build())
    assert "left" in result.params["corner_splines"]


def test_corner_spline_invalid_side_raises():
    with pytest.raises(BuildError):
        Wall(span=3000, height=2440).corner_spline(side="top").build()


def test_corner_spline_shape_has_volume():
    result = (Wall(span=3000, height=2440, stock="SIP-150")
        .corner_spline(side="left")
        .build())
    assert result.shape.Volume > 0
    assert abs(result.shape.BoundBox.XLength - 3045) < 0.1


# ── sip_constants ─────────────────────────────────────────────────────────────

from elixifree.domains.sip import Wall, RoofPanel, Foundation, sip_constants


def test_sip_constants_sip100():
    c = sip_constants("SIP-100")
    assert c["face"] == 11
    assert c["core"] == 100
    assert c["total"] == 122


def test_sip_constants_sip200_default():
    c = sip_constants()
    assert c["total"] == 222


def test_sip_constants_groove_dimensions():
    c = sip_constants("SIP-150")
    assert c["groove_width"] == 45
    assert c["groove_depth"] == 50


def test_sip_constants_invalid_stock_raises():
    with pytest.raises(BuildError):
        sip_constants("SIP-999")
