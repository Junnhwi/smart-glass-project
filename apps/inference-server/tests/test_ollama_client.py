import importlib

import pytest

from src.clients import ollama_client
from src.utils import config


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": "{}"}}


class _FakeSession:
    def __init__(self):
        self.calls = []
        self.headers = {}

    def post(self, url, *, json, timeout):  # noqa: A002
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return _FakeResponse()


def test_make_client():
    # Ensure client can be instantiated with default settings
    c = ollama_client.OllamaClient()
    assert c is not None


def test_client_uses_api_llm_ollama_env_as_fallback(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_URL", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_TIMEOUT_SEC", raising=False)
    monkeypatch.setenv("API_LLM_OLLAMA_BASE_URL", "https://ollama.com/api")
    monkeypatch.setenv("API_LLM_OLLAMA_API_KEY", "test-ollama-key")
    monkeypatch.setenv("API_LLM_OLLAMA_TIMEOUT_SEC", "17")

    importlib.reload(config)
    importlib.reload(ollama_client)

    c = ollama_client.OllamaClient()

    assert c.base_url == "https://ollama.com/api"
    assert c.timeout == 17
    assert c.vlm_model == "gemma3:12b"
    assert c.session.headers["Authorization"] == "Bearer test-ollama-key"


def test_client_posts_vlm_payload_to_chat_endpoint(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_URL", "https://ollama.com/api")
    monkeypatch.setenv("OLLAMA_VLM_MODEL", "gemma3:4b")
    importlib.reload(config)
    importlib.reload(ollama_client)

    c = ollama_client.OllamaClient()
    fake_session = _FakeSession()
    c.session = fake_session

    result = c.send_vlm_input(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Describe the image.",
                    "images": ["base64-image"],
                }
            ],
            "format": "json",
            "stream": False,
        }
    )

    assert result == {"message": {"content": "{}"}}
    assert fake_session.calls == [
        {
            "url": "https://ollama.com/api/chat",
            "json": {
                "model": "gemma3:4b",
                "messages": [
                    {
                        "role": "user",
                        "content": "Describe the image.",
                        "images": ["base64-image"],
                    }
                ],
                "format": "json",
                "stream": False,
            },
            "timeout": c.timeout,
        }
    ]
