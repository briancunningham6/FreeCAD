"""Tests for elixifree.sip constructability functions.

These functions are used by the assembly pipeline, not by LLM-generated scripts.
Run under FreeCAD's Python — conftest.py handles sys.path setup.
"""
import pytest
from elixifree.sip import sip_panel, spline_groove, route_core_channel, panel_zone

STOCK = {
    "SIP-100": (100, 11, 122),
    "SIP-150": (150, 11, 172),
    "SIP-200": (200, 11, 222),
    "SIP-250": (250, 11, 272),
    "SIP-300": (300, 11, 322),
}


class TestSipPanel:
    def test_default_stock_dimensions(self):
        p = sip_panel(1200, 2700)
        assert abs(p.BoundBox.XLength - 1200) < 0.1
        assert abs(p.BoundBox.ZLength - 2700) < 0.1
        assert abs(p.BoundBox.YLength - 222) < 0.1  # SIP-200

    def test_all_stocks(self):
        for stock, (core, face, total) in STOCK.items():
            p = sip_panel(1200, 2700, stock=stock)
            assert abs(p.BoundBox.YLength - total) < 0.1, f"Wrong thickness for {stock}"

    def test_invalid_stock_raises(self):
        with pytest.raises((ValueError, Exception)):
            sip_panel(1200, 2700, stock="SIP-999")

    def test_volume_matches_solid_block(self):
        p = sip_panel(1200, 2700, stock="SIP-150")
        expected = 1200 * 172 * 2700
        assert abs(p.Volume - expected) < 100


class TestSplineGroove:
    def test_left_reduces_volume(self):
        p = sip_panel(1200, 2700, stock="SIP-150")
        assert spline_groove(p, side="left").Volume < p.Volume

    def test_right_reduces_volume(self):
        p = sip_panel(1200, 2700, stock="SIP-150")
        assert spline_groove(p, side="right").Volume < p.Volume

    def test_invalid_side_raises(self):
        p = sip_panel(1200, 2700)
        with pytest.raises(ValueError):
            spline_groove(p, side="top")


class TestRouteCoreChannel:
    def test_bottom_reduces_volume(self):
        p = sip_panel(1200, 2700, stock="SIP-150")
        assert route_core_channel(p, edge="bottom").Volume < p.Volume

    def test_top_reduces_volume(self):
        p = sip_panel(1200, 2700, stock="SIP-150")
        assert route_core_channel(p, edge="top").Volume < p.Volume

    def test_preserves_total_thickness(self):
        p = sip_panel(1200, 2700, stock="SIP-150")
        channelled = route_core_channel(p, edge="bottom")
        assert abs(channelled.BoundBox.YLength - 172) < 0.1

    def test_invalid_edge_raises(self):
        p = sip_panel(1200, 2700)
        with pytest.raises(ValueError):
            route_core_channel(p, edge="left")


class TestPanelZone:
    def test_is_alias_for_sip_panel(self):
        p1 = sip_panel(1200, 2700, stock="SIP-150")
        p2 = panel_zone(1200, 2700, stock="SIP-150")
        assert abs(p1.Volume - p2.Volume) < 0.01
