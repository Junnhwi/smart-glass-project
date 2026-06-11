from __future__ import annotations

import unittest
from unittest.mock import patch

from src.database.memory_store import MemoryLocation, MemoryRecord
from src.modules.media.service import (
    MediaAccessService,
    MediaUrlSignerConfigError,
    S3MediaUrlSigner,
)


class FakeS3Client:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.deleted_objects: list[dict[str, object]] = []

    def generate_presigned_url(
        self,
        client_method: str,
        *,
        Params: dict[str, object],
        ExpiresIn: int,
    ) -> str:
        self.calls.append(
            {
                "client_method": client_method,
                "Params": Params,
                "ExpiresIn": ExpiresIn,
            }
        )
        return f"https://signed.example.com/{Params['Key']}?expires={ExpiresIn}"

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.deleted_objects.append({"Bucket": Bucket, "Key": Key})


class FakeMediaRepository:
    def __init__(self, records: list[MemoryRecord]) -> None:
        self.records = records
        self.last_list_args: tuple[str, int | None] | None = None
        self.last_get_args: tuple[str, str] | None = None
        self.last_batch_get_args: tuple[str, tuple[str, ...]] | None = None
        self.health_checked = False

    def list_by_user(
        self,
        user_id: str,
        *,
        limit: int | None = None,
    ) -> list[MemoryRecord]:
        self.last_list_args = (user_id, limit)
        filtered = [record for record in self.records if record.user_id == user_id]
        if isinstance(limit, int) and limit > 0:
            return filtered[:limit]
        return filtered

    def get_by_image_key(self, user_id: str, image_key: str) -> MemoryRecord | None:
        self.last_get_args = (user_id, image_key)
        for record in self.records:
            if record.user_id == user_id and record.image_key == image_key:
                return record
        return None

    def list_by_image_keys(
        self,
        user_id: str,
        image_keys: list[str],
    ) -> list[MemoryRecord]:
        self.last_batch_get_args = (user_id, tuple(image_keys))
        requested = set(image_keys)
        return [
            record
            for record in self.records
            if record.user_id == user_id and record.image_key in requested
        ]

    def check_health(self) -> None:
        self.health_checked = True


class MediaUrlSignerTests(unittest.TestCase):
    def test_sign_get_object_generates_presigned_url(self) -> None:
        client = FakeS3Client()
        signer = S3MediaUrlSigner(
            client=client,
            default_bucket_name="smart-glass-test",
            default_expiration_sec=300,
        )

        result = signer.sign_get_object(
            "captures/user-1/photo.jpg",
            expires_in_sec=180,
        )

        self.assertEqual(result.image_key, "captures/user-1/photo.jpg")
        self.assertEqual(result.expires_in_sec, 180)
        self.assertIn("https://signed.example.com/", result.access_url)
        self.assertEqual(
            client.calls,
            [
                {
                    "client_method": "get_object",
                    "Params": {
                        "Bucket": "smart-glass-test",
                        "Key": "captures/user-1/photo.jpg",
                    },
                    "ExpiresIn": 180,
                }
            ],
        )

    def test_sign_get_object_normalizes_object_key_before_signing(self) -> None:
        client = FakeS3Client()
        signer = S3MediaUrlSigner(
            client=client,
            default_bucket_name="smart-glass-test",
            default_expiration_sec=300,
        )

        result = signer.sign_get_object(" captures//user-1//photo.jpg ")

        self.assertEqual(result.image_key, "captures/user-1/photo.jpg")
        self.assertEqual(
            client.calls[0]["Params"]["Key"],
            "captures/user-1/photo.jpg",
        )

    def test_sign_get_object_rejects_traversal_key(self) -> None:
        signer = S3MediaUrlSigner(
            client=FakeS3Client(),
            default_bucket_name="smart-glass-test",
            default_expiration_sec=300,
        )

        with self.assertRaisesRegex(ValueError, "path traversal"):
            signer.sign_get_object("captures/user-1/../private.jpg")

    def test_sign_get_object_uses_default_expiration(self) -> None:
        client = FakeS3Client()
        signer = S3MediaUrlSigner(
            client=client,
            default_bucket_name="smart-glass-test",
            default_expiration_sec=300,
        )

        result = signer.sign_get_object("captures/user-1/photo.jpg")

        self.assertEqual(result.expires_in_sec, 300)
        self.assertEqual(client.calls[0]["ExpiresIn"], 300)

    def test_sign_get_object_rejects_invalid_expiration(self) -> None:
        signer = S3MediaUrlSigner(
            client=FakeS3Client(),
            default_bucket_name="smart-glass-test",
            default_expiration_sec=300,
        )

        with self.assertRaisesRegex(
            ValueError,
            "expiresInSec must be between 30 and 3600",
        ):
            signer.sign_get_object("captures/user-1/photo.jpg", expires_in_sec=10)

    def test_check_health_requires_bucket_configuration(self) -> None:
        signer = S3MediaUrlSigner(
            client=FakeS3Client(),
            default_expiration_sec=300,
        )

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(MediaUrlSignerConfigError):
                signer.check_health()

    def test_sign_put_object_generates_presigned_upload_url(self) -> None:
        client = FakeS3Client()
        signer = S3MediaUrlSigner(
            client=client,
            default_bucket_name="smart-glass-test",
            default_expiration_sec=300,
        )

        result = signer.sign_put_object(
            "captures/user-1/photo.jpg",
            content_type="image/jpeg",
            expires_in_sec=180,
        )

        self.assertEqual(result.image_key, "captures/user-1/photo.jpg")
        self.assertEqual(result.expires_in_sec, 180)
        self.assertIn("https://signed.example.com/", result.access_url)
        self.assertEqual(
            client.calls,
            [
                {
                    "client_method": "put_object",
                    "Params": {
                        "Bucket": "smart-glass-test",
                        "Key": "captures/user-1/photo.jpg",
                        "ContentType": "image/jpeg",
                    },
                    "ExpiresIn": 180,
                }
            ],
        )

    def test_delete_object_deletes_normalized_object_key(self) -> None:
        client = FakeS3Client()
        signer = S3MediaUrlSigner(
            client=client,
            default_bucket_name="smart-glass-test",
            default_expiration_sec=300,
        )

        deleted_key = signer.delete_object(" captures//user-1//photo.jpg ")

        self.assertEqual(deleted_key, "captures/user-1/photo.jpg")
        self.assertEqual(
            client.deleted_objects,
            [
                {
                    "Bucket": "smart-glass-test",
                    "Key": "captures/user-1/photo.jpg",
                }
            ],
        )

    def test_media_access_service_lists_gallery_items(self) -> None:
        repository = FakeMediaRepository(
            [
                MemoryRecord(
                    memory_id="mem-1",
                    user_id="user-1",
                    image_key="captures/user-1/photo-1.jpg",
                    image_url=None,
                    captured_at="2026-04-17T09:00:00Z",
                    caption="wallet on the desk",
                    scene_summary="desk scene",
                    detected_objects=["wallet"],
                    tags=["desk"],
                    ocr_text=None,
                    note=None,
                    position_hint="desk 위",
                    location=MemoryLocation(name="workspace"),
                ),
                MemoryRecord(
                    memory_id="mem-2",
                    user_id="user-1",
                    image_key="captures/user-1/photo-2.jpg",
                    image_url=None,
                    captured_at="2026-04-17T08:00:00Z",
                    caption="keys beside mug",
                    scene_summary="kitchen scene",
                    detected_objects=["keys"],
                    tags=["kitchen"],
                    ocr_text=None,
                    note=None,
                    position_hint="mug 옆",
                    location=MemoryLocation(name="kitchen"),
                ),
            ]
        )
        service = MediaAccessService(
            repository,
            S3MediaUrlSigner(
                client=FakeS3Client(),
                default_bucket_name="smart-glass-test",
                default_expiration_sec=300,
            ),
            default_gallery_limit=50,
        )

        items = service.list_gallery_items(user_id="user-1", limit=10)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].memory_id, "mem-1")
        self.assertEqual(items[0].image_key, "captures/user-1/photo-1.jpg")
        self.assertEqual(repository.last_list_args, ("user-1", 10))

    def test_media_access_service_validates_ownership_before_signing(self) -> None:
        repository = FakeMediaRepository(
            [
                MemoryRecord(
                    memory_id="mem-1",
                    user_id="user-1",
                    image_key="captures/user-1/photo-1.jpg",
                    image_url=None,
                    captured_at="2026-04-17T09:00:00Z",
                    caption="wallet on the desk",
                    scene_summary="desk scene",
                    detected_objects=["wallet"],
                    tags=["desk"],
                    ocr_text=None,
                    note=None,
                    position_hint="desk 위",
                    location=MemoryLocation(name="workspace"),
                )
            ]
        )
        signer_client = FakeS3Client()
        service = MediaAccessService(
            repository,
            S3MediaUrlSigner(
                client=signer_client,
                default_bucket_name="smart-glass-test",
                default_expiration_sec=300,
            ),
        )

        result = service.issue_access_url(
            user_id="user-1",
            image_key=" captures//user-1//photo-1.jpg ",
            expires_in_sec=180,
        )

        self.assertEqual(result.image_key, "captures/user-1/photo-1.jpg")
        self.assertEqual(repository.last_get_args, ("user-1", "captures/user-1/photo-1.jpg"))
        self.assertEqual(signer_client.calls[0]["ExpiresIn"], 180)

    def test_media_access_service_rejects_non_owned_image(self) -> None:
        service = MediaAccessService(
            FakeMediaRepository([]),
            S3MediaUrlSigner(
                client=FakeS3Client(),
                default_bucket_name="smart-glass-test",
                default_expiration_sec=300,
            ),
        )

        with self.assertRaisesRegex(
            PermissionError,
            "imageKey does not belong to the requested user",
        ):
            service.issue_access_url(
                user_id="user-1",
                image_key="captures/user-2/private.jpg",
            )

    def test_media_access_service_issues_batch_urls_with_single_repository_lookup(self) -> None:
        repository = FakeMediaRepository(
            [
                MemoryRecord(
                    memory_id="mem-1",
                    user_id="user-1",
                    image_key="captures/user-1/photo-1.jpg",
                    image_url=None,
                    captured_at="2026-04-17T09:00:00Z",
                    caption="wallet on the desk",
                    scene_summary="desk scene",
                    detected_objects=["wallet"],
                    tags=["desk"],
                    ocr_text=None,
                    note=None,
                    position_hint="desk 옆",
                    location=MemoryLocation(name="workspace"),
                ),
                MemoryRecord(
                    memory_id="mem-2",
                    user_id="user-1",
                    image_key="captures/user-1/photo-2.jpg",
                    image_url=None,
                    captured_at="2026-04-17T08:00:00Z",
                    caption="keys beside mug",
                    scene_summary="kitchen scene",
                    detected_objects=["keys"],
                    tags=["kitchen"],
                    ocr_text=None,
                    note=None,
                    position_hint="mug 옆",
                    location=MemoryLocation(name="kitchen"),
                ),
            ]
        )
        signer_client = FakeS3Client()
        service = MediaAccessService(
            repository,
            S3MediaUrlSigner(
                client=signer_client,
                default_bucket_name="smart-glass-test",
                default_expiration_sec=300,
            ),
        )

        results = service.issue_access_urls(
            user_id="user-1",
            image_keys=[
                "captures/user-1/photo-1.jpg",
                "captures/user-1/photo-2.jpg",
                "captures/user-1/photo-1.jpg",
            ],
            expires_in_sec=240,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(
            repository.last_batch_get_args,
            (
                "user-1",
                (
                    "captures/user-1/photo-1.jpg",
                    "captures/user-1/photo-2.jpg",
                ),
            ),
        )
        self.assertEqual(len(signer_client.calls), 2)
        self.assertEqual(signer_client.calls[0]["ExpiresIn"], 240)

    def test_media_access_service_deletes_media_object(self) -> None:
        signer_client = FakeS3Client()
        service = MediaAccessService(
            FakeMediaRepository([]),
            S3MediaUrlSigner(
                client=signer_client,
                default_bucket_name="smart-glass-test",
                default_expiration_sec=300,
            ),
        )

        deleted_key = service.delete_media_object(
            image_key=" captures//user-1//photo-1.jpg "
        )

        self.assertEqual(deleted_key, "captures/user-1/photo-1.jpg")
        self.assertEqual(
            signer_client.deleted_objects,
            [
                {
                    "Bucket": "smart-glass-test",
                    "Key": "captures/user-1/photo-1.jpg",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
