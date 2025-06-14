"""Interactive mode for selective post transfer."""

from datetime import datetime

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from mastodon_to_bluesky.models import MastodonPost

console = Console()


class InteractiveTransfer:
    """Handle interactive post selection and editing."""

    def __init__(self, transfer_manager):
        self.transfer_manager = transfer_manager

    def format_post_preview(self, post: MastodonPost) -> Panel:
        """Format a post for preview display."""
        # Convert HTML to text for preview
        text = self.transfer_manager._html_to_text(post.content)

        # Create content sections
        content = Text()

        # Add header info
        content.append(f"ID: {post.id}\n", style="dim")
        content.append(f"Date: {post.created_at.strftime('%Y-%m-%d %H:%M')}\n", style="dim")

        # Add content warning if present
        if post.spoiler_text:
            content.append(f"\nCW: {post.spoiler_text}\n", style="yellow bold")

        # Add main content
        content.append(f"\n{text}\n", style="white")

        # Add media info
        if post.media_attachments:
            content.append(f"\n📎 {len(post.media_attachments)} media attachment(s)\n", style="cyan")
            for i, media in enumerate(post.media_attachments, 1):
                media_type = media.get("type", "unknown")
                desc = media.get("description", "No description")
                content.append(f"  {i}. {media_type}: {desc[:50]}...\n", style="dim cyan")

        # Add metadata
        if post.in_reply_to_id:
            content.append("\n↩️  This is a reply\n", style="dim yellow")
        if post.reblog:
            content.append("\n🔁 This is a boost\n", style="dim green")

        # Calculate thread info
        posts_needed = len(self.transfer_manager._split_text(text, 300))
        if posts_needed > 1:
            content.append(f"\n🧵 Will create {posts_needed} posts\n", style="blue")

        return Panel(
            content,
            title=f"[bold]Post from {post.url}[/bold]",
            border_style="blue",
            padding=(1, 2),
        )

    def edit_post_text(self, original_text: str) -> str:
        """Allow user to edit post text."""
        console.print("\n[yellow]Current text:[/yellow]")
        console.print(original_text)
        console.print("\n[dim]Press Ctrl+D when done, Ctrl+C to cancel[/dim]")

        try:
            lines = []
            while True:
                try:
                    line = input()
                    lines.append(line)
                except EOFError:
                    break

            edited_text = "\n".join(lines)
            return edited_text if edited_text.strip() else original_text

        except KeyboardInterrupt:
            return original_text

    def process_post_interactive(self, post: MastodonPost) -> str:
        """Process a single post interactively. Returns action: transfer, skip, or quit."""
        # Show post preview
        console.print(self.format_post_preview(post))

        # Show options
        console.print("\n[bold]What would you like to do?[/bold]")
        console.print("[green]t[/green] - Transfer this post")
        console.print("[yellow]s[/yellow] - Skip this post")
        console.print("[blue]e[/blue] - Edit before transferring")
        console.print("[red]q[/red] - Quit interactive mode")

        while True:
            choice = click.prompt(
                "\nYour choice",
                type=click.Choice(["t", "s", "e", "q"], case_sensitive=False),
                show_choices=False,
            ).lower()

            if choice == "t":
                return "transfer"
            elif choice == "s":
                return "skip"
            elif choice == "e":
                # Edit the post
                edited_text = self.edit_post_text(self.transfer_manager._html_to_text(post.content))
                # Update post content (convert back to HTML-ish format)
                post.content = f"<p>{edited_text}</p>"
                console.print("[green]✓ Post updated[/green]")
                # Show preview again
                console.print(self.format_post_preview(post))
                continue
            elif choice == "q":
                return "quit"

    def run_interactive_transfer(
        self,
        posts,
        skip_existing: bool = True,
    ) -> dict:
        """Run the interactive transfer process."""
        stats = {
            "processed": 0,
            "transferred": 0,
            "skipped": 0,
            "errors": 0,
            "user_skipped": 0,
        }

        console.print("[bold cyan]Interactive Transfer Mode[/bold cyan]")
        console.print("You'll be shown each post and can choose what to do.\n")

        for post in posts:
            stats["processed"] += 1

            # Skip if already transferred
            if skip_existing and post.id in self.transfer_manager.state.transferred_ids:
                stats["skipped"] += 1
                continue

            # Clear screen for better visibility
            console.clear()
            console.print(f"[bold]Post {stats['processed']} of ?[/bold]\n")

            # Process post interactively
            action = self.process_post_interactive(post)

            if action == "transfer":
                console.print("\n[yellow]Transferring post...[/yellow]")
                success = self.transfer_manager._transfer_post(post)

                if success:
                    self.transfer_manager.state.transferred_ids.add(post.id)
                    self.transfer_manager.state.last_mastodon_id = post.id
                    self.transfer_manager.state.last_updated = datetime.now()
                    self.transfer_manager._save_state()
                    stats["transferred"] += 1
                    console.print("[green]✓ Post transferred successfully![/green]")
                else:
                    stats["errors"] += 1
                    console.print("[red]✗ Failed to transfer post[/red]")

                # Pause before next post
                if not click.confirm("\nContinue to next post?", default=True):
                    break

            elif action == "skip":
                stats["user_skipped"] += 1
                console.print("[yellow]Post skipped[/yellow]")

            elif action == "quit":
                console.print("\n[yellow]Exiting interactive mode...[/yellow]")
                break

        # Show summary
        console.print("\n[bold]Transfer Summary:[/bold]")
        console.print(f"Processed: {stats['processed']}")
        console.print(f"Transferred: {stats['transferred']}")
        console.print(f"Skipped (existing): {stats['skipped']}")
        console.print(f"Skipped (by user): {stats['user_skipped']}")
        console.print(f"Errors: {stats['errors']}")

        return stats
