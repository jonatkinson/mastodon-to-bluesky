from mastodon_to_bluesky import __version__


def test_version():
    assert __version__ == "0.1.0"


def test_cli_import():
    # Test that CLI can be imported
    from mastodon_to_bluesky.cli import cli

    assert cli is not None
