# Mastodon to Bluesky Transfer Tool

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A command-line tool to transfer your posts from Mastodon to Bluesky, preserving media attachments, thread structure, and rich text formatting.

## Why This Tool?

As social media platforms evolve, many users find themselves wanting to establish a presence on multiple platforms. This tool helps you migrate your Mastodon content to Bluesky while preserving as much of the original formatting and context as possible. Whether you're cross-posting, migrating, or just backing up your content, this tool automates what would otherwise be a tedious manual process.

## Features

- Transfer posts from Mastodon to Bluesky
- Preserve media attachments (up to 4 images per post)
- Convert long posts into proper threads
- Parse and preserve mentions, hashtags, and links
- Handle content warnings
- Incremental transfers (remembers what's been transferred)
- Dry-run mode for testing
- Filter by date range, replies, and boosts
- Interactive mode for selective transfers
- Configuration file and environment variable support
- Automatic retry with exponential backoff

## Requirements

- Python 3.11 or higher
- A Mastodon account with an access token
- A Bluesky account with an app password

## Installation

### Using uv tool (recommended for regular use)

```bash
# Install the tool globally
uv tool install mastodon-to-bluesky

# Now use it directly
mastodon-to-bluesky transfer --help

# Update to latest version
uv tool upgrade mastodon-to-bluesky

# Uninstall
uv tool uninstall mastodon-to-bluesky
```

### Using uvx (for one-time use)

```bash
# Run without installing
uvx mastodon-to-bluesky transfer --help

# Or use with environment variables set
uvx mastodon-to-bluesky transfer --limit 10

# Run a specific version
uvx mastodon-to-bluesky@1.0.0 transfer --help
```

### Using pip

```bash
pip install mastodon-to-bluesky
```

### From source

```bash
git clone https://github.com/jonatkinson/mastodon-to-bluesky.git
cd mastodon-to-bluesky
uv pip install -e .
```

## Quick Start

1. **Get your Mastodon access token:**
   - Go to your Mastodon instance settings
   - Navigate to Development > New Application
   - Give it a name and grant read permissions
   - Copy the access token

2. **Get your Bluesky app password:**
   - Go to Settings > App Passwords in Bluesky
   - Create a new app password
   - Copy the generated password

3. **Run the transfer:**

```bash
uvx mastodon-to-bluesky transfer \
  --mastodon-instance https://mastodon.social \
  --mastodon-token YOUR_MASTODON_TOKEN \
  --bluesky-handle you.bsky.social \
  --bluesky-password YOUR_APP_PASSWORD
```

## Configuration

### Configuration File

Create `~/.config/mastodon-to-bluesky/config.json`:

```json
{
  "mastodon_instance": "https://mastodon.social",
  "mastodon_token": "your-mastodon-token",
  "bluesky_handle": "you.bsky.social",
  "bluesky_password": "your-app-password"
}
```

### Environment Variables

```bash
export MASTODON_INSTANCE="https://mastodon.social"
export MASTODON_TOKEN="your-mastodon-token"
export BLUESKY_HANDLE="you.bsky.social"
export BLUESKY_PASSWORD="your-app-password"
```

## Usage Examples

### Test Connections

Test your Mastodon connection:
```bash
uvx mastodon-to-bluesky test-mastodon --limit 5
```

Test your Bluesky connection:
```bash
uvx mastodon-to-bluesky test-bluesky
```

### Transfer Options

Dry run (preview what would be posted):
```bash
uvx mastodon-to-bluesky transfer --dry-run --limit 10
```

Transfer posts from a specific date range:
```bash
uvx mastodon-to-bluesky transfer \
  --since 2024-01-01 \
  --until 2024-12-31
```

Include replies and boosts:
```bash
uvx mastodon-to-bluesky transfer \
  --include-replies \
  --include-boosts
```

Interactive mode (select posts one by one):
```bash
uvx mastodon-to-bluesky transfer --interactive --limit 20
```

Retry failed posts:
```bash
uvx mastodon-to-bluesky retry-failed
```

## How It Works

1. **Fetches posts** from your Mastodon account via the API
2. **Converts content** from HTML to plain text while preserving formatting
3. **Downloads media** attachments (images only, up to 4 per post)
4. **Splits long posts** into threads (Bluesky has a 300-character limit)
5. **Parses rich text** to create proper mentions, hashtags, and links
6. **Creates posts** on Bluesky with proper threading
7. **Tracks progress** to avoid duplicates in future runs

## Features in Detail

### Media Handling
- Downloads and re-uploads images (JPEG, PNG, GIF, WebP)
- Preserves alt text from Mastodon
- Supports up to 4 images per post (Bluesky limitation)
- Videos and audio files are skipped with a note

### Text Processing
- Converts HTML to plain text
- Preserves paragraph breaks
- Handles mentions (@user.bsky.social format)
- Preserves hashtags and links
- Content warnings become "CW: [warning]" prefix

### Thread Creation
- Posts over 300 characters are split into threads
- Each part is numbered (e.g., "[1/3]", "[2/3]", "[3/3]")
- Smart splitting at sentence boundaries
- Maintains readability at split points

### State Management
- Tracks transferred post IDs in `.mastodon-to-bluesky-state.json`
- Stores state in the current directory by default
- Allows incremental transfers
- Prevents duplicate posts

### Retry Logic
- Automatic retry for failed posts with exponential backoff
- Categorizes errors (rate limit, network, API errors)
- Configurable retry attempts (default: 3)
- Manual retry command for persistent failures

## Limitations

- **Post timestamps**: Bluesky doesn't support backdating posts. All transferred posts will have the current date/time. The original Mastodon timestamp is appended to each post as "[Originally posted: YYYY-MM-DD HH:MM UTC]"
- **Media types**: Only supports image media (no video/audio yet)
- **Polls**: Not supported (Bluesky doesn't have polls)
- **Formatting**: Some rich text formatting may be simplified
- **Quote posts**: Converted to regular posts with links
- **Post visibility**: All posts are public on Bluesky (no granular privacy controls)

## Troubleshooting

### "Rate limit exceeded"
The tool handles rate limits automatically by waiting. If you see repeated rate limit errors, wait a few minutes before retrying.

### "Authentication failed"
- For Mastodon: Check your access token has read permissions
- For Bluesky: Make sure you're using an app password, not your main password

### "Failed to parse mention"
Some Mastodon mentions may not have corresponding Bluesky accounts. These are left as plain text.

### Media upload failures
- Check file size (Bluesky has limits)
- Ensure the media URL is still accessible
- Try running with fewer posts at a time

### "Invalid datetime format" errors
- This is usually due to timezone handling
- The tool now converts all timestamps to current time due to Bluesky limitations
- Original timestamps are preserved in the post text

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/jonatkinson/mastodon-to-bluesky.git
cd mastodon-to-bluesky

# Install dependencies
uv sync

# Run tests
uv run pytest

# Run with local changes
uv run mastodon-to-bluesky --help
```

### Project Structure

```
mastodon-to-bluesky/
├── src/mastodon_to_bluesky/
│   ├── __init__.py
│   ├── cli.py          # Command-line interface
│   ├── mastodon.py     # Mastodon API client
│   ├── bluesky.py      # Bluesky API client
│   ├── models.py       # Data models
│   └── transfer.py     # Transfer logic
├── tests/              # Test files
├── pyproject.toml      # Project configuration
└── README.md           # This file
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a list of changes in each version.

## Acknowledgments

- Thanks to the Mastodon and Bluesky communities
- Built with [atproto](https://atproto.com/) for Bluesky integration
- Uses [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) for HTML parsing
- CLI powered by [Click](https://click.palletsprojects.com/) and [Rich](https://rich.readthedocs.io/)