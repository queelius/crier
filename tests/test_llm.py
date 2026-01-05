"""Tests for the LLM provider module."""

import pytest
from unittest.mock import Mock, patch, MagicMock, PropertyMock

from crier.llm import (
    LLMProvider,
    LLMProviderError,
    RewriteResult,
    OpenAICompatProvider,
    get_provider,
    DEFAULT_REWRITE_PROMPT,
)


class TestRewriteResult:
    """Tests for the RewriteResult dataclass."""

    def test_basic_result(self):
        """Test creating a basic result."""
        result = RewriteResult(
            text="Short summary",
            model="llama3",
        )
        assert result.text == "Short summary"
        assert result.model == "llama3"
        assert result.tokens_used is None

    def test_result_with_tokens(self):
        """Test result with token count."""
        result = RewriteResult(
            text="Summary text",
            model="gpt-4o-mini",
            tokens_used=150,
        )
        assert result.tokens_used == 150


class TestOpenAICompatProvider:
    """Tests for the OpenAI-compatible provider."""

    def test_provider_initialization(self):
        """Test provider initializes correctly."""
        provider = OpenAICompatProvider(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="llama3",
        )
        assert provider.base_url == "http://localhost:11434/v1"
        assert provider.api_key == "test-key"
        assert provider.model == "llama3"
        assert provider.name == "openai"

    def test_base_url_trailing_slash_removed(self):
        """Test that trailing slash is removed from base_url."""
        provider = OpenAICompatProvider(
            base_url="http://localhost:11434/v1/",
            api_key="",
            model="llama3",
        )
        assert provider.base_url == "http://localhost:11434/v1"

    def test_custom_prompt_template(self):
        """Test custom prompt template."""
        custom_prompt = "Summarize: {title}\n{body}\nMax: {max_chars} for {platform}"
        provider = OpenAICompatProvider(
            base_url="http://localhost:11434/v1",
            api_key="",
            model="llama3",
            prompt_template=custom_prompt,
        )
        assert provider.prompt_template == custom_prompt

    def test_default_prompt_template(self):
        """Test default prompt template is used."""
        provider = OpenAICompatProvider(
            base_url="http://localhost:11434/v1",
            api_key="",
            model="llama3",
        )
        assert provider.prompt_template == DEFAULT_REWRITE_PROMPT

    @patch("crier.llm.openai_compat.requests.post")
    def test_rewrite_success(self, mock_post):
        """Test successful rewrite call."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": "A great article about testing!"}}
            ],
            "usage": {"total_tokens": 100},
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        provider = OpenAICompatProvider(
            base_url="http://localhost:11434/v1",
            api_key="test-key",
            model="llama3",
        )

        result = provider.rewrite(
            title="Test Article",
            body="This is a long article body...",
            max_chars=280,
            platform="bluesky",
        )

        assert result.text == "A great article about testing!"
        assert result.model == "llama3"
        assert result.tokens_used == 100

        # Verify API was called correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "http://localhost:11434/v1/chat/completions"
        assert call_args[1]["headers"]["Content-Type"] == "application/json"
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-key"

    @patch("crier.llm.openai_compat.requests.post")
    def test_rewrite_no_api_key(self, mock_post):
        """Test rewrite without API key (for local providers like Ollama)."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Summary"}}],
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        provider = OpenAICompatProvider(
            base_url="http://localhost:11434/v1",
            api_key="",  # Empty key for Ollama
            model="llama3",
        )

        provider.rewrite(
            title="Test",
            body="Body",
            max_chars=280,
            platform="bluesky",
        )

        # Authorization header should not be present
        call_args = mock_post.call_args
        assert "Authorization" not in call_args[1]["headers"]

    @patch("crier.llm.openai_compat.requests.post")
    def test_rewrite_truncates_long_response(self, mock_post):
        """Test that overly long responses are truncated at sentence boundary."""
        # Response that's too long (350 chars > 280 limit)
        long_text = "This is sentence one. " * 20  # ~440 chars
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": long_text}}],
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        provider = OpenAICompatProvider(
            base_url="http://localhost:11434/v1",
            api_key="",
            model="llama3",
        )

        result = provider.rewrite(
            title="Test",
            body="Body",
            max_chars=280,
            platform="bluesky",
        )

        # Result should be truncated to <= 280 chars
        assert len(result.text) <= 280
        # Should end at sentence boundary
        assert result.text.endswith(".")

    @patch("crier.llm.openai_compat.requests.post")
    def test_rewrite_api_error(self, mock_post):
        """Test handling of API errors."""
        import requests
        mock_post.side_effect = requests.RequestException("Connection failed")

        provider = OpenAICompatProvider(
            base_url="http://localhost:11434/v1",
            api_key="",
            model="llama3",
        )

        with pytest.raises(LLMProviderError) as exc_info:
            provider.rewrite(
                title="Test",
                body="Body",
                max_chars=280,
                platform="bluesky",
            )

        assert "API request failed" in str(exc_info.value)

    @patch("crier.llm.openai_compat.requests.post")
    def test_rewrite_malformed_response(self, mock_post):
        """Test handling of malformed API responses."""
        mock_response = Mock()
        mock_response.json.return_value = {"unexpected": "format"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        provider = OpenAICompatProvider(
            base_url="http://localhost:11434/v1",
            api_key="",
            model="llama3",
        )

        with pytest.raises(LLMProviderError) as exc_info:
            provider.rewrite(
                title="Test",
                body="Body",
                max_chars=280,
                platform="bluesky",
            )

        assert "Unexpected API response format" in str(exc_info.value)

    @patch("crier.llm.openai_compat.requests.post")
    def test_rewrite_truncates_long_body(self, mock_post):
        """Test that very long article bodies are truncated before sending."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Summary"}}],
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        provider = OpenAICompatProvider(
            base_url="http://localhost:11434/v1",
            api_key="",
            model="llama3",
        )

        # Create a very long body (>4000 chars)
        long_body = "x" * 5000

        provider.rewrite(
            title="Test",
            body=long_body,
            max_chars=280,
            platform="bluesky",
        )

        # Check that the body in the prompt was truncated
        call_args = mock_post.call_args
        request_data = call_args[1]["json"]
        prompt = request_data["messages"][0]["content"]

        # The body in the prompt should be truncated + "[Content truncated...]"
        assert "[Content truncated...]" in prompt


class TestGetProvider:
    """Tests for the get_provider factory function."""

    def test_get_provider_openai(self):
        """Test creating OpenAI-compatible provider."""
        config = {
            "provider": "openai",
            "base_url": "http://localhost:11434/v1",
            "api_key": "test-key",
            "model": "llama3",
        }
        provider = get_provider(config)
        assert isinstance(provider, OpenAICompatProvider)
        assert provider.model == "llama3"

    def test_get_provider_empty_config(self):
        """Test empty config returns None."""
        assert get_provider({}) is None
        assert get_provider(None) is None

    def test_get_provider_missing_base_url(self):
        """Test config without base_url returns None."""
        config = {
            "provider": "openai",
            "model": "llama3",
        }
        assert get_provider(config) is None

    def test_get_provider_missing_model(self):
        """Test config without model returns None."""
        config = {
            "provider": "openai",
            "base_url": "http://localhost:11434/v1",
        }
        assert get_provider(config) is None

    def test_get_provider_unknown_type(self):
        """Test unknown provider type returns None."""
        config = {
            "provider": "unknown",
            "base_url": "http://example.com",
            "model": "model",
        }
        assert get_provider(config) is None

    def test_get_provider_with_custom_prompt(self):
        """Test custom prompt is passed to provider."""
        config = {
            "provider": "openai",
            "base_url": "http://localhost:11434/v1",
            "model": "llama3",
            "rewrite_prompt": "Custom prompt: {title}",
        }
        provider = get_provider(config)
        assert provider.prompt_template == "Custom prompt: {title}"


class TestConfigIntegration:
    """Tests for LLM config integration."""

    def test_get_llm_config_from_file(self, tmp_config):
        """Test loading LLM config from config file."""
        import yaml
        from crier.config import get_llm_config

        config = {
            "llm": {
                "provider": "openai",
                "base_url": "http://localhost:11434/v1",
                "model": "llama3",
            }
        }
        tmp_config.write_text(yaml.dump(config))

        llm_config = get_llm_config()
        assert llm_config["provider"] == "openai"
        assert llm_config["base_url"] == "http://localhost:11434/v1"
        assert llm_config["model"] == "llama3"

    def test_get_llm_config_env_override(self, tmp_config, monkeypatch):
        """Test environment variables override config file."""
        import yaml
        from crier.config import get_llm_config

        config = {
            "llm": {
                "provider": "openai",
                "base_url": "http://config-url/v1",
                "model": "config-model",
                "api_key": "config-key",
            }
        }
        tmp_config.write_text(yaml.dump(config))

        # Environment variables override
        monkeypatch.setenv("CRIER_LLM_BASE_URL", "http://env-url/v1")
        monkeypatch.setenv("CRIER_LLM_MODEL", "env-model")
        monkeypatch.setenv("CRIER_LLM_API_KEY", "env-key")

        llm_config = get_llm_config()
        assert llm_config["base_url"] == "http://env-url/v1"
        assert llm_config["model"] == "env-model"
        assert llm_config["api_key"] == "env-key"

    def test_get_llm_config_openai_api_key_fallback(self, tmp_config, monkeypatch):
        """Test fallback to standard OPENAI_API_KEY env var."""
        from crier.config import get_llm_config

        tmp_config.write_text("")

        # Only OPENAI_API_KEY set (standard env var)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        llm_config = get_llm_config()
        assert llm_config["api_key"] == "sk-test-key"
        # Should default to OpenAI endpoint and model
        assert llm_config["base_url"] == "https://api.openai.com/v1"
        assert llm_config["model"] == "gpt-4o-mini"

    def test_get_llm_config_crier_key_takes_precedence(self, tmp_config, monkeypatch):
        """Test CRIER_LLM_API_KEY takes precedence over OPENAI_API_KEY."""
        from crier.config import get_llm_config

        tmp_config.write_text("")

        monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
        monkeypatch.setenv("CRIER_LLM_API_KEY", "crier-key")

        llm_config = get_llm_config()
        assert llm_config["api_key"] == "crier-key"

    def test_get_llm_config_defaults_with_api_key(self, tmp_config, monkeypatch):
        """Test defaults are applied when API key is present but base_url/model missing."""
        import yaml
        from crier.config import get_llm_config

        # Config with only api_key
        config = {"llm": {"api_key": "my-key"}}
        tmp_config.write_text(yaml.dump(config))

        llm_config = get_llm_config()
        assert llm_config["api_key"] == "my-key"
        assert llm_config["base_url"] == "https://api.openai.com/v1"
        assert llm_config["model"] == "gpt-4o-mini"

    def test_is_llm_configured_true(self, tmp_config):
        """Test is_llm_configured returns True when configured."""
        import yaml
        from crier.config import is_llm_configured

        config = {
            "llm": {
                "base_url": "http://localhost:11434/v1",
                "model": "llama3",
            }
        }
        tmp_config.write_text(yaml.dump(config))

        assert is_llm_configured() is True

    def test_is_llm_configured_false(self, tmp_config):
        """Test is_llm_configured returns False when not configured."""
        from crier.config import is_llm_configured

        tmp_config.write_text("")

        assert is_llm_configured() is False

    def test_set_llm_config(self, tmp_config):
        """Test setting LLM config."""
        import yaml
        from crier.config import set_llm_config, get_llm_config

        set_llm_config(
            provider="openai",
            base_url="http://localhost:11434/v1",
            model="llama3",
        )

        llm_config = get_llm_config()
        assert llm_config["provider"] == "openai"
        assert llm_config["base_url"] == "http://localhost:11434/v1"
        assert llm_config["model"] == "llama3"


class TestDefaultRewritePrompt:
    """Tests for the default rewrite prompt."""

    def test_prompt_contains_placeholders(self):
        """Test that the default prompt has required placeholders."""
        assert "{title}" in DEFAULT_REWRITE_PROMPT
        assert "{body}" in DEFAULT_REWRITE_PROMPT
        assert "{max_chars}" in DEFAULT_REWRITE_PROMPT
        assert "{platform}" in DEFAULT_REWRITE_PROMPT

    def test_prompt_formatting(self):
        """Test that the prompt can be formatted."""
        formatted = DEFAULT_REWRITE_PROMPT.format(
            title="Test Title",
            body="Test body content",
            max_chars=280,
            platform="bluesky",
        )
        assert "Test Title" in formatted
        assert "Test body content" in formatted
        assert "280" in formatted
        assert "bluesky" in formatted
