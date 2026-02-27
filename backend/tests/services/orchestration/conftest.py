"""Shared fixtures for orchestration tests."""

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "l3: L3 convergence engine tests")
