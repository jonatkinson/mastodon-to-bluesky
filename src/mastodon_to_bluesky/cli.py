import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from mastodon_to_bluesky.bluesky import BlueskyClient
from mastodon_to_bluesky.mastodon import MastodonClient
from mastodon_to_bluesky.transfer import TransferManager

console = Console()


def load_config():
    config = {}
    config_path = Path.home() / ".config" / "mastodon-to-bluesky" / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    
    # Environment variables override config file
    env_mapping = {
        "MASTODON_INSTANCE": "mastodon_instance",
        "MASTODON_TOKEN": "mastodon_token",
        "BLUESKY_HANDLE": "bluesky_handle",
        "BLUESKY_PASSWORD": "bluesky_password",
    }
    
    for env_var, config_key in env_mapping.items():
        if value := os.environ.get(env_var):
            config[config_key] = value
    
    return config


@click.group()
@click.version_option()
def cli():
    """Transfer posts from Mastodon to Bluesky."""
    pass


@cli.command()
@click.option(
    "--instance",
    help="Mastodon instance URL (e.g., https://mastodon.social)",
    required=True,
)
@click.option(
    "--token",
    help="Mastodon access token",
    required=True,
)
@click.option(
    "--limit",
    type=int,
    default=10,
    help="Maximum number of posts to fetch (default: 10)",
)
@click.option(
    "--include-replies",
    is_flag=True,
    help="Include replies in the output",
)
@click.option(
    "--include-boosts",
    is_flag=True,
    help="Include boosts/reblogs in the output",
)
def test_mastodon(
    instance: str,
    token: str,
    limit: int,
    include_replies: bool,
    include_boosts: bool,
):
    """Test Mastodon API connection and fetch posts."""
    console.print(f"[bold]Testing Mastodon API connection...[/bold]")
    console.print(f"Instance: {instance}")
    
    try:
        # Initialize and authenticate
        client = MastodonClient(instance, token)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Authenticating...", total=None)
            account = client.authenticate()
            progress.update(task, description=f"Authenticated as @{account['username']}")
        
        # Fetch posts
        console.print(f"\n[bold]Fetching up to {limit} posts...[/bold]")
        posts = client.get_posts(
            limit=limit,
            include_replies=include_replies,
            include_boosts=include_boosts,
        )
        
        if not posts:
            console.print("[yellow]No posts found[/yellow]")
            return
        
        console.print(f"[green]Found {len(posts)} posts[/green]\n")
        
        # Display posts in a table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="dim", width=20)
        table.add_column("Date", width=20)
        table.add_column("Content", width=50)
        table.add_column("Media", width=10)
        table.add_column("Type", width=10)
        
        for post in posts[:10]:  # Show max 10 in table
            # Truncate content for display
            content = post.content[:47] + "..." if len(post.content) > 50 else post.content
            # Remove HTML tags for cleaner display
            content = content.replace("<p>", "").replace("</p>", "").replace("<br>", " ")
            
            post_type = "post"
            if post.reblog:
                post_type = "boost"
            elif post.in_reply_to_id:
                post_type = "reply"
            
            table.add_row(
                post.id,
                post.created_at.strftime("%Y-%m-%d %H:%M"),
                content,
                str(len(post.media_attachments)),
                post_type,
            )
        
        console.print(table)
        
        # Summary statistics
        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"Total posts: {len(posts)}")
        console.print(f"Posts with media: {sum(1 for p in posts if p.media_attachments)}")
        console.print(f"Replies: {sum(1 for p in posts if p.in_reply_to_id)}")
        console.print(f"Boosts: {sum(1 for p in posts if p.reblog)}")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option(
    "--mastodon-instance",
    help="Mastodon instance URL (e.g., https://mastodon.social)",
    required=True,
)
@click.option(
    "--mastodon-token",
    help="Mastodon access token",
    required=True,
)
@click.option(
    "--bluesky-handle",
    help="Bluesky handle (e.g., user.bsky.social)",
    required=True,
)
@click.option(
    "--bluesky-password",
    help="Bluesky app password",
    required=True,
)
@click.option(
    "--limit",
    type=int,
    help="Maximum number of posts to transfer",
)
@click.option(
    "--since",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Only transfer posts after this date",
)
@click.option(
    "--until",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Only transfer posts before this date",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview what would be transferred without actually doing it",
)
@click.option(
    "--skip-existing",
    is_flag=True,
    default=True,
    help="Skip posts that have already been transferred (default: True)",
)
@click.option(
    "--include-replies",
    is_flag=True,
    help="Include replies in the transfer",
)
@click.option(
    "--include-boosts",
    is_flag=True,
    help="Include boosts/reblogs in the transfer",
)
@click.option(
    "--state-file",
    type=click.Path(),
    default=".mastodon-to-bluesky-state.json",
    help="File to store transfer state",
)
def transfer(
    mastodon_instance: str,
    mastodon_token: str,
    bluesky_handle: str,
    bluesky_password: str,
    limit: Optional[int],
    since: Optional[datetime],
    until: Optional[datetime],
    dry_run: bool,
    skip_existing: bool,
    include_replies: bool,
    include_boosts: bool,
    state_file: str,
):
    """Transfer posts from Mastodon to Bluesky."""
    # Load config and override with CLI options
    config = load_config()
    
    mastodon_instance = mastodon_instance or config.get("mastodon_instance")
    mastodon_token = mastodon_token or config.get("mastodon_token")
    bluesky_handle = bluesky_handle or config.get("bluesky_handle")
    bluesky_password = bluesky_password or config.get("bluesky_password")
    
    # Validate required options
    if not all([mastodon_instance, mastodon_token, bluesky_handle, bluesky_password]):
        console.print("[red]Error: Missing required credentials[/red]")
        console.print("Please provide all required options or set them in environment variables/config file")
        sys.exit(1)
    
    # Initialize clients
    console.print(f"[bold]Connecting to Mastodon instance:[/bold] {mastodon_instance}")
    mastodon = MastodonClient(mastodon_instance, mastodon_token)
    
    console.print(f"[bold]Connecting to Bluesky as:[/bold] {bluesky_handle}")
    bluesky = BlueskyClient(bluesky_handle, bluesky_password)
    
    # Initialize transfer manager
    transfer_manager = TransferManager(
        mastodon_client=mastodon,
        bluesky_client=bluesky,
        state_file=Path(state_file),
        dry_run=dry_run,
    )
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Authenticating...", total=None)
            
            # Authenticate both services
            mastodon.authenticate()
            progress.update(task, description="Authenticated with Mastodon")
            
            bluesky.authenticate()
            progress.update(task, description="Authenticated with Bluesky")
            
            # Run the transfer
            progress.update(task, description="Starting transfer...")
            
        result = transfer_manager.transfer_posts(
            limit=limit,
            since=since,
            until=until,
            skip_existing=skip_existing,
            include_replies=include_replies,
            include_boosts=include_boosts,
        )
        
        # Display results
        console.print()
        console.print("[bold green]Transfer complete![/bold green]")
        console.print(f"Posts processed: {result['processed']}")
        console.print(f"Posts transferred: {result['transferred']}")
        console.print(f"Posts skipped: {result['skipped']}")
        if result.get('errors'):
            console.print(f"[yellow]Errors: {result['errors']}[/yellow]")
        
        if dry_run:
            console.print()
            console.print("[yellow]This was a dry run. No posts were actually transferred.[/yellow]")
    
    except KeyboardInterrupt:
        console.print("\n[yellow]Transfer interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    cli()