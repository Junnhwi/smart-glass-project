import io
import os
import unittest
from unittest.mock import patch

from PIL import Image

from src.queue.tasks import process_vision_inference


class _FakeBody:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class _FakeS3Client:
    def __init__(self, payload: bytes, content_type: str = "image/jpeg"):
        self.payload = payload
        self.content_type = content_type

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        return {
            "Body": _FakeBody(self.payload),
            "ContentType": self.content_type,
        }


def _build_test_image_bytes() -> bytes:
    image = Image.new("RGB", (4, 4), color=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


class TaskContractTestCase(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["AWS_S3_BUCKET_NAME"] = "smart-glass-test"
        os.environ["VISION_CAPTION_MODEL"] = "blip-base"
        os.environ["VISION_CAPTION_QUANTIZATION"] = "none"
        os.environ["VISION_CAPTION_DTYPE"] = "float16"
        os.environ.pop("VISION_PROVIDER_METADATA_INCLUDE_RAW", None)

    def tearDown(self) -> None:
        for name in (
            "AWS_S3_BUCKET_NAME",
            "VISION_CAPTION_MODEL",
            "VISION_CAPTION_QUANTIZATION",
            "VISION_CAPTION_DTYPE",
            "VISION_PROVIDER_METADATA_INCLUDE_RAW",
        ):
            os.environ.pop(name, None)

    def test_process_vision_inference_returns_vlm_success_contract(self) -> None:
        with patch(
            "src.queue.tasks.get_s3_client",
            return_value=_FakeS3Client(_build_test_image_bytes()),
        ):
            with patch(
                "src.queue.tasks.generate_caption",
                return_value={
                    "caption": "a wallet is on the desk next to the keyboard",
                    "elapsed_sec": 0.42,
                    "peak_memory_mb": 512.5,
                    "load_time_sec": 1.2,
                    "model_id": "Salesforce/blip-image-captioning-base",
                    "model_key": "blip-base",
                    "device": "cuda",
                    "quantization": "none",
                    "prompt": "a photography of",
                },
            ):
                result = process_vision_inference(
                    image_key="captures/wallet-01.jpg",
                    user_id="user-1",
                    memory_id="mem-1",
                    captured_at="2026-04-04T10:00:00Z",
                    image_url="https://example.com/captures/wallet-01.jpg",
                    request_id="req-123",
                )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["requestId"], "req-123")
        self.assertEqual(result["memoryId"], "mem-1")
        self.assertEqual(result["userId"], "user-1")
        self.assertEqual(result["sourceImage"]["imageKey"], "captures/wallet-01.jpg")
        self.assertEqual(result["sourceImage"]["contentType"], "image/jpeg")
        self.assertEqual(
            result["metadata"]["caption"],
            "a wallet is on the desk next to the keyboard",
        )
        self.assertEqual(result["metadata"]["detectedObjects"], [])
        self.assertEqual(result["metadata"]["tags"], [])
        self.assertEqual(result["metadata"]["positionHint"], "desk 옆")
        self.assertEqual(result["providerMetadata"]["modelKey"], "blip-base")
        self.assertEqual(result["providerMetadata"]["raw"], None)
        self.assertEqual(result["runtime"]["latencySec"], 0.42)
        self.assertEqual(result["runtime"]["peakMemoryMb"], 512.5)

    def test_process_vision_inference_returns_vlm_error_contract(self) -> None:
        with patch(
            "src.queue.tasks.get_s3_client",
            side_effect=RuntimeError("s3 unavailable"),
        ):
            result = process_vision_inference(
                image_key="captures/wallet-01.jpg",
                user_id="user-1",
                memory_id="mem-1",
                request_id="req-err-1",
            )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["requestId"], "req-err-1")
        self.assertEqual(result["errorCode"], "inference_task_error")
        self.assertEqual(result["message"], "s3 unavailable")
        self.assertTrue(result["retryable"])
        self.assertEqual(result["providerMetadata"]["modelKey"], "blip-base")
