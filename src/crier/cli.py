"""Command-line interface for crier."""

import os
import random
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import (
    get_api_key, set_api_key, load_config, load_global_config,
    get_profile, set_profile, get_all_profiles,
    get_content_paths, add_content_path, remove_content_path, set_content_paths,
    is_manual_mode_key, is_import_mode_key, is_platform_configured,
    get_platform_mode, is_short_form_platform, get_llm_config, set_llm_config, is_llm_configured,
    get_llm_retry_count, get_llm_truncate_fallback, get_rewrite_author,
)
from .converters import parse_markdown_file
from .platforms import PLATFORMS, get_platform
from .platforms.base import Article
from .utils import (
    is_in_content_paths as _is_in_content_paths,
    parse_date_filter as _parse_date_filter_impl,
    get_content_date as _get_content_date,
    get_content_tags as _get_content_tags,
    find_content_files as _find_content_files,
)
from .registry import (
    record_publication,
    record_thread_publication,
    get_registry_path,
    is_published,
    has_content_changed,
    get_file_content_hash,
    get_publication_info,
    get_platform_publications,
    get_article_by_file,
    get_all_articles,
    remove_publication,
)

console = Console()


_SEVERITY_LABELS = {
    "error": "[red]ERROR[/red]",
    "warning": "[yellow]WARNING[/yellow]",
    "info": "[blue]INFO[/blue]",
}

# Padded for aligned tabular output in the check command
_SEVERITY_LABELS_PADDED = {
    "error": "[red]ERROR  [/red]",
    "warning": "[yellow]WARNING[/yellow]",
    "info": "[blue]INFO   [/blue]",
}


def _severity_label(severity: str, padded: bool = False) -> str:
    """Return a Rich-formatted label for a check severity level."""
    labels = _SEVERITY_LABELS_PADDED if padded else _SEVERITY_LABELS
    return labels.get(severity, severity)


def _parse_date_filter(value: str) -> datetime:
    """Parse date filter, raising click.BadParameter on invalid input."""
    try:
        return _parse_date_filter_impl(value)
    except ValueError:
        raise click.BadParameter(
            f"Invalid date format: '{value}'\n\n"
            "Examples:\n"
            "  --since 1d         (1 day ago)\n"
            "  --since 1w         (1 week ago)\n"
            "  --since 1m         (1 month ago)\n"
            "  --since 1y         (1 year ago)\n"
            "  --since 2025-01-01 (absolute date)"
        )


@click.group()
@click.version_option(version=__version__)
def cli():
    """Crier - Cross-post your content everywhere."""
    pass


@cli.command()
def init():
    """Initialize crier for your project.

    Sets up the registry, detects content directories, and helps
    configure platforms for cross-posting.
    """
    import questionary
    from .registry import REGISTRY_DIR, REGISTRY_FILE

    console.print("\n[bold]Welcome to Crier![/bold]")
    console.print("Let's set up cross-posting for your project.\n")

    # Step 1: Create .crier directory
    registry_dir = Path.cwd() / REGISTRY_DIR
    registry_file = registry_dir / REGISTRY_FILE

    if registry_file.exists():
        console.print(f"[green]✓[/green] Registry already exists: {registry_file}")
    else:
        registry_dir.mkdir(parents=True, exist_ok=True)
        # Create empty registry
        registry_file.write_text("version: 2\narticles: {}\n")
        console.print(f"[green]✓[/green] Created registry: {registry_file}")

    console.print()

    # Step 2: Detect content directories
    console.print("[bold]Step 1: Content Directories[/bold]")
    console.print("[dim]Where are your markdown posts?[/dim]\n")

    # Look for common content directory patterns
    candidates = []
    for pattern in ["content", "posts", "articles", "blog", "_posts", "src/content"]:
        path = Path.cwd() / pattern
        if path.is_dir():
            # Count markdown files
            md_files = list(path.glob("**/*.md"))
            if md_files:
                candidates.append((str(path.relative_to(Path.cwd())), len(md_files)))

    current_paths = get_content_paths()
    if current_paths:
        console.print(f"[dim]Currently configured: {', '.join(current_paths)}[/dim]\n")

    if candidates:
        choices = [
            questionary.Choice(
                title=f"{path}/ ({count} markdown files)",
                value=path,
                checked=path in current_paths,
            )
            for path, count in candidates
        ]

        selected = questionary.checkbox(
            "Select directories to scan for content:",
            choices=choices,
        ).ask()

        if selected is None:
            console.print("[yellow]Setup cancelled.[/yellow]")
            return

        if selected:
            set_content_paths(selected)
            console.print(f"[green]✓[/green] Content paths: {', '.join(selected)}")

            # Set default exclude patterns for content discovery
            from .config import (set_exclude_patterns, DEFAULT_EXCLUDE_PATTERNS,
                                set_file_extensions, DEFAULT_FILE_EXTENSIONS)
            set_exclude_patterns(DEFAULT_EXCLUDE_PATTERNS)
            patterns_str = ', '.join(DEFAULT_EXCLUDE_PATTERNS)
            console.print(f"[green]✓[/green] Exclude patterns: {patterns_str}")

            # Set default file extensions
            set_file_extensions(DEFAULT_FILE_EXTENSIONS)
            console.print(f"[green]✓[/green] File extensions: {', '.join(DEFAULT_FILE_EXTENSIONS)}")
        else:
            console.print("[dim]No content paths selected. You can add them later with:[/dim]")
            console.print("[dim]  crier config content add <directory>[/dim]")
    else:
        console.print("[yellow]No content directories found.[/yellow]")
        console.print(
            "[dim]You can add them later with:"
            " crier config content add <directory>[/dim]"
        )

    console.print()

    # Step 3: Platform configuration
    console.print("[bold]Step 2: Platform Configuration[/bold]")
    console.print("[dim]Which platforms do you want to publish to?[/dim]\n")

    # Group platforms by category
    categories = {
        "Blog Platforms": ["devto", "hashnode", "medium", "ghost", "wordpress"],
        "Social Media": ["bluesky", "mastodon", "twitter", "threads", "linkedin"],
        "Newsletters": ["buttondown"],
        "Announcements": ["telegram", "discord"],
    }

    # Build choices showing configured status
    choices = []
    for category, platform_names in categories.items():
        # Only include platforms that are registered
        available = [p for p in platform_names if p in PLATFORMS]
        if available:
            for p in available:
                is_configured = bool(get_api_key(p))
                status = " [green](configured)[/green]" if is_configured else ""
                choices.append(questionary.Choice(
                    title=f"{p} ({category.split()[0].lower()}){status}",
                    value=p,
                    checked=is_configured,
                ))

    selected_platforms = questionary.checkbox(
        "Select platforms to configure:",
        choices=choices,
    ).ask()

    if selected_platforms is None:
        console.print("[yellow]Setup cancelled.[/yellow]")
        return

    # Configure each selected platform
    for platform in selected_platforms:
        existing_key = get_api_key(platform)
        if existing_key:
            update = questionary.confirm(
                f"{platform} is already configured. Update API key?",
                default=False,
            ).ask()
            if not update:
                continue

        # Platform-specific prompts
        if platform == "bluesky":
            console.print(f"\n[bold]{platform}[/bold]")
            console.print(
                "[dim]Get an app password at:"
                " https://bsky.app/settings/app-passwords[/dim]"
            )
            handle = questionary.text("Bluesky handle (e.g., user.bsky.social):").ask()
            password = questionary.password("App password:").ask()
            if handle and password:
                set_api_key(platform, f"{handle}:{password}")
                console.print(f"[green]✓[/green] {platform} configured")
        elif platform == "mastodon":
            console.print(f"\n[bold]{platform}[/bold]")
            console.print("[dim]Create an access token in Preferences > Development[/dim]")
            instance = questionary.text("Instance URL (e.g., https://mastodon.social):").ask()
            token = questionary.password("Access token:").ask()
            if instance and token:
                set_api_key(platform, f"{instance}:{token}")
                console.print(f"[green]✓[/green] {platform} configured")
        elif platform == "devto":
            console.print(f"\n[bold]{platform}[/bold]")
            console.print("[dim]Get your API key at: https://dev.to/settings/extensions[/dim]")
            key = questionary.password("DEV.to API key:").ask()
            if key:
                set_api_key(platform, key)
                console.print(f"[green]✓[/green] {platform} configured")
        elif platform == "hashnode":
            console.print(f"\n[bold]{platform}[/bold]")
            console.print("[dim]Get your API key at: https://hashnode.com/settings/developer[/dim]")
            key = questionary.password("Hashnode API key:").ask()
            pub_id = questionary.text("Publication ID (from your publication settings):").ask()
            if key and pub_id:
                set_api_key(platform, f"{key}:{pub_id}")
                console.print(f"[green]✓[/green] {platform} configured")
        elif platform == "telegram":
            console.print(f"\n[bold]{platform}[/bold]")
            console.print("[dim]Get a bot token from @BotFather[/dim]")
            token = questionary.password("Bot token:").ask()
            chat_id = questionary.text("Chat ID (channel or group):").ask()
            if token and chat_id:
                set_api_key(platform, f"{token}:{chat_id}")
                console.print(f"[green]✓[/green] {platform} configured")
        elif platform == "discord":
            console.print(f"\n[bold]{platform}[/bold]")
            console.print("[dim]Create a webhook in channel settings[/dim]")
            webhook = questionary.password("Webhook URL:").ask()
            if webhook:
                set_api_key(platform, webhook)
                console.print(f"[green]✓[/green] {platform} configured")
        else:
            # Generic API key prompt
            console.print(f"\n[bold]{platform}[/bold]")
            key = questionary.password(f"{platform} API key:").ask()
            if key:
                set_api_key(platform, key)
                console.print(f"[green]✓[/green] {platform} configured")

    console.print()

    # Step 4: LLM Configuration (for auto-rewrite)
    console.print("[bold]Step 4: LLM Configuration (Optional)[/bold]")
    console.print(
        "[dim]Auto-rewrite uses an LLM to generate"
        " short-form posts from your articles.[/dim]"
    )
    console.print()

    # Check if already configured
    llm_already_configured = is_llm_configured()
    llm_source = None
    if llm_already_configured:
        if os.environ.get("OPENAI_API_KEY"):
            llm_source = "environment variable"
        else:
            llm_source = "config file"
        console.print(f"[green]✓[/green] LLM already configured (source: {llm_source})")
        configure_llm = questionary.confirm(
            "Update LLM configuration?",
            default=False,
        ).ask()
    else:
        configure_llm = questionary.confirm(
            "Configure LLM for auto-rewrite?",
            default=False,
        ).ask()

    if configure_llm:
        console.print()
        console.print(
            "[dim]Tip: Set OPENAI_API_KEY env var and it"
            " just works (defaults to gpt-4o-mini)[/dim]"
        )
        console.print()

        provider_choice = questionary.select(
            "Which provider?",
            choices=[
                questionary.Choice("OpenAI (default)", value="openai"),
                questionary.Choice("Custom/Ollama (OpenAI-compatible)", value="custom"),
            ],
        ).ask()

        if provider_choice == "openai":
            key = questionary.password("OpenAI API key (or press Enter to skip):").ask()
            if key:
                set_llm_config(api_key=key)
                console.print("[green]✓[/green] OpenAI API key saved")
                console.print(
                    "[dim]Using default: base_url=api.openai.com,"
                    " model=gpt-4o-mini[/dim]"
                )
        elif provider_choice == "custom":
            base_url = questionary.text(
                "Base URL:",
                default="http://localhost:11434/v1",
            ).ask()
            model = questionary.text(
                "Model name:",
                default="llama3",
            ).ask()
            key = questionary.password("API key (press Enter if not needed):").ask()

            if base_url and model:
                set_llm_config(base_url=base_url, model=model, api_key=key or "")
                console.print("[green]✓[/green] LLM configured")

    console.print()

    # Step 5: Summary and next steps
    console.print("[bold]Setup Complete![/bold]\n")
    console.print("Next steps:")
    console.print("  1. Run [cyan]crier audit[/cyan] to see what can be published")
    console.print("  2. Run [cyan]crier publish <file> --to <platform>[/cyan] to publish content")
    console.print("  3. Run [cyan]crier doctor[/cyan] to verify your API keys work")
    console.print()

    # Mention Claude Code integration
    console.print("[dim]Using Claude Code? Install the crier skill with:[/dim]")
    console.print("[dim]  crier skill install[/dim]")
    console.print("[dim]Then just ask Claude to cross-post your content![/dim]")
    console.print()


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--to", "-t", "platform_args", multiple=True,
              help="Platform(s) to publish to (can specify multiple)")
@click.option("--profile", "-p", "profile_name",
              help="Use a predefined profile (group of platforms)")
@click.option("--draft", is_flag=True, help="Publish as draft")
@click.option("--dry-run", is_flag=True,
              help="Preview what would be published without actually publishing")
@click.option("--manual", is_flag=True,
              help="Use manual mode: generate content for copy-paste instead of API")
@click.option("--no-browser", is_flag=True,
              help="Don't auto-open browser in manual mode")
@click.option("--rewrite", "rewrite_content", default=None,
              help="Use custom content instead of article body (for short-form platforms)")
@click.option("--rewrite-file", "rewrite_file", default=None, type=click.Path(exists=True),
              help="Read rewrite content from a file")
@click.option("--rewrite-author", "rewrite_author", default=None,
              help="Label for who wrote the rewrite (e.g., 'claude-code')")
@click.option("--auto-rewrite/--no-auto-rewrite", default=False,
              help="Auto-generate rewrites using configured LLM for short-form platforms")
@click.option("--auto-rewrite-retry", "-R", "auto_rewrite_retry", type=int, default=None,
              help="Retry auto-rewrite N times if output exceeds limit (default from config)")
@click.option("--auto-rewrite-truncate", "auto_rewrite_truncate", is_flag=True, default=None,
              help="Hard-truncate at sentence boundary if retries fail")
@click.option("--temperature", type=float, default=None,
              help="LLM temperature (0.0-2.0, higher=more creative)")
@click.option("--model", "model_override", default=None,
              help="Override LLM model for this publish")
@click.option("--yes", "-y", is_flag=True,
              help="Assume success for manual mode (skip confirmation prompt)")
@click.option("--json", "json_output", is_flag=True,
              help="Output results as JSON for automation")
@click.option("--batch", is_flag=True,
              help="Non-interactive batch mode"
                   " (implies --yes --json, skips manual/import platforms)")
@click.option("--quiet", "-q", is_flag=True,
              help="Suppress non-essential output (for scripting)")
@click.option("--schedule", "schedule_time", default=None,
              help="Schedule publish for later (e.g., 'tomorrow 9am', '2025-01-24 09:00')")
@click.option("--thread", is_flag=True,
              help="Split content into a thread for social platforms (Bluesky, Mastodon)")
@click.option("--thread-style", "thread_style", default="numbered",
              type=click.Choice(["numbered", "simple", "emoji"]),
              help="Thread numbering style (default: numbered)")
@click.option("--no-check", is_flag=True,
              help="Skip pre-publish validation checks")
@click.option("--strict", is_flag=True,
              help="Treat check warnings as errors (block publish)")
def publish(file: str, platform_args: tuple[str, ...], profile_name: str | None,
            draft: bool, dry_run: bool, manual: bool, no_browser: bool,
            rewrite_content: str | None, rewrite_file: str | None, rewrite_author: str | None,
            auto_rewrite: bool, auto_rewrite_retry: int | None, auto_rewrite_truncate: bool | None,
            temperature: float | None, model_override: str | None,
            yes: bool, json_output: bool, batch: bool, quiet: bool, schedule_time: str | None,
            thread: bool, thread_style: str, no_check: bool, strict: bool):
    """Publish a markdown file to one or more platforms.

    For short-form platforms (Bluesky, Twitter, etc.), use --rewrite to provide
    custom content that fits the platform's character limit.

    Use --auto-rewrite to automatically generate short-form content using
    a configured LLM (OpenAI, Ollama, etc.). Configure LLM in ~/.config/crier/config.yaml.

    Use --manual to generate content for copy-paste instead of using APIs.
    This is useful for platforms with restrictive API access (Medium, LinkedIn).

    Use --batch for non-interactive automation (implies --yes --json, skips manual platforms).
    """
    import json as json_module
    import webbrowser
    import pyperclip
    from rich.panel import Panel
    from .config import get_default_profile, get_rewrite_author

    # Batch mode implies --yes and --json
    if batch:
        yes = True
        json_output = True

    # Silent mode: suppress non-essential output
    silent = quiet or json_output

    # Validate --auto-rewrite requires LLM configuration
    llm_provider = None
    if auto_rewrite:
        if not is_llm_configured():
            if json_output:
                print(json_module.dumps({
                    "success": False,
                    "error": "--auto-rewrite requires LLM configuration",
                }))
            else:
                console.print("[red]Error: LLM not configured for --auto-rewrite[/red]")
                console.print()
                console.print("[bold]Fix:[/bold] export OPENAI_API_KEY=sk-...")
                console.print("[bold]Or:[/bold]  crier config llm set api_key sk-...")
                console.print()
                console.print(
                    "[dim]For Ollama: crier config llm set"
                    " base_url http://localhost:11434/v1[/dim]"
                )
                console.print("[dim]            crier config llm set model llama3[/dim]")
            raise SystemExit(1)

        # Resolve auto-rewrite settings from config if not specified on CLI
        if auto_rewrite_retry is None:
            auto_rewrite_retry = get_llm_retry_count()
        if auto_rewrite_truncate is None:
            auto_rewrite_truncate = get_llm_truncate_fallback()

        # Initialize LLM provider with optional overrides
        from .llm import get_provider
        llm_config = get_llm_config()
        llm_provider = get_provider(
            llm_config,
            temperature=temperature,
            model=model_override,
        )
        if not llm_provider:
            if json_output:
                print(json_module.dumps({
                    "success": False,
                    "error": "Failed to initialize LLM provider",
                }))
            else:
                console.print("[red]Error: Failed to initialize LLM provider.[/red]")
            raise SystemExit(1)

    # Resolve platforms from --to and --profile
    platforms: list[str] = []

    if profile_name:
        profile_platforms = get_profile(profile_name)
        if profile_platforms is None:
            if json_output:
                print(json_module.dumps({
                    "success": False,
                    "error": f"Unknown profile: {profile_name}",
                }))
            else:
                console.print(f"[red]Unknown profile: {profile_name}[/red]")
                console.print(
                    "[dim]Create a profile with:"
                    " crier config profile set <name> <platforms>[/dim]"
                )
            raise SystemExit(1)
        platforms.extend(profile_platforms)

    if platform_args:
        platforms.extend(platform_args)

    # Use default_profile if no platforms specified
    if not platforms:
        default_profile = get_default_profile()
        if default_profile:
            profile_platforms = get_profile(default_profile)
            if profile_platforms:
                platforms.extend(profile_platforms)
                if not silent:
                    console.print(f"[dim]Using default profile: {default_profile}[/dim]")

    # Require explicit platform selection
    if not platforms:
        if json_output:
            print(json_module.dumps({"success": False, "error": "No platform specified"}))
        else:
            console.print("[red]No platform specified.[/red]")
            console.print()

            # Show available profiles if any
            all_profiles = get_all_profiles()
            if all_profiles:
                console.print("[bold]Available profiles:[/bold]")
                for pname, plats in list(all_profiles.items())[:5]:  # Show up to 5
                    expanded = get_profile(pname)
                    platforms_str = ", ".join(expanded or plats)
                    console.print(f"  --profile {pname}  [dim]({platforms_str})[/dim]")
                if len(all_profiles) > 5:
                    console.print(f"  [dim]... and {len(all_profiles) - 5} more[/dim]")
                console.print()

            console.print("[bold]Or specify directly:[/bold]")
            console.print("  --to devto --to bluesky")
            console.print()
            console.print("[dim]Set a default: crier config set default_profile <name>[/dim]")
        raise SystemExit(1)

    # Use config default for rewrite_author if not specified
    if rewrite_author is None:
        rewrite_author = get_rewrite_author()

    # Remove duplicates while preserving order
    seen = set()
    unique_platforms = []
    for p in platforms:
        if p not in seen:
            seen.add(p)
            unique_platforms.append(p)
    platforms = unique_platforms

    # Pre-publish validation checks
    if not no_check:
        from .checker import check_file
        from .config import get_check_overrides, get_site_base_url

        report = check_file(
            file,
            platforms=platforms,
            severity_overrides=get_check_overrides(),
            site_base_url=get_site_base_url(),
        )

        if strict:
            report = report.with_elevated_warnings()

        if report.results:
            if report.has_errors:
                if json_output:
                    print(json_module.dumps({
                        "success": False,
                        "error": "Pre-publish check failed",
                        "checks": [
                            {"severity": r.severity, "check": r.check_name, "message": r.message}
                            for r in report.results
                        ],
                    }))
                else:
                    console.print("\n[red]Pre-publish check failed:[/red]")
                    for r in report.results:
                        label = _severity_label(r.severity)
                        console.print(f"  {label} {r.check_name}: {r.message}")
                    console.print("\n[dim]Use --no-check to skip validation.[/dim]")
                raise SystemExit(1)

            # Warnings present but no errors — show and continue
            if not silent:
                warning_count = sum(1 for r in report.results if r.severity == "warning")
                info_count = sum(1 for r in report.results if r.severity == "info")
                parts = []
                if warning_count:
                    parts.append(f"{warning_count} warning{'s' if warning_count != 1 else ''}")
                if info_count:
                    parts.append(f"{info_count} info")
                console.print(f"[dim]Pre-publish check: {', '.join(parts)}. Continuing...[/dim]")

    # Handle scheduling if --schedule is provided
    if schedule_time:
        from .scheduler import parse_schedule_time, create_scheduled_post

        scheduled_dt = parse_schedule_time(schedule_time)
        if scheduled_dt is None:
            if json_output:
                print(json_module.dumps({
                    "success": False,
                    "error": f"Could not parse schedule time: {schedule_time}",
                }))
            else:
                console.print(f"[red]Could not parse schedule time: {schedule_time}[/red]")
                console.print()
                console.print("Examples:")
                console.print("  --schedule '2025-01-24 09:00'")
                console.print("  --schedule 'tomorrow 9am'")
                console.print("  --schedule 'in 2 hours'")
            raise SystemExit(1)

        # Create scheduled posts for each platform
        scheduled_posts = []
        for platform_name in platforms:
            post = create_scheduled_post(
                file_path=file,
                platform=platform_name,
                scheduled_time=scheduled_dt,
                rewrite=rewrite_content,
                auto_rewrite=auto_rewrite,
                profile=profile_name,
            )
            scheduled_posts.append(post)

        if json_output:
            output = {
                "command": "publish",
                "scheduled": True,
                "file": file,
                "posts": [p.to_dict() for p in scheduled_posts],
                "scheduled_time": scheduled_dt.isoformat(),
            }
            print(json_module.dumps(output, indent=2, default=str))
        else:
            local_time = scheduled_dt.astimezone()
            time_str = local_time.strftime('%Y-%m-%d %H:%M %Z')
            console.print(f"[green]✓ Scheduled for {time_str}[/green]")
            for post in scheduled_posts:
                console.print(f"  • {post.platform}: {post.id}")
            console.print()
            console.print("[dim]Run 'crier schedule list' to view scheduled posts.[/dim]")
            console.print(
                "[dim]Run 'crier schedule run' to process"
                " due posts (add to crontab).[/dim]"
            )
        return

    # Batch mode: filter out manual/import platforms
    skipped_platforms = []
    if batch:
        api_platforms = []
        for p in platforms:
            mode = get_platform_mode(p)
            if mode == 'api':
                api_platforms.append(p)
            else:
                skipped_platforms.append({"platform": p, "reason": f"skipped ({mode} mode)"})
        platforms = api_platforms

        if not platforms:
            # All platforms were manual/import - output JSON and exit
            if json_output:
                output = {
                    "command": "publish",
                    "file": file,
                    "results": [],
                    "skipped": skipped_platforms,
                    "summary": {"succeeded": 0, "failed": 0, "skipped": len(skipped_platforms)},
                }
                print(json_module.dumps(output, indent=2))
            else:
                console.print("[yellow]No API platforms to publish to in batch mode.[/yellow]")
            return

    article = parse_markdown_file(file)

    if draft:
        article.published = False

    # Handle rewrite content
    is_rewritten = False
    posted_content = None
    if rewrite_file:
        with open(rewrite_file) as f:
            rewrite_content = f.read().strip()
    if rewrite_content:
        is_rewritten = True
        posted_content = rewrite_content
        # Create a modified article with the rewritten content
        article = Article(
            title=article.title,
            body=rewrite_content,  # Use rewritten content as body
            description=article.description,
            tags=article.tags,
            canonical_url=article.canonical_url,
            published=article.published,
            cover_image=article.cover_image,
        )

    # Require canonical_url for registry tracking
    if not article.canonical_url:
        console.print("[yellow]Warning: Missing canonical_url in front matter[/yellow]")
        console.print()
        console.print("[dim]Fix: Add to your file's YAML front matter:[/dim]")
        console.print("[dim]  canonical_url: https://yoursite.com/path/to/article/[/dim]")
        console.print()
        console.print("[dim]Or set site_base_url for auto-inference:[/dim]")
        console.print("[dim]  crier config set site_base_url https://yoursite.com[/dim]")
        console.print()

    # Warn if file is outside content_paths
    file_path = Path(file)
    if not _is_in_content_paths(file_path):
        content_paths = get_content_paths()
        if content_paths:
            console.print(
                "[yellow]Note: This file is not in your"
                " configured content_paths.[/yellow]"
            )
            console.print(
                "[dim]It will be tracked in the registry,"
                " but `crier audit` won't find it.[/dim]"
            )
            console.print(
                "[dim]To include it in audits, run:"
                " crier config content add <directory>[/dim]"
            )
            console.print()

    # Dry run: show what would be published
    if dry_run:
        console.print("\n[bold]Dry Run Preview[/bold]")
        console.print("[dim]No changes will be made[/dim]\n")

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

        # Track platforms needing auto-rewrite
        rewrite_previews = {}

        for platform_name in platforms:
            api_key = get_api_key(platform_name)
            if not api_key:
                # Get API key URL if available
                notes = f"crier config set {platform_name}.api_key YOUR_KEY"
                if platform_name in PLATFORMS:
                    platform_cls = PLATFORMS[platform_name]
                    api_url = getattr(platform_cls, 'api_key_url', None)
                    if api_url:
                        notes = f"Get key: {api_url}"
                platform_table.add_row(
                    platform_name,
                    "[red]✗ Not configured[/red]",
                    notes
                )
            elif platform_name not in PLATFORMS:
                platform_table.add_row(
                    platform_name,
                    "[red]✗ Unknown[/red]",
                    "Platform not found"
                )
            else:
                platform_cls = get_platform(platform_name)
                platform = platform_cls(api_key or "dry-run")
                max_len = platform.max_content_length

                # Check if auto-rewrite would be triggered
                if auto_rewrite and llm_provider and max_len and len(article.body) > max_len:
                    platform_table.add_row(
                        platform_name,
                        "[yellow]⚙ Needs rewrite[/yellow]",
                        f"Content too long ({len(article.body)} > {max_len})"
                    )
                    # Generate actual rewrite preview
                    try:
                        console.print(
                            f"[dim]Generating rewrite preview"
                            f" for {platform_name}...[/dim]"
                        )
                        from .llm import LLMProviderError
                        rewrite_result = llm_provider.rewrite(
                            title=article.title,
                            body=article.body,
                            max_chars=max_len,
                            platform=platform_name,
                        )
                        rewrite_previews[platform_name] = {
                            "text": rewrite_result.text,
                            "length": len(rewrite_result.text),
                            "max": max_len,
                            "fits": len(rewrite_result.text) <= max_len,
                        }
                    except LLMProviderError as e:
                        rewrite_previews[platform_name] = {"error": str(e)}
                elif max_len and len(article.body) > max_len:
                    platform_table.add_row(
                        platform_name,
                        "[red]✗ Content too long[/red]",
                        f"{len(article.body)} > {max_len} chars (use --rewrite or --auto-rewrite)"
                    )
                else:
                    platform_table.add_row(
                        platform_name,
                        "[green]✓ Ready[/green]",
                        "Would publish"
                    )

        console.print(platform_table)

        # Show rewrite previews if any
        if rewrite_previews:
            console.print()
            console.print("[bold]Auto-Rewrite Previews[/bold]")
            for platform_name, preview in rewrite_previews.items():
                if "error" in preview:
                    console.print(f"\n[red]✗ {platform_name}: {preview['error']}[/red]")
                else:
                    pct = preview['length'] * 100 // preview['max']
                    if preview["fits"]:
                        status = "[green]✓ Fits[/green]"
                    else:
                        status = "[red]✗ Still too long[/red]"
                    length = preview['length']
                    max_len = preview['max']
                    console.print(
                        f"\n[bold]{platform_name}[/bold]"
                        f" ({length}/{max_len} chars, {pct}%)"
                        f" {status}"
                    )
                    console.print(Panel(preview["text"], border_style="dim"))

        return

    # Actual publishing with results table
    results = []

    for platform_name in platforms:
        api_key = get_api_key(platform_name)

        # Determine mode:
        # 1. Import mode: api_key is "import" - user imports from canonical URL
        # 2. Manual mode: --manual flag or api_key is "manual"/"paste" - copy-paste
        # 3. API mode: normal API publishing
        use_import = is_import_mode_key(api_key)
        use_manual = manual or is_manual_mode_key(api_key)

        # Check if platform is configured at all
        if not api_key and not is_platform_configured(platform_name):
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

            # For manual/import mode with no real API key, we still need a platform instance
            # Pass a dummy key since we won't be making API calls
            is_real_key = (
                api_key
                and not is_manual_mode_key(api_key)
                and not is_import_mode_key(api_key)
            )
            effective_key = api_key if is_real_key else "manual"
            platform = platform_cls(effective_key)

            # Handle import mode (api_key: import) - user imports from canonical URL
            if use_import:
                if not article.canonical_url:
                    results.append({
                        "platform": platform_name,
                        "success": False,
                        "error": "Import mode requires canonical_url in front matter",
                        "url": None,
                        "id": None,
                    })
                    continue

                # Platform-specific import URLs
                import_urls = {
                    "medium": "https://medium.com/p/import",
                    "devto": "https://dev.to/import",
                }
                import_url = import_urls.get(platform_name, f"https://{platform_name}.com")

                # Create a result for import mode
                result = type("Result", (), {
                    "success": True,
                    "requires_confirmation": True,
                    "is_import_mode": True,
                    "canonical_url": article.canonical_url,
                    "import_url": import_url,
                    "article_id": None,
                    "url": None,
                    "error": None,
                })()

            # Handle manual mode (--manual flag or auto-detected from key)
            elif use_manual:
                manual_content = platform.format_for_manual(article)
                compose_url = platform.compose_url or f"https://{platform_name}.com"

                # Check content length if applicable
                max_len = platform.max_content_length
                if max_len and len(manual_content) > max_len:
                    results.append({
                        "platform": platform_name,
                        "success": False,
                        "error": (
                            f"Content too long:"
                            f" {len(manual_content)} chars"
                            f" (limit: {max_len})"
                        ),
                        "url": None,
                        "id": None,
                    })
                    continue

                # Create a result that requires confirmation
                result = type("Result", (), {
                    "success": True,
                    "requires_confirmation": True,
                    "manual_content": manual_content,
                    "compose_url": compose_url,
                    "article_id": None,
                    "url": None,
                    "error": None,
                })()
            else:
                # Check if manual rewrite content exceeds platform limit
                if rewrite_content and not auto_rewrite and platform.max_content_length:
                    max_len = platform.max_content_length
                    if len(article.body) > max_len:
                        results.append({
                            "platform": platform_name,
                            "success": False,
                            "error": (
                                f"Rewrite content too long:"
                                f" {len(article.body)} chars"
                                f" (limit: {max_len})"
                            ),
                            "url": None,
                            "id": None,
                        })
                        continue

                # Check if auto-rewrite is needed for this platform
                publish_article = article
                platform_rewritten = False
                platform_rewrite_content = None

                if auto_rewrite and llm_provider and platform.max_content_length:
                    max_len = platform.max_content_length
                    if len(article.body) > max_len:
                        from .rewrite import auto_rewrite_for_platform

                        rw = auto_rewrite_for_platform(
                            article, platform_name, max_len, llm_provider,
                            retry_count=auto_rewrite_retry or 0,
                            truncate_fallback=bool(auto_rewrite_truncate),
                            silent=silent, console=console,
                        )
                        if rw.success:
                            publish_article = rw.article
                            platform_rewritten = True
                            platform_rewrite_content = rw.rewrite_text
                        else:
                            results.append({
                                "platform": platform_name,
                                "success": False,
                                "error": rw.error,
                                "url": None,
                                "id": None,
                            })
                            continue

                # Handle threading if requested
                thread_result = None
                if thread and platform.supports_threads:
                    from .threading import split_into_thread

                    # Use the content to thread (rewrite or original body)
                    thread_content = publish_article.body
                    max_len = platform.max_content_length or 300

                    # Split into thread posts
                    thread_posts = split_into_thread(
                        thread_content,
                        max_length=max_len,
                        style=thread_style,
                        max_posts=platform.thread_max_posts,
                    )

                    if len(thread_posts) > 1:
                        if not silent:
                            console.print(
                                f"[dim]Publishing thread"
                                f" ({len(thread_posts)} posts)"
                                f" to {platform_name}...[/dim]"
                            )
                        thread_result = platform.publish_thread(thread_posts)
                    else:
                        # Single post, use regular publish
                        if not silent:
                            console.print(f"[dim]Publishing to {platform_name}...[/dim]")
                        result = platform.publish(publish_article)
                elif thread and not platform.supports_threads:
                    # Platform doesn't support threads
                    results.append({
                        "platform": platform_name,
                        "success": False,
                        "error": f"{platform_name} does not support thread posting",
                        "url": None,
                        "id": None,
                    })
                    continue
                else:
                    if not silent:
                        console.print(f"[dim]Publishing to {platform_name}...[/dim]")
                    result = platform.publish(publish_article)

                # Handle thread result
                if thread_result is not None:
                    # Convert thread result to standard result for processing
                    result = type("Result", (), {
                        "success": thread_result.success,
                        "article_id": thread_result.root_id,
                        "url": thread_result.root_url,
                        "error": thread_result.error,
                        "requires_confirmation": False,
                        "is_thread": True,
                        "thread_ids": thread_result.post_ids,
                        "thread_urls": thread_result.post_urls,
                    })()

                # Track rewrite info for registry
                if platform_rewritten:
                    is_rewritten = True
                    posted_content = platform_rewrite_content
                    if not rewrite_author:
                        rewrite_author = f"llm:{llm_provider.model}"

            # Handle manual/import mode confirmation flow
            if result.requires_confirmation:
                console.print()

                # Import mode: show URL to import from
                if getattr(result, 'is_import_mode', False):
                    console.print(Panel(
                        f"[bold]Import from:[/bold] {result.canonical_url}",
                        title=f"[bold]Import to {platform_name}[/bold]",
                    ))
                    console.print(f"Go to: {result.import_url}")
                    target_url = result.import_url
                else:
                    # Manual mode: show content to copy
                    console.print(Panel(
                        result.manual_content,
                        title=f"[bold]Copy this to {platform_name}[/bold]",
                        subtitle=f"{len(result.manual_content)} characters",
                    ))

                    # Copy to clipboard
                    try:
                        pyperclip.copy(result.manual_content)
                        console.print("[green]✓ Copied to clipboard[/green]")
                    except Exception:
                        console.print(
                            "[yellow]Could not copy to clipboard"
                            " (install xclip/xsel on Linux)[/yellow]"
                        )

                    console.print(f"Compose at: {result.compose_url}")
                    target_url = result.compose_url

                # Open browser unless --no-browser or --yes (Claude will tell user)
                if not no_browser and not yes:
                    webbrowser.open(target_url)
                    console.print("[dim]Browser opened[/dim]")

                # Ask for confirmation (skip if --yes)
                console.print()
                if yes:
                    console.print(
                        f"[dim]--yes flag set, assuming successful"
                        f" post to {platform_name}[/dim]"
                    )
                    posted = True
                else:
                    posted = click.confirm(
                        f"Did you successfully post to {platform_name}?",
                        default=False,
                    )

                if posted:
                    if yes:
                        post_url = ""  # Skip URL prompt in --yes mode
                    else:
                        post_url = click.prompt(
                            "Enter the post URL (or press enter to skip)",
                            default="",
                            show_default=False,
                        )

                    # Record to registry
                    if article.canonical_url:
                        content_hash = get_file_content_hash(Path(file))
                        mode_id = "import" if getattr(result, 'is_import_mode', False) else "manual"
                        record_publication(
                            canonical_url=article.canonical_url,
                            platform=platform_name,
                            article_id=mode_id,
                            url=post_url or None,
                            title=article.title,
                            source_file=file,
                            content_hash=content_hash,
                            rewritten=is_rewritten,
                            rewrite_author=rewrite_author if is_rewritten else None,
                            posted_content=posted_content if is_rewritten else None,
                        )

                    is_import = getattr(result, 'is_import_mode', False)
                    mode_label = "(import)" if is_import else "(manual)"
                    results.append({
                        "platform": platform_name,
                        "success": True,
                        "error": None,
                        "url": post_url or mode_label,
                        "id": mode_id if article.canonical_url else None,
                    })
                    console.print(f"[green]✓ Recorded publication to {platform_name}[/green]")
                else:
                    results.append({
                        "platform": platform_name,
                        "success": False,
                        "error": "User cancelled",
                        "url": None,
                        "id": None,
                    })
                    console.print("[yellow]Not recorded in registry[/yellow]")

                continue  # Skip normal result handling

            # Normal (non-manual) result handling
            result_data = {
                "platform": platform_name,
                "success": result.success,
                "error": result.error,
                "url": result.url,
                "id": result.article_id,
            }

            # Add thread info if this was a thread
            # (check for True explicitly to handle Mock objects)
            is_thread_result = getattr(result, 'is_thread', None) is True
            if is_thread_result:
                result_data["is_thread"] = True
                result_data["thread_ids"] = getattr(result, 'thread_ids', None)
                result_data["thread_urls"] = getattr(result, 'thread_urls', None)

            results.append(result_data)

            # Record successful publication to registry
            if result.success and article.canonical_url:
                content_hash = get_file_content_hash(Path(file))

                # Use thread-specific recording if this was a thread
                thread_ids = getattr(result, 'thread_ids', None) if is_thread_result else None
                if is_thread_result and thread_ids:
                    record_thread_publication(
                        canonical_url=article.canonical_url,
                        platform=platform_name,
                        root_id=result.article_id,
                        root_url=result.url,
                        thread_ids=thread_ids,
                        thread_urls=getattr(result, 'thread_urls', None),
                        title=article.title,
                        source_file=file,
                        content_hash=content_hash,
                        rewritten=is_rewritten,
                        rewrite_author=rewrite_author if is_rewritten else None,
                    )
                else:
                    record_publication(
                        canonical_url=article.canonical_url,
                        platform=platform_name,
                        article_id=result.article_id,
                        url=result.url,
                        title=article.title,
                        source_file=file,
                        content_hash=content_hash,
                        rewritten=is_rewritten,
                        rewrite_author=rewrite_author if is_rewritten else None,
                        posted_content=posted_content if is_rewritten else None,
                    )

        except Exception as e:
            results.append({
                "platform": platform_name,
                "success": False,
                "error": str(e),
                "url": None,
                "id": None,
            })

    # Calculate summary
    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count

    # JSON output mode
    if json_output:
        json_results = []
        for r in results:
            result_obj = {
                "platform": r["platform"],
                "success": r["success"],
            }
            if r["success"]:
                result_obj["article_id"] = r.get("id")
                result_obj["url"] = r["url"]
                result_obj["action"] = "published"
            else:
                result_obj["error"] = r["error"]
                # Add suggestion for content length errors
                if r["error"] and "too long" in r["error"].lower():
                    result_obj["suggestion"] = {
                        "flag": "--rewrite",
                        "reason": "short-form platform",
                    }
            json_results.append(result_obj)

        output = {
            "command": "publish",
            "file": file,
            "title": article.title,
            "canonical_url": article.canonical_url,
            "results": json_results,
            "skipped": skipped_platforms if batch else [],
            "summary": {
                "succeeded": success_count,
                "failed": fail_count,
                "skipped": len(skipped_platforms) if batch else 0,
            },
        }
        print(json_module.dumps(output, indent=2))
        return

    # Display results table (non-JSON mode)
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
    if fail_count == 0:
        console.print(f"\n[green]All {success_count} platform(s) published successfully.[/green]")
    elif success_count == 0:
        console.print(f"\n[red]All {fail_count} platform(s) failed.[/red]")
        raise SystemExit(1)
    else:
        console.print(f"\n[yellow]{success_count} succeeded, {fail_count} failed.[/yellow]")
        raise SystemExit(2)  # Partial failure


@cli.command(name="list")
@click.argument("platform", required=False, default=None)
@click.option("--limit", "-n", default=10, help="Number of articles to show")
@click.option("--verbose", "-v", is_flag=True, help="Show all columns")
@click.option("--remote", "-r", is_flag=True, help="Query platform API instead of registry")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["table", "urls", "json"]),
    default="table",
    help="Output format: table (default), urls (one per line), json",
)
@click.option(
    "--group-by",
    "group_by",
    type=click.Choice(["platform", "article"]),
    default=None,
    help="Group results by platform or article (only when listing all platforms)",
)
def list_articles(
    platform: str | None, limit: int, verbose: bool,
    remote: bool, output_format: str, group_by: str | None,
):
    """List your crossposted articles.

    Without PLATFORM argument, shows all publications across all platforms.
    With PLATFORM argument, shows only that platform's publications.

    By default, shows articles from your local registry (what you've published).
    Use --remote to query the platform's API directly (requires PLATFORM).
    """
    import json as json_module

    # --remote requires a specific platform
    if remote and not platform:
        console.print("[red]Error: --remote requires a PLATFORM argument[/red]")
        console.print("[dim]Example: crier list devto --remote[/dim]")
        raise SystemExit(1)

    if remote:
        # Query platform API directly (old behavior)
        api_key = get_api_key(platform)
        if not api_key:
            console.print(f"[red]No API key configured for {platform}[/red]")
            return

        try:
            platform_cls = get_platform(platform)
            plat = platform_cls(api_key)
            articles = plat.list_articles(limit)

            if not articles:
                console.print(f"No articles found on {platform}.")
                return

            # JSON output
            if output_format == "json":
                print(json_module.dumps(articles, indent=2))
                return

            # URLs only output
            if output_format == "urls":
                for article in articles:
                    url = article.get("url", "")
                    if url:
                        print(url)
                return

            # Table output
            table = Table(title=f"Articles on {platform} (remote)")
            table.add_column("Title", style="green")
            table.add_column("URL", style="blue", no_wrap=True)

            for article in articles[:limit]:
                table.add_row(
                    article.get("title", "")[:60],
                    article.get("url", ""),
                )

            console.print(table)

        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
        return

    # Handle no platform specified - show all publications
    if platform is None:
        all_publications = []
        for plat_name in PLATFORMS:
            pubs = get_platform_publications(plat_name)
            for pub in pubs:
                pub["platform"] = plat_name
            all_publications.extend(pubs)

        if not all_publications:
            console.print("No articles in registry.")
            console.print(
                "[dim]Publish something first with:"
                " crier publish <file> --to <platform>[/dim]"
            )
            return

        # Sort by published_at descending
        all_publications.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        all_publications = all_publications[:limit]

        # JSON output
        if output_format == "json":
            print(json_module.dumps(all_publications, indent=2))
            return

        # URLs only output
        if output_format == "urls":
            for pub in all_publications:
                url = pub.get("platform_url", "")
                if url:
                    print(url)
            return

        # Table output - group by article shows unique articles with their platforms
        if group_by == "article":
            # Group by canonical_url
            from collections import defaultdict
            by_article: dict[str, list[dict]] = defaultdict(list)
            for pub in all_publications:
                by_article[pub.get("canonical_url", "")].append(pub)

            table = Table(title="Your publications (grouped by article)")
            table.add_column("Title", style="green", max_width=40)
            table.add_column("Platforms", style="cyan")
            table.add_column("Source", style="dim", max_width=30)

            for canonical_url, pubs in by_article.items():
                platforms_str = ", ".join(sorted(set(p["platform"] for p in pubs)))
                title = pubs[0].get("title", "")[:40] if pubs else ""
                source = pubs[0].get("source_file", "")[:30] if pubs else ""
                table.add_row(title, platforms_str, source)

            console.print(table)
        else:
            # Default or group_by == "platform": show all with platform column
            table = Table(title="Your publications (all platforms)")
            if verbose:
                table.add_column("Title", style="green", max_width=30)
                table.add_column("Platform", style="cyan")
                table.add_column("Source", style="dim", max_width=25)
                table.add_column("URL", style="blue")
                table.add_column("Rewritten", style="yellow", max_width=10)

                for pub in all_publications:
                    rewritten = "Yes" if pub.get("rewritten") else ""
                    if pub.get("rewrite_author"):
                        rewritten = pub.get("rewrite_author")
                    table.add_row(
                        (pub.get("title") or "")[:30],
                        pub.get("platform", ""),
                        (pub.get("source_file") or "")[:25],
                        pub.get("platform_url", ""),
                        rewritten,
                    )
            else:
                table.add_column("Title", style="green", max_width=40)
                table.add_column("Platform", style="cyan")
                table.add_column("URL", style="blue")

                for pub in all_publications:
                    table.add_row(
                        (pub.get("title") or "")[:40],
                        pub.get("platform", ""),
                        pub.get("platform_url", ""),
                    )

            console.print(table)
        return

    # Default: read from registry for specific platform (what YOU have published)
    publications = get_platform_publications(platform)

    if not publications:
        console.print(f"No articles published to {platform} in registry.")
        console.print("[dim]Use --remote to query the platform API directly.[/dim]")
        return

    # Sort by published_at descending
    publications.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    publications = publications[:limit]

    # JSON output
    if output_format == "json":
        print(json_module.dumps(publications, indent=2))
        return

    # URLs only output
    if output_format == "urls":
        for pub in publications:
            url = pub.get("platform_url", "")
            if url:
                print(url)
        return

    # Table output
    table = Table(title=f"Your publications to {platform}")

    if verbose:
        table.add_column("Title", style="green", max_width=35)
        table.add_column("Source", style="cyan", max_width=30)
        table.add_column("Platform URL", style="blue")
        table.add_column("Rewritten", style="yellow", max_width=10)

        for pub in publications:
            rewritten = "Yes" if pub.get("rewritten") else ""
            if pub.get("rewrite_author"):
                rewritten = pub.get("rewrite_author")
            table.add_row(
                (pub.get("title") or "")[:35],
                (pub.get("source_file") or "")[:30],
                pub.get("platform_url", ""),
                rewritten,
            )
    else:
        table.add_column("Title", style="green")
        table.add_column("Platform URL", style="blue", no_wrap=True)

        for pub in publications:
            table.add_row(
                (pub.get("title") or "")[:50],
                pub.get("platform_url", ""),
            )

    console.print(table)


@cli.command()
def doctor():
    """Check configuration and validate API keys."""
    console.print("\n[bold]Crier Doctor[/bold]")
    console.print("[dim]Checking your configuration...[/dim]\n")

    table = Table(title="Platform Health Check")
    table.add_column("Platform", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    healthy = 0
    unhealthy = 0
    manual_count = 0

    for name in PLATFORMS:
        api_key = get_api_key(name)

        # Check if configured for import mode
        if is_import_mode_key(api_key):
            table.add_row(
                name,
                "[cyan]📥 Import mode[/cyan]",
                "User imports from canonical URL"
            )
            manual_count += 1  # Count with manual for stats
            continue

        # Check if configured for manual mode
        if is_manual_mode_key(api_key):
            table.add_row(
                name,
                "[blue]📋 Manual mode[/blue]",
                "Copy-paste (no API)"
            )
            manual_count += 1
            continue

        if not api_key and not is_platform_configured(name):
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
                "API key valid"
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
    total_configured = healthy + unhealthy + manual_count
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  Configured: {total_configured}/{len(PLATFORMS)} platforms")

    if unhealthy > 0:
        console.print(f"  [red]Unhealthy: {unhealthy}[/red]")
    if healthy > 0:
        console.print(f"  [green]Healthy: {healthy}[/green]")
    if manual_count > 0:
        console.print(f"  [blue]Manual mode: {manual_count}[/blue]")

    if unhealthy > 0:
        console.print("\n[yellow]Tip: Check your API keys for failing platforms.[/yellow]")
    elif healthy > 0 or manual_count > 0:
        console.print("\n[green]All configured platforms are ready![/green]")
    else:
        console.print("\n[dim]No platforms configured yet.[/dim]")
        console.print("[dim]Run: crier config set <platform>.api_key YOUR_KEY[/dim]")
        console.print("[dim]Or for manual mode: crier config set <platform>.api_key manual[/dim]")


@cli.command(name="platforms")
def show_platforms():
    """Show all available platforms with their status and descriptions.

    Lists each platform with its configuration status, mode (API/manual/import),
    character limits, and a brief description.
    """
    table = Table(title="Available Platforms")
    table.add_column("Platform", style="cyan")
    table.add_column("Status")
    table.add_column("Mode")
    table.add_column("Limit", justify="right")
    table.add_column("Description", style="dim")

    for name in sorted(PLATFORMS.keys()):
        platform_cls = PLATFORMS[name]
        api_key = get_api_key(name)

        # Determine status
        if is_import_mode_key(api_key):
            status = "[cyan]✓ Import mode[/cyan]"
            mode = "import"
        elif is_manual_mode_key(api_key):
            status = "[blue]✓ Manual mode[/blue]"
            mode = "paste"
        elif api_key and is_platform_configured(name):
            status = "[green]✓ Configured[/green]"
            mode = "API"
        else:
            status = "[dim]✗ Not configured[/dim]"
            mode = "-"

        # Get character limit
        max_len = getattr(platform_cls, 'max_content_length', None)
        limit_str = f"{max_len}" if max_len else "-"

        # Get description
        description = getattr(platform_cls, 'description', "Publishing platform")

        table.add_row(name, status, mode, limit_str, description)

    console.print(table)

    # Setup hint
    console.print()
    console.print("[dim]Setup: crier config set <platform>.api_key YOUR_KEY[/dim]")

    # Show API key URLs for unconfigured platforms
    unconfigured = [name for name in PLATFORMS if not get_api_key(name)]
    if unconfigured:
        console.print()
        console.print("[bold]Get API keys:[/bold]")
        for name in sorted(unconfigured)[:5]:  # Show up to 5
            platform_cls = PLATFORMS[name]
            url = getattr(platform_cls, 'api_key_url', None)
            if url:
                console.print(f"  {name}: {url}")
        if len(unconfigured) > 5:
            console.print(f"  [dim]... and {len(unconfigured) - 5} more[/dim]")


@cli.group()
def config():
    """Manage crier configuration."""
    pass


@config.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """Set a configuration value (e.g., devto.api_key, site_base_url)."""
    from .config import set_site_base_url

    parts = key.split(".")

    if key == "site_base_url":
        set_site_base_url(value)
        console.print(f"[green]Set site_base_url: {value}[/green]")
        console.print(
            "[dim]Canonical URLs will be auto-inferred for"
            " content without explicit canonical_url.[/dim]"
        )
    elif len(parts) == 2 and parts[1] == "api_key":
        platform = parts[0]
        set_api_key(platform, value)
        console.print(f"[green]Set API key for {platform}[/green]")
    else:
        console.print(f"[red]Unknown config key: {key}[/red]")
        console.print("Use: crier config set <platform>.api_key <value>")
        console.print("     crier config set site_base_url <url>")


@config.command(name="get")
@click.argument("key")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def config_get(key: str, json_output: bool):
    """Get a configuration value by key path.

    Supports dot notation for nested keys:
        crier config get llm.model
        crier config get platforms.devto.api_key
        crier config get site_base_url
    """
    import json as json_module
    from .config import load_global_config, load_local_config

    global_cfg = load_global_config()
    local_cfg = load_local_config()
    # Local config takes precedence
    merged = {**global_cfg, **local_cfg}

    # Navigate dot notation path
    parts = key.split(".")
    value = merged
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            value = None
            break

    if json_output:
        print(json_module.dumps({"key": key, "value": value}))
    else:
        if value is None:
            console.print(f"[yellow]Key not found: {key}[/yellow]")
            raise SystemExit(1)
        else:
            # For simple values, just print them
            if isinstance(value, (str, int, float, bool)):
                console.print(str(value))
            else:
                # For complex values (dict/list), use JSON-like format
                console.print(json_module.dumps(value, indent=2))


@config.command(name="show")
def config_show():
    """Show current configuration (hides API keys)."""
    from .config import (
        get_config_path, get_local_config_path, get_api_key_source,
        load_global_config, load_local_config,
    )

    # Show paths first
    console.print("\n[bold]Configuration Paths[/bold]")

    global_path = get_config_path()
    global_status = "[green]found[/green]" if global_path.exists() else "[dim]not found[/dim]"
    console.print(f"  Global config: {global_path} ({global_status})")

    local_path = get_local_config_path()
    local_status = "[green]found[/green]" if local_path.exists() else "[dim]not found[/dim]"
    console.print(f"  Local config:  {local_path} ({local_status})")

    registry_path = get_registry_path()
    registry_status = "[green]found[/green]" if registry_path.exists() else "[dim]not found[/dim]"
    console.print(f"  Registry:      {registry_path} ({registry_status})")
    console.print()

    cfg = load_config()
    global_cfg = load_global_config()
    local_cfg = load_local_config()

    if not cfg and not global_cfg and not local_cfg:
        console.print("No configuration found.")
        return

    # Show content paths with source
    content_paths = get_content_paths()
    if content_paths:
        # Determine source
        source = "local" if local_cfg.get("content_paths") else "global"
        console.print(f"[bold]Content Paths[/bold] [dim](from {source} config)[/dim]")
        for p in content_paths:
            path_obj = Path(p)
            if path_obj.exists():
                console.print(f"  [green]✓[/green] {p}")
            else:
                console.print(f"  [red]✗[/red] {p} [dim](not found)[/dim]")
        console.print()

    # Show site_base_url (for canonical URL inference)
    from .config import get_site_base_url
    site_base_url = get_site_base_url()
    if site_base_url:
        console.print("[bold]Site Base URL[/bold] [dim](for canonical URL inference)[/dim]")
        console.print(f"  {site_base_url}")
        console.print()
    else:
        console.print("[bold]Site Base URL[/bold] [dim](for canonical URL inference)[/dim]")
        console.print("  [dim]Not configured - canonical_url required in front matter[/dim]")
        console.print("  [dim]Set with: crier config set site_base_url https://yoursite.com[/dim]")
        console.print()

    # Show exclude patterns
    from .config import (get_exclude_patterns, DEFAULT_EXCLUDE_PATTERNS,
                        get_file_extensions, DEFAULT_FILE_EXTENSIONS,
                        get_default_profile, get_rewrite_author)
    exclude_patterns = get_exclude_patterns()
    if not exclude_patterns:
        console.print("[bold]Exclude Patterns[/bold] [dim](not configured)[/dim]")
        console.print(
            "  [dim]None - all .md files included."
            " Run 'crier init' to set defaults.[/dim]"
        )
    else:
        is_default = exclude_patterns == DEFAULT_EXCLUDE_PATTERNS
        label = 'default' if is_default else 'custom'
        console.print(f"[bold]Exclude Patterns[/bold] [dim]({label})[/dim]")
        for pattern in exclude_patterns:
            console.print(f"  • {pattern}")
    console.print()

    # Show file extensions
    file_extensions = get_file_extensions()
    if not file_extensions:
        console.print("[bold]File Extensions[/bold] [dim](not configured)[/dim]")
        console.print("  [dim]Using default: .md. Run 'crier init' to set explicitly.[/dim]")
    else:
        is_default = file_extensions == DEFAULT_FILE_EXTENSIONS
        label = 'default' if is_default else 'custom'
        console.print(f"[bold]File Extensions[/bold] [dim]({label})[/dim]")
        console.print(f"  {', '.join(file_extensions)}")
    console.print()

    # Show default profile
    default_profile = get_default_profile()
    if default_profile:
        console.print("[bold]Default Profile[/bold]")
        console.print(f"  {default_profile}")
    else:
        console.print("[bold]Default Profile[/bold] [dim](not set)[/dim]")
        console.print("  [dim]Platform must be specified with --to or --profile[/dim]")
    console.print()

    # Show rewrite author
    rewrite_author = get_rewrite_author()
    if rewrite_author:
        console.print("[bold]Rewrite Author[/bold]")
        console.print(f"  {rewrite_author}")
    else:
        console.print("[bold]Rewrite Author[/bold] [dim](not set)[/dim]")
        console.print("  [dim]Use --rewrite-author to specify when publishing rewrites[/dim]")
    console.print()

    # Show platforms with source
    table = Table(title="Configured Platforms")
    table.add_column("Platform", style="cyan")
    table.add_column("API Key", style="green")
    table.add_column("Source", style="dim")

    platforms = cfg.get("platforms", {})
    for name, settings in platforms.items():
        api_key = get_api_key(name)  # Get actual key (may be from env)
        if api_key:
            masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "****"
        else:
            masked = "[dim]not set[/dim]"

        source = get_api_key_source(name)
        source_display = {
            "env": "[yellow]env var[/yellow]",
            "global": "global",
            None: "[dim]—[/dim]",
        }.get(source, source)

        table.add_row(name, masked, source_display)

    console.print(table)

    # Show profiles with source
    global_profiles = global_cfg.get("profiles", {})
    local_profiles = local_cfg.get("profiles", {})
    all_profiles = cfg.get("profiles", {})

    if all_profiles:
        console.print()
        profile_table = Table(title="Profiles")
        profile_table.add_column("Name", style="cyan")
        profile_table.add_column("Platforms", style="green")
        profile_table.add_column("Source", style="dim")

        for name, plats in all_profiles.items():
            # Determine source
            if name in local_profiles:
                source = "local"
            elif name in global_profiles:
                source = "global"
            else:
                source = "—"

            profile_table.add_row(name, ", ".join(plats), source)

        console.print(profile_table)

    # Show all available platforms
    console.print()
    available_table = Table(title="Available Platforms")
    available_table.add_column("Platform", style="cyan")
    available_table.add_column("Status")

    for name in PLATFORMS:
        api_key = get_api_key(name)
        if api_key:
            status = "[green]Configured[/green]"
        else:
            status = "[dim]Not configured[/dim]"
        available_table.add_row(name, status)

    console.print(available_table)


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


# --- LLM Config Commands ---

@config.group()
def llm():
    """Manage LLM configuration for auto-rewrite."""
    pass


def _get_llm_config_sources() -> dict[str, str]:
    """Get the source of each LLM config value (env, config, default, or unset)."""
    sources = {}
    global_config = load_global_config()

    # Check api_key source
    if os.environ.get("OPENAI_API_KEY"):
        sources["api_key"] = "env (OPENAI_API_KEY)"
    elif global_config.get("llm", {}).get("api_key"):
        sources["api_key"] = "config"
    else:
        sources["api_key"] = "unset"

    # Check base_url source
    if os.environ.get("OPENAI_BASE_URL"):
        sources["base_url"] = "env (OPENAI_BASE_URL)"
    elif global_config.get("llm", {}).get("base_url"):
        sources["base_url"] = "config"
    else:
        # Check if it's using the default (when api_key is set)
        llm_config = get_llm_config()
        if llm_config.get("base_url"):
            sources["base_url"] = "default"
        else:
            sources["base_url"] = "unset"

    # Check model source (no env var - config only)
    if global_config.get("llm", {}).get("model"):
        sources["model"] = "config"
    else:
        # Check if it's using the default (when api_key is set)
        llm_config = get_llm_config()
        if llm_config.get("model"):
            sources["model"] = "default"
        else:
            sources["model"] = "unset"

    return sources


def _mask_api_key(key: str | None) -> str:
    """Mask API key for display, showing only first/last few chars."""
    if not key:
        return "[dim]not set[/dim]"
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"


@llm.command(name="show")
def llm_show():
    """Show current LLM configuration."""
    llm_config = get_llm_config()
    sources = _get_llm_config_sources()

    console.print("[bold]LLM Configuration:[/bold]")
    console.print()

    # Status
    if is_llm_configured():
        console.print("  [green]Status:[/green] configured")
    else:
        console.print("  [yellow]Status:[/yellow] not configured")

    console.print()

    # API Key
    api_key = llm_config.get("api_key")
    masked = _mask_api_key(api_key)
    source = sources['api_key']
    console.print(f"  [bold]api_key:[/bold] {masked} [dim]({source})[/dim]")

    # Base URL
    base_url = llm_config.get("base_url", "")
    if base_url:
        console.print(f"  [bold]base_url:[/bold] {base_url} [dim]({sources['base_url']})[/dim]")
    else:
        console.print(f"  [bold]base_url:[/bold] [dim]not set ({sources['base_url']})[/dim]")

    # Model
    model = llm_config.get("model", "")
    if model:
        console.print(f"  [bold]model:[/bold] {model} [dim]({sources['model']})[/dim]")
    else:
        console.print(f"  [bold]model:[/bold] [dim]not set ({sources['model']})[/dim]")

    # Custom prompt (if set)
    if llm_config.get("rewrite_prompt"):
        console.print("  [bold]rewrite_prompt:[/bold] [dim](custom)[/dim]")

    console.print()

    # Auto-rewrite settings
    console.print("[bold]Auto-rewrite settings:[/bold]")
    temp = llm_config.get("temperature", 0.7)
    retry = llm_config.get("retry_count", 0)
    truncate = llm_config.get("truncate_fallback", False)
    console.print(f"  [bold]temperature:[/bold] {temp}")
    console.print(f"  [bold]retry_count:[/bold] {retry}")
    console.print(f"  [bold]truncate_fallback:[/bold] {truncate}")

    console.print()

    if not is_llm_configured():
        console.print("[dim]Configure with:[/dim]")
        console.print("[dim]  export OPENAI_API_KEY=sk-...  (simplest)[/dim]")
        console.print("[dim]  crier config llm set api_key <key>[/dim]")


@llm.command(name="set")
@click.argument("key", type=click.Choice([
    "api_key", "base_url", "model", "temperature", "retry_count", "truncate_fallback"
]))
@click.argument("value")
def llm_set(key: str, value: str):
    """Set an LLM configuration value.

    KEY is one of: api_key, base_url, model, temperature, retry_count, truncate_fallback

    Examples:
        crier config llm set api_key sk-...
        crier config llm set base_url http://localhost:11434/v1
        crier config llm set model llama3
        crier config llm set temperature 0.8
        crier config llm set retry_count 3
        crier config llm set truncate_fallback true
    """
    if key == "api_key":
        set_llm_config(api_key=value)
    elif key == "base_url":
        set_llm_config(base_url=value)
    elif key == "model":
        set_llm_config(model=value)
    elif key == "temperature":
        try:
            set_llm_config(temperature=float(value))
        except ValueError:
            console.print(f"[red]Error: '{value}' is not a valid number for temperature[/red]")
            raise SystemExit(1)
    elif key == "retry_count":
        try:
            set_llm_config(retry_count=int(value))
        except ValueError:
            console.print(f"[red]Error: '{value}' is not a valid integer for retry_count[/red]")
            raise SystemExit(1)
    elif key == "truncate_fallback":
        set_llm_config(truncate_fallback=value.lower() in ("true", "1", "yes"))

    console.print(f"[green]LLM {key} set successfully.[/green]")

    # Show current config status
    if is_llm_configured():
        console.print("[dim]LLM is now configured and ready to use.[/dim]")
    else:
        llm_config = get_llm_config()
        missing = []
        if not llm_config.get("base_url"):
            missing.append("base_url")
        if not llm_config.get("model"):
            missing.append("model")
        if missing:
            console.print(f"[dim]Still need: {', '.join(missing)}[/dim]")


@llm.command(name="test")
def llm_test():
    """Test LLM connection with a simple request."""
    from .llm import get_provider, LLMProviderError

    if not is_llm_configured():
        console.print("[red]LLM is not configured.[/red]")
        console.print("[dim]Configure with: export OPENAI_API_KEY=sk-...[/dim]")
        raise SystemExit(1)

    llm_config = get_llm_config()
    provider = get_provider(llm_config)

    if not provider:
        console.print("[red]Failed to create LLM provider.[/red]")
        raise SystemExit(1)

    console.print(f"[dim]Testing connection to {llm_config.get('base_url')}...[/dim]")
    console.print(f"[dim]Model: {llm_config.get('model')}[/dim]")
    console.print()

    try:
        result = provider.rewrite(
            title="Test Article",
            body="This is a test article to verify the LLM connection is working properly.",
            max_chars=280,
            platform="test",
        )
        console.print("[green]✓ Connection successful![/green]")
        console.print(f"[dim]Response ({result.tokens_used or '?'} tokens):[/dim]")
        console.print(f"  {result.text}")
    except LLMProviderError as e:
        console.print(f"[red]✗ Connection failed: {e}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]✗ Unexpected error: {e}[/red]")
        raise SystemExit(1)


@cli.command()
@click.argument("path", type=click.Path(exists=True), required=False)
@click.option("--to", "-t", "platform_filter", multiple=True,
              help="Only check specific platform(s)")
@click.option("--profile", "-p", "profile_name",
              help="Only check platforms in a profile")
@click.option("--publish", is_flag=True, help="Publish missing content (interactive selection)")
@click.option("--yes", "-y", is_flag=True, help="Publish all missing without prompting")
@click.option("--dry-run", is_flag=True,
              help="Show what would be published without actually publishing")
@click.option("--only-api", is_flag=True,
              help="Only check platforms with API access (skip manual/import/paste)")
@click.option("--long-form", is_flag=True,
              help="Only check long-form platforms (skip those with character limits)")
@click.option("--sample", type=int, default=None,
              help="Randomly sample N items for processing")
@click.option("--include-changed", is_flag=True,
              help="Include changed/dirty items (default: missing only)")
@click.option("--include-archived", is_flag=True,
              help="Include archived items (default: skip archived)")
@click.option("--since", "since_date", default=None,
              help="Only include content from this date (e.g., 1w, 7d, 2025-01-01)")
@click.option("--until", "until_date", default=None,
              help="Only include content until this date (e.g., 1w, 7d, 2025-01-01)")
@click.option("--tag", "-T", "tag_filter", multiple=True,
              help="Only include content with these tags (case-insensitive, OR logic)")
@click.option("--json", "json_output", is_flag=True,
              help="Output results as JSON for automation")
@click.option("--batch", is_flag=True,
              help="Non-interactive batch mode (implies --yes --json --only-api)")
@click.option("--quiet", "-q", is_flag=True,
              help="Suppress non-essential output (for scripting)")
@click.option("--auto-rewrite/--no-auto-rewrite", default=False,
              help="Auto-generate rewrites using configured LLM for short-form platforms")
@click.option("--auto-rewrite-retry", "-R", "auto_rewrite_retry", type=int, default=None,
              help="Retry auto-rewrite N times if output exceeds limit (default from config)")
@click.option("--auto-rewrite-truncate", "auto_rewrite_truncate", is_flag=True, default=None,
              help="Hard-truncate at sentence boundary if retries fail")
@click.option("--verbose", "-v", is_flag=True,
              help="Show detailed output per file")
@click.option("--check", "run_checks", is_flag=True,
              help="Validate content before publishing (skip files that fail)")
def audit(path: str | None, platform_filter: tuple[str, ...], profile_name: str | None,
          publish: bool, yes: bool, dry_run: bool, only_api: bool, long_form: bool,
          sample: int | None, include_changed: bool, include_archived: bool,
          since_date: str | None, until_date: str | None,
          tag_filter: tuple[str, ...], json_output: bool, batch: bool, quiet: bool,
          auto_rewrite: bool, auto_rewrite_retry: int | None, auto_rewrite_truncate: bool | None,
          verbose: bool, run_checks: bool):
    """Audit content to see what's missing from platforms.

    PATH can be a file or directory. If not provided, uses configured content_paths.
    Only files with valid front matter (title) are included.

    Use --publish to interactively select which missing items to publish.
    Use --publish --yes to publish all missing items without prompting.
    Use --publish --dry-run to preview what would be published.

    \b
    Bulk operation filters:
      --only-api        Skip platforms configured for manual/import mode
      --long-form       Skip short-form platforms (bluesky, mastodon, etc.)
      --tag             Filter by tags (case-insensitive, OR logic)
      --sample N        Randomly select N items from the actionable pool
      --include-changed Also process changed/dirty items (default: missing only)

    Use --batch for non-interactive automation (implies --yes --json --only-api).
    """
    import json as json_module

    # Batch mode implies --yes, --json, and --only-api
    if batch:
        yes = True
        json_output = True
        only_api = True

    # Silent mode: suppress non-essential output
    silent = quiet or json_output

    # Initialize LLM provider if auto-rewrite is enabled
    llm_provider = None
    if auto_rewrite:
        from .llm import get_provider

        llm_config = get_llm_config()
        if not llm_config:
            if json_output:
                print(json_module.dumps({
                    "success": False,
                    "error": "--auto-rewrite requires LLM configuration",
                }))
            else:
                console.print(
                    "[red]Error: --auto-rewrite requires"
                    " LLM configuration.[/red]"
                )
                console.print(
                    "[dim]Run 'crier llm set' to configure,"
                    " or 'crier init' for guided setup.[/dim]"
                )
            raise SystemExit(1)
        llm_provider = get_provider(llm_config)

        # Resolve auto-rewrite settings from config if not specified on CLI
        if auto_rewrite_retry is None:
            auto_rewrite_retry = get_llm_retry_count()
        if auto_rewrite_truncate is None:
            auto_rewrite_truncate = get_llm_truncate_fallback()

    # Determine which platforms to check
    check_platforms: list[str] = []

    if profile_name:
        profile_platforms = get_profile(profile_name)
        if profile_platforms is None:
            if json_output:
                print(json_module.dumps({
                    "success": False,
                    "error": f"Unknown profile: {profile_name}",
                }))
            else:
                console.print(f"[red]Unknown profile: {profile_name}[/red]")
            raise SystemExit(1)
        check_platforms.extend(profile_platforms)

    if platform_filter:
        check_platforms.extend(platform_filter)

    # Default to all configured platforms
    if not check_platforms:
        check_platforms = [name for name in PLATFORMS if get_api_key(name)]

    # Apply mode filter: only API platforms (skip manual/import)
    if only_api:
        check_platforms = [p for p in check_platforms
                          if get_platform_mode(p) == 'api']

    # Apply content-type filter: only long-form platforms (skip short-form)
    if long_form:
        check_platforms = [p for p in check_platforms
                          if not is_short_form_platform(p)]

    if not check_platforms:
        console.print("[yellow]No platforms configured.[/yellow]")
        return

    # Find content files
    files = _find_content_files(path)

    # Apply date filtering
    if since_date or until_date:
        since_dt = _parse_date_filter(since_date) if since_date else None
        until_dt = _parse_date_filter(until_date) if until_date else None

        filtered_files = []
        for f in files:
            content_date = _get_content_date(f)
            if content_date:
                # Make comparison timezone-naive if needed
                if content_date.tzinfo is not None:
                    content_date = content_date.replace(tzinfo=None)
                if since_dt and content_date < since_dt:
                    continue
                if until_dt and content_date > until_dt:
                    continue
            filtered_files.append(f)
        files = filtered_files

    # Apply tag filtering
    if tag_filter:
        filter_tags = {t.lower().strip() for t in tag_filter}
        filtered_files = []
        for f in files:
            content_tags = _get_content_tags(f)
            # OR logic: include if any tag matches
            if any(tag in filter_tags for tag in content_tags):
                filtered_files.append(f)
        files = filtered_files

    # Apply archived filtering (default: exclude archived)
    if not include_archived:
        from .registry import is_archived as _is_archived
        filtered_files = []
        for f in files:
            try:
                article = parse_markdown_file(str(f))
                if article.canonical_url and _is_archived(article.canonical_url):
                    continue  # Skip archived
            except Exception:
                pass  # Include if we can't check
            filtered_files.append(f)
        files = filtered_files

    if not files:
        if path:
            console.print(f"[yellow]No content files found in {path}[/yellow]")
        else:
            content_paths = get_content_paths()
            if not content_paths:
                console.print("[yellow]No content paths configured.[/yellow]")
                console.print("[dim]Add one with: crier config content add <path>[/dim]")
            else:
                paths_str = ', '.join(content_paths)
                console.print(
                    f"[yellow]No content files found in"
                    f" configured paths: {paths_str}[/yellow]"
                )
        return

    console.print("\n[bold]Content Audit[/bold]")
    n_files = len(files)
    n_plats = len(check_platforms)
    console.print(
        f"[dim]Checking {n_files} file(s)"
        f" against {n_plats} platform(s)[/dim]\n"
    )

    # Build audit table and track actionable items
    table = Table(title="Audit Results")
    table.add_column("File", style="cyan")

    for platform in check_platforms:
        table.add_column(platform, justify="center")

    uptodate_count = 0
    dirty_count = 0
    # Track actionable items: (file_path, platform, canonical_url, title, action)
    # action is "publish" for missing or "update" for dirty
    missing_items: list[tuple[Path, str, str, str]] = []
    dirty_items: list[tuple[Path, str, str, str]] = []

    def get_display_path(fp: Path) -> str:
        """Get a display-friendly path, handling both absolute and relative paths."""
        try:
            return str(fp.relative_to(Path.cwd()))
        except ValueError:
            return str(fp)

    for file_path in sorted(files):
        row = [get_display_path(file_path)]

        # Get canonical_url and title from the article
        try:
            article = parse_markdown_file(str(file_path))
            canonical_url = article.canonical_url
            title = article.title
        except Exception:
            canonical_url = None
            title = file_path.name

        # Calculate current content hash for dirty detection
        current_hash = get_file_content_hash(file_path) if canonical_url else None

        for platform in check_platforms:
            if canonical_url and is_published(canonical_url, platform):
                # Check if content has changed (dirty)
                if current_hash and has_content_changed(canonical_url, current_hash, platform):
                    row.append("[yellow]⚠[/yellow]")
                    dirty_count += 1
                    dirty_items.append((file_path, platform, canonical_url, title))
                else:
                    row.append("[green]✓[/green]")
                    uptodate_count += 1
            else:
                row.append("[red]✗[/red]")
                if canonical_url:  # Only track if we have a canonical_url
                    missing_items.append((file_path, platform, canonical_url, title))

        table.add_row(*row)

    # JSON output mode for audit
    if json_output and not publish:
        actionable_items_json = []
        for fp, plat, curl, title in missing_items:
            actionable_items_json.append({
                "file": str(fp),
                "canonical_url": curl,
                "platform": plat,
                "title": title,
                "status": "missing",
                "action_needed": "publish",
            })
        for fp, plat, curl, title in dirty_items:
            actionable_items_json.append({
                "file": str(fp),
                "canonical_url": curl,
                "platform": plat,
                "title": title,
                "status": "changed",
                "action_needed": "update",
            })

        output = {
            "command": "audit",
            "path": path,
            "files_scanned": len(files),
            "platforms_checked": check_platforms,
            "actionable": actionable_items_json,
            "summary": {
                "up_to_date": uptodate_count,
                "changed": dirty_count,
                "missing": len(missing_items),
            },
        }
        print(json_module.dumps(output, indent=2))
        return

    console.print(table)

    # Legend
    console.print("[dim]Legend: ✓ up-to-date  ⚠ changed  ✗ missing[/dim]")

    # Summary
    total_pairs = len(files) * len(check_platforms)
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  Files: {len(files)}")
    console.print(f"  Platforms: {len(check_platforms)}")
    console.print(f"  [dim]Total file-platform pairs: {total_pairs}[/dim]")
    console.print(f"  Up-to-date: [green]{uptodate_count}[/green]")
    console.print(f"  Changed: [yellow]{dirty_count}[/yellow]")
    console.print(f"  Missing: [red]{len(missing_items)}[/red]")

    actionable_count = len(missing_items) + len(dirty_items)
    if actionable_count == 0:
        console.print("\n[green]All content is up-to-date![/green]")
        return

    if not publish and not dry_run:
        console.print("\n[dim]Use --publish to publish missing content.[/dim]")
        console.print("[dim]Use --publish --include-changed to also update changed content.[/dim]")
        console.print("[dim]Use --publish --dry-run to preview what would be published.[/dim]")
        return

    # Build combined list with action type: (file_path, platform, canonical_url, title, action)
    # action is "publish" for missing or "update" for dirty
    # Default: missing items only. Add dirty items if --include-changed.
    actionable_items: list[tuple[Path, str, str, str, str]] = []
    for item in missing_items:
        actionable_items.append((*item, "publish"))

    if include_changed:
        for item in dirty_items:
            actionable_items.append((*item, "update"))

    # Apply sampling if requested
    if sample is not None and len(actionable_items) > sample:
        actionable_items = random.sample(actionable_items, sample)

    # Apply check filtering if --check is used with --publish
    if run_checks and publish and actionable_items:
        from .checker import check_file
        from .config import get_check_overrides, get_site_base_url

        severity_overrides = get_check_overrides()
        site_base_url = get_site_base_url()

        checked_items = []
        skipped_count = 0
        for item in actionable_items:
            file_path = item[0]
            platform = item[1]
            report = check_file(
                file_path,
                platforms=[platform],
                severity_overrides=severity_overrides,
                site_base_url=site_base_url,
            )
            if report.has_errors:
                skipped_count += 1
                if not silent:
                    error_msgs = [r.message for r in report.results if r.severity == "error"]
                    console.print(
                        f"  [yellow]Skipping {file_path.name}"
                        f" → {platform}: {error_msgs[0]}[/yellow]"
                    )
            else:
                checked_items.append(item)

        if skipped_count and not silent:
            suffix = 's' if skipped_count != 1 else ''
            console.print(
                f"[yellow]Skipped {skipped_count}"
                f" item{suffix} due to check failures[/yellow]"
            )
        actionable_items = checked_items

    # Dry run mode - show what would be published without doing it
    if dry_run:
        console.print("\n[bold]Dry Run Preview[/bold]")
        console.print("[dim]No changes will be made[/dim]\n")

        if not actionable_items:
            console.print("[green]Nothing to publish - all content is up-to-date![/green]")
            return

        preview_table = Table(title="Would Process")
        preview_table.add_column("Action", style="cyan", width=8)
        preview_table.add_column("Title", style="green")
        preview_table.add_column("Platform", style="blue")
        preview_table.add_column("Body", justify="right")
        preview_table.add_column("Notes", style="dim")

        for file_path, platform, canonical_url, title, action in actionable_items:
            try:
                article = parse_markdown_file(str(file_path))
                body_len = len(article.body)

                # Check for content length issues
                platform_cls = get_platform(platform)
                max_len = platform_cls.max_content_length
                if max_len and body_len > max_len:
                    notes = f"[yellow]⚠ Exceeds {max_len} char limit - needs --rewrite[/yellow]"
                else:
                    notes = ""

                if action == "publish":
                    action_label = "[green]NEW[/green]"
                else:
                    action_label = "[yellow]UPDATE[/yellow]"
                preview_table.add_row(
                    action_label,
                    title[:40] + ("..." if len(title) > 40 else ""),
                    platform,
                    f"{body_len:,}",
                    notes,
                )
            except Exception as e:
                preview_table.add_row(
                    action.upper(),
                    title[:40],
                    platform,
                    "?",
                    f"[red]Error: {e}[/red]",
                )

        console.print(preview_table)

        new_count = sum(1 for _, _, _, _, a in actionable_items if a == "publish")
        update_count = len(actionable_items) - new_count
        console.print(f"\n[bold]Would process:[/bold] {new_count} new, {update_count} updates")
        console.print("\n[dim]Run without --dry-run to actually publish.[/dim]")
        return

    # Publishing mode - handle both missing (new) and dirty (update) items
    console.print()

    if yes:
        # Do all without prompting
        selected_items = actionable_items
    else:
        # Interactive checkbox selection
        import questionary

        choices = [
            questionary.Choice(
                title=(
                    f"{title[:40]}{'...' if len(title) > 40 else ''}"
                    f" → {platform}"
                    f" [{'NEW' if action == 'publish' else 'UPDATE'}]"
                ),
                value=(file_path, platform, canonical_url, title, action),
                checked=True,  # Default to selected
            )
            for file_path, platform, canonical_url, title, action in actionable_items
        ]

        selected_items = questionary.checkbox(
            "Select items to publish/update (space to toggle, enter to confirm):",
            choices=choices,
        ).ask()

        if selected_items is None:
            console.print("[dim]Cancelled.[/dim]")
            return

        if not selected_items:
            console.print("[dim]No items selected.[/dim]")
            return

    # Do the publishing/updating
    new_count = sum(1 for _, _, _, _, action in selected_items if action == "publish")
    update_count = len(selected_items) - new_count
    if not silent:
        total = len(selected_items)
        console.print(
            f"\n[bold]Processing {total} item(s)"
            f" ({new_count} new, {update_count} updates)...[/bold]\n"
        )

    success_count = 0
    fail_count = 0
    publish_results = []  # For JSON output

    for file_path, platform, canonical_url, title, action in selected_items:
        article = parse_markdown_file(str(file_path))
        api_key = get_api_key(platform)

        if not api_key:
            if not silent:
                hint = f"crier config set {platform}.api_key YOUR_KEY"
                if platform in PLATFORMS:
                    api_url = getattr(PLATFORMS[platform], 'api_key_url', None)
                    if api_url:
                        hint = f"Get key: {api_url}"
                console.print(f"[red]✗ {title[:30]} → {platform}: Not configured[/red]")
                console.print(f"  [dim]{hint}[/dim]")
            publish_results.append({
                "file": str(file_path),
                "platform": platform,
                "success": False,
                "error": "Not configured",
                "action": action,
            })
            fail_count += 1
            continue

        if not article.canonical_url:
            if not silent:
                console.print(f"[yellow]⚠ {title[:30]}: Missing canonical_url[/yellow]")
                console.print("  [dim]Add canonical_url to front matter or set site_base_url[/dim]")
            publish_results.append({
                "file": str(file_path),
                "platform": platform,
                "success": False,
                "error": "Missing canonical_url",
                "action": action,
            })
            fail_count += 1
            continue

        try:
            platform_cls = get_platform(platform)
            plat = platform_cls(api_key)

            # Check if auto-rewrite is needed for this platform
            publish_article = article
            max_len = platform_cls.max_content_length
            rewritten = False
            rewrite_content = None

            if auto_rewrite and llm_provider and max_len and len(article.body) > max_len:
                from .rewrite import auto_rewrite_for_platform

                rw = auto_rewrite_for_platform(
                    article, platform, max_len, llm_provider,
                    retry_count=auto_rewrite_retry or 0,
                    truncate_fallback=bool(auto_rewrite_truncate),
                    silent=silent, console=console,
                )
                if rw.success:
                    publish_article = rw.article
                    rewritten = True
                    rewrite_content = rw.rewrite_text
                else:
                    publish_results.append({
                        "file": str(file_path),
                        "platform": platform,
                        "success": False,
                        "error": rw.error,
                        "action": action,
                    })
                    fail_count += 1
                    continue

            if action == "publish":
                # New publication
                if not silent:
                    console.print(f"[dim]Publishing {title[:30]} → {platform}...[/dim]")
                result = plat.publish(publish_article)
                action_verb = "Published"
            else:
                # Update existing publication
                pub_info = get_publication_info(canonical_url, platform)
                if not pub_info or not pub_info.get("article_id"):
                    if not silent:
                        console.print(
                            f"[yellow]⚠ {title[:30]} → {platform}:"
                            f" No article_id in registry,"
                            f" skipping[/yellow]"
                        )
                    publish_results.append({
                        "file": str(file_path),
                        "platform": platform,
                        "success": False,
                        "error": "No article_id in registry",
                        "action": action,
                    })
                    fail_count += 1
                    continue

                article_id = pub_info["article_id"]
                if not silent:
                    console.print(f"[dim]Updating {title[:30]} → {platform}...[/dim]")
                result = plat.update(article_id, publish_article)
                action_verb = "Updated"

            if result.success:
                if not silent:
                    verb = action_verb.lower()
                    console.print(
                        f"[green]✓ {title[:30]}"
                        f" → {platform} ({verb})[/green]"
                    )
                content_hash = get_file_content_hash(file_path)
                record_publication(
                    canonical_url=article.canonical_url,
                    platform=platform,
                    article_id=result.article_id,
                    url=result.url,
                    title=article.title,
                    source_file=str(file_path),
                    content_hash=content_hash,
                    rewritten=rewritten,
                    rewrite_author=get_rewrite_author() if rewritten else None,
                    posted_content=rewrite_content if rewritten else None,
                )
                publish_results.append({
                    "file": str(file_path),
                    "platform": platform,
                    "success": True,
                    "action": action,
                    "article_id": result.article_id,
                    "url": result.url,
                })
                success_count += 1
            else:
                if not silent:
                    console.print(f"[red]✗ {title[:30]} → {platform}: {result.error}[/red]")
                publish_results.append({
                    "file": str(file_path),
                    "platform": platform,
                    "success": False,
                    "error": result.error,
                    "action": action,
                })
                fail_count += 1

        except Exception as e:
            if not silent:
                console.print(f"[red]✗ {title[:30]} → {platform}: {e}[/red]")
            publish_results.append({
                "file": str(file_path),
                "platform": platform,
                "success": False,
                "error": str(e),
                "action": action,
            })
            fail_count += 1

    # Final output
    if json_output:
        output = {
            "command": "audit",
            "mode": "publish",
            "results": publish_results,
            "summary": {
                "succeeded": success_count,
                "failed": fail_count,
            },
        }
        print(json_module.dumps(output, indent=2))
    else:
        console.print()
        if fail_count == 0:
            console.print(f"[green]All {success_count} operation(s) succeeded![/green]")
        else:
            console.print(f"[yellow]{success_count} succeeded, {fail_count} failed.[/yellow]")

    # Exit codes: 0=success, 1=all failed, 2=partial failure
    if fail_count > 0 and success_count == 0:
        raise SystemExit(1)
    elif fail_count > 0:
        raise SystemExit(2)


@cli.command()
@click.argument("path", type=click.Path(exists=True), required=False)
@click.option("--tag", "-T", "tag_filter", multiple=True,
              help="Only include content with these tags (case-insensitive, OR logic)")
@click.option("--since", "since_date", default=None,
              help="Only include content from this date (e.g., 1w, 7d, 2025-01-01)")
@click.option("--until", "until_date", default=None,
              help="Only include content until this date (e.g., 1w, 7d, 2025-01-01)")
@click.option("--sample", type=int, default=None,
              help="Randomly sample N items")
@click.option("--json", "json_output", is_flag=True,
              help="Output results as JSON")
@click.option("--quiet", "-q", is_flag=True,
              help="Suppress non-essential output (for scripting)")
@click.option("--verbose", "-v", is_flag=True,
              help="Show all tags and descriptions")
def search(
    path: str | None, tag_filter: tuple[str, ...],
    since_date: str | None, until_date: str | None,
    sample: int | None, json_output: bool,
    quiet: bool, verbose: bool,
):
    """Search and list content files with metadata.

    PATH can be a file or directory. If not provided, uses configured content_paths.

    Filters:
    --tag: Filter by tags (case-insensitive, multiple tags use OR logic).
    --since/--until: Filter by date.
    --sample N: Randomly select N items.

    Use --json for machine-readable output.
    """
    import json as json_module

    # Silent mode: suppress non-essential output
    silent = quiet or json_output

    # Find content files
    files = _find_content_files(path)

    # Apply date filtering
    if since_date or until_date:
        since_dt = _parse_date_filter(since_date) if since_date else None
        until_dt = _parse_date_filter(until_date) if until_date else None

        filtered_files = []
        for f in files:
            content_date = _get_content_date(f)
            if content_date:
                # Make comparison timezone-naive if needed
                if content_date.tzinfo is not None:
                    content_date = content_date.replace(tzinfo=None)
                if since_dt and content_date < since_dt:
                    continue
                if until_dt and content_date > until_dt:
                    continue
            filtered_files.append(f)
        files = filtered_files

    # Apply tag filtering
    if tag_filter:
        filter_tags = {t.lower().strip() for t in tag_filter}
        filtered_files = []
        for f in files:
            content_tags = _get_content_tags(f)
            # OR logic: include if any tag matches
            if any(tag in filter_tags for tag in content_tags):
                filtered_files.append(f)
        files = filtered_files

    # Apply sampling
    if sample and len(files) > sample:
        files = random.sample(files, sample)

    if not files:
        if json_output:
            print(json_module.dumps({"results": [], "count": 0}))
        elif not silent:
            if path:
                console.print(f"[yellow]No content files found in {path}[/yellow]")
            else:
                console.print("[yellow]No content files found[/yellow]")
        return

    # Collect metadata for each file
    results = []
    for f in files:
        try:
            article = parse_markdown_file(str(f))
            if article and article.title:
                content_date = _get_content_date(f)
                results.append({
                    "file": str(f),
                    "title": article.title,
                    "date": content_date.isoformat() if content_date else None,
                    "tags": _get_content_tags(f),
                    "words": len(article.body.split()) if article.body else 0,
                    "description": article.description,
                })
        except Exception:
            # Skip files that can't be parsed
            pass

    if json_output:
        print(json_module.dumps({"results": results, "count": len(results)}, indent=2))
    else:
        # Rich table output
        table = Table(title=f"Content ({len(results)} files)")
        table.add_column("File", style="cyan", max_width=40, overflow="ellipsis")
        table.add_column("Title", style="green", max_width=30, overflow="ellipsis")
        table.add_column("Date", style="yellow", width=10)
        if verbose:
            table.add_column("Tags", style="blue", max_width=40)
            table.add_column("Words", style="dim", justify="right", width=6)
            table.add_column("Description", style="dim", max_width=30, overflow="ellipsis")
        else:
            table.add_column("Tags", style="blue", max_width=20, overflow="ellipsis")
            table.add_column("Words", style="dim", justify="right", width=6)

        for r in results:
            date_str = r["date"][:10] if r["date"] else "-"

            tags = r["tags"]
            if verbose:
                tags_str = ", ".join(tags) if tags else "-"
            else:
                tags_str = ", ".join(tags[:3])
                if len(tags) > 3:
                    tags_str += f" (+{len(tags) - 3})"

            if verbose:
                table.add_row(
                    str(r["file"]),
                    r["title"],
                    date_str,
                    tags_str,
                    str(r["words"]),
                    r.get("description", "-") or "-",
                )
            else:
                table.add_row(
                    str(r["file"]),
                    r["title"],
                    date_str,
                    tags_str,
                    str(r["words"]),
                )
        console.print(table)


@cli.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--to", "-t", "platform_args", multiple=True,
              help="Check against specific platform(s)")
@click.option("--all", "-a", "check_all", is_flag=True,
              help="Check all content files")
@click.option("--json", "json_output", is_flag=True,
              help="Output results as JSON")
@click.option("--strict", is_flag=True,
              help="Treat warnings as errors")
@click.option("--check-links", is_flag=True,
              help="Also check external links (slow)")
def check(files: tuple[str, ...], platform_args: tuple[str, ...], check_all: bool,
          json_output: bool, strict: bool, check_links: bool):
    """Validate content before publishing.

    Checks front matter, content, and platform-specific requirements.

    \b
    Examples:
      crier check article.md
      crier check article.md --to bluesky --to devto
      crier check --all --strict
      crier check article.md --json
      crier check article.md --check-links
    """
    import json as json_module
    import sys
    from .checker import check_file, CheckReport
    from .config import get_check_overrides, get_site_base_url

    # Determine which files to check
    if check_all:
        file_paths = _find_content_files()
        if not file_paths:
            if json_output:
                click.echo(json_module.dumps({"error": "No content files found"}))
            else:
                console.print("[yellow]No content files found.[/yellow]")
            sys.exit(1)
    elif files:
        file_paths = [Path(f) for f in files]
    else:
        click.echo("Error: Provide file(s) or use --all to check all content.")
        sys.exit(1)

    # Load config
    severity_overrides = get_check_overrides()
    site_base_url = get_site_base_url()

    platforms = list(platform_args) if platform_args else None

    # Run checks
    reports: list[CheckReport] = []
    for fp in file_paths:
        report = check_file(
            fp,
            platforms=platforms,
            severity_overrides=severity_overrides,
            site_base_url=site_base_url,
            check_links=check_links,
        )
        if strict:
            report = report.with_elevated_warnings()
        reports.append(report)

    # Output
    if json_output:
        output = {
            "reports": [
                {
                    "file": r.file,
                    "passed": r.passed,
                    "results": [
                        {
                            "severity": cr.severity,
                            "check": cr.check_name,
                            "message": cr.message,
                            **({"line": cr.line} if cr.line else {}),
                            **({"platform": cr.platform} if cr.platform else {}),
                        }
                        for cr in r.results
                    ],
                }
                for r in reports
            ],
            "summary": {
                "files": len(reports),
                "passed": sum(1 for r in reports if r.passed),
                "failed": sum(1 for r in reports if not r.passed),
            },
        }
        click.echo(json_module.dumps(output, indent=2))
    else:
        for report in reports:
            if not report.results:
                console.print(f"\n[green]✓[/green] {report.file}")
                continue

            console.print(f"\n{report.file}")
            for result in report.results:
                line_info = f":{result.line}" if result.line else ""
                platform_info = f" [{result.platform}]" if result.platform else ""
                label = _severity_label(result.severity, padded=True)
                name = f"{result.check_name:<24}"
                msg = f"{result.message}{line_info}{platform_info}"
                console.print(f"  {label} {name} {msg}")

        # Summary
        total_errors = sum(1 for r in reports for cr in r.results if cr.severity == "error")
        total_warnings = sum(1 for r in reports for cr in r.results if cr.severity == "warning")
        total_info = sum(1 for r in reports for cr in r.results if cr.severity == "info")

        parts = []
        if total_errors:
            parts.append(f"[red]{total_errors} error{'s' if total_errors != 1 else ''}[/red]")
        if total_warnings:
            s = 's' if total_warnings != 1 else ''
            parts.append(f"[yellow]{total_warnings} warning{s}[/yellow]")
        if total_info:
            parts.append(f"[blue]{total_info} info[/blue]")

        if parts:
            console.print(f"\n{', '.join(parts)}")
        else:
            s = 's' if len(reports) != 1 else ''
            console.print(f"\n[green]All {len(reports)} file{s} passed.[/green]")

    # Exit code
    any_errors = any(not r.passed for r in reports)
    all_failed = all(not r.passed for r in reports) if reports else False

    if not any_errors:
        sys.exit(0)
    elif all_failed or len(reports) == 1:
        sys.exit(1)
    else:
        sys.exit(2)  # Partial failure


@cli.command()
@click.argument("file", type=click.Path(exists=True), required=False)
@click.option("--all", "-a", "show_all", is_flag=True, hidden=True,
              help="(deprecated) Show all tracked posts")
@click.option("--verbose", "-v", is_flag=True, help="Show content hashes and all platforms")
def status(file: str | None, show_all: bool, verbose: bool):
    """Show publication status for a file or all tracked posts.

    Without arguments, shows all tracked posts.
    With a FILE argument, shows detailed status for that file.
    """
    if file:
        # Show status for a specific file
        result = get_article_by_file(file)

        if not result:
            console.print(f"[yellow]No publication record found for {file}[/yellow]")
            console.print("[dim]This file hasn't been published with crier yet.[/dim]")
            return

        canonical_url, article_data = result

        console.print(f"\n[bold]Publication Status: {article_data.get('title', file)}[/bold]")
        console.print(f"[dim]Canonical: {canonical_url}[/dim]")

        # Check if content has changed
        file_path = Path(file)
        current_hash = None
        stored_hash = article_data.get("content_hash")
        if file_path.exists():
            current_hash = get_file_content_hash(file_path)
            if stored_hash and current_hash != stored_hash:
                console.print("[yellow]⚠ Content has changed since last publication[/yellow]")

        if verbose:
            console.print(f"[dim]Stored hash: {stored_hash or 'none'}[/dim]")
            if current_hash:
                console.print(f"[dim]Current hash: {current_hash}[/dim]")

        console.print()

        table = Table(title="Publications")
        table.add_column("Platform", style="cyan")
        table.add_column("Status")
        table.add_column("URL")
        table.add_column("Published")
        if verbose:
            table.add_column("Article ID", style="dim")
            table.add_column("Rewritten", style="yellow")

        publications = article_data.get("platforms", {})

        # Show all platforms, marking which are published
        for platform_name in PLATFORMS:
            if platform_name in publications:
                pub = publications[platform_name]
                row = [
                    platform_name,
                    "[green]✓ Published[/green]",
                    pub.get("url") or "[dim]no url[/dim]",
                    pub.get("published_at", "")[:10] if pub.get("published_at") else "",
                ]
                if verbose:
                    row.append(pub.get("id") or "[dim]-[/dim]")
                    rewritten = "Yes" if pub.get("rewritten") else ""
                    if pub.get("rewrite_author"):
                        rewritten = pub.get("rewrite_author")
                    row.append(rewritten or "[dim]-[/dim]")
                table.add_row(*row)
            else:
                api_key = get_api_key(platform_name)
                if api_key:
                    row = [
                        platform_name,
                        "[yellow]○ Not published[/yellow]",
                        "",
                        "",
                    ]
                    if verbose:
                        row.extend(["", ""])
                    table.add_row(*row)
                elif verbose:
                    # Only show unconfigured platforms in verbose mode
                    table.add_row(
                        platform_name,
                        "[dim]- Not configured[/dim]",
                        "",
                        "",
                        "",
                        "",
                    )

        console.print(table)

    else:
        # Show all tracked posts (registry v2: keyed by canonical_url)
        all_articles = get_all_articles()

        if not all_articles:
            console.print("[yellow]No posts tracked yet.[/yellow]")
            console.print("[dim]Publish a file to start tracking.[/dim]")
            return

        console.print("\n[bold]Tracked Posts[/bold]")
        console.print(f"[dim]Registry: {get_registry_path()}[/dim]\n")

        table = Table(title=f"All Tracked Posts ({len(all_articles)})")
        table.add_column("Source File", style="cyan")
        table.add_column("Title")
        table.add_column("Platforms")
        table.add_column("Changed")
        if verbose:
            table.add_column("Canonical URL", style="dim", max_width=35)
            table.add_column("Hash", style="dim", width=8)

        for canonical_url, article_data in all_articles.items():
            platforms = article_data.get("platforms", {})
            platform_list = ", ".join(platforms.keys()) if platforms else "[dim]none[/dim]"

            source_file = article_data.get("source_file")
            stored_hash = article_data.get("content_hash")
            if source_file:
                full_path = Path(source_file)
                if full_path.exists():
                    current_hash = get_file_content_hash(full_path)
                    is_changed = stored_hash and current_hash != stored_hash
                    changed = "[yellow]⚠ Yes[/yellow]" if is_changed else "No"
                    display_file = source_file
                else:
                    changed = "[red]File missing[/red]"
                    display_file = f"{source_file} [dim](missing)[/dim]"
            else:
                changed = "[dim]?[/dim]"
                display_file = "[dim]unknown[/dim]"

            row = [
                display_file,
                (article_data.get("title") or "")[:35],
                platform_list,
                changed,
            ]
            if verbose:
                row.append(canonical_url[:35] if canonical_url else "")
                row.append(stored_hash[:8] if stored_hash else "-")
            table.add_row(*row)

        console.print(table)


@cli.group()
def skill():
    """Manage Claude Code skill integration."""
    pass


@skill.command(name="install")
@click.option("--local", is_flag=True,
              help="Install to .claude/skills/ (repo-local) instead of ~/.claude/skills/")
def skill_install(local: bool):
    """Install or update the crier skill for Claude Code.

    By default, installs to ~/.claude/skills/crier/ (global).
    Use --local to install to .claude/skills/crier/ (repo-local).
    """
    from .skill import install, is_installed, get_skill_path, get_skill_content

    location = "local" if local else "global"
    status = is_installed()
    skill_path = get_skill_path(local)

    # Check if already installed and up-to-date
    already_installed = (local and status["local"]) or (not local and status["global"])
    if already_installed:
        installed_content = skill_path.read_text()
        current_content = get_skill_content()
        if installed_content == current_content:
            console.print(f"[green]Skill already installed and up-to-date ({location}).[/green]")
            console.print(f"[dim]Path: {skill_path}[/dim]")
            return
        # Outdated - will update
        action = "Updated"
    else:
        action = "Installed"

    path = install(local=local)
    console.print(f"[green]✓ {action} crier skill ({location})[/green]")
    console.print(f"[dim]Path: {path}[/dim]")


@skill.command(name="uninstall")
@click.option("--local", is_flag=True,
              help="Uninstall from .claude/skills/ instead of ~/.claude/skills/")
def skill_uninstall(local: bool):
    """Uninstall the crier skill from Claude Code."""
    from .skill import uninstall

    location = "local" if local else "global"

    if uninstall(local=local):
        console.print(f"[green]✓ Uninstalled crier skill ({location})[/green]")
    else:
        console.print(f"[yellow]Skill not installed ({location}).[/yellow]")


@skill.command(name="status")
def skill_status():
    """Check if the crier skill is installed and up-to-date."""
    from .skill import is_installed, get_skill_path, get_skill_content

    status = is_installed()
    current_content = get_skill_content()
    needs_update = []

    console.print("\n[bold]Claude Code Skill Status[/bold]\n")

    # Check global
    global_path = get_skill_path(local=False)
    if status["global"]:
        installed_content = global_path.read_text()
        if installed_content == current_content:
            global_status = "[green]installed (up-to-date)[/green]"
        else:
            global_status = "[yellow]installed (outdated)[/yellow]"
            needs_update.append("global")
    else:
        global_status = "[dim]not installed[/dim]"
    console.print(f"  Global: {global_path}")
    console.print(f"          {global_status}")

    console.print()

    # Check local
    local_path = get_skill_path(local=True)
    if status["local"]:
        installed_content = local_path.read_text()
        if installed_content == current_content:
            local_status = "[green]installed (up-to-date)[/green]"
        else:
            local_status = "[yellow]installed (outdated)[/yellow]"
            needs_update.append("local")
    else:
        local_status = "[dim]not installed[/dim]"
    console.print(f"  Local:  {local_path}")
    console.print(f"          {local_status}")

    # Show hints
    if not status["global"] and not status["local"]:
        console.print("\n[dim]Install with: crier skill install[/dim]")
    elif needs_update:
        console.print()
        for location in needs_update:
            flag = " --local" if location == "local" else ""
            console.print(
                f"[yellow]Update {location} skill with:"
                f" crier skill install{flag}[/yellow]"
            )


@skill.command(name="show")
def skill_show():
    """Display the skill content."""
    from .skill import get_skill_content

    console.print(get_skill_content())


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--platform", "-t", "platform_name", required=True,
              help="Platform to register publication for")
@click.option("--url", "-u", default=None,
              help="URL of the published article (optional)")
@click.option("--id", "article_id", default=None,
              help="Platform-specific article ID (optional)")
@click.option("--yes", "-y", is_flag=True,
              help="Overwrite existing entry without prompting")
def register(file: str, platform_name: str, url: str | None, article_id: str | None, yes: bool):
    """Manually register a file as published to a platform.

    Use this when you've published content outside of crier and want to
    track it in the registry, or to fix registry entries.

    Example:
        crier register article.md --platform medium --url https://medium.com/@user/article
    """
    article = parse_markdown_file(file)

    if not article.canonical_url:
        console.print("[red]Error: Missing canonical_url in front matter[/red]")
        console.print()
        console.print("[dim]Fix: Add to your file's YAML front matter:[/dim]")
        console.print("[dim]  canonical_url: https://yoursite.com/path/to/article/[/dim]")
        console.print()
        console.print("[dim]Or set site_base_url for auto-inference:[/dim]")
        console.print("[dim]  crier config set site_base_url https://yoursite.com[/dim]")
        return

    # Check if already registered
    if is_published(article.canonical_url, platform_name):
        console.print(f"[yellow]Already registered to {platform_name}.[/yellow]")
        if not yes and not click.confirm("Overwrite existing entry?", default=False):
            return

    content_hash = get_file_content_hash(Path(file))

    record_publication(
        canonical_url=article.canonical_url,
        platform=platform_name,
        article_id=article_id or "manual",
        url=url,
        title=article.title,
        source_file=file,
        content_hash=content_hash,
    )

    console.print(f"[green]✓ Registered {file} as published to {platform_name}[/green]")
    if url:
        console.print(f"[dim]URL: {url}[/dim]")


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--platform", "-t", "platform_name", required=True,
              help="Platform to unregister from")
def unregister(file: str, platform_name: str):
    """Remove a publication record from the registry.

    Use this when a publication was recorded incorrectly or you've
    deleted the post from the platform.

    Example:
        crier unregister article.md --platform medium
    """
    article = parse_markdown_file(file)

    if not article.canonical_url:
        console.print("[red]Error: Missing canonical_url in front matter[/red]")
        console.print("[dim]This file is not tracked in the registry.[/dim]")
        return

    if not is_published(article.canonical_url, platform_name):
        console.print(f"[yellow]Not registered to {platform_name}.[/yellow]")
        return

    if remove_publication(article.canonical_url, platform_name):
        console.print(f"[green]✓ Unregistered {file} from {platform_name}[/green]")
    else:
        console.print("[red]Failed to unregister.[/red]")


@cli.group()
def schedule():
    """Manage scheduled posts."""
    pass


@schedule.command(name="list")
@click.option("--status", "-s", type=click.Choice(["pending", "published", "failed", "cancelled"]),
              help="Filter by status (default: all)")
@click.option("--json", "json_output", is_flag=True,
              help="Output results as JSON")
def schedule_list(status: str | None, json_output: bool):
    """List scheduled posts.

    Shows all scheduled posts, optionally filtered by status.
    """
    import json as json_module
    from .scheduler import list_scheduled_posts

    posts = list_scheduled_posts(status=status)

    if json_output:
        output = {
            "command": "schedule list",
            "posts": [p.to_dict() for p in posts],
            "count": len(posts),
        }
        print(json_module.dumps(output, indent=2, default=str))
        return

    if not posts:
        console.print("[dim]No scheduled posts.[/dim]")
        return

    table = Table(title="Scheduled Posts")
    table.add_column("ID", style="cyan")
    table.add_column("File", style="green")
    table.add_column("Platform", style="blue")
    table.add_column("Scheduled", style="yellow")
    table.add_column("Status")

    for post in posts:
        # Format scheduled time nicely
        local_time = post.scheduled_time.astimezone()
        time_str = local_time.strftime("%Y-%m-%d %H:%M")

        # Format status
        status_display = {
            "pending": "[yellow]pending[/yellow]",
            "published": "[green]published[/green]",
            "failed": "[red]failed[/red]",
            "cancelled": "[dim]cancelled[/dim]",
        }.get(post.status, post.status)

        platform_display = post.profile if post.profile else post.platform

        table.add_row(
            post.id,
            str(Path(post.file_path).name),
            platform_display,
            time_str,
            status_display,
        )

    console.print(table)


@schedule.command(name="show")
@click.argument("post_id")
@click.option("--json", "json_output", is_flag=True,
              help="Output results as JSON")
def schedule_show(post_id: str, json_output: bool):
    """Show details of a scheduled post."""
    import json as json_module
    from .scheduler import get_scheduled_post

    post = get_scheduled_post(post_id)

    if not post:
        if json_output:
            print(json_module.dumps({"success": False, "error": f"Post {post_id} not found"}))
        else:
            console.print(f"[red]Post {post_id} not found.[/red]")
        raise SystemExit(1)

    if json_output:
        print(json_module.dumps({"success": True, "post": post.to_dict()}, indent=2, default=str))
        return

    table = Table(show_header=False, box=None)
    table.add_column("Field", style="cyan")
    table.add_column("Value")

    # Format scheduled time
    local_time = post.scheduled_time.astimezone()

    table.add_row("ID", post.id)
    table.add_row("File", post.file_path)
    table.add_row("Platform", post.profile if post.profile else post.platform)
    table.add_row("Scheduled", local_time.strftime("%Y-%m-%d %H:%M %Z"))
    table.add_row("Created", post.created_at.astimezone().strftime("%Y-%m-%d %H:%M %Z"))
    table.add_row("Status", post.status)
    if post.error:
        table.add_row("Error", f"[red]{post.error}[/red]")
    if post.rewrite:
        rewrite_display = post.rewrite[:50] + "..." if len(post.rewrite) > 50 else post.rewrite
        table.add_row("Rewrite", rewrite_display)
    table.add_row("Auto-rewrite", "Yes" if post.auto_rewrite else "No")

    console.print(table)


@schedule.command(name="cancel")
@click.argument("post_id")
@click.option("--json", "json_output", is_flag=True,
              help="Output results as JSON")
def schedule_cancel(post_id: str, json_output: bool):
    """Cancel a scheduled post.

    Only pending posts can be cancelled.
    """
    import json as json_module
    from .scheduler import cancel_scheduled_post, get_scheduled_post

    post = get_scheduled_post(post_id)
    if not post:
        if json_output:
            print(json_module.dumps({"success": False, "error": f"Post {post_id} not found"}))
        else:
            console.print(f"[red]Post {post_id} not found.[/red]")
        raise SystemExit(1)

    if post.status != "pending":
        if json_output:
            print(json_module.dumps({
                "success": False,
                "error": f"Post is {post.status}, not pending",
            }))
        else:
            console.print(f"[yellow]Post is {post.status}, cannot cancel.[/yellow]")
        raise SystemExit(1)

    if cancel_scheduled_post(post_id):
        if json_output:
            print(json_module.dumps({"success": True, "cancelled": post_id}))
        else:
            console.print(f"[green]✓ Cancelled scheduled post {post_id}[/green]")
    else:
        if json_output:
            print(json_module.dumps({"success": False, "error": "Failed to cancel"}))
        else:
            console.print("[red]Failed to cancel.[/red]")
        raise SystemExit(1)


@schedule.command(name="run")
@click.option("--dry-run", is_flag=True,
              help="Show what would be published without actually publishing")
@click.option("--json", "json_output", is_flag=True,
              help="Output results as JSON")
def schedule_run(dry_run: bool, json_output: bool):
    """Process due scheduled posts (for cron).

    Publishes all pending posts where scheduled_time <= now.
    This command is designed to be called from cron.

    Example crontab entry (run every 5 minutes):
        */5 * * * * cd /path/to/project && crier schedule run
    """
    import json as json_module
    from .scheduler import get_due_posts, update_scheduled_post
    from .converters import parse_markdown_file
    from .platforms import get_platform, PLATFORMS

    due_posts = get_due_posts()

    if not due_posts:
        if json_output:
            print(json_module.dumps({"command": "schedule run", "processed": 0, "results": []}))
        elif not json_output:
            console.print("[dim]No posts due.[/dim]")
        return

    if dry_run:
        if not json_output:
            console.print("[bold]Dry Run - Due Posts[/bold]\n")
            for post in due_posts:
                console.print(
                    f"  • {post.file_path} → {post.platform}"
                    f" (scheduled: {post.scheduled_time})"
                )
            console.print(f"\n[dim]{len(due_posts)} post(s) would be published.[/dim]")
        else:
            output = {
                "command": "schedule run",
                "dry_run": True,
                "due": [p.to_dict() for p in due_posts],
            }
            print(json_module.dumps(output, indent=2, default=str))
        return

    results = []
    success_count = 0
    fail_count = 0

    for post in due_posts:
        # Check file exists
        file_path = Path(post.file_path)
        if not file_path.exists():
            update_scheduled_post(post.id, status="failed", error="Source file not found")
            results.append({"id": post.id, "success": False, "error": "Source file not found"})
            fail_count += 1
            if not json_output:
                console.print(f"[red]✗[/red] {post.id}: Source file not found")
            continue

        # Parse article
        try:
            article = parse_markdown_file(str(file_path))
        except Exception as e:
            update_scheduled_post(post.id, status="failed", error=str(e))
            results.append({"id": post.id, "success": False, "error": str(e)})
            fail_count += 1
            if not json_output:
                console.print(f"[red]✗[/red] {post.id}: {e}")
            continue

        # Get platform
        platform_name = post.platform
        if platform_name not in PLATFORMS:
            err = f"Unknown platform: {platform_name}"
            update_scheduled_post(post.id, status="failed", error=err)
            results.append({"id": post.id, "success": False, "error": err})
            fail_count += 1
            if not json_output:
                console.print(f"[red]✗[/red] {post.id}: Unknown platform {platform_name}")
            continue

        api_key = get_api_key(platform_name)
        if not api_key:
            err = f"No API key for {platform_name}"
            update_scheduled_post(post.id, status="failed", error=err)
            results.append({"id": post.id, "success": False, "error": err})
            fail_count += 1
            if not json_output:
                console.print(f"[red]✗[/red] {post.id}: No API key for {platform_name}")
            continue

        # Handle rewrite if specified
        if post.rewrite:
            article = Article(
                title=article.title,
                body=post.rewrite,
                description=article.description,
                tags=article.tags,
                canonical_url=article.canonical_url,
                published=article.published,
                cover_image=article.cover_image,
            )

        # Publish
        try:
            platform_cls = get_platform(platform_name)
            platform = platform_cls(api_key)
            result = platform.publish(article)

            if result.success:
                update_scheduled_post(post.id, status="published")

                # Record in registry
                if article.canonical_url:
                    record_publication(
                        canonical_url=article.canonical_url,
                        platform=platform_name,
                        article_id=result.article_id,
                        url=result.url,
                        title=article.title,
                        source_file=str(file_path),
                    )

                results.append({
                    "id": post.id,
                    "success": True,
                    "platform": platform_name,
                    "url": result.url,
                })
                success_count += 1
                if not json_output:
                    console.print(f"[green]✓[/green] {post.id}: Published to {platform_name}")
            else:
                update_scheduled_post(post.id, status="failed", error=result.error)
                results.append({"id": post.id, "success": False, "error": result.error})
                fail_count += 1
                if not json_output:
                    console.print(f"[red]✗[/red] {post.id}: {result.error}")

        except Exception as e:
            update_scheduled_post(post.id, status="failed", error=str(e))
            results.append({"id": post.id, "success": False, "error": str(e)})
            fail_count += 1
            if not json_output:
                console.print(f"[red]✗[/red] {post.id}: {e}")

    if json_output:
        output = {
            "command": "schedule run",
            "processed": len(due_posts),
            "results": results,
            "summary": {"succeeded": success_count, "failed": fail_count},
        }
        print(json_module.dumps(output, indent=2, default=str))
    else:
        console.print(f"\n[bold]Processed {len(due_posts)} scheduled post(s):[/bold]")
        console.print(f"  Succeeded: [green]{success_count}[/green]")
        console.print(f"  Failed: [red]{fail_count}[/red]")

    # Exit code
    if fail_count > 0:
        if success_count > 0:
            raise SystemExit(2)  # Partial failure
        raise SystemExit(1)


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--from", "-f", "platform_args", multiple=True,
              help="Platform(s) to delete from (can specify multiple)")
@click.option("--all", "-a", "delete_all", is_flag=True,
              help="Delete from all platforms where published")
@click.option("--yes", "-y", is_flag=True,
              help="Skip confirmation prompt")
@click.option("--dry-run", is_flag=True,
              help="Preview what would be deleted without actually deleting")
@click.option("--batch", is_flag=True,
              help="Non-interactive batch mode (implies --yes, outputs JSON)")
@click.option("--json", "json_output", is_flag=True,
              help="Output results as JSON")
def delete(file: str, platform_args: tuple[str, ...], delete_all: bool,
           yes: bool, dry_run: bool, batch: bool, json_output: bool):
    """Delete content from platform(s).

    Removes the published content from specified platforms via their APIs.
    Updates the registry to mark the publication as deleted.

    Examples:
        crier delete article.md --from devto
        crier delete article.md --from devto --from bluesky
        crier delete article.md --all
        crier delete article.md --all --dry-run
    """
    import json as json_module
    from .registry import record_deletion

    # Batch mode implies --yes and JSON output
    if batch:
        yes = True
        json_output = True

    article = parse_markdown_file(file)

    if not article.canonical_url:
        if json_output:
            print(json_module.dumps({
                "success": False,
                "error": "Missing canonical_url in front matter",
            }))
        else:
            console.print("[red]Error: Missing canonical_url in front matter[/red]")
        raise SystemExit(1)

    # Get article data from registry
    article_data = get_article_by_file(file)
    if not article_data:
        if json_output:
            print(json_module.dumps({"success": False, "error": "Not found in registry"}))
        else:
            console.print("[yellow]This file is not tracked in the registry.[/yellow]")
        raise SystemExit(1)

    canonical_url, registry_entry = article_data
    platforms_data = registry_entry.get("platforms", {})

    # Determine which platforms to delete from
    platforms_to_delete: list[str] = []

    if delete_all:
        # Delete from all platforms where not already deleted
        for platform_name, pub_data in platforms_data.items():
            if "deleted_at" not in pub_data:
                platforms_to_delete.append(platform_name)
    elif platform_args:
        platforms_to_delete = list(platform_args)
    else:
        if json_output:
            print(json_module.dumps({
                "success": False,
                "error": "Specify platforms with --from or use --all",
            }))
        else:
            console.print("[red]Error: Specify platforms with --from or use --all[/red]")
            console.print()
            console.print("Examples:")
            console.print("  crier delete article.md --from devto")
            console.print("  crier delete article.md --all")
        raise SystemExit(1)

    if not platforms_to_delete:
        if json_output:
            print(json_module.dumps({"success": True, "message": "No platforms to delete from"}))
        else:
            console.print("[yellow]No platforms to delete from (all already deleted?).[/yellow]")
        return

    # Dry run: preview deletions
    if dry_run:
        if not json_output:
            console.print("[bold]Dry Run Preview[/bold]")
            console.print("[dim]No changes will be made[/dim]\n")

            table = Table(title=f"Delete: {article.title}")
            table.add_column("Platform", style="cyan")
            table.add_column("Status")
            table.add_column("Article ID")

            for platform_name in platforms_to_delete:
                pub_data = platforms_data.get(platform_name, {})
                article_id = pub_data.get("id", "unknown")

                if platform_name not in platforms_data:
                    table.add_row(platform_name, "[yellow]Not published[/yellow]", "-")
                elif "deleted_at" in pub_data:
                    table.add_row(platform_name, "[dim]Already deleted[/dim]", str(article_id))
                else:
                    platform_cls = PLATFORMS.get(platform_name)
                    if platform_cls and not platform_cls.supports_delete:
                        table.add_row(
                            platform_name,
                            "[yellow]API delete not supported[/yellow]",
                            str(article_id),
                        )
                    else:
                        table.add_row(platform_name, "[green]Would delete[/green]", str(article_id))

            console.print(table)
        else:
            preview = {
                "command": "delete",
                "dry_run": True,
                "file": file,
                "platforms": platforms_to_delete,
            }
            print(json_module.dumps(preview, indent=2))
        return

    # Confirmation prompt
    if not yes and not json_output:
        console.print(f"[bold]Delete from {len(platforms_to_delete)} platform(s):[/bold]")
        for p in platforms_to_delete:
            console.print(f"  • {p}")
        console.print()

        import questionary
        confirm = questionary.confirm("Proceed with deletion?", default=False).ask()
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            return

    # Execute deletions
    results = []
    success_count = 0
    fail_count = 0

    for platform_name in platforms_to_delete:
        pub_data = platforms_data.get(platform_name, {})
        article_id = pub_data.get("id")

        # Check if already deleted
        if "deleted_at" in pub_data:
            results.append({
                "platform": platform_name,
                "success": True,
                "skipped": True,
                "reason": "Already deleted",
            })
            continue

        # Check if not published
        if platform_name not in platforms_data:
            results.append({
                "platform": platform_name,
                "success": False,
                "error": "Not published to this platform",
            })
            fail_count += 1
            continue

        # Check if platform exists
        if platform_name not in PLATFORMS:
            results.append({
                "platform": platform_name,
                "success": False,
                "error": "Unknown platform",
            })
            fail_count += 1
            continue

        platform_cls = PLATFORMS[platform_name]

        # Check if platform supports delete
        if not platform_cls.supports_delete:
            url = pub_data.get("url", "")
            results.append({
                "platform": platform_name,
                "success": False,
                "error": f"Platform does not support API deletion. Delete manually at: {url}",
            })
            fail_count += 1
            continue

        # Get API key
        api_key = get_api_key(platform_name)
        if not api_key or is_manual_mode_key(api_key) or is_import_mode_key(api_key):
            url = pub_data.get("url", "")
            results.append({
                "platform": platform_name,
                "success": False,
                "error": f"No API key configured. Delete manually at: {url}",
            })
            fail_count += 1
            continue

        # Execute deletion
        try:
            platform = platform_cls(api_key)
            delete_result = platform.delete(article_id)

            if delete_result.success:
                # Record deletion in registry
                record_deletion(canonical_url, platform_name)
                results.append({
                    "platform": platform_name,
                    "success": True,
                    "article_id": article_id,
                })
                success_count += 1
                if not json_output:
                    console.print(f"[green]✓[/green] Deleted from {platform_name}")
            else:
                results.append({
                    "platform": platform_name,
                    "success": False,
                    "error": delete_result.error,
                })
                fail_count += 1
                if not json_output:
                    console.print(f"[red]✗[/red] {platform_name}: {delete_result.error}")

        except Exception as e:
            results.append({
                "platform": platform_name,
                "success": False,
                "error": str(e),
            })
            fail_count += 1
            if not json_output:
                console.print(f"[red]✗[/red] {platform_name}: {e}")

    # Output JSON results
    if json_output:
        output = {
            "command": "delete",
            "file": file,
            "results": results,
            "summary": {
                "succeeded": success_count,
                "failed": fail_count,
            },
        }
        print(json_module.dumps(output, indent=2))

    # Exit code
    if fail_count > 0:
        if success_count > 0:
            raise SystemExit(2)  # Partial failure
        raise SystemExit(1)  # Complete failure


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--json", "json_output", is_flag=True,
              help="Output result as JSON")
def archive(file: str, json_output: bool):
    """Archive content (exclude from audit --publish).

    Archived content is marked as "retired" in the registry. It will be
    excluded from `crier audit --publish` by default, but remains visible
    in `crier status`.

    Use this when content is outdated but you don't want to delete it
    from platforms.

    Example:
        crier archive article.md
    """
    import json as json_module
    from .registry import set_archived, is_archived

    article = parse_markdown_file(file)

    if not article.canonical_url:
        if json_output:
            print(json_module.dumps({
                "success": False,
                "error": "Missing canonical_url in front matter",
            }))
        else:
            console.print("[red]Error: Missing canonical_url in front matter[/red]")
        raise SystemExit(1)

    # Check if already archived
    if is_archived(article.canonical_url):
        if json_output:
            print(json_module.dumps({"success": True, "already_archived": True}))
        else:
            console.print("[yellow]Already archived.[/yellow]")
        return

    # Set archived
    if set_archived(article.canonical_url, archived=True):
        if json_output:
            print(json_module.dumps({"success": True, "archived": True}))
        else:
            console.print(f"[green]✓ Archived: {article.title}[/green]")
            console.print("[dim]This content will be excluded from audit --publish.[/dim]")
    else:
        if json_output:
            print(json_module.dumps({"success": False, "error": "Not found in registry"}))
        else:
            console.print("[yellow]Not found in registry. Publish it first.[/yellow]")
        raise SystemExit(1)


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--json", "json_output", is_flag=True,
              help="Output result as JSON")
def unarchive(file: str, json_output: bool):
    """Unarchive content (include in audit --publish again).

    Reverses the effect of `crier archive`. The content will be included
    in `crier audit --publish` again.

    Example:
        crier unarchive article.md
    """
    import json as json_module
    from .registry import set_archived, is_archived

    article = parse_markdown_file(file)

    if not article.canonical_url:
        if json_output:
            print(json_module.dumps({
                "success": False,
                "error": "Missing canonical_url in front matter",
            }))
        else:
            console.print("[red]Error: Missing canonical_url in front matter[/red]")
        raise SystemExit(1)

    # Check if archived
    if not is_archived(article.canonical_url):
        if json_output:
            print(json_module.dumps({"success": True, "already_unarchived": True}))
        else:
            console.print("[yellow]Not archived.[/yellow]")
        return

    # Unarchive
    if set_archived(article.canonical_url, archived=False):
        if json_output:
            print(json_module.dumps({"success": True, "archived": False}))
        else:
            console.print(f"[green]✓ Unarchived: {article.title}[/green]")
            console.print("[dim]This content will be included in audit --publish again.[/dim]")
    else:
        if json_output:
            print(json_module.dumps({"success": False, "error": "Failed to unarchive"}))
        else:
            console.print("[red]Failed to unarchive.[/red]")
        raise SystemExit(1)


@cli.command()
@click.argument("file", type=click.Path(exists=True), required=False)
@click.option("--platform", "-p", "platforms", multiple=True,
              help="Filter to specific platforms")
@click.option("--refresh", is_flag=True,
              help="Refresh stats from platforms (ignore cache)")
@click.option("--json", "json_output", is_flag=True,
              help="Output result as JSON")
@click.option("--top", type=int, default=0,
              help="Show top N articles by engagement")
@click.option("--since", "since_str",
              help="Filter to articles published since (1d, 1w, 1m, or YYYY-MM-DD)")
def stats(file: str | None, platforms: tuple[str, ...], refresh: bool,
          json_output: bool, top: int, since_str: str | None):
    """Show engagement stats for published content.

    Without a file argument, shows aggregate stats across all content.
    With a file argument, shows detailed stats for that article.

    Examples:
        crier stats article.md
        crier stats article.md --refresh
        crier stats --top 10
        crier stats --since 1m
        crier stats --platform devto --json
    """
    import json as json_module
    from .registry import (
        get_all_articles,
        get_article_by_file,
        get_cached_stats,
        save_stats,
        get_stats_age_seconds,
    )
    from .platforms import get_platform

    # Parse --since filter
    since_date = None
    if since_str:
        since_date = _parse_date_filter(since_str)

    # Cache TTL: 1 hour
    CACHE_TTL_SECONDS = 3600

    def fetch_stats_for_platform(
        canonical_url: str, platform_name: str, article_id: str,
    ) -> dict | None:
        """Fetch stats from platform API and cache them."""
        try:
            api_key = get_api_key(platform_name)
            if not api_key or is_manual_mode_key(api_key) or is_import_mode_key(api_key):
                return None

            platform_obj = get_platform(platform_name, api_key)
            if not platform_obj or not platform_obj.supports_stats:
                return None

            stats_result = platform_obj.get_stats(article_id)
            if stats_result:
                # Cache the stats
                save_stats(
                    canonical_url,
                    platform_name,
                    views=stats_result.views,
                    likes=stats_result.likes,
                    comments=stats_result.comments,
                    reposts=stats_result.reposts,
                )
                return {
                    "views": stats_result.views,
                    "likes": stats_result.likes,
                    "comments": stats_result.comments,
                    "reposts": stats_result.reposts,
                }
        except Exception:
            pass
        return None

    def get_or_fetch_stats(canonical_url: str, platform_name: str, article_id: str) -> dict | None:
        """Get cached stats or fetch fresh ones."""
        if not refresh:
            # Check cache age
            age = get_stats_age_seconds(canonical_url, platform_name)
            if age is not None and age < CACHE_TTL_SECONDS:
                cached = get_cached_stats(canonical_url, platform_name)
                if cached:
                    return {
                        "views": cached.get("views"),
                        "likes": cached.get("likes"),
                        "comments": cached.get("comments"),
                        "reposts": cached.get("reposts"),
                        "fetched_at": cached.get("fetched_at"),
                    }

        # Fetch fresh stats
        return fetch_stats_for_platform(canonical_url, platform_name, article_id)

    def format_number(n: int | None) -> str:
        """Format number with commas, or - if None."""
        if n is None:
            return "-"
        return f"{n:,}"

    def format_time_ago(iso_str: str | None) -> str:
        """Format ISO timestamp as 'X ago'."""
        if not iso_str:
            return "-"
        try:
            dt = datetime.fromisoformat(iso_str)
            now = datetime.now(dt.tzinfo)
            delta = now - dt
            if delta.total_seconds() < 60:
                return "just now"
            elif delta.total_seconds() < 3600:
                mins = int(delta.total_seconds() / 60)
                return f"{mins}m ago"
            elif delta.total_seconds() < 86400:
                hours = int(delta.total_seconds() / 3600)
                return f"{hours}h ago"
            else:
                days = int(delta.total_seconds() / 86400)
                return f"{days}d ago"
        except Exception:
            return "-"

    # Single article mode
    if file:
        article = parse_markdown_file(file)
        if not article.canonical_url:
            if json_output:
                print(json_module.dumps({
                "success": False,
                "error": "Missing canonical_url in front matter",
            }))
            else:
                console.print("[red]Error: Missing canonical_url in front matter[/red]")
            raise SystemExit(1)

        result = get_article_by_file(file)
        if not result:
            if json_output:
                print(json_module.dumps({"success": False, "error": "Not found in registry"}))
            else:
                console.print("[yellow]Not found in registry. Publish it first.[/yellow]")
            raise SystemExit(1)

        canonical_url, article_data = result
        article_platforms = article_data.get("platforms", {})

        # Filter platforms if specified
        if platforms:
            article_platforms = {k: v for k, v in article_platforms.items() if k in platforms}

        if not article_platforms:
            if json_output:
                print(json_module.dumps({"success": False, "error": "No matching platforms found"}))
            else:
                console.print("[yellow]No matching platforms found.[/yellow]")
            raise SystemExit(1)

        # Gather stats for each platform
        stats_data = []
        totals = {"views": 0, "likes": 0, "comments": 0, "reposts": 0}
        platforms_without_stats = []

        for platform_name, pub_data in article_platforms.items():
            if pub_data.get("deleted_at"):
                continue

            article_id = pub_data.get("id")
            if not article_id:
                continue

            stats_result = get_or_fetch_stats(canonical_url, platform_name, article_id)
            if stats_result:
                stats_data.append({
                    "platform": platform_name,
                    "url": pub_data.get("url"),
                    **stats_result,
                })
                for key in totals:
                    if stats_result.get(key) is not None:
                        totals[key] += stats_result[key]
            else:
                # Check if platform supports stats
                try:
                    api_key = get_api_key(platform_name)
                    has_real_key = (
                        api_key
                        and not is_manual_mode_key(api_key)
                        and not is_import_mode_key(api_key)
                    )
                    if has_real_key:
                        platform_obj = get_platform(platform_name, api_key)
                        if platform_obj and not platform_obj.supports_stats:
                            platforms_without_stats.append(platform_name)
                except Exception:
                    pass

        if json_output:
            output = {
                "success": True,
                "title": article.title,
                "canonical_url": canonical_url,
                "platforms": stats_data,
                "totals": totals,
            }
            if platforms_without_stats:
                output["platforms_without_stats"] = platforms_without_stats
            print(json_module.dumps(output, indent=2))
        else:
            console.print(f"\n[bold]{article.title}[/bold]")
            console.print("=" * len(article.title))
            console.print()

            if stats_data:
                table = Table(show_header=True, header_style="bold")
                table.add_column("Platform")
                table.add_column("Views", justify="right")
                table.add_column("Likes", justify="right")
                table.add_column("Comments", justify="right")
                table.add_column("Reposts", justify="right")
                table.add_column("Last Updated")

                for s in stats_data:
                    table.add_row(
                        s["platform"],
                        format_number(s.get("views")),
                        format_number(s.get("likes")),
                        format_number(s.get("comments")),
                        format_number(s.get("reposts")),
                        format_time_ago(s.get("fetched_at")),
                    )

                # Add totals row
                table.add_row(
                    "[bold]Total[/bold]",
                    format_number(totals["views"] or None),
                    format_number(totals["likes"] or None),
                    format_number(totals["comments"] or None),
                    format_number(totals["reposts"] or None),
                    "",
                    style="bold",
                )

                console.print(table)

            if platforms_without_stats:
                no_stats = ', '.join(platforms_without_stats)
                console.print(
                    f"\n[dim]Note: {no_stats}"
                    f" do not provide stats via API[/dim]"
                )

        return

    # Aggregate mode (no file specified)
    all_articles = get_all_articles()
    if not all_articles:
        if json_output:
            print(json_module.dumps({"success": False, "error": "No articles in registry"}))
        else:
            console.print("[yellow]No articles in registry. Publish some content first.[/yellow]")
        raise SystemExit(1)

    # Collect stats for all articles
    article_stats = []
    grand_totals = {"views": 0, "likes": 0, "comments": 0, "reposts": 0}
    platforms_seen = set()

    for canonical_url, article_data in all_articles.items():
        # Apply --since filter
        if since_date:
            # Check if any publication is after since_date
            any_after = False
            for pub_data in article_data.get("platforms", {}).values():
                pub_date_str = pub_data.get("published_at")
                if pub_date_str:
                    try:
                        pub_date = datetime.fromisoformat(pub_date_str)
                        if pub_date.date() >= since_date:
                            any_after = True
                            break
                    except Exception:
                        pass
            if not any_after:
                continue

        article_totals = {"views": 0, "likes": 0, "comments": 0, "reposts": 0}
        article_platforms = []

        for platform_name, pub_data in article_data.get("platforms", {}).items():
            if pub_data.get("deleted_at"):
                continue

            # Filter platforms if specified
            if platforms and platform_name not in platforms:
                continue

            article_id = pub_data.get("id")
            if not article_id:
                continue

            stats_result = get_or_fetch_stats(canonical_url, platform_name, article_id)
            if stats_result:
                platforms_seen.add(platform_name)
                article_platforms.append(platform_name)
                for key in article_totals:
                    if stats_result.get(key) is not None:
                        article_totals[key] += stats_result[key]
                        grand_totals[key] += stats_result[key]

        if article_platforms:
            engagement_score = (
                (article_totals["likes"] or 0) +
                (article_totals["comments"] or 0) * 2 +
                (article_totals["reposts"] or 0) * 3
            )
            article_stats.append({
                "canonical_url": canonical_url,
                "title": article_data.get("title", "Untitled"),
                "platforms": article_platforms,
                **article_totals,
                "engagement_score": engagement_score,
            })

    # Sort by engagement score
    article_stats.sort(key=lambda x: x["engagement_score"], reverse=True)

    # Apply --top filter
    if top > 0:
        article_stats = article_stats[:top]

    if json_output:
        output = {
            "success": True,
            "articles": article_stats,
            "totals": grand_totals,
            "platforms": list(platforms_seen),
        }
        print(json_module.dumps(output, indent=2))
    else:
        title = "Content Stats"
        if top > 0:
            title = f"Top {top} Articles by Engagement"
        if since_str:
            title += f" (since {since_str})"

        console.print(f"\n[bold]{title}[/bold]")
        console.print("=" * len(title))
        console.print()

        if article_stats:
            table = Table(show_header=True, header_style="bold")
            table.add_column("#", justify="right")
            table.add_column("Title", max_width=40)
            table.add_column("Views", justify="right")
            table.add_column("Likes", justify="right")
            table.add_column("Comments", justify="right")
            table.add_column("Platforms")

            for i, a in enumerate(article_stats, 1):
                title_str = a["title"][:37] + "..." if len(a["title"]) > 40 else a["title"]
                table.add_row(
                    str(i),
                    title_str,
                    format_number(a.get("views")),
                    format_number(a.get("likes")),
                    format_number(a.get("comments")),
                    ", ".join(a["platforms"]),
                )

            console.print(table)

            console.print("\n[bold]Summary[/bold]")
            console.print(f"  Total views: {format_number(grand_totals['views'] or None)}")
            console.print(f"  Total likes: {format_number(grand_totals['likes'] or None)}")
            console.print(f"  Total comments: {format_number(grand_totals['comments'] or None)}")
            console.print(f"  Total reposts: {format_number(grand_totals['reposts'] or None)}")
            console.print(f"  Platforms: {', '.join(sorted(platforms_seen))}")
        else:
            console.print("[yellow]No stats available for the specified criteria.[/yellow]")


if __name__ == "__main__":
    cli()
