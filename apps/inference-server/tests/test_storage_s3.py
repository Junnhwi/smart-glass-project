import os
import unittest
from unittest.mock import patch

from botocore.exceptions import BotoCoreError, ClientError

from src.storage.s3 import (
    S3StorageService,
    StorageAccessError,
    StorageConfigError,
    StorageNotFoundError,
)


class _FakeBody:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class _FakeS3Client:
    def __init__(self, *, payload: bytes = b"image-bytes", content_type: str = "image/jpeg"):
        self.payload = payload
        self.content_type = content_type
        self.put_calls: list[dict[str, object]] = []

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        return {
            "Body": _FakeBody(self.payload),
            "ContentType": self.content_type,
        }

    def put_object(self, **kwargs) -> None:
        self.put_calls.append(kwargs)


class _MissingObjectClient:
    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        raise ClientError(
            {
                "Error": {
                    "Code": "NoSuchKey",
                    "Message": "missing object",
                }
            },
            "GetObject",
        )


class _AccessDeniedClient:
    def put_object(self, **kwargs) -> None:
        raise ClientError(
            {
                "Error": {
                    "Code": "AccessDenied",
                    "Message": "denied",
                }
            },
            "PutObject",
        )


class _BrokenClient:
    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        raise BotoCoreError()


class StorageServiceTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        for name in (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_REGION",
            "AWS_S3_BUCKET_NAME",
        ):
            os.environ.pop(name, None)

    def test_read_object_returns_storage_object(self) -> None:
        service = S3StorageService(
            client=_FakeS3Client(payload=b"abc123", content_type="image/png"),
            default_bucket_name="smart-glass-test",
        )

        result = service.read_object("captures/test.png")

        self.assertEqual(result.bucket_name, "smart-glass-test")
        self.assertEqual(result.key, "captures/test.png")
        self.assertEqual(result.body, b"abc123")
        self.assertEqual(result.content_type, "image/png")

    def test_write_object_passes_content_type_to_client(self) -> None:
        client = _FakeS3Client()
        service = S3StorageService(
            client=client,
            default_bucket_name="smart-glass-test",
        )

        service.write_object(
            "captures/test.png",
            b"payload",
            content_type="image/png",
        )

        self.assertEqual(len(client.put_calls), 1)
        self.assertEqual(client.put_calls[0]["Bucket"], "smart-glass-test")
        self.assertEqual(client.put_calls[0]["Key"], "captures/test.png")
        self.assertEqual(client.put_calls[0]["Body"], b"payload")
        self.assertEqual(client.put_calls[0]["ContentType"], "image/png")

    def test_read_object_raises_not_found_for_missing_key(self) -> None:
        service = S3StorageService(
            client=_MissingObjectClient(),
            default_bucket_name="smart-glass-test",
        )

        with self.assertRaises(StorageNotFoundError):
            service.read_object("captures/missing.png")

    def test_write_object_raises_access_error_for_denied_client_error(self) -> None:
        service = S3StorageService(
            client=_AccessDeniedClient(),
            default_bucket_name="smart-glass-test",
        )

        with self.assertRaises(StorageAccessError):
            service.write_object("captures/test.png", b"payload")

    def test_read_object_raises_access_error_for_botocore_failure(self) -> None:
        service = S3StorageService(
            client=_BrokenClient(),
            default_bucket_name="smart-glass-test",
        )

        with self.assertRaises(StorageAccessError):
            service.read_object("captures/test.png")

    def test_service_raises_config_error_when_bucket_is_missing(self) -> None:
        service = S3StorageService(client=_FakeS3Client())

        with self.assertRaises(StorageConfigError):
            service.read_object("captures/test.png")

    def test_service_builds_client_from_env(self) -> None:
        os.environ["AWS_ACCESS_KEY_ID"] = "test-access"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "test-secret"
        os.environ["AWS_REGION"] = "ap-northeast-2"
        os.environ["AWS_S3_BUCKET_NAME"] = "smart-glass-test"

        fake_client = _FakeS3Client()
        with patch("src.storage.s3.boto3.client", return_value=fake_client) as mocked_client:
            service = S3StorageService()
            service.read_object("captures/test.png")

        mocked_client.assert_called_once_with(
            "s3",
            aws_access_key_id="test-access",
            aws_secret_access_key="test-secret",
            region_name="ap-northeast-2",
        )


if __name__ == "__main__":
    unittest.main()
