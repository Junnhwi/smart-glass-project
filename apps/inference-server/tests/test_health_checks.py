import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.health.checks import check_model_config, check_storage
from src.storage.s3 import StorageAccessError


class StorageHealthCheckTestCase(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["AWS_ACCESS_KEY_ID"] = "test-access"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "test-secret"
        os.environ["AWS_S3_BUCKET_NAME"] = "smart-glass-test"
        os.environ["AWS_REGION"] = "ap-northeast-2"

    def tearDown(self) -> None:
        for name in (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_S3_BUCKET_NAME",
            "AWS_REGION",
            "INFERENCE_STORAGE_READINESS_MODE",
            "INFERENCE_SERVING_PROFILE_PATH",
            "VISION_CAPTION_MODEL",
            "VISION_CAPTION_QUANTIZATION",
            "VISION_CAPTION_DTYPE",
        ):
            os.environ.pop(name, None)

    def test_check_storage_skips_probe_in_config_mode(self) -> None:
        os.environ["INFERENCE_STORAGE_READINESS_MODE"] = "config"

        with patch("src.health.checks.get_storage_service") as mocked_service:
            status, detail = check_storage()

        self.assertEqual(status, "ok")
        self.assertEqual(detail["status"], "ok")
        self.assertEqual(detail["mode"], "config")
        self.assertEqual(detail["probe"]["status"], "skipped")
        mocked_service.assert_not_called()

    def test_check_storage_runs_probe_in_deep_mode(self) -> None:
        os.environ["INFERENCE_STORAGE_READINESS_MODE"] = "deep"

        with patch("src.health.checks.get_storage_service") as mocked_service:
            status, detail = check_storage()

        self.assertEqual(status, "ok")
        self.assertEqual(detail["status"], "ok")
        self.assertEqual(detail["mode"], "deep")
        self.assertEqual(detail["probe"]["status"], "ok")
        mocked_service.return_value.probe_bucket_access.assert_called_once_with(
            bucket_name="smart-glass-test"
        )

    def test_check_storage_reports_probe_error_in_deep_mode(self) -> None:
        os.environ["INFERENCE_STORAGE_READINESS_MODE"] = "deep"

        with patch("src.health.checks.get_storage_service") as mocked_service:
            mocked_service.return_value.probe_bucket_access.side_effect = (
                StorageAccessError("bucket unreachable")
            )
            status, detail = check_storage()

        self.assertEqual(status, "error")
        self.assertEqual(detail["status"], "error")
        self.assertEqual(detail["probe"]["status"], "error")
        self.assertIn("bucket unreachable", detail["probe"]["message"])

    def test_check_storage_reports_invalid_mode(self) -> None:
        os.environ["INFERENCE_STORAGE_READINESS_MODE"] = "invalid"

        status, detail = check_storage()

        self.assertEqual(status, "error")
        self.assertEqual(detail["status"], "error")
        self.assertEqual(detail["mode"], "invalid")
        self.assertIn("Unsupported INFERENCE_STORAGE_READINESS_MODE", detail["message"])

    def test_check_storage_skips_probe_when_config_is_missing(self) -> None:
        os.environ.pop("AWS_S3_BUCKET_NAME", None)
        os.environ["INFERENCE_STORAGE_READINESS_MODE"] = "deep"

        with patch("src.health.checks.get_storage_service") as mocked_service:
            status, detail = check_storage()

        self.assertEqual(status, "error")
        self.assertEqual(detail["status"], "error")
        self.assertEqual(detail["probe"]["status"], "skipped")
        mocked_service.assert_not_called()

    def test_check_model_config_reports_profile_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            profile_path = Path(tmp_dir) / "serving-profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "profile_type": "caption_serving_profile",
                        "generated_at_utc": "2026-04-08T00:00:00Z",
                        "default": {
                            "model_key": "blip-base",
                            "quantization": "none",
                            "dtype_name": "float16",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ",
                {"INFERENCE_SERVING_PROFILE_PATH": str(profile_path)},
                clear=True,
            ):
                status, detail = check_model_config()

        self.assertEqual(status, "ok")
        self.assertEqual(detail["status"], "ok")
        self.assertEqual(detail["source"], "profile")
        self.assertEqual(detail["model_key"], "blip-base")
        self.assertEqual(detail["profile_path"], str(profile_path))


if __name__ == "__main__":
    unittest.main()
