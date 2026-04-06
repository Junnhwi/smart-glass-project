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
            "VISION_QWEN_FALLBACK_MODEL",
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
        self.assertEqual(result["metadata"]["positionHint"], "keyboard 옆")
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

    def test_process_vision_inference_routes_qwen_vlm_metadata_to_contract(self) -> None:
        os.environ["VISION_CAPTION_MODEL"] = "qwen2.5-vl-7b"
        os.environ["VISION_CAPTION_QUANTIZATION"] = "4bit"

        with patch(
            "src.queue.tasks.get_s3_client",
            return_value=_FakeS3Client(_build_test_image_bytes()),
        ):
            with patch(
                "src.queue.tasks.generate_qwen_vlm_metadata",
                return_value={
                    "metadata": {
                        "caption": "지갑이 키보드 옆 책상 위에 놓여 있다",
                        "sceneSummary": "작업용 책상 장면",
                        "detectedObjects": ["지갑", "키보드"],
                        "tags": ["지갑", "키보드", "책상"],
                        "ocrText": None,
                        "positionHint": "키보드 옆",
                        "location": None,
                    },
                    "pipeline_output": {
                        "capture_id": "capture-1",
                        "timestamp": "2026-04-06T14:00:00",
                        "image_path": None,
                        "sharpness_score": 123.45,
                        "inference_time": 1.17,
                        "scene_summary": "작업용 책상 장면",
                        "location_context": "사무실",
                        "objects": [
                            {
                                "object_id": 1,
                                "name": "지갑",
                                "confidence": 0.8,
                                "position": {
                                    "depth_hint": "near",
                                    "surface": "책상 위",
                                },
                                "visual_features": {
                                    "color": "검정",
                                    "material": "가죽",
                                    "brand": None,
                                    "shape": "직사각형",
                                },
                                "nearby_objects": ["키보드"],
                                "raw_description_ko": "키보드 옆 지갑",
                            }
                        ],
                        "pipeline_meta": {
                            "vlm_model": "Qwen/Qwen2.5-VL-7B-Instruct",
                            "object_count": 1,
                            "vram_allocated_gb": 5.2,
                            "vram_peak_gb": 5.4,
                            "vram_total_gb": 8.0,
                        },
                    },
                    "elapsed_sec": 1.17,
                    "peak_memory_mb": 2048.0,
                    "load_time_sec": 8.5,
                    "model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
                    "model_key": "qwen2.5-vl-7b",
                    "device": "cuda",
                    "quantization": "4bit",
                    "prompt": "structured prompt",
                    "system_prompt": "system",
                    "raw_output_text": "{\"caption\":\"지갑이 키보드 옆 책상 위에 놓여 있다\"}",
                },
            ):
                result = process_vision_inference(
                    image_key="captures/wallet-02.jpg",
                    user_id="user-2",
                    memory_id="mem-2",
                    request_id="req-qwen-1",
                )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["requestId"], "req-qwen-1")
        self.assertEqual(result["metadata"]["caption"], "지갑이 키보드 옆 책상 위에 놓여 있다")
        self.assertEqual(result["metadata"]["sceneSummary"], "작업용 책상 장면")
        self.assertEqual(result["metadata"]["detectedObjects"], ["지갑", "키보드"])
        self.assertEqual(result["metadata"]["positionHint"], "키보드 옆")
        self.assertEqual(result["pipelineOutput"]["capture_id"], "capture-1")
        self.assertEqual(result["pipelineOutput"]["objects"][0]["name"], "지갑")
        self.assertEqual(result["providerMetadata"]["modelKey"], "qwen2.5-vl-7b")
        self.assertEqual(result["providerMetadata"]["modelFamily"], "qwen2_5_vl")
        self.assertEqual(result["runtime"]["peakMemoryMb"], 2048.0)

    def test_process_vision_inference_retries_with_qwen_fallback_model(self) -> None:
        os.environ["VISION_CAPTION_MODEL"] = "qwen2.5-vl-7b"
        os.environ["VISION_CAPTION_QUANTIZATION"] = "4bit"
        os.environ["VISION_QWEN_FALLBACK_MODEL"] = "qwen2.5-vl-3b"

        with patch(
            "src.queue.tasks.get_s3_client",
            return_value=_FakeS3Client(_build_test_image_bytes()),
        ):
            with patch(
                "src.queue.tasks.generate_qwen_vlm_metadata",
                side_effect=[
                    RuntimeError("CUDA out of memory"),
                    {
                        "metadata": {
                            "caption": "맥북과 아이폰이 책상 위에 있다",
                            "sceneSummary": "전자기기 책상 장면",
                            "detectedObjects": ["맥북", "아이폰"],
                            "tags": ["맥북", "아이폰", "책상 위"],
                            "ocrText": None,
                            "positionHint": "책상 위",
                            "location": None,
                        },
                        "pipeline_output": {
                            "capture_id": "capture-fallback",
                            "timestamp": "2026-04-06T14:00:00",
                            "image_path": None,
                            "sharpness_score": 111.0,
                            "inference_time": 2.34,
                            "scene_summary": "전자기기 책상 장면",
                            "location_context": "작업 공간",
                            "objects": [],
                            "pipeline_meta": {
                                "vlm_model": "Qwen/Qwen2.5-VL-3B-Instruct",
                                "object_count": 0,
                                "vram_allocated_gb": 3.0,
                                "vram_peak_gb": 3.2,
                                "vram_total_gb": 8.0,
                            },
                        },
                        "elapsed_sec": 2.34,
                        "peak_memory_mb": 1536.0,
                        "load_time_sec": 12.0,
                        "model_id": "Qwen/Qwen2.5-VL-3B-Instruct",
                        "model_key": "qwen2.5-vl-3b",
                        "device": "cuda",
                        "quantization": "4bit",
                        "prompt": "structured prompt",
                        "system_prompt": "system",
                        "raw_output_text": "{\"caption\":\"맥북과 아이폰이 책상 위에 있다\"}",
                    },
                ],
            ) as mocked_generate:
                result = process_vision_inference(
                    image_key="captures/desk-01.jpg",
                    user_id="user-3",
                    request_id="req-qwen-fallback-1",
                )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["providerMetadata"]["modelKey"], "qwen2.5-vl-3b")
        self.assertEqual(result["metadata"]["detectedObjects"], ["맥북", "아이폰"])
        self.assertEqual(result["pipelineOutput"]["capture_id"], "capture-fallback")
        self.assertEqual(mocked_generate.call_count, 2)
        self.assertEqual(mocked_generate.call_args_list[0].kwargs["model_key"], "qwen2.5-vl-7b")
        self.assertEqual(mocked_generate.call_args_list[1].kwargs["model_key"], "qwen2.5-vl-3b")
