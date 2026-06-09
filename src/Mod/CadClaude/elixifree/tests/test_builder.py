"""Tests for elixifree.builder — BuildResult, BuildError, ComponentBuilder."""
import importlib.util
import os

import pytest

# Import builder directly to avoid triggering elixifree/__init__.py's FreeCAD import.
# conftest.py adds the Mod/CadClaude directory to sys.path.
_spec = importlib.util.spec_from_file_location(
    "elixifree.builder",
    os.path.join(os.path.dirname(__file__), "..", "builder.py"),
)
_builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_builder)
BuildResult = _builder.BuildResult
BuildError = _builder.BuildError
ComponentBuilder = _builder.ComponentBuilder


class TestBuildResult:
    def test_stores_params(self):
        result = BuildResult(shape=None, params={"span": 4000}, gaps=[])
        assert result.params["span"] == 4000

    def test_gaps_default_empty(self):
        result = BuildResult(shape=None, params={})
        assert result.gaps == []

    def test_gaps_accumulate(self):
        result = BuildResult(shape=None, params={}, gaps=["tapered_top: not supported"])
        assert len(result.gaps) == 1
        assert "tapered_top" in result.gaps[0]

    def test_mutable_default_not_shared(self):
        r1 = BuildResult(shape=None, params={})
        r2 = BuildResult(shape=None, params={})
        r1.gaps.append("x")
        assert r2.gaps == []


class TestBuildError:
    def test_is_exception(self):
        with pytest.raises(BuildError):
            raise BuildError("span must be positive")

    def test_message(self):
        err = BuildError("span must be positive")
        assert "span must be positive" in str(err)

    def test_is_exception_subclass(self):
        assert issubclass(BuildError, Exception)


class TestComponentBuilder:
    def test_build_calls_validate_and_geometry(self):
        class MinimalBuilder(ComponentBuilder):
            def _validate(self):
                pass

            def _build_geometry(self):
                return "fake_shape"

            def _params(self):
                return {"key": "value"}

        result = MinimalBuilder().build()
        assert isinstance(result, BuildResult)
        assert result.shape == "fake_shape"
        assert result.params == {"key": "value"}
        assert result.gaps == []

    def test_validate_error_propagates(self):
        class StrictBuilder(ComponentBuilder):
            def _validate(self):
                raise BuildError("invalid")

            def _build_geometry(self):
                return None

            def _params(self):
                return {}

        with pytest.raises(BuildError, match="invalid"):
            StrictBuilder().build()

    def test_geometry_exception_wrapped(self):
        class CrashBuilder(ComponentBuilder):
            def _build_geometry(self):
                raise RuntimeError("oops")

            def _params(self):
                return {}

        with pytest.raises(BuildError, match="Geometry construction failed"):
            CrashBuilder().build()

    def test_log_gap_accumulates(self):
        class GappyBuilder(ComponentBuilder):
            def _build_geometry(self):
                self._log_gap("feature_x: not supported")
                return "shape"

            def _params(self):
                return {}

        result = GappyBuilder().build()
        assert len(result.gaps) == 1
        assert "feature_x" in result.gaps[0]

    def test_build_result_gaps_are_copy(self):
        """Mutating the returned gaps list must not affect the builder state."""
        class GappyBuilder(ComponentBuilder):
            def _build_geometry(self):
                self._log_gap("gap_a")
                return "shape"

            def _params(self):
                return {}

        b = GappyBuilder()
        result = b.build()
        result.gaps.append("injected")
        result2 = b.build()
        assert "injected" not in result2.gaps
