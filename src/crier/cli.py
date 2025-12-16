"""Command-line interface for crier."""

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import get_api_key, set_api_key, load_config
from .converters import parse_markdown_file
from .platforms import PLATFORMS, get_platform

console = Console()


@click.group()
@click.version_option(version=__version__)
def cli():
    """Crier - Cross-post your content to dev.to, Hashnode, Medium, and more."""
    pass


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--to", "-t", "platforms", multiple=True, default=["devto"],
              help="Platform(s) to publish to (can specify multiple)")
@click.option("--draft", is_flag=True, help="Publish as draft")
def publish(file: str, platforms: tuple[str, ...], draft: bool):
    """Publish a markdown file to one or more platforms."""
    article = parse_markdown_file(file)

    if draft:
        article.published = False

    for platform_name in platforms:
        api_key = get_api_key(platform_name)
        if not api_key:
            console.print(f"[red]No API key configured for {platform_name}[/red]")
            console.print(f"Run: crier config set {platform_name}.api_key YOUR_KEY")
            continue

        try:
            platform_cls = get_platform(platform_name)
            platform = platform_cls(api_key)

            console.print(f"[blue]Publishing to {platform_name}...[/blue]")
            result = platform.publish(article)

            if result.success:
                console.print(f"[green]Published![/green] {result.url}")
            else:
                console.print(f"[red]Failed:[/red] {result.error}")

        except Exception as e:
            console.print(f"[red]Error with {platform_name}:[/red] {e}")


@cli.command()
@click.argument("platform")
@click.argument("article_id")
@click.option("--file", "-f", type=click.Path(exists=True), required=True,
              help="Markdown file with updated content")
def update(platform: str, article_id: str, file: str):
    """Update an existing article on a platform."""
    api_key = get_api_key(platform)
    if not api_key:
        console.print(f"[red]No API key configured for {platform}[/red]")
        return

    article = parse_markdown_file(file)

    try:
        platform_cls = get_platform(platform)
        plat = platform_cls(api_key)

        console.print(f"[blue]Updating article {article_id} on {platform}...[/blue]")
        result = plat.update(article_id, article)

        if result.success:
            console.print(f"[green]Updated![/green] {result.url}")
        else:
            console.print(f"[red]Failed:[/red] {result.error}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


@cli.command(name="list")
@click.argument("platform")
@click.option("--limit", "-n", default=10, help="Number of articles to show")
def list_articles(platform: str, limit: int):
    """List your articles on a platform."""
    api_key = get_api_key(platform)
    if not api_key:
        console.print(f"[red]No API key configured for {platform}[/red]")
        return

    try:
        platform_cls = get_platform(platform)
        plat = platform_cls(api_key)

        articles = plat.list_articles(limit)

        if not articles:
            console.print("No articles found.")
            return

        table = Table(title=f"Articles on {platform}")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="green")
        table.add_column("Published", style="yellow")
        table.add_column("URL", style="blue")

        for article in articles:
            table.add_row(
                str(article.get("id", "")),
                article.get("title", "")[:50],
                str(article.get("published", "")),
                article.get("url", ""),
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


@cli.group()
def config():
    """Manage crier configuration."""
    pass


@config.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Set a configuration value (e.g., devto.api_key)."""
    parts = key.split(".")

    if len(parts) == 2 and parts[1] == "api_key":
        platform = parts[0]
        set_api_key(platform, value)
        console.print(f"[green]Set API key for {platform}[/green]")
    else:
        console.print(f"[red]Unknown config key: {key}[/red]")
        console.print("Use: crier config set <platform>.api_key <value>")


@config.command(name="show")
def config_show():
    """Show current configuration (hides API keys)."""
    cfg = load_config()

    if not cfg:
        console.print("No configuration found.")
        console.print(f"Config file: ~/.config/crier/config.yaml")
        return

    table = Table(title="Crier Configuration")
    table.add_column("Platform", style="cyan")
    table.add_column("API Key", style="green")

    platforms = cfg.get("platforms", {})
    for name, settings in platforms.items():
        api_key = settings.get("api_key", "")
        # Mask the API key
        masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "****"
        table.add_row(name, masked)

    console.print(table)


@cli.command()
def platforms():
    """List available platforms."""
    table = Table(title="Available Platforms")
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="green")

    for name in PLATFORMS:
        api_key = get_api_key(name)
        status = "Configured" if api_key else "Not configured"
        style = "green" if api_key else "yellow"
        table.add_row(name, f"[{style}]{status}[/{style}]")

    console.print(table)


if __name__ == "__main__":
    cli()
