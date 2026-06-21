# model_client.py
"""
Model abstraction layer for switching between Anthropic API and local models.
Supports Anthropic, Ollama, and llama.cpp backends.
"""

import base64
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
import anthropic
import requests
import json


class ModelResponse:
    """Standardized response format across all model backends"""

    def __init__(self, text: str, input_tokens: int = 0, output_tokens: int = 0, model: str = ""):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model


class BaseModelClient(ABC):
    """Base class for all model clients"""

    @abstractmethod
    def generate_text(self, prompt: str, max_tokens: int = 1024) -> ModelResponse:
        """Generate text from a text prompt"""
        pass

    @abstractmethod
    def generate_vision(
        self,
        prompt: str,
        image_data: str,
        media_type: str = "image/jpeg",
        max_tokens: int = 1024
    ) -> ModelResponse:
        """Generate text from image + text prompt"""
        pass


class AnthropicClient(BaseModelClient):
    """Anthropic API client"""

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: Optional[str] = None):
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def generate_text(self, prompt: str, max_tokens: int = 1024) -> ModelResponse:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

        return ModelResponse(
            text=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self.model
        )

    def generate_vision(
        self,
        prompt: str,
        image_data: str,
        media_type: str = "image/jpeg",
        max_tokens: int = 1024
    ) -> ModelResponse:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                    {"type": "text", "text": prompt}
                ]
            }]
        )

        return ModelResponse(
            text=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self.model
        )


class OpenRouterClient(BaseModelClient):
    """OpenRouter API client — routes to 300+ models via OpenAI-compatible API."""

    OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, model: str = "openai/gpt-oss-120b", api_key: Optional[str] = None):
        import os
        self.model = model
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in environment or provided")

    def _call(self, messages: List[Dict[str, Any]], max_tokens: int = 1024) -> ModelResponse:
        import httpx
        response = httpx.post(
            self.OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Title": "Valkyrie Overseer",
            },
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": messages,
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage", {})
        return ModelResponse(
            text=data["choices"][0]["message"]["content"],
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            model=self.model,
        )

    def generate_text(self, prompt: str, max_tokens: int = 1024) -> ModelResponse:
        return self._call([{"role": "user", "content": prompt}], max_tokens)

    def generate_vision(
        self,
        prompt: str,
        image_data: str,
        media_type: str = "image/jpeg",
        max_tokens: int = 1024
    ) -> ModelResponse:
        return self._call([{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_data}"}},
                {"type": "text", "text": prompt},
            ],
        }], max_tokens)


class OllamaClient(BaseModelClient):
    """Ollama local model client"""

    def __init__(self, model: str = "llama3.2-vision", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.api_url = f"{base_url}/api/generate"
        self.chat_url = f"{base_url}/api/chat"

    def generate_text(self, prompt: str, max_tokens: int = 1024) -> ModelResponse:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens
            }
        }

        response = requests.post(self.api_url, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()

        return ModelResponse(
            text=data.get("response", ""),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            model=self.model
        )

    def generate_vision(
        self,
        prompt: str,
        image_data: str,
        media_type: str = "image/jpeg",
        max_tokens: int = 1024
    ) -> ModelResponse:
        """
        Ollama vision support requires a vision-capable model like llama3.2-vision
        """
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_data]  # Ollama expects base64 image data
                }
            ],
            "stream": False,
            "options": {
                "num_predict": max_tokens
            }
        }

        response = requests.post(self.chat_url, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()

        message = data.get("message", {})
        return ModelResponse(
            text=message.get("content", ""),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            model=self.model
        )


class LlamaCppClient(BaseModelClient):
    """llama.cpp server client (for llava models with vision support)"""

    def __init__(self, model: str = "llava", base_url: str = "http://localhost:8080"):
        self.model = model
        self.base_url = base_url
        self.completion_url = f"{base_url}/completion"

    def generate_text(self, prompt: str, max_tokens: int = 1024) -> ModelResponse:
        payload = {
            "prompt": prompt,
            "n_predict": max_tokens,
            "temperature": 0.7,
        }

        response = requests.post(self.completion_url, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()

        return ModelResponse(
            text=data.get("content", ""),
            input_tokens=data.get("tokens_evaluated", 0),
            output_tokens=data.get("tokens_predicted", 0),
            model=self.model
        )

    def generate_vision(
        self,
        prompt: str,
        image_data: str,
        media_type: str = "image/jpeg",
        max_tokens: int = 1024
    ) -> ModelResponse:
        """
        llama.cpp with llava support
        Image should be base64 encoded
        """
        payload = {
            "prompt": prompt,
            "image_data": [{"data": image_data, "id": 0}],
            "n_predict": max_tokens,
            "temperature": 0.7,
        }

        response = requests.post(self.completion_url, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()

        return ModelResponse(
            text=data.get("content", ""),
            input_tokens=data.get("tokens_evaluated", 0),
            output_tokens=data.get("tokens_predicted", 0),
            model=self.model
        )


def create_model_client(
    backend: str = "anthropic",
    model: Optional[str] = None,
    **kwargs
) -> BaseModelClient:
    """
    Factory function to create the appropriate model client.

    Args:
        backend: One of "anthropic", "ollama", "llamacpp"
        model: Model name (defaults vary by backend)
        **kwargs: Additional backend-specific arguments

    Returns:
        BaseModelClient instance

    Examples:
        # Anthropic
        client = create_model_client("anthropic", model="claude-sonnet-4-6")

        # Ollama
        client = create_model_client("ollama", model="llama3.2-vision")

        # llama.cpp
        client = create_model_client("llamacpp", base_url="http://localhost:8080")
    """
    backend = backend.lower()

    if backend == "openrouter":
        default_model = "openai/gpt-oss-120b"
        return OpenRouterClient(model=model or default_model, **kwargs)

    elif backend == "anthropic":
        default_model = "claude-sonnet-4-6"
        return AnthropicClient(model=model or default_model, **kwargs)

    elif backend == "ollama":
        default_model = "llama3.2-vision"
        return OllamaClient(model=model or default_model, **kwargs)

    elif backend == "llamacpp":
        default_model = "llava"
        return LlamaCppClient(model=model or default_model, **kwargs)

    else:
        raise ValueError(f"Unknown backend: {backend}. Choose from: anthropic, ollama, llamacpp")


# Example usage:
if __name__ == "__main__":
    # Test with Anthropic (requires ANTHROPIC_API_KEY)
    print("Testing Anthropic client...")
    try:
        client = create_model_client("anthropic")
        response = client.generate_text("What is 2+2?", max_tokens=100)
        print(f"Response: {response.text}")
        print(f"Tokens: {response.input_tokens} in, {response.output_tokens} out")
    except Exception as e:
        print(f"Anthropic test failed: {e}")

    # Test with Ollama (requires Ollama running locally)
    print("\nTesting Ollama client...")
    try:
        client = create_model_client("ollama", model="llama3.2")
        response = client.generate_text("What is 2+2?", max_tokens=100)
        print(f"Response: {response.text}")
        print(f"Tokens: {response.input_tokens} in, {response.output_tokens} out")
    except Exception as e:
        print(f"Ollama test failed: {e}")
