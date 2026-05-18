from unittest.mock import patch

from PIL import Image

from src.adapters.ollama_adapter import generate_ollama_vlm_metadata


class _FakeOllamaClient:
    vlm_model = "gemma3:12b"

    def __init__(self):
        self.payload = None

    def send_vlm_input(self, payload):
        self.payload = payload
        return {
            "model": "gemma3:12b",
            "created_at": "2026-05-18T10:19:30Z",
            "message": {
                "role": "assistant",
                "content": (
                    '{"caption":"a desk with earbuds","sceneSummary":"workspace",'
                    '"detectedObjects":["desk","earbuds"],'
                    '"objects":[{"name":"earbuds","positionHint":"on the desk near the laptop",'
                    '"nearbyObjects":["laptop"],"surface":"desk"}],'
                    '"tags":["workspace","electronics"],'
                    '"positionHint":"earbuds on the desk near the laptop"}'
                ),
            },
            "done": True,
            "done_reason": "stop",
        }


def test_generate_ollama_vlm_metadata_uses_chat_vision_payload():
    fake_client = _FakeOllamaClient()

    with patch(
        "src.adapters.ollama_adapter.make_ollama_client",
        return_value=fake_client,
    ):
        result = generate_ollama_vlm_metadata(
            image=Image.new("RGB", (2, 2), color=(255, 255, 255)),
            model_key="blip-base",
        )

    assert fake_client.payload["format"] == "json"
    assert fake_client.payload["stream"] is False
    assert fake_client.payload["messages"][0]["role"] == "user"
    assert fake_client.payload["messages"][0]["images"]
    assert result["model_key"] == "gemma3:12b"
    assert result["provider"] == "ollama"
    assert result["metadata"]["caption"] == "a desk with earbuds"
    assert result["metadata"]["sceneSummary"] == "workspace"
    assert result["metadata"]["detectedObjects"] == ["desk", "earbuds"]
    assert result["metadata"]["tags"] == ["workspace", "electronics"]
    assert result["metadata"]["positionHint"] == "earbuds on the desk near the laptop"
    assert result["pipeline_output"]["objects"] == [
        {
            "object_id": 1,
            "name": "earbuds",
            "position": {
                "hint": "on the desk near the laptop",
                "surface": "desk",
            },
            "nearby_objects": ["laptop"],
        }
    ]
