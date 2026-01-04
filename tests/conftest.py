"""Shared test fixtures for crier tests."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from crier.platforms.base import Article


@pytest.fixture
def sample_article():
    """Create a sample Article for testing."""
    return Article(
        title="Test Article Title",
        body="This is the body of the test article.\n\nIt has multiple paragraphs.",
        description="A brief description of the test article",
        tags=["python", "testing", "crier"],
        canonical_url="https://example.com/test-article",
        published=True,
    )


@pytest.fixture
def sample_markdown_file(tmp_path):
    """Create a sample markdown file with front matter."""
    content = """\
---
title: "Test Article Title"
description: "A brief description"
tags: [python, testing]
canonical_url: https://example.com/test-article
published: true
---

This is the body of the test article.

It has multiple paragraphs.
"""
    md_file = tmp_path / "test_article.md"
    md_file.write_text(content)
    return md_file


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Create a temporary config file and patch the config path."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"

    # Create local .crier directory for local config
    local_config_dir = tmp_path / ".crier"
    local_config_dir.mkdir()

    # Patch the config path
    monkeypatch.setattr("crier.config.DEFAULT_CONFIG_FILE", config_file)
    monkeypatch.setattr("crier.config.DEFAULT_CONFIG_DIR", config_dir)

    # Clear any cached config
    monkeypatch.delenv("CRIER_CONFIG", raising=False)

    # Change to tmp_path so local config is found there
    monkeypatch.chdir(tmp_path)

    return config_file


@pytest.fixture
def tmp_registry(tmp_path, monkeypatch):
    """Create a temporary registry directory."""
    registry_dir = tmp_path / ".crier"
    registry_dir.mkdir()
    registry_file = registry_dir / "registry.yaml"

    # Initialize empty registry
    registry_file.write_text("version: 2\narticles: {}\n")

    # Patch to use tmp_path as cwd for registry discovery
    original_cwd = Path.cwd()
    monkeypatch.chdir(tmp_path)

    return registry_dir


@pytest.fixture
def mock_env_api_key(monkeypatch):
    """Factory fixture to set environment API keys."""
    def _set_key(platform: str, value: str):
        monkeypatch.setenv(f"CRIER_{platform.upper()}_API_KEY", value)
    return _set_key


@pytest.fixture
def configured_platforms(tmp_config):
    """Create a config with some platforms configured."""
    config = {
        "platforms": {
            "devto": {"api_key": "devto_test_key"},
            "bluesky": {"api_key": "handle.bsky.social:app-password"},
            "twitter": {"api_key": "manual"},
            "linkedin": {"api_key": ""},
        },
        "profiles": {
            "blogs": ["devto", "hashnode"],
            "social": ["bluesky", "mastodon"],
            "all": ["blogs", "social"],
        },
        "content_paths": ["posts", "articles"],
    }
    tmp_config.write_text(yaml.dump(config))
    return tmp_config
