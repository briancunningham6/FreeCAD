"""
Shared pytest configuration for ElixiFree tests.

Adds the parent Mod/CadClaude directory to sys.path so that
`import elixifree` works regardless of where pytest is invoked from.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
