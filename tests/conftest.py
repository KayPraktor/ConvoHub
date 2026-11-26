import os

import pytest

from convohub import config, i18n


@pytest.fixture(autouse=True)
def _isolated_language(tmp_path, monkeypatch):
    """Every test starts with its own (missing) database, so server texts never depend on the user's real
    data folder: the interface language is English until a test chooses otherwise. Tests that need a
    database still point DB_PATH at their own file."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "default.db")
    i18n.reset_cache()
    yield
    i18n.reset_cache()


@pytest.fixture(autouse=True)
def _no_real_keychain(monkeypatch):
    """On a Mac, saving a key would go to the user's login Keychain: tests use the key file instead.
    (tests/test_platform.py has a real Keychain test, run only with CONVOHUB_TEST_KEYCHAIN=1.)"""
    if os.environ.get("CONVOHUB_TEST_KEYCHAIN") != "1":
        monkeypatch.setenv("CONVOHUB_NO_KEYCHAIN", "1")
