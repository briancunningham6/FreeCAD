"""Tests for elixifree.sip wall panel functions. Run under FreeCAD's Python."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from elixifree.sip import sip_panel, spline_groove, route_core_channel, panel_zone


# Stock table expected values: (core_mm, face_mm, total_mm)
STOCK = {
    "SIP-100": (100, 11, 122),
    "SIP-150": (150, 11, 172),
    "SIP-200": (200, 11, 222),
    "SIP-250": (250, 11, 272),
    "SIP-300": (300, 11, 322),
}


def test_sip_panel_default_stock_dimensions():
    p = sip_panel(1200, 2700)
    bb = p.BoundBox
    assert abs(bb.XLength - 1200) < 0.1
    assert abs(bb.ZLength - 2700) < 0.1
    assert abs(bb.YLength - 222) < 0.1  # SIP-200 default


def test_sip_panel_all_stocks():
    for stock, (core, face, total) in STOCK.items():
        p = sip_panel(1200, 2700, stock=stock)
        assert abs(p.BoundBox.YLength - total) < 0.1, f"Wrong thickness for {stock}"


def test_sip_panel_invalid_stock():
    with pytest.raises(ValueError):
        sip_panel(1200, 2700, stock="SIP-999")


def test_sip_panel_has_three_layers():
    # A 3-layer fused panel should have volume = width * total_thickness * height
    p = sip_panel(1200, 2700, stock="SIP-150")
    expected_vol = 1200 * 172 * 2700
    assert abs(p.Volume - expected_vol) < 100  # tolerance for fuse seam


def test_spline_groove_reduces_volume():
    p = sip_panel(1200, 2700, stock="SIP-150")
    grooved = spline_groove(p, side="left")
    assert grooved.Volume < p.Volume


def test_spline_groove_right_side():
    p = sip_panel(1200, 2700, stock="SIP-150")
    grooved = spline_groove(p, side="right")
    assert grooved.Volume < p.Volume


def test_spline_groove_invalid_side():
    p = sip_panel(1200, 2700)
    with pytest.raises(ValueError):
        spline_groove(p, side="top")


def test_route_core_channel_reduces_volume():
    p = sip_panel(1200, 2700, stock="SIP-150")
    channelled = route_core_channel(p, edge="bottom")
    assert channelled.Volume < p.Volume


def test_route_core_channel_preserves_total_thickness():
    """Channel cuts foam core only — total Y thickness (OSB skins) must be unchanged."""
    p = sip_panel(1200, 2700, stock="SIP-150")
    channelled = route_core_channel(p, edge="bottom")
    assert abs(channelled.BoundBox.YLength - 172) < 0.1


def test_route_core_channel_top():
    p = sip_panel(1200, 2700, stock="SIP-150")
    channelled = route_core_channel(p, edge="top")
    assert channelled.Volume < p.Volume


def test_panel_zone_is_alias_for_sip_panel():
    p1 = sip_panel(1200, 2700, stock="SIP-150")
    p2 = panel_zone(1200, 2700, stock="SIP-150")
    assert abs(p1.Volume - p2.Volume) < 0.01
