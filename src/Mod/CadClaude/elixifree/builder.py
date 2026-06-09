"""
ElixiFree builder infrastructure.

BuildResult   — returned by every builder's .build() call.
BuildError    — raised for invalid parameters or geometry failures.
ComponentBuilder — base class all domain builders extend.
"""


class BuildResult:
    """
    The output of a builder's .build() call.

    shape:  native Part.Shape — assign directly to feature.Shape
    params: plain dict of the builder's input parameters — serialisable,
            diffable, usable as test fixtures
    gaps:   list of strings describing geometry the library could not handle
            declaratively — logged for future library development
    """

    def __init__(self, shape, params, gaps=None):
        self.shape = shape
        self.params = params
        self.gaps = gaps or []

    def add_to_doc(self, name, doc=None):
        """
        Add shape to a FreeCAD document as a Part::Feature.
        Creates a new document if doc is None and no active document exists.
        """
        import FreeCAD
        if doc is None:
            doc = FreeCAD.ActiveDocument or FreeCAD.newDocument(name)
        feature = doc.addObject("Part::Feature", name)
        feature.Shape = self.shape
        doc.recompute()
        if FreeCAD.GuiUp:
            FreeCAD.Gui.ActiveDocument.ActiveView.fitAll()
        return feature


class BuildError(Exception):
    """Raised when builder parameters are invalid or geometry construction fails."""
    pass


class ComponentBuilder:
    """
    Base class for all ElixiFree domain builders.

    Subclasses must implement:
      _validate()        — raise BuildError for invalid parameter combinations
      _build_geometry()  — return a Part.Shape
      _params()          — return a plain dict of input parameters

    Gap logging:
      Call self._log_gap(description) when falling back to raw Part calls.
      Gaps are included in the BuildResult for surfacing in the Lab UI.
    """

    def __init__(self):
        self._gaps = []

    def build(self):
        """Validate parameters, build geometry, return BuildResult."""
        self._validate()
        try:
            shape = self._build_geometry()
        except BuildError:
            raise
        except Exception as e:
            raise BuildError(f"Geometry construction failed: {e}") from e
        return BuildResult(shape=shape, params=self._params(), gaps=list(self._gaps))

    def _validate(self):
        """Override to raise BuildError for invalid parameters."""
        pass

    def _build_geometry(self):
        """Override to return a Part.Shape."""
        raise NotImplementedError(f"{type(self).__name__} must implement _build_geometry()")

    def _params(self):
        """Override to return a plain dict of input parameters."""
        raise NotImplementedError(f"{type(self).__name__} must implement _params()")

    def _log_gap(self, description):
        """
        Record a geometry gap — called when falling back to raw Part calls.
        The description should name the feature and explain why the library
        cannot handle it declaratively.
        Example: self._log_gap("tapered_top: non-rectangular wall tops not supported")
        """
        import logging
        logging.getLogger(__name__).info("[ElixiFree gap] %s", description)
        self._gaps.append(description)
