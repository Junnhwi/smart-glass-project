import unittest

from src.ingestion.vlm_adapter import memory_record_from_vlm_result


class VlmAdapterTestCase(unittest.TestCase):
    def test_memory_record_from_vlm_result_maps_scene_metadata(self) -> None:
        payload = memory_record_from_vlm_result(
            {
                "status": "success",
                "requestId": "req-1",
                "taskType": "metadata",
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
                    "positionHint": "desk next to the keyboard",
                    "location": None,
                },
                "pipelineOutput": {
                    "scene_summary": "office desk scene",
                    "location_context": "workroom",
                    "objects": [],
                },
                "providerMetadata": {
                    "modelKey": "qwen2.5-vl-3b",
                    "raw": {"prompt": "a photography of"},
                },
            }
        )

        self.assertEqual(payload.memory_id, "mem-1")
        self.assertEqual(payload.user_id, "user-1")
        self.assertEqual(payload.image_key, "captures/wallet-01.jpg")
        self.assertEqual(payload.caption, "a wallet is on the desk next to the keyboard")
        self.assertEqual(payload.scene_summary, "office desk scene")
        self.assertEqual(payload.detected_objects, ["wallet", "desk", "keyboard"])
        self.assertEqual(payload.tags, ["office", "wallet", "desk", "keyboard"])
        self.assertEqual(payload.ocr_text, "todo list")
        self.assertEqual(payload.position_hint, "desk next to the keyboard")
        self.assertEqual(payload.location.name, "workroom")

    def test_memory_record_from_vlm_result_maps_capability_gated_fields_when_supported(
        self,
    ) -> None:
        payload = memory_record_from_vlm_result(
            {
                "status": "success",
                "requestId": "req-2",
                "taskType": "metadata",
                "memoryId": "mem-2",
                "userId": "user-2",
                "capturedAt": "2026-04-04T10:00:00Z",
                "sourceImage": {
                    "imageKey": "captures/desk-01.jpg",
                    "imageUrl": None,
                    "contentType": "image/jpeg",
                },
                "metadata": {
                    "caption": "작업용 책상 장면",
                    "sceneSummary": "작업용 책상 장면",
                    "detectedObjects": ["지갑", "키보드"],
                    "tags": ["지갑", "책상"],
                    "ocrText": "회의 메모",
                    "positionHint": "키보드 옆",
                    "location": {"name": "workroom", "address": "desk area"},
                },
                "providerMetadata": {
                    "modelKey": "qwen2.5-vl-7b",
                    "capabilities": {
                        "caption": True,
                        "positionHint": True,
                        "sceneSummary": True,
                        "detectedObjects": True,
                        "tags": True,
                        "ocrText": False,
                        "location": True,
                        "pipelineOutput": True,
                    },
                },
            }
        )

        self.assertEqual(payload.memory_id, "mem-2")
        self.assertEqual(payload.scene_summary, "작업용 책상 장면")
        self.assertEqual(payload.detected_objects, ["지갑", "키보드"])
        self.assertEqual(payload.tags, ["지갑", "책상"])
        self.assertEqual(payload.position_hint, "키보드 옆")
        self.assertEqual(payload.ocr_text, None)
        self.assertEqual(payload.location.name, "workroom")
        self.assertEqual(payload.location.address, "desk area")

    def test_memory_record_from_vlm_result_rejects_non_success_result(self) -> None:
        with self.assertRaisesRegex(ValueError, "successful VLM inference results"):
            memory_record_from_vlm_result(
                {
                    "status": "error",
                    "requestId": "req-err-1",
                    "userId": "user-1",
                }
            )


if __name__ == "__main__":
    unittest.main()
