# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-01-14

### Added
- Initial release
- Transfer posts from Mastodon to Bluesky
- Support for media attachments (images only)
- Automatic thread creation for long posts
- Rich text parsing (mentions, hashtags, links)
- Content warning handling
- State tracking for incremental transfers
- Dry-run mode
- Interactive mode for selective transfers
- Date range filtering
- Reply and boost filtering
- Retry mechanism with exponential backoff
- Configuration file and environment variable support
- Test commands for both platforms

### Known Issues
- Bluesky doesn't support backdating posts, so all posts appear with current timestamps
- Original timestamps are appended to post content as a workaround
- Video and audio attachments are not supported
- Some rich text formatting may be simplified

[Unreleased]: https://github.com/jonatkinson/mastodon-to-bluesky/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jonatkinson/mastodon-to-bluesky/releases/tag/v0.1.0