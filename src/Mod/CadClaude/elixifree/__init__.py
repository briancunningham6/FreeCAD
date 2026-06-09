"""
ElixiFree — declarative CAD primitives over native FreeCAD Part.

Core layer: domain-agnostic geometry functions that return Part.Shape.
No custom objects, no document state.

Domain layers live under elixifree.domains.*:
    elixifree.domains.sip  — SIP (Structural Insulated Panel) builders

Typical usage in a component script::

    from elixifree import box, cut, add_to_doc
    result = cut(box(500, 300, 200), box(490, 290, 200, at=(5, 5, 5)))
    add_to_doc(result, "Body")
"""
from elixifree.builder import BuildResult, BuildError, ComponentBuilder
import FreeCAD
import Part
from FreeCAD import Vector

__all__ = [
    # Builder infrastructure
    "BuildResult",
    "BuildError",
    "ComponentBuilder",
    # Core geometry primitives
    "box",
    "cylinder",
    "fuse",
    "cut",
    "translate",
    "mirror",
    "fillet",
    "chamfer",
    "add_to_doc",
]


def box(w, h, d, at=(0, 0, 0)):
    """Axis-aligned box: width (X) × height (Y) × depth (Z), with corner at *at*.

    Args:
        w: Width along X axis (mm).
        h: Height along Y axis (mm).
        d: Depth along Z axis (mm).
        at: (x, y, z) tuple for the bottom-left-front corner. Default (0, 0, 0).

    Returns:
        Part.Shape
    """
    return Part.makeBox(w, h, d, Vector(*at))


def cylinder(r, h, at=(0, 0, 0)):
    """Upright cylinder along Z axis with radius *r* and height *h*.

    Args:
        r: Radius (mm).
        h: Height along Z axis (mm).
        at: (x, y, z) tuple for the centre of the bottom face. Default (0, 0, 0).

    Returns:
        Part.Shape
    """
    return Part.makeCylinder(r, h, Vector(*at))


def fuse(*shapes):
    """Fuse two or more shapes into one solid.

    Args:
        *shapes: Two or more Part.Shape objects.

    Returns:
        Part.Shape — the Boolean union.

    Raises:
        ValueError: If fewer than 2 shapes are supplied.
    """
    if len(shapes) < 2:
        raise ValueError("fuse() requires at least 2 shapes")
    result = shapes[0]
    for s in shapes[1:]:
        result = result.fuse(s)
    return result


def cut(base, *tools):
    """Subtract one or more tool shapes from *base*, applied left-to-right.

    Args:
        base: The base Part.Shape to cut from.
        *tools: One or more Part.Shape objects to subtract.

    Returns:
        Part.Shape — base with all tools subtracted.
    """
    result = base
    for tool in tools:
        result = result.cut(tool)
    return result


def translate(shape, x=0, y=0, z=0):
    """Return a translated copy of *shape* — the original is not modified.

    Args:
        shape: Part.Shape to move.
        x: X displacement (mm). Default 0.
        y: Y displacement (mm). Default 0.
        z: Z displacement (mm). Default 0.

    Returns:
        Part.Shape — a new copy at the new position.
    """
    copy = shape.copy()
    copy.translate(Vector(x, y, z))
    return copy


def mirror(shape, plane="XZ"):
    """Mirror *shape* about a named global plane through the origin.

    Args:
        shape: Part.Shape to mirror.
        plane: ``"XY"``, ``"XZ"`` (default), or ``"YZ"``.

    Returns:
        Part.Shape — the mirrored copy.

    Raises:
        ValueError: If *plane* is not one of the three supported values.
    """
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
    """Round edges of *shape* with the given *radius*.

    Args:
        shape: Part.Shape to fillet.
        radius: Fillet radius (mm).
        edge_selector: Optional callable ``(edge) -> bool`` to restrict which
            edges are filleted. If ``None``, all edges are filleted.

    Returns:
        Part.Shape — filleted shape, or *shape* unmodified if the fillet fails
        (OCCT often fails on degenerate geometry or very large radii).
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
    """Chamfer edges of *shape* with the given *size*.

    Args:
        shape: Part.Shape to chamfer.
        size: Chamfer size (mm).
        edge_selector: Optional callable ``(edge) -> bool`` to restrict which
            edges are chamfered. If ``None``, all edges are chamfered.

    Returns:
        Part.Shape — chamfered shape, or *shape* unmodified if the chamfer fails.
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
    """Add *shape* to a FreeCAD document as a ``Part::Feature``, then recompute.

    Creates a new document named *name* if no active document exists and *doc*
    is not supplied.  In headless (worker) mode the new document is also set as
    the active document so downstream export code can find it.

    Args:
        shape: Part.Shape to add.
        name: Feature name (also used as the document name when creating one).
        doc: Existing FreeCAD document to add to. If ``None``, uses or creates
            the active document.

    Returns:
        The newly created ``Part::Feature`` object.
    """
    if doc is None:
        doc = FreeCAD.ActiveDocument
        if doc is None:
            doc = FreeCAD.newDocument(name)
            FreeCAD.setActiveDocument(doc.Name)
    feature = doc.addObject("Part::Feature", name)
    feature.Shape = shape
    doc.recompute()
    if FreeCAD.GuiUp:
        FreeCAD.Gui.ActiveDocument.ActiveView.fitAll()
    return feature
