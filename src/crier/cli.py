"""Command-line interface for crier."""

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import (
    get_api_key, set_api_key, load_config, get_profile, set_profile, get_all_profiles,
    get_content_paths, add_content_path, remove_content_path, set_content_paths,
)
from .converters import parse_markdown_file
from .platforms import PLATFORMS, get_platform
from .registry import (
    record_publication,
    get_post_status,
    get_all_posts,
    get_registry_path,
    is_published,
    has_content_changed,
)

console = Console()


def _has_valid_front_matter(file_path: Path) -> bool:
    """Check if a file has valid front matter with a title."""
    try:
        article = parse_markdown_file(str(file_path))
        return bool(article.title)
    except Exception:
        return False


def _find_content_files(explicit_path: str | None = None) -> list[Path]:
    """Find content files to process.

    Args:
        explicit_path: If provided, scan this path. Otherwise use content_paths config.

    Returns:
        List of Path objects for files with valid front matter.
    """
    files: list[Path] = []

    if explicit_path:
        # Explicit path provided - use it
        path_obj = Path(explicit_path)
        if path_obj.is_file():
            files = [path_obj]
        else:
            files = list(path_obj.glob("**/*.md"))
    else:
        # Use configured content_paths
        content_paths = get_content_paths()
        if not content_paths:
            return []

        for content_path in content_paths:
            path_obj = Path(content_path)
            if path_obj.is_file():
                files.append(path_obj)
            elif path_obj.is_dir():
                files.extend(path_obj.glob("**/*.md"))

    # Filter to only files with valid front matter
    valid_files = [f for f in files if _has_valid_front_matter(f)]
    return valid_files


@click.group()
@click.version_option(version=__version__)
def cli():
    """Crier - Cross-post your content everywhere."""
    pass


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--to", "-t", "platform_args", multiple=True,
              help="Platform(s) to publish to (can specify multiple)")
@click.option("--profile", "-p", "profile_name",
              help="Use a predefined profile (group of platforms)")
@click.option("--draft", is_flag=True, help="Publish as draft")
@click.option("--dry-run", is_flag=True, help="Preview what would be published without actually publishing")
def publish(file: str, platform_args: tuple[str, ...], profile_name: str | None, draft: bool, dry_run: bool):
    """Publish a markdown file to one or more platforms."""
    # Resolve platforms from --to and --profile
    platforms: list[str] = []

    if profile_name:
        profile_platforms = get_profile(profile_name)
        if profile_platforms is None:
            console.print(f"[red]Unknown profile: {profile_name}[/red]")
            console.print("[dim]Create a profile with: crier config profile set <name> <platforms>[/dim]")
            return
        platforms.extend(profile_platforms)

    if platform_args:
        platforms.extend(platform_args)

    # Default to devto if nothing specified
    if not platforms:
        platforms = ["devto"]

    # Remove duplicates while preserving order
    seen = set()
    unique_platforms = []
    for p in platforms:
        if p not in seen:
            seen.add(p)
            unique_platforms.append(p)
    platforms = unique_platforms

    article = parse_markdown_file(file)

    if draft:
        article.published = False

    # Dry run: show what would be published
    if dry_run:
        console.print(f"\n[bold]Dry Run Preview[/bold]")
        console.print(f"[dim]No changes will be made[/dim]\n")

        info_table = Table(show_header=False, box=None)
        info_table.add_column("Field", style="cyan")
        info_table.add_column("Value")

        info_table.add_row("File", file)
        info_table.add_row("Title", article.title)
        info_table.add_row("Description", article.description or "[dim]not set[/dim]")
        info_table.add_row("Tags", ", ".join(article.tags) if article.tags else "[dim]none[/dim]")
        info_table.add_row("Canonical URL", article.canonical_url or "[dim]not set[/dim]")
        info_table.add_row("Status", "Draft" if not article.published else "Published")
        info_table.add_row("Body", f"{len(article.body)} characters")

        console.print(info_table)
        console.print()

        platform_table = Table(title="Target Platforms")
        platform_table.add_column("Platform", style="cyan")
        platform_table.add_column("Status", style="green")
        platform_table.add_column("Notes")

        for platform_name in platforms:
            api_key = get_api_key(platform_name)
            if not api_key:
                platform_table.add_row(
                    platform_name,
                    "[red]✗ Not configured[/red]",
                    f"Run: crier config set {platform_name}.api_key YOUR_KEY"
                )
            elif platform_name not in PLATFORMS:
                platform_table.add_row(
                    platform_name,
                    "[red]✗ Unknown[/red]",
                    "Platform not found"
                )
            else:
                platform_table.add_row(
                    platform_name,
                    "[green]✓ Ready[/green]",
                    "Would publish"
                )

        console.print(platform_table)
        return

    # Actual publishing with results table
    results = []

    for platform_name in platforms:
        api_key = get_api_key(platform_name)
        if not api_key:
            results.append({
                "platform": platform_name,
                "success": False,
                "error": "Not configured",
                "url": None,
                "id": None,
            })
            continue

        try:
            platform_cls = get_platform(platform_name)
            platform = platform_cls(api_key)

            console.print(f"[dim]Publishing to {platform_name}...[/dim]")
            result = platform.publish(article)

            results.append({
                "platform": platform_name,
                "success": result.success,
                "error": result.error,
                "url": result.url,
                "id": result.article_id,
            })

            # Record successful publication to registry
            if result.success:
                record_publication(
                    file_path=file,
                    platform=platform_name,
                    article_id=result.article_id,
                    url=result.url,
                    title=article.title,
                    canonical_url=article.canonical_url,
                )

        except Exception as e:
            results.append({
                "platform": platform_name,
                "success": False,
                "error": str(e),
                "url": None,
                "id": None,
            })

    # Display results table
    console.print()
    table = Table(title=f"Publishing Results: {article.title}")
    table.add_column("Platform", style="cyan")
    table.add_column("Status")
    table.add_column("URL / Error")

    for r in results:
        if r["success"]:
            status = "[green]✓ Published[/green]"
            detail = r["url"] or "[dim]no url[/dim]"
        else:
            status = "[red]✗ Failed[/red]"
            detail = f"[red]{r['error']}[/red]"

        table.add_row(r["platform"], status, detail)

    console.print(table)

    # Summary
    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count

    if fail_count == 0:
        console.print(f"\n[green]All {success_count} platform(s) published successfully.[/green]")
    elif success_count == 0:
        console.print(f"\n[red]All {fail_count} platform(s) failed.[/red]")
    else:
        console.print(f"\n[yellow]{success_count} succeeded, {fail_count} failed.[/yellow]")


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


@cli.command()
def doctor():
    """Check configuration and validate API keys."""
    console.print("\n[bold]Crier Doctor[/bold]")
    console.print("[dim]Checking your configuration...[/dim]\n")

    cfg = load_config()
    configured_platforms = cfg.get("platforms", {})

    table = Table(title="Platform Health Check")
    table.add_column("Platform", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    healthy = 0
    unhealthy = 0

    for name in PLATFORMS:
        api_key = get_api_key(name)

        if not api_key:
            table.add_row(
                name,
                "[dim]○ Not configured[/dim]",
                "[dim]No API key set[/dim]"
            )
            continue

        # Try to validate the API key by making a simple request
        try:
            platform_cls = get_platform(name)
            platform = platform_cls(api_key)

            # Try list_articles as a health check (most platforms support it)
            # This is a read-only operation that validates auth
            platform.list_articles(limit=1)

            table.add_row(
                name,
                "[green]✓ Healthy[/green]",
                f"API key valid"
            )
            healthy += 1

        except NotImplementedError:
            # Platform doesn't support listing (e.g., Medium, Twitter copy-paste)
            table.add_row(
                name,
                "[yellow]? Configured[/yellow]",
                "Cannot verify (no list support)"
            )
            healthy += 1  # Count as healthy since it's configured

        except Exception as e:
            error_msg = str(e)[:50]
            table.add_row(
                name,
                "[red]✗ Error[/red]",
                f"[red]{error_msg}[/red]"
            )
            unhealthy += 1

    console.print(table)

    # Summary
    total_configured = healthy + unhealthy
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  Configured: {total_configured}/{len(PLATFORMS)} platforms")

    if unhealthy > 0:
        console.print(f"  [red]Unhealthy: {unhealthy}[/red]")
    if healthy > 0:
        console.print(f"  [green]Healthy: {healthy}[/green]")

    if unhealthy > 0:
        console.print(f"\n[yellow]Tip: Check your API keys for failing platforms.[/yellow]")
    elif healthy > 0:
        console.print(f"\n[green]All configured platforms are healthy![/green]")
    else:
        console.print(f"\n[dim]No platforms configured yet.[/dim]")
        console.print(f"[dim]Run: crier config set <platform>.api_key YOUR_KEY[/dim]")


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

    # Show platforms
    table = Table(title="Configured Platforms")
    table.add_column("Platform", style="cyan")
    table.add_column("API Key", style="green")

    platforms = cfg.get("platforms", {})
    for name, settings in platforms.items():
        api_key = settings.get("api_key", "")
        # Mask the API key
        masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "****"
        table.add_row(name, masked)

    console.print(table)

    # Show profiles
    profiles = cfg.get("profiles", {})
    if profiles:
        console.print()
        profile_table = Table(title="Profiles")
        profile_table.add_column("Name", style="cyan")
        profile_table.add_column("Platforms", style="green")

        for name, plats in profiles.items():
            profile_table.add_row(name, ", ".join(plats))

        console.print(profile_table)


@config.group()
def profile():
    """Manage publishing profiles."""
    pass


@profile.command(name="set")
@click.argument("name")
@click.argument("platforms", nargs=-1, required=True)
def profile_set(name: str, platforms: tuple[str, ...]):
    """Create or update a profile.

    Example: crier config profile set blogs devto hashnode ghost
    """
    set_profile(name, list(platforms))
    console.print(f"[green]Profile '{name}' set to: {', '.join(platforms)}[/green]")


@profile.command(name="show")
@click.argument("name", required=False)
def profile_show(name: str | None):
    """Show profiles (all or a specific one)."""
    profiles = get_all_profiles()

    if not profiles:
        console.print("[yellow]No profiles defined yet.[/yellow]")
        console.print("[dim]Create one with: crier config profile set <name> <platforms>[/dim]")
        return

    if name:
        if name not in profiles:
            console.print(f"[red]Profile '{name}' not found.[/red]")
            return

        expanded = get_profile(name)
        console.print(f"[bold]Profile: {name}[/bold]")
        console.print(f"Defined as: {', '.join(profiles[name])}")
        if expanded != profiles[name]:
            console.print(f"Expands to: {', '.join(expanded or [])}")
    else:
        table = Table(title="Publishing Profiles")
        table.add_column("Name", style="cyan")
        table.add_column("Platforms", style="green")
        table.add_column("Expanded", style="dim")

        for pname, plats in profiles.items():
            expanded = get_profile(pname)
            expanded_str = ", ".join(expanded or []) if expanded != plats else ""
            table.add_row(pname, ", ".join(plats), expanded_str)

        console.print(table)


@profile.command(name="delete")
@click.argument("name")
def profile_delete(name: str):
    """Delete a profile."""
    cfg = load_config()
    profiles = cfg.get("profiles", {})

    if name not in profiles:
        console.print(f"[red]Profile '{name}' not found.[/red]")
        return

    del profiles[name]
    cfg["profiles"] = profiles

    from .config import save_config
    save_config(cfg)

    console.print(f"[green]Profile '{name}' deleted.[/green]")


@config.group()
def content():
    """Manage content paths for scanning."""
    pass


@content.command(name="add")
@click.argument("path")
def content_add(path: str):
    """Add a content path.

    Example: crier config content add content/posts
    """
    add_content_path(path)
    console.print(f"[green]Added content path: {path}[/green]")


@content.command(name="remove")
@click.argument("path")
def content_remove(path: str):
    """Remove a content path."""
    if remove_content_path(path):
        console.print(f"[green]Removed content path: {path}[/green]")
    else:
        console.print(f"[red]Content path not found: {path}[/red]")


@content.command(name="show")
def content_show():
    """Show configured content paths."""
    paths = get_content_paths()

    if not paths:
        console.print("[yellow]No content paths configured.[/yellow]")
        console.print("[dim]Add one with: crier config content add <path>[/dim]")
        return

    console.print("[bold]Content Paths:[/bold]")
    for p in paths:
        path_obj = Path(p)
        if path_obj.exists():
            console.print(f"  [green]✓[/green] {p}")
        else:
            console.print(f"  [red]✗[/red] {p} [dim](not found)[/dim]")


@content.command(name="set")
@click.argument("paths", nargs=-1, required=True)
def content_set(paths: tuple[str, ...]):
    """Set content paths (replaces existing).

    Example: crier config content set content/posts content/blog
    """
    set_content_paths(list(paths))
    console.print(f"[green]Content paths set to: {', '.join(paths)}[/green]")


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


@cli.command()
@click.argument("path", type=click.Path(exists=True), required=False)
@click.option("--to", "-t", "platform_filter", multiple=True,
              help="Only check specific platform(s)")
@click.option("--profile", "-p", "profile_name",
              help="Only check platforms in a profile")
def audit(path: str | None, platform_filter: tuple[str, ...], profile_name: str | None):
    """Audit content to see what's missing from platforms.

    PATH can be a file or directory. If not provided, uses configured content_paths.
    Only files with valid front matter (title) are included.
    """
    # Determine which platforms to check
    check_platforms: list[str] = []

    if profile_name:
        profile_platforms = get_profile(profile_name)
        if profile_platforms is None:
            console.print(f"[red]Unknown profile: {profile_name}[/red]")
            return
        check_platforms.extend(profile_platforms)

    if platform_filter:
        check_platforms.extend(platform_filter)

    # Default to all configured platforms
    if not check_platforms:
        check_platforms = [name for name in PLATFORMS if get_api_key(name)]

    if not check_platforms:
        console.print("[yellow]No platforms configured.[/yellow]")
        return

    # Find content files
    files = _find_content_files(path)

    if not files:
        if path:
            console.print(f"[yellow]No content files found in {path}[/yellow]")
        else:
            content_paths = get_content_paths()
            if not content_paths:
                console.print("[yellow]No content paths configured.[/yellow]")
                console.print("[dim]Add one with: crier config content add <path>[/dim]")
            else:
                console.print(f"[yellow]No content files found in configured paths: {', '.join(content_paths)}[/yellow]")
        return

    console.print(f"\n[bold]Content Audit[/bold]")
    console.print(f"[dim]Checking {len(files)} file(s) against {len(check_platforms)} platform(s)[/dim]\n")

    # Build audit table
    table = Table(title=f"Audit Results")
    table.add_column("File", style="cyan")

    for platform in check_platforms:
        table.add_column(platform, justify="center")

    missing_count = 0
    published_count = 0

    def get_display_path(fp: Path) -> str:
        """Get a display-friendly path, handling both absolute and relative paths."""
        try:
            return str(fp.relative_to(Path.cwd()))
        except ValueError:
            # Path is not relative to cwd, just use as-is
            return str(fp)

    for file_path in sorted(files):
        row = [get_display_path(file_path)]

        for platform in check_platforms:
            if is_published(file_path, platform):
                row.append("[green]✓[/green]")
                published_count += 1
            else:
                row.append("[yellow]✗[/yellow]")
                missing_count += 1

        table.add_row(*row)

    console.print(table)

    # Summary
    total = len(files) * len(check_platforms)
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  Files: {len(files)}")
    console.print(f"  Platforms checked: {len(check_platforms)}")
    console.print(f"  Published: [green]{published_count}[/green]")
    console.print(f"  Missing: [yellow]{missing_count}[/yellow]")

    if missing_count > 0:
        backfill_cmd = f"crier backfill {path}" if path else "crier backfill"
        console.print(f"\n[dim]Run '{backfill_cmd}' to publish missing content.[/dim]")


@cli.command()
@click.argument("path", type=click.Path(exists=True), required=False)
@click.option("--to", "-t", "platform_filter", multiple=True,
              help="Only publish to specific platform(s)")
@click.option("--profile", "-p", "profile_name",
              help="Only publish to platforms in a profile")
@click.option("--dry-run", is_flag=True, help="Preview what would be published")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def backfill(path: str | None, platform_filter: tuple[str, ...], profile_name: str | None,
             dry_run: bool, yes: bool):
    """Publish content that's missing from platforms.

    PATH can be a file or directory. If not provided, uses configured content_paths.
    Only files with valid front matter (title) are included.
    """
    # Determine which platforms to publish to
    target_platforms: list[str] = []

    if profile_name:
        profile_platforms = get_profile(profile_name)
        if profile_platforms is None:
            console.print(f"[red]Unknown profile: {profile_name}[/red]")
            return
        target_platforms.extend(profile_platforms)

    if platform_filter:
        target_platforms.extend(platform_filter)

    # Default to all configured platforms
    if not target_platforms:
        target_platforms = [name for name in PLATFORMS if get_api_key(name)]

    if not target_platforms:
        console.print("[yellow]No platforms configured.[/yellow]")
        return

    # Find content files
    files = _find_content_files(path)

    if not files:
        if path:
            console.print(f"[yellow]No content files found in {path}[/yellow]")
        else:
            content_paths = get_content_paths()
            if not content_paths:
                console.print("[yellow]No content paths configured.[/yellow]")
                console.print("[dim]Add one with: crier config content add <path>[/dim]")
            else:
                console.print(f"[yellow]No content files found in configured paths: {', '.join(content_paths)}[/yellow]")
        return

    # Find what needs to be published
    to_publish: list[tuple[Path, str]] = []  # (file, platform)

    for file_path in files:
        for platform in target_platforms:
            if not is_published(file_path, platform):
                to_publish.append((file_path, platform))

    if not to_publish:
        console.print("[green]Everything is already published![/green]")
        return

    console.print(f"\n[bold]Backfill Preview[/bold]")
    console.print(f"[dim]Found {len(to_publish)} missing publication(s)[/dim]\n")

    # Group by file for display
    by_file: dict[Path, list[str]] = {}
    for file_path, platform in to_publish:
        if file_path not in by_file:
            by_file[file_path] = []
        by_file[file_path].append(platform)

    table = Table(title="Pending Publications")
    table.add_column("File", style="cyan")
    table.add_column("Missing Platforms", style="yellow")

    def get_display_path(fp: Path) -> str:
        """Get a display-friendly path, handling both absolute and relative paths."""
        try:
            return str(fp.relative_to(Path.cwd()))
        except ValueError:
            return str(fp)

    for file_path, platforms in by_file.items():
        rel_path = get_display_path(file_path)
        table.add_row(rel_path, ", ".join(platforms))

    console.print(table)

    if dry_run:
        console.print("\n[dim]Dry run - no changes made.[/dim]")
        return

    # Confirm
    if not yes:
        console.print()
        if not click.confirm(f"Publish {len(to_publish)} item(s)?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    # Do the publishing
    console.print()
    success_count = 0
    fail_count = 0

    for file_path, platform in to_publish:
        article = parse_markdown_file(str(file_path))
        api_key = get_api_key(platform)

        if not api_key:
            console.print(f"[red]✗ {file_path.name} → {platform}: Not configured[/red]")
            fail_count += 1
            continue

        try:
            platform_cls = get_platform(platform)
            plat = platform_cls(api_key)

            console.print(f"[dim]Publishing {file_path.name} → {platform}...[/dim]")
            result = plat.publish(article)

            if result.success:
                console.print(f"[green]✓ {file_path.name} → {platform}[/green]")
                record_publication(
                    file_path=str(file_path),
                    platform=platform,
                    article_id=result.article_id,
                    url=result.url,
                    title=article.title,
                    canonical_url=article.canonical_url,
                )
                success_count += 1
            else:
                console.print(f"[red]✗ {file_path.name} → {platform}: {result.error}[/red]")
                fail_count += 1

        except Exception as e:
            console.print(f"[red]✗ {file_path.name} → {platform}: {e}[/red]")
            fail_count += 1

    # Summary
    console.print()
    if fail_count == 0:
        console.print(f"[green]All {success_count} publication(s) succeeded![/green]")
    else:
        console.print(f"[yellow]{success_count} succeeded, {fail_count} failed.[/yellow]")


WORKFLOW_TEMPLATE = """\
# Crier Auto-Publish Workflow
#
# Automatically cross-posts content when you push to main/master.
# API keys are stored as GitHub Secrets.

name: Auto-Publish Content

on:
  push:
    branches: [main, master]
    paths:
      - 'posts/**/*.md'
      - 'content/**/*.md'
  workflow_dispatch:  # Allow manual trigger

jobs:
  publish:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install Crier
        run: pip install crier

      - name: Audit and publish
        env:
{env_block}
        run: |
          echo "=== Configured Platforms ==="
          crier platforms

          echo "=== Audit ==="
          if [ -d "posts" ]; then
            crier audit ./posts || true
          elif [ -d "content" ]; then
            crier audit ./content || true
          fi

          echo "=== Publishing ==="
          if [ -d "posts" ]; then
            crier backfill ./posts --yes || true
          elif [ -d "content" ]; then
            crier backfill ./content --yes || true
          fi

      - name: Commit registry updates
        run: |
          git config --local user.email "github-actions[bot]@users.noreply.github.com"
          git config --local user.name "github-actions[bot]"

          if [ -d ".crier" ]; then
            git add .crier/
            git diff --staged --quiet || git commit -m "Update crier publication registry

            🤖 Auto-updated by Crier GitHub Action"
            git push
          fi
"""


@cli.command(name="init-action")
@click.option("--content-path", "-c", default=None,
              help="Path to content (default: posts/ or content/)")
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
def init_action(content_path: str | None, dry_run: bool, yes: bool):
    """Set up GitHub Action workflow and secrets for auto-publishing.

    This command will:
    1. Create .github/workflows/crier-publish.yml
    2. Set GitHub repository secrets from your local crier config

    Requires the GitHub CLI (gh) to be installed and authenticated.
    """
    import subprocess
    import shutil

    # Check for gh CLI
    if not shutil.which("gh"):
        console.print("[red]GitHub CLI (gh) is not installed.[/red]")
        console.print("[dim]Install it from: https://cli.github.com/[/dim]")
        return

    # Check gh auth status
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            console.print("[red]GitHub CLI is not authenticated.[/red]")
            console.print("[dim]Run: gh auth login[/dim]")
            return
    except Exception as e:
        console.print(f"[red]Error checking gh auth: {e}[/red]")
        return

    # Check we're in a git repo with GitHub remote
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            console.print("[red]Not in a GitHub repository.[/red]")
            console.print("[dim]Make sure you're in a git repo with a GitHub remote.[/dim]")
            return
        repo_name = result.stdout.strip()
    except Exception as e:
        console.print(f"[red]Error detecting repository: {e}[/red]")
        return

    console.print(f"\n[bold]Crier GitHub Action Setup[/bold]")
    console.print(f"[dim]Repository: {repo_name}[/dim]\n")

    # Get configured platforms and their API keys
    cfg = load_config()
    configured_platforms = cfg.get("platforms", {})

    if not configured_platforms:
        console.print("[yellow]No platforms configured in crier.[/yellow]")
        console.print("[dim]Run: crier config set <platform>.api_key YOUR_KEY[/dim]")
        return

    # Build list of secrets to set
    secrets_to_set: list[tuple[str, str]] = []
    env_lines: list[str] = []

    for platform_name, platform_config in configured_platforms.items():
        api_key = platform_config.get("api_key")
        if api_key:
            secret_name = f"CRIER_{platform_name.upper()}_API_KEY"
            secrets_to_set.append((secret_name, api_key))
            env_lines.append(f"          {secret_name}: ${{{{ secrets.{secret_name} }}}}")

    if not secrets_to_set:
        console.print("[yellow]No API keys found in config.[/yellow]")
        return

    # Preview what we'll do
    console.print("[bold]Will perform the following:[/bold]\n")

    # Workflow file
    workflow_path = Path(".github/workflows/crier-publish.yml")
    console.print(f"[cyan]1. Create workflow file:[/cyan]")
    console.print(f"   {workflow_path}")

    # Secrets
    console.print(f"\n[cyan]2. Set {len(secrets_to_set)} GitHub secret(s):[/cyan]")
    for secret_name, _ in secrets_to_set:
        console.print(f"   • {secret_name}")

    if dry_run:
        console.print("\n[dim]Dry run - no changes made.[/dim]")
        return

    # Confirm
    if not yes:
        console.print()
        if not click.confirm("Proceed with setup?"):
            console.print("[dim]Cancelled.[/dim]")
            return

    console.print()

    # Create workflow file
    workflow_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate workflow with correct env block
    env_block = "\n".join(env_lines)
    workflow_content = WORKFLOW_TEMPLATE.format(env_block=env_block)

    # Customize content path if specified
    if content_path:
        # Replace default paths with custom one
        workflow_content = workflow_content.replace(
            "paths:\n      - 'posts/**/*.md'\n      - 'content/**/*.md'",
            f"paths:\n      - '{content_path}/**/*.md'"
        )
        workflow_content = workflow_content.replace(
            'if [ -d "posts" ]; then\n            crier audit ./posts || true\n          elif [ -d "content" ]; then\n            crier audit ./content || true\n          fi',
            f'crier audit ./{content_path} || true'
        )
        workflow_content = workflow_content.replace(
            'if [ -d "posts" ]; then\n            crier backfill ./posts --yes || true\n          elif [ -d "content" ]; then\n            crier backfill ./content --yes || true\n          fi',
            f'crier backfill ./{content_path} --yes || true'
        )

    workflow_path.write_text(workflow_content)
    console.print(f"[green]✓ Created {workflow_path}[/green]")

    # Set secrets via gh CLI
    for secret_name, secret_value in secrets_to_set:
        try:
            result = subprocess.run(
                ["gh", "secret", "set", secret_name],
                input=secret_value,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                console.print(f"[green]✓ Set secret {secret_name}[/green]")
            else:
                console.print(f"[red]✗ Failed to set {secret_name}: {result.stderr}[/red]")
        except Exception as e:
            console.print(f"[red]✗ Error setting {secret_name}: {e}[/red]")

    console.print(f"\n[bold green]Setup complete![/bold green]")
    console.print(f"\n[dim]Next steps:[/dim]")
    console.print(f"[dim]1. Commit and push the workflow file[/dim]")
    console.print(f"[dim]2. Add markdown files to posts/ or content/[/dim]")
    console.print(f"[dim]3. Push to main/master to trigger auto-publishing[/dim]")


@cli.command()
@click.argument("file", type=click.Path(exists=True), required=False)
@click.option("--all", "-a", "show_all", is_flag=True, help="Show all tracked posts")
def status(file: str | None, show_all: bool):
    """Show publication status for a file or all tracked posts."""
    if file:
        # Show status for a specific file
        post_status = get_post_status(file)

        if not post_status:
            console.print(f"[yellow]No publication record found for {file}[/yellow]")
            console.print("[dim]This file hasn't been published with crier yet.[/dim]")
            return

        console.print(f"\n[bold]Publication Status: {post_status.get('title', file)}[/bold]")

        if post_status.get("canonical_url"):
            console.print(f"[dim]Canonical: {post_status['canonical_url']}[/dim]")

        # Check if content has changed
        if has_content_changed(file):
            console.print("[yellow]⚠ Content has changed since last publication[/yellow]")

        console.print()

        table = Table(title="Publications")
        table.add_column("Platform", style="cyan")
        table.add_column("Status")
        table.add_column("URL")
        table.add_column("Published")

        publications = post_status.get("publications", {})

        # Show all platforms, marking which are published
        for platform_name in PLATFORMS:
            if platform_name in publications:
                pub = publications[platform_name]
                table.add_row(
                    platform_name,
                    "[green]✓ Published[/green]",
                    pub.get("url") or "[dim]no url[/dim]",
                    pub.get("published_at", "")[:10] if pub.get("published_at") else "",
                )
            else:
                api_key = get_api_key(platform_name)
                if api_key:
                    table.add_row(
                        platform_name,
                        "[yellow]○ Not published[/yellow]",
                        "",
                        "",
                    )
                else:
                    table.add_row(
                        platform_name,
                        "[dim]- Not configured[/dim]",
                        "",
                        "",
                    )

        console.print(table)

    elif show_all:
        # Show all tracked posts
        all_posts = get_all_posts()

        if not all_posts:
            console.print("[yellow]No posts tracked yet.[/yellow]")
            console.print("[dim]Publish a file to start tracking.[/dim]")
            return

        console.print(f"\n[bold]Tracked Posts[/bold]")
        console.print(f"[dim]Registry: {get_registry_path()}[/dim]\n")

        table = Table(title=f"All Tracked Posts ({len(all_posts)})")
        table.add_column("File", style="cyan")
        table.add_column("Title")
        table.add_column("Platforms")
        table.add_column("Changed")

        for file_path, post_data in all_posts.items():
            publications = post_data.get("publications", {})
            platform_list = ", ".join(publications.keys()) if publications else "[dim]none[/dim]"

            # Check if file still exists and has changed
            full_path = Path(file_path)
            if full_path.exists():
                changed = "⚠ Yes" if has_content_changed(file_path) else "No"
            else:
                changed = "[red]File missing[/red]"

            table.add_row(
                file_path,
                (post_data.get("title") or "")[:40],
                platform_list,
                changed,
            )

        console.print(table)

    else:
        # No file specified, show help
        console.print("[yellow]Usage:[/yellow]")
        console.print("  crier status <file>    Show publication status for a file")
        console.print("  crier status --all     Show all tracked posts")


if __name__ == "__main__":
    cli()
