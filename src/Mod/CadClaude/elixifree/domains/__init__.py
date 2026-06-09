"""
ElixiFree domain builders.

Each sub-module provides design-stage builders for a specific construction domain.
Builders return BuildResult objects containing the shape, parameters, and any gap
descriptions for geometry the library could not handle declaratively.

Available domains:
    elixifree.domains.sip  — SIP (Structural Insulated Panel) building components
"""

__all__ = ["sip"]
