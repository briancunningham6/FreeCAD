"""Tests for elixifree.domains.sip — Wall, RoofPanel, Foundation builders.

Run under FreeCAD's Python — requires FreeCAD on sys.path.
conftest.py in this directory handles the path setup.
"""
import pytest
from elixifree.builder import BuildResult, BuildError
from elixifree.domains.sip import Wall, RoofPanel, Foundation, sip_constants


class TestWallPlain:
    def test_returns_build_result(self):
        assert isinstance(Wall(span=4000, height=2440, stock="SIP-100").build(), BuildResult)

    def test_span(self):
        result = Wall(span=4000, height=2440, stock="SIP-100").build()
        assert abs(result.shape.BoundBox.XLength - 4000) < 0.1

    def test_height(self):
        result = Wall(span=4000, height=2440, stock="SIP-100").build()
        assert abs(result.shape.BoundBox.ZLength - 2440) < 0.1

    def test_thickness_matches_stock(self):
        result = Wall(span=4000, height=2440, stock="SIP-100").build()
        assert abs(result.shape.BoundBox.YLength - 122) < 0.1

    def test_default_stock_is_sip200(self):
        result = Wall(span=4000, height=2440).build()
        assert abs(result.shape.BoundBox.YLength - 222) < 0.1

    def test_params_captured(self):
        result = Wall(span=4000, height=2440, stock="SIP-100").build()
        assert result.params["span"] == 4000
        assert result.params["height"] == 2440
        assert result.params["stock"] == "SIP-100"

    def test_invalid_stock_raises(self):
        with pytest.raises(BuildError):
            Wall(span=4000, height=2440, stock="SIP-999").build()

    def test_zero_span_raises(self):
        with pytest.raises(BuildError):
            Wall(span=0, height=2440).build()

    def test_negative_height_raises(self):
        with pytest.raises(BuildError):
            Wall(span=4000, height=-1).build()

    def test_has_volume(self):
        result = Wall(span=4000, height=2440, stock="SIP-150").build()
        assert result.shape.Volume > 0

    def test_spline_grooves_reduce_volume(self):
        result = Wall(span=4000, height=2440, stock="SIP-100").build()
        bb = result.shape.BoundBox
        assert result.shape.Volume < bb.XLength * bb.YLength * bb.ZLength

    def test_no_gaps_for_plain_wall(self):
        assert Wall(span=4000, height=2440, stock="SIP-100").build().gaps == []


class TestWallOpenings:
    def test_door_reduces_volume(self):
        plain = Wall(span=4000, height=2440, stock="SIP-100").build()
        with_door = (Wall(span=4000, height=2440, stock="SIP-100")
            .opening(x=1500, z=0, width=900, height=2100)
            .build())
        assert with_door.shape.Volume < plain.shape.Volume

    def test_opening_params_captured(self):
        result = (Wall(span=4000, height=2440, stock="SIP-100")
            .opening(x=1500, z=0, width=900, height=2100)
            .build())
        assert len(result.params["openings"]) == 1
        assert result.params["openings"][0]["width"] == 900

    def test_multiple_openings(self):
        result = (Wall(span=5000, height=2440, stock="SIP-100")
            .opening(x=500, z=800, width=1200, height=1000)
            .opening(x=3000, z=0, width=900, height=2100)
            .build())
        assert len(result.params["openings"]) == 2
        assert result.shape.Volume > 0

    def test_opening_outside_span_raises(self):
        with pytest.raises(BuildError):
            (Wall(span=4000, height=2440)
                .opening(x=3500, z=0, width=900, height=2100)
                .build())

    def test_opening_outside_height_raises(self):
        with pytest.raises(BuildError):
            (Wall(span=4000, height=2440)
                .opening(x=1500, z=2000, width=900, height=600)
                .build())


class TestWallOrientation:
    def test_orient_y_swaps_axes(self):
        result = Wall(span=4000, height=2440, stock="SIP-100").orient("Y").build()
        bb = result.shape.BoundBox
        assert abs(bb.XLength - 122) < 0.1
        assert abs(bb.YLength - 4000) < 0.1
        assert abs(bb.ZLength - 2440) < 0.1

    def test_orient_x_is_default(self):
        result = Wall(span=4000, height=2440, stock="SIP-100").orient("X").build()
        assert abs(result.shape.BoundBox.XLength - 4000) < 0.1

    def test_orient_invalid_raises(self):
        with pytest.raises(BuildError):
            Wall(span=4000, height=2440).orient("Z").build()

    def test_orientation_in_params(self):
        result = Wall(span=4000, height=2440, stock="SIP-100").orient("Y").build()
        assert result.params["orientation"] == "Y"


class TestWallCornerSpline:
    def test_increases_volume(self):
        plain = Wall(span=3000, height=2440, stock="SIP-100").build()
        with_splines = (Wall(span=3000, height=2440, stock="SIP-100")
            .corner_spline(side="left")
            .corner_spline(side="right")
            .build())
        assert with_splines.shape.Volume > plain.shape.Volume

    def test_extends_bounding_box(self):
        result = (Wall(span=3000, height=2440, stock="SIP-100")
            .corner_spline(side="left")
            .corner_spline(side="right")
            .build())
        assert abs(result.shape.BoundBox.XLength - 3090) < 0.1

    def test_params_captured(self):
        result = (Wall(span=3000, height=2440, stock="SIP-100")
            .corner_spline(side="left")
            .build())
        assert "left" in result.params["corner_splines"]

    def test_invalid_side_raises(self):
        with pytest.raises(BuildError):
            Wall(span=3000, height=2440).corner_spline(side="top").build()

    def test_has_volume(self):
        result = (Wall(span=3000, height=2440, stock="SIP-150")
            .corner_spline(side="left")
            .build())
        assert result.shape.Volume > 0


class TestWallInnerGroove:
    def test_reduces_volume(self):
        plain = Wall(span=4000, height=2440, stock="SIP-100").build()
        grooved = Wall(span=4000, height=2440, stock="SIP-100").inner_groove(x=500).build()
        assert grooved.shape.Volume < plain.shape.Volume

    def test_params_captured(self):
        result = (Wall(span=4000, height=2440, stock="SIP-100")
            .inner_groove(x=500, width=45, depth=50)
            .build())
        assert len(result.params["inner_grooves"]) == 1
        assert result.params["inner_grooves"][0]["x"] == 500

    def test_multiple_grooves(self):
        result = (Wall(span=4000, height=2440, stock="SIP-100")
            .inner_groove(x=61)
            .inner_groove(x=3939)
            .build())
        assert len(result.params["inner_grooves"]) == 2
        assert result.shape.Volume > 0


class TestRoofPanel:
    def test_returns_build_result(self):
        assert isinstance(RoofPanel(span=4200, depth=3200, stock="SIP-150").build(), BuildResult)

    def test_span(self):
        result = RoofPanel(span=4200, depth=3200, stock="SIP-150").build()
        assert abs(result.shape.BoundBox.XLength - 4200) < 0.1

    def test_depth(self):
        result = RoofPanel(span=4200, depth=3200, stock="SIP-150").build()
        assert abs(result.shape.BoundBox.ZLength - 3200) < 0.1

    def test_thickness_matches_stock(self):
        result = RoofPanel(span=4200, depth=3200, stock="SIP-150").build()
        assert abs(result.shape.BoundBox.YLength - 172) < 0.1

    def test_params_captured(self):
        result = RoofPanel(span=4200, depth=3200, stock="SIP-150").build()
        assert result.params["span"] == 4200
        assert result.params["depth"] == 3200
        assert result.params["stock"] == "SIP-150"

    def test_zero_span_raises(self):
        with pytest.raises(BuildError):
            RoofPanel(span=0, depth=3200).build()

    def test_pitch_logs_gap(self):
        result = RoofPanel(span=4200, depth=3200, stock="SIP-150").pitch(degrees=15).build()
        assert len(result.gaps) == 1
        assert "pitch" in result.gaps[0].lower()


class TestFoundation:
    def test_returns_build_result(self):
        assert isinstance(Foundation(length=4200, width=3400, depth=200).build(), BuildResult)

    def test_dimensions(self):
        result = Foundation(length=4200, width=3400, depth=200).build()
        assert abs(result.shape.BoundBox.XLength - 4200) < 0.1
        assert abs(result.shape.BoundBox.YLength - 3400) < 0.1
        assert abs(result.shape.BoundBox.ZLength - 200) < 0.1

    def test_params_captured(self):
        result = Foundation(length=4200, width=3400, depth=200).build()
        assert result.params["length"] == 4200
        assert result.params["width"] == 3400
        assert result.params["depth"] == 200

    def test_default_type(self):
        result = Foundation(length=4200, width=3400, depth=200).build()
        assert result.params["type"] == "concrete_slab"

    def test_zero_depth_raises(self):
        with pytest.raises(BuildError):
            Foundation(length=4200, width=3400, depth=0).build()


class TestSipConstants:
    def test_sip100(self):
        c = sip_constants("SIP-100")
        assert c["face"] == 11
        assert c["core"] == 100
        assert c["total"] == 122

    def test_default_is_sip200(self):
        assert sip_constants()["total"] == 222

    def test_groove_dimensions(self):
        c = sip_constants("SIP-150")
        assert c["groove_width"] == 45
        assert c["groove_depth"] == 50

    def test_invalid_stock_raises(self):
        with pytest.raises(BuildError):
            sip_constants("SIP-999")
