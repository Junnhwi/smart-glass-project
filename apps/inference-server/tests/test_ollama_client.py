import pytest

from src.clients.ollama_client import OllamaClient


def test_make_client():
    # Ensure client can be instantiated with default settings
    c = OllamaClient()
    assert c is not None
