"""OpenAI-compatible LLM provider.

Works with:
- OpenAI API
- Ollama (with OpenAI-compatible endpoint)
- Groq
- Together AI
- vLLM
- Any other OpenAI-compatible API
"""

import requests

from .provider import LLMProvider, LLMProviderError, RewriteResult, DEFAULT_REWRITE_PROMPT, RETRY_PROMPT_ADDITION


class OpenAICompatProvider(LLMProvider):
    """OpenAI-compatible LLM provider.

    Uses the OpenAI chat completions API format, which is supported
    by many LLM providers including Ollama, Groq, Together, and more.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        prompt_template: str | None = None,
        temperature: float = 0.7,
    ):
        """Initialize the provider.

        Args:
            base_url: API base URL (e.g., 'http://localhost:11434/v1' for Ollama).
            api_key: API key (can be empty for local providers like Ollama).
            model: Model name (e.g., 'llama3', 'gpt-4o-mini').
            prompt_template: Optional custom prompt template.
            temperature: LLM temperature (0.0-2.0, higher=more creative).
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.prompt_template = prompt_template or DEFAULT_REWRITE_PROMPT
        self.temperature = temperature

    @property
    def name(self) -> str:
        return "openai"

    def rewrite(
        self,
        title: str,
        body: str,
        max_chars: int,
        platform: str,
        *,
        previous_attempt: str | None = None,
        previous_length: int | None = None,
    ) -> RewriteResult:
        """Generate a short-form rewrite using OpenAI-compatible API."""
        # Truncate body if too long (context limits)
        max_body_chars = 4000
        if len(body) > max_body_chars:
            body = body[:max_body_chars] + "\n\n[Content truncated...]"

        # Format the prompt
        prompt = self.prompt_template.format(
            title=title,
            body=body,
            max_chars=max_chars,
            platform=platform,
        )

        # Add retry feedback if this is a retry attempt
        if previous_length is not None and previous_length > max_chars:
            excess = previous_length - max_chars
            prompt += RETRY_PROMPT_ADDITION.format(
                previous_length=previous_length,
                max_chars=max_chars,
                excess=excess,
            )

        # Make API request
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": self.temperature,
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=60,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise LLMProviderError(f"API request failed: {e}") from e

        try:
            result = response.json()
            text = result["choices"][0]["message"]["content"].strip()
            tokens_used = result.get("usage", {}).get("total_tokens")
        except (KeyError, IndexError) as e:
            raise LLMProviderError(f"Unexpected API response format: {e}") from e

        # Track if we need to truncate
        original_length = len(text)
        was_truncated = False

        # Ensure result fits within limit
        if len(text) > max_chars:
            was_truncated = True
            # Try to truncate at sentence boundary
            truncated = text[:max_chars]
            last_period = truncated.rfind('.')
            last_question = truncated.rfind('?')
            last_exclaim = truncated.rfind('!')
            last_sentence = max(last_period, last_question, last_exclaim)
            if last_sentence > max_chars // 2:
                text = truncated[:last_sentence + 1]
            else:
                text = truncated

        return RewriteResult(
            text=text,
            model=self.model,
            tokens_used=tokens_used,
            was_truncated=was_truncated,
            original_length=original_length if was_truncated else None,
        )
