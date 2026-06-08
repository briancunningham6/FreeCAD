"""Tests for elixifree generic core primitives. Run under FreeCAD's Python."""
import sys
import os

# Ensure the Mod/CadClaude directory is on sys.path so `import elixifree` works
# when tests are run from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import FreeCAD
from elixifree import box, cylinder, fuse, cut, translate, mirror, fillet, chamfer


def test_box_dimensions():
    s = box(100, 200, 300)
    bb = s.BoundBox
    assert abs(bb.XLength - 100) < 0.01
    assert abs(bb.YLength - 200) < 0.01
    assert abs(bb.ZLength - 300) < 0.01


def test_box_placement():
    s = box(10, 10, 10, at=(5, 6, 7))
    bb = s.BoundBox
    assert abs(bb.XMin - 5) < 0.01
    assert abs(bb.YMin - 6) < 0.01
    assert abs(bb.ZMin - 7) < 0.01


def test_cylinder_dimensions():
    s = cylinder(50, 100)
    bb = s.BoundBox
    assert abs(bb.XLength - 100) < 0.01  # diameter
    assert abs(bb.ZLength - 100) < 0.01  # height


def test_fuse_combines_shapes():
    a = box(10, 10, 10)
    b = box(10, 10, 10, at=(10, 0, 0))
    result = fuse(a, b)
    assert result.Volume > a.Volume


def test_fuse_requires_two_shapes():
    with pytest.raises(ValueError):
        fuse(box(10, 10, 10))


def test_cut_removes_material():
    base = box(100, 100, 100)
    tool = box(50, 50, 50)
    result = cut(base, tool)
    assert result.Volume < base.Volume


def test_translate_moves_shape():
    s = box(10, 10, 10)
    moved = translate(s, x=100, y=200, z=300)
    bb = moved.BoundBox
    assert abs(bb.XMin - 100) < 0.01
    assert abs(bb.YMin - 200) < 0.01
    assert abs(bb.ZMin - 300) < 0.01


def test_translate_does_not_mutate_original():
    s = box(10, 10, 10)
    _ = translate(s, x=100)
    assert abs(s.BoundBox.XMin) < 0.01


def test_mirror_xz():
    s = box(10, 10, 10, at=(0, 5, 0))
    m = mirror(s, plane="XZ")
    # Original is at Y=5..15; mirror should be at Y=-15..-5
    assert m.BoundBox.YMax < 0


def test_mirror_invalid_plane():
    with pytest.raises(ValueError):
        mirror(box(10, 10, 10), plane="AB")


def test_fillet_returns_shape():
    s = box(50, 50, 50)
    result = fillet(s, 2)
    # Volume should increase slightly or stay same (fillet rounds corners)
    assert result.Volume > 0


def test_chamfer_returns_shape():
    s = box(50, 50, 50)
    result = chamfer(s, 2)
    assert result.Volume > 0
