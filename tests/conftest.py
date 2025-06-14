import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Provide a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_config_file(temp_dir):
    """Create a mock configuration file."""
    config_file = temp_dir / "config.json"
    config_file.write_text("""{
        "mastodon_instance": "https://mastodon.social",
        "mastodon_token": "test-token",
        "bluesky_handle": "test.bsky.social",
        "bluesky_password": "test-password"
    }""")
    return config_file


@pytest.fixture
def mock_state_file(temp_dir):
    """Create a mock state file path."""
    return temp_dir / "state.json"
