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

from .provider import LLMProvider, LLMProviderError, RewriteResult, DEFAULT_REWRITE_PROMPT


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
    ):
        """Initialize the provider.

        Args:
            base_url: API base URL (e.g., 'http://localhost:11434/v1' for Ollama).
            api_key: API key (can be empty for local providers like Ollama).
            model: Model name (e.g., 'llama3', 'gpt-4o-mini').
            prompt_template: Optional custom prompt template.
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.prompt_template = prompt_template or DEFAULT_REWRITE_PROMPT

    @property
    def name(self) -> str:
        return "openai"

    def rewrite(
        self,
        title: str,
        body: str,
        max_chars: int,
        platform: str,
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
            "max_tokens": max_chars * 2,  # Allow room for the response
            "temperature": 0.7,
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

        # Ensure result fits within limit
        if len(text) > max_chars:
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
        )
