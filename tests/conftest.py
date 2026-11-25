"""Shared fixtures for the HomePool tests.

The pure modules under ``pool/`` and ``modes/`` need nothing from Home
Assistant. The integration tests use pytest-homeassistant-custom-component,
which provides a real ``hass`` instance; this switch lets it load the
component from ``custom_components/``.
"""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow the test hass to load custom_components/homepool."""
    yield
