from datetime import datetime

from mastodon_to_bluesky.models import BlueskyPost, MastodonPost, TransferState


class TestMastodonPost:
    def test_initialization(self):
        post = MastodonPost(
            id="123456",
            created_at=datetime(2024, 1, 15, 10, 30, 0),
            content="<p>Hello world!</p>",
            url="https://mastodon.social/@user/123456",
        )

        assert post.id == "123456"
        assert post.created_at == datetime(2024, 1, 15, 10, 30, 0)
        assert post.content == "<p>Hello world!</p>"
        assert post.url == "https://mastodon.social/@user/123456"
        assert post.reblog is None
        assert post.in_reply_to_id is None
        assert post.spoiler_text == ""
        assert post.visibility == "public"
        assert post.media_attachments == []

    def test_with_media(self):
        post = MastodonPost(
            id="123",
            created_at=datetime.now(),
            content="<p>With media</p>",
            url="https://example.com",
            media_attachments=[{"type": "image", "url": "https://example.com/image.jpg"}],
        )

        assert len(post.media_attachments) == 1
        assert post.media_attachments[0]["type"] == "image"


class TestBlueskyPost:
    def test_initialization(self):
        post = BlueskyPost(text="Hello Bluesky!", created_at=datetime(2024, 1, 15, 12, 0, 0))

        assert post.text == "Hello Bluesky!"
        assert post.created_at == datetime(2024, 1, 15, 12, 0, 0)
        assert post.facets == []
        assert post.embed is None
        assert post.reply is None

    def test_with_facets(self):
        post = BlueskyPost(
            text="Test post",
            created_at=datetime.now(),
            facets=[{"index": {"byteStart": 0, "byteEnd": 4}, "features": [{"$type": "app.bsky.richtext.facet#link"}]}],
        )

        assert len(post.facets) == 1
        assert post.facets[0]["index"]["byteStart"] == 0


class TestTransferState:
    def test_initialization(self):
        state = TransferState()

        assert state.last_mastodon_id is None
        assert state.transferred_ids == set()
        assert isinstance(state.last_updated, datetime)

    def test_with_data(self):
        state = TransferState(last_mastodon_id="123456", transferred_ids={"123", "456", "789"})

        assert state.last_mastodon_id == "123456"
        assert len(state.transferred_ids) == 3
        assert "123" in state.transferred_ids
