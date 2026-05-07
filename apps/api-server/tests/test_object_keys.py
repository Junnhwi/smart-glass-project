from __future__ import annotations

import unittest

from src.modules.media.object_keys import (
    build_capture_object_key,
    normalize_capture_object_key_for_user,
    normalize_storage_object_key,
    object_key_file_name,
)


class ObjectKeyPolicyTests(unittest.TestCase):
    def test_build_capture_object_key_uses_canonical_capture_structure(self) -> None:
        key = build_capture_object_key(
            user_id="user 1",
            captured_at="2026-04-17T09:30:00Z",
            capture_id="capture 001",
            file_name="smart glass photo.jpg",
        )

        self.assertEqual(
            key,
            "captures/user-1/2026/04/17/capture-001-smart-glass-photo.jpg",
        )

    def test_normalize_storage_object_key_collapses_slashes(self) -> None:
        key = normalize_storage_object_key(" captures//user-1//photo.jpg ")

        self.assertEqual(key, "captures/user-1/photo.jpg")

    def test_normalize_storage_object_key_rejects_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a URL"):
            normalize_storage_object_key(
                "https://storage.example.com/captures/user-1/photo.jpg"
            )

    def test_normalize_storage_object_key_rejects_absolute_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "relative object key"):
            normalize_storage_object_key("/captures/user-1/photo.jpg")

    def test_normalize_storage_object_key_rejects_traversal(self) -> None:
        with self.assertRaisesRegex(ValueError, "path traversal"):
            normalize_storage_object_key("captures/user-1/../private.jpg")

    def test_normalize_storage_object_key_rejects_control_characters(self) -> None:
        with self.assertRaisesRegex(ValueError, "control characters"):
            normalize_storage_object_key("captures/user-1/photo\x00.jpg")

    def test_normalize_capture_object_key_for_user_allows_user_prefix(self) -> None:
        key = normalize_capture_object_key_for_user(
            " captures//user-1//photo.jpg ",
            user_id="user 1",
        )

        self.assertEqual(key, "captures/user-1/photo.jpg")

    def test_normalize_capture_object_key_for_user_rejects_cross_user_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "requesting user's captures prefix"):
            normalize_capture_object_key_for_user(
                "captures/user-2/private.jpg",
                user_id="user-1",
            )

    def test_normalize_capture_object_key_for_user_rejects_non_capture_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "requesting user's captures prefix"):
            normalize_capture_object_key_for_user(
                "private/photo.jpg",
                user_id="user-1",
            )

    def test_object_key_file_name_returns_last_segment(self) -> None:
        self.assertEqual(
            object_key_file_name("captures/user-1/2026/04/17/photo.jpg"),
            "photo.jpg",
        )


if __name__ == "__main__":
    unittest.main()
