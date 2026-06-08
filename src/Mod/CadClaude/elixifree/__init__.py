"""
ElixiFree — declarative CAD primitives over native FreeCAD Part.
All functions return Part.Shape. No custom objects, no document state.
"""
import FreeCAD
import Part
from FreeCAD import Vector


def box(w, h, d, at=(0, 0, 0)):
    """Axis-aligned box: width (X), height (Y), depth (Z), placed at `at`."""
    return Part.makeBox(w, h, d, Vector(*at))


def cylinder(r, h, at=(0, 0, 0)):
    """Upright cylinder (Z axis) of radius `r` and height `h`, placed at `at`."""
    return Part.makeCylinder(r, h, Vector(*at))


def fuse(*shapes):
    """Fuse two or more shapes into one. Raises ValueError if fewer than 2 shapes."""
    if len(shapes) < 2:
        raise ValueError("fuse() requires at least 2 shapes")
    result = shapes[0]
    for s in shapes[1:]:
        result = result.fuse(s)
    return result


def cut(base, *tools):
    """Cut one or more tool shapes from base, in order."""
    result = base
    for tool in tools:
        result = result.cut(tool)
    return result


def translate(shape, x=0, y=0, z=0):
    """Return a copy of shape moved by (x, y, z)."""
    copy = shape.copy()
    copy.translate(Vector(x, y, z))
    return copy


def mirror(shape, plane="XZ"):
    """Mirror shape about a named plane: 'XY', 'XZ', or 'YZ'."""
    planes = {
        "XY": (Vector(0, 0, 0), Vector(0, 0, 1)),
        "XZ": (Vector(0, 0, 0), Vector(0, 1, 0)),
        "YZ": (Vector(0, 0, 0), Vector(1, 0, 0)),
    }
    if plane not in planes:
        raise ValueError(f"mirror() plane must be one of {list(planes.keys())}")
    origin, normal = planes[plane]
    return shape.mirror(origin, normal)


def fillet(shape, radius, edge_selector=None):
    """
    Fillet edges of shape. If edge_selector is None, fillets all edges.
    edge_selector is a callable (edge) -> bool to filter edges.
    Returns shape unmodified on failure (fillet often fails on degenerate geometry).
    """
    try:
        edges = shape.Edges
        if edge_selector is not None:
            edges = [e for e in edges if edge_selector(e)]
        return shape.makeFillet(radius, edges)
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("fillet failed, returning shape unmodified: %s", e)
        return shape


def chamfer(shape, size, edge_selector=None):
    """
    Chamfer edges of shape. If edge_selector is None, chamfers all edges.
    Returns shape unmodified on failure.
    """
    try:
        edges = shape.Edges
        if edge_selector is not None:
            edges = [e for e in edges if edge_selector(e)]
        return shape.makeChamfer(size, edges)
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("chamfer failed, returning shape unmodified: %s", e)
        return shape


def add_to_doc(shape, name, doc=None):
    """
    Add shape to a FreeCAD document as a Part::Feature, recompute, and fit view.
    Creates a new document named `name` if doc is None and no active document exists.
    """
    if doc is None:
        doc = FreeCAD.ActiveDocument or FreeCAD.newDocument(name)
    feature = doc.addObject("Part::Feature", name)
    feature.Shape = shape
    doc.recompute()
    if FreeCAD.GuiUp:
        FreeCAD.Gui.ActiveDocument.ActiveView.fitAll()
    return feature
