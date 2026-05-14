import json
import logging
import unittest

from src.core.logging import JsonFormatter


class JsonFormatterTestCase(unittest.TestCase):
    def test_formatter_includes_worker_operational_fields(self) -> None:
        record = logging.LogRecord(
            name="src.queue.tasks",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Inference task completed",
            args=(),
            exc_info=None,
        )
        for key, value in {
            "request_id": "req-1",
            "task_name": "process_vision_inference",
            "image_key": "captures/image.jpg",
            "memory_id": "mem-1",
            "user_id": "user-1",
            "model_key": "qwen2.5-vl-7b",
            "model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
            "model_mode": "vlm",
            "quantization": "4bit",
            "dtype_name": "float16",
            "settings_source": "env",
            "soft_time_limit_sec": 120,
            "hard_time_limit_sec": 150,
            "fallback_model_key": "qwen2.5-vl-3b",
            "fallback_triggered": False,
            "latency_sec": 1.25,
            "peak_memory_mb": 2048.0,
        }.items():
            setattr(record, key, value)

        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["request_id"], "req-1")
        self.assertEqual(payload["memory_id"], "mem-1")
        self.assertEqual(payload["model_id"], "Qwen/Qwen2.5-VL-7B-Instruct")
        self.assertEqual(payload["model_mode"], "vlm")
        self.assertEqual(payload["dtype_name"], "float16")
        self.assertEqual(payload["settings_source"], "env")
        self.assertEqual(payload["soft_time_limit_sec"], 120)
        self.assertEqual(payload["hard_time_limit_sec"], 150)
        self.assertEqual(payload["fallback_model_key"], "qwen2.5-vl-3b")
        self.assertFalse(payload["fallback_triggered"])

    def test_formatter_includes_retry_and_failure_fields(self) -> None:
        record = logging.LogRecord(
            name="src.queue.tasks",
            level=logging.WARNING,
            pathname=__file__,
            lineno=20,
            msg="Inference task failed with retryable error, scheduling retry",
            args=(),
            exc_info=None,
        )
        for key, value in {
            "error_code": "storage_access_error",
            "retryable": True,
            "failure_category": "storage",
            "retry_count": 1,
            "max_retries": 2,
            "retry_delay_sec": 20,
        }.items():
            setattr(record, key, value)

        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["error_code"], "storage_access_error")
        self.assertTrue(payload["retryable"])
        self.assertEqual(payload["failure_category"], "storage")
        self.assertEqual(payload["retry_count"], 1)
        self.assertEqual(payload["max_retries"], 2)
        self.assertEqual(payload["retry_delay_sec"], 20)

    def test_formatter_includes_preload_fields(self) -> None:
        record = logging.LogRecord(
            name="src.worker_preload",
            level=logging.INFO,
            pathname=__file__,
            lineno=30,
            msg="Worker model preload completed",
            args=(),
            exc_info=None,
        )
        record.task_name = "worker_preload"
        record.model_key = "blip-base"
        record.model_id = "Salesforce/blip-image-captioning-base"
        record.dtype_name = "float16"
        record.load_time_sec = 1.75

        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["task_name"], "worker_preload")
        self.assertEqual(payload["model_key"], "blip-base")
        self.assertEqual(payload["model_id"], "Salesforce/blip-image-captioning-base")
        self.assertEqual(payload["dtype_name"], "float16")
        self.assertEqual(payload["load_time_sec"], 1.75)


if __name__ == "__main__":
    unittest.main()
