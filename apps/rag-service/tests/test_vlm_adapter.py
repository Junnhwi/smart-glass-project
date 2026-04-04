import unittest

from src.ingestion.vlm_adapter import memory_record_from_vlm_result


class VlmAdapterTestCase(unittest.TestCase):
    def test_memory_record_from_vlm_result_maps_stable_fields(self) -> None:
        payload = memory_record_from_vlm_result(
            {
                "status": "success",
                "requestId": "req-1",
                "taskType": "caption",
                "memoryId": "mem-1",
                "userId": "user-1",
                "capturedAt": "2026-04-04T10:00:00Z",
                "sourceImage": {
                    "imageKey": "captures/wallet-01.jpg",
                    "imageUrl": "https://example.com/captures/wallet-01.jpg",
                    "contentType": "image/jpeg",
                },
                "metadata": {
                    "caption": "a wallet is on the desk next to the keyboard",
                    "sceneSummary": "office desk scene",
                    "detectedObjects": ["wallet", "desk", "keyboard"],
                    "tags": ["office"],
                    "ocrText": "todo list",
                    "positionHint": "desk 옆",
                    "location": {"name": "workroom"},
                },
                "providerMetadata": {
                    "modelKey": "blip-base",
                    "raw": {"prompt": "a photography of"},
                },
            }
        )

        self.assertEqual(payload.memory_id, "mem-1")
        self.assertEqual(payload.user_id, "user-1")
        self.assertEqual(payload.image_key, "captures/wallet-01.jpg")
        self.assertEqual(payload.caption, "a wallet is on the desk next to the keyboard")
        self.assertEqual(payload.detected_objects, ["wallet", "desk", "keyboard"])
        self.assertEqual(payload.tags, ["office"])
        self.assertEqual(payload.position_hint, "desk 옆")
        self.assertEqual(payload.scene_summary, None)
        self.assertEqual(payload.ocr_text, None)
        self.assertEqual(payload.location.name, None)

    def test_memory_record_from_vlm_result_rejects_non_success_result(self) -> None:
        with self.assertRaisesRegex(ValueError, "successful VLM inference results"):
            memory_record_from_vlm_result(
                {
                    "status": "error",
                    "requestId": "req-err-1",
                    "userId": "user-1",
                }
            )
