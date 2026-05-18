import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Any, Dict, Optional

from ..utils.config import Settings

logger = logging.getLogger(__name__)


def _build_session_with_retries(settings: Settings) -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=max(0, settings.ollama_retry_count),
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    if settings.ollama_api_key:
        session.headers.update({"Authorization": f"Bearer {settings.ollama_api_key}"})
    session.headers.update({"Content-Type": "application/json"})
    return session


class OllamaClient:
    """Ollama Cloud client wrapper with retries and simple error mapping."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        self.base_url = (self.settings.ollama_api_url or "").rstrip("/")
        self.timeout = self.settings.ollama_timeout_sec
        self.vlm_model = self.settings.ollama_vlm_model
        self.session = _build_session_with_retries(self.settings)

    def send_vlm_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/chat"
        payload = {"model": self.vlm_model, **payload}
        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.exception("Ollama request failed: %s", e)
            # Re-raise to allow upstream retry logic
            raise


def make_ollama_client() -> OllamaClient:
    return OllamaClient()
