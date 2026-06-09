"""Tests for elixifree core primitives (box, cylinder, fuse, cut, translate, mirror, fillet, chamfer).

Run under FreeCAD's Python — requires FreeCAD on sys.path.
conftest.py in this directory handles the path setup.
"""
import pytest
from elixifree import box, cylinder, fuse, cut, translate, mirror, fillet, chamfer


class TestBox:
    def test_dimensions(self):
        s = box(100, 200, 300)
        assert abs(s.BoundBox.XLength - 100) < 0.01
        assert abs(s.BoundBox.YLength - 200) < 0.01
        assert abs(s.BoundBox.ZLength - 300) < 0.01

    def test_placement(self):
        s = box(10, 10, 10, at=(5, 6, 7))
        assert abs(s.BoundBox.XMin - 5) < 0.01
        assert abs(s.BoundBox.YMin - 6) < 0.01
        assert abs(s.BoundBox.ZMin - 7) < 0.01

    def test_default_placement_at_origin(self):
        s = box(10, 10, 10)
        assert abs(s.BoundBox.XMin) < 0.01
        assert abs(s.BoundBox.YMin) < 0.01
        assert abs(s.BoundBox.ZMin) < 0.01


class TestCylinder:
    def test_dimensions(self):
        s = cylinder(50, 100)
        assert abs(s.BoundBox.XLength - 100) < 0.01  # diameter
        assert abs(s.BoundBox.ZLength - 100) < 0.01  # height

    def test_placement(self):
        s = cylinder(10, 20, at=(5, 5, 5))
        assert abs(s.BoundBox.ZMin - 5) < 0.01


class TestFuse:
    def test_combines_shapes(self):
        a = box(10, 10, 10)
        b = box(10, 10, 10, at=(10, 0, 0))
        result = fuse(a, b)
        assert result.Volume > a.Volume

    def test_requires_two_shapes(self):
        with pytest.raises(ValueError):
            fuse(box(10, 10, 10))


class TestCut:
    def test_removes_material(self):
        base = box(100, 100, 100)
        tool = box(50, 50, 50)
        result = cut(base, tool)
        assert result.Volume < base.Volume

    def test_multiple_tools(self):
        base = box(100, 100, 100)
        t1 = box(20, 100, 100, at=(0, 0, 0))
        t2 = box(20, 100, 100, at=(80, 0, 0))
        result = cut(base, t1, t2)
        assert result.Volume < cut(base, t1).Volume


class TestTranslate:
    def test_moves_shape(self):
        s = box(10, 10, 10)
        moved = translate(s, x=100, y=200, z=300)
        assert abs(moved.BoundBox.XMin - 100) < 0.01
        assert abs(moved.BoundBox.YMin - 200) < 0.01
        assert abs(moved.BoundBox.ZMin - 300) < 0.01

    def test_does_not_mutate_original(self):
        s = box(10, 10, 10)
        _ = translate(s, x=100)
        assert abs(s.BoundBox.XMin) < 0.01

    def test_returns_copy(self):
        s = box(10, 10, 10)
        moved = translate(s, x=50)
        assert moved is not s


class TestMirror:
    def test_xz_plane(self):
        s = box(10, 10, 10, at=(0, 5, 0))
        m = mirror(s, plane="XZ")
        assert m.BoundBox.YMax < 0

    def test_invalid_plane(self):
        with pytest.raises(ValueError):
            mirror(box(10, 10, 10), plane="AB")

    def test_default_plane_is_xz(self):
        s = box(10, 10, 10, at=(0, 5, 0))
        assert mirror(s).BoundBox.YMax < 0


class TestFillet:
    def test_returns_shape_with_volume(self):
        s = box(50, 50, 50)
        result = fillet(s, 2)
        assert result.Volume > 0

    def test_returns_original_on_failure(self):
        s = box(1, 1, 1)
        result = fillet(s, 999)  # absurd radius — should fail silently
        assert result.Volume > 0


class TestChamfer:
    def test_returns_shape_with_volume(self):
        s = box(50, 50, 50)
        result = chamfer(s, 2)
        assert result.Volume > 0

    def test_returns_original_on_failure(self):
        s = box(1, 1, 1)
        result = chamfer(s, 999)
        assert result.Volume > 0
