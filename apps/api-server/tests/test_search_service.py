from __future__ import annotations

import unittest

from src.database.memory_store import MemoryLocation, MemoryRecord
from src.modules.search.service import MemoryQueryService
from src.modules.search.text import format_timestamp


class FakeMemoryRepository:
    def __init__(self, records: list[MemoryRecord]) -> None:
        self.records = records
        self.last_user_id: str | None = None
        self.last_limit: int | None = None
        self.health_checked = False

    def list_by_user(self, user_id: str, *, limit: int | None = None) -> list[MemoryRecord]:
        self.last_user_id = user_id
        self.last_limit = limit
        return [record for record in self.records if record.user_id == user_id]

    def check_health(self) -> None:
        self.health_checked = True


class MemoryQueryServiceTests(unittest.TestCase):
    def test_format_timestamp_uses_korean_ampm_time(self) -> None:
        self.assertEqual(
            format_timestamp("2026-04-30T09:00:00Z"),
            "2026-04-30 \uc624\uc804 9\uc2dc",
        )
        self.assertEqual(
            format_timestamp("2026-04-30T12:00:00Z"),
            "2026-04-30 \uc624\ud6c4 12\uc2dc",
        )
        self.assertEqual(
            format_timestamp("2026-04-30T15:30:00Z"),
            "2026-04-30 \uc624\ud6c4 3\uc2dc 30\ubd84",
        )

    def test_search_ranks_matching_record(self) -> None:
        repository = FakeMemoryRepository(
            [
                MemoryRecord(
                    memory_id="mem-wallet-01",
                    user_id="user-1",
                    image_key="captures/wallet-01.jpg",
                    image_url=None,
                    captured_at="2026-04-17T09:00:00Z",
                    caption="wallet on the desk next to the keyboard",
                    scene_summary="workspace desk scene",
                    detected_objects=["wallet", "desk", "keyboard"],
                    tags=["office"],
                    ocr_text=None,
                    note=None,
                    position_hint="keyboard 옆",
                    location=MemoryLocation(name="workspace"),
                ),
                MemoryRecord(
                    memory_id="mem-umbrella-01",
                    user_id="user-1",
                    image_key="captures/umbrella-01.jpg",
                    image_url=None,
                    captured_at="2026-04-17T08:00:00Z",
                    caption="umbrella leaning against sofa",
                    scene_summary="living room scene",
                    detected_objects=["umbrella", "sofa"],
                    tags=["living-room"],
                    ocr_text=None,
                    note=None,
                    position_hint="sofa 옆",
                    location=MemoryLocation(name="living room"),
                ),
            ]
        )
        service = MemoryQueryService(repository)

        hits = service.search("user-1", "\ub0b4 \uc9c0\uac11 \uc5b4\ub514\uc5d0 \uc788\uc5c8\uc9c0?", 3)

        self.assertEqual(repository.last_user_id, "user-1")
        self.assertEqual(repository.last_limit, 40)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].memory.memory_id, "mem-wallet-01")
        self.assertIn("wallet", hits[0].matched_terms)

    def test_search_handles_korean_particle_query(self) -> None:
        repository = FakeMemoryRepository(
            [
                MemoryRecord(
                    memory_id="mem-umbrella-01",
                    user_id="user-2",
                    image_key="captures/umbrella-01.jpg",
                    image_url=None,
                    captured_at="2026-04-17T08:00:00Z",
                    caption="umbrella leaning against sofa",
                    scene_summary=None,
                    detected_objects=["umbrella", "sofa"],
                    tags=["living-room"],
                    ocr_text=None,
                    note=None,
                    position_hint="sofa 옆",
                    location=MemoryLocation(name="living room"),
                ),
            ]
        )
        service = MemoryQueryService(repository)

        hits = service.search("user-2", "\uc6b0\uc0b0\uc740 \uc5b4\ub514\uc5d0?", 3)

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].memory.memory_id, "mem-umbrella-01")
        self.assertIn("umbrella", hits[0].matched_terms)

    def test_search_matches_earbuds_aliases_and_ignores_question_fillers(self) -> None:
        repository = FakeMemoryRepository(
            [
                MemoryRecord(
                    memory_id="mem-earbuds-01",
                    user_id="user-4",
                    image_key="captures/earbuds-01.jpg",
                    image_url=None,
                    captured_at="2026-04-30T09:00:00Z",
                    caption="earbuds on the desk next to the laptop",
                    scene_summary="workspace desk scene with earbuds",
                    detected_objects=["earbuds", "desk", "laptop"],
                    tags=["workspace"],
                    ocr_text=None,
                    note=None,
                    position_hint="next to laptop",
                    location=MemoryLocation(name="workspace"),
                ),
                MemoryRecord(
                    memory_id="mem-wallet-01",
                    user_id="user-4",
                    image_key="captures/wallet-01.jpg",
                    image_url=None,
                    captured_at="2026-04-30T08:00:00Z",
                    caption="wallet inside the drawer",
                    scene_summary="drawer scene",
                    detected_objects=["wallet", "drawer"],
                    tags=["workspace"],
                    ocr_text=None,
                    note=None,
                    position_hint="inside drawer",
                    location=MemoryLocation(name="workspace"),
                ),
            ]
        )
        service = MemoryQueryService(repository)

        queries = [
            "\ub0b4 \uc5d0\uc5b4\ud31f \uc5b4\ub514\ub2e4 \ub1a8\ub354\ub77c?",
            "\ubc84\uc988 \ucc3e\uc544\uc918",
            "\ubb34\uc120\uc774\uc5b4\ud3f0 \uc5b4\ub514\uc5d0 \uc788\uc5b4?",
        ]

        for query in queries:
            with self.subTest(query=query):
                hits = service.search("user-4", query, 3)
                self.assertGreaterEqual(len(hits), 1)
                self.assertEqual(hits[0].memory.memory_id, "mem-earbuds-01")
                self.assertIn("earbuds", hits[0].matched_terms)

    def test_search_uses_term_after_negative_cue(self) -> None:
        repository = FakeMemoryRepository(
            [
                MemoryRecord(
                    memory_id="mem-earbuds-01",
                    user_id="user-5",
                    image_key="captures/earbuds-01.jpg",
                    image_url=None,
                    captured_at="2026-04-30T09:00:00Z",
                    caption="earbuds on the desk next to the laptop",
                    scene_summary=None,
                    detected_objects=["earbuds", "desk", "laptop"],
                    tags=["workspace"],
                    ocr_text=None,
                    note=None,
                    position_hint="next to laptop",
                    location=MemoryLocation(name="workspace"),
                ),
                MemoryRecord(
                    memory_id="mem-wallet-01",
                    user_id="user-5",
                    image_key="captures/wallet-01.jpg",
                    image_url=None,
                    captured_at="2026-04-30T08:00:00Z",
                    caption="wallet inside the drawer",
                    scene_summary=None,
                    detected_objects=["wallet", "drawer"],
                    tags=["workspace"],
                    ocr_text=None,
                    note=None,
                    position_hint="inside drawer",
                    location=MemoryLocation(name="workspace"),
                ),
            ]
        )
        service = MemoryQueryService(repository)

        hits = service.search(
            "user-5",
            "\uc774\uc5b4\ud3f0 \ub9d0\uace0 \uc9c0\uac11 \uc5b4\ub514 \uc788\uc5b4?",
            3,
        )

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].memory.memory_id, "mem-wallet-01")
        self.assertIn("wallet", hits[0].matched_terms)

    def test_chat_answer_mentions_object_position_and_time(self) -> None:
        repository = FakeMemoryRepository(
            [
                MemoryRecord(
                    memory_id="mem-earbuds-01",
                    user_id="user-6",
                    image_key="captures/earbuds-01.jpg",
                    image_url=None,
                    captured_at="2026-04-30T09:00:00Z",
                    caption="earbuds on the desk next to the laptop",
                    scene_summary="workspace desk scene with earbuds",
                    detected_objects=["earbuds", "desk", "laptop"],
                    tags=["workspace"],
                    ocr_text=None,
                    note=None,
                    position_hint="next to laptop",
                    location=MemoryLocation(name="workspace"),
                ),
            ]
        )
        service = MemoryQueryService(repository)

        answer, hits = service.chat(
            "user-6",
            "\ub0b4 \uc5d0\uc5b4\ud31f \uc5b4\ub514\ub2e4 \ub1a8\ub354\ub77c?",
            3,
        )

        self.assertEqual(len(hits), 1)
        self.assertIn("\ucc3e\uc73c\uc2e0 \uc774\uc5b4\ud3f0\uc740", answer.text)
        self.assertIn("\ub178\ud2b8\ubd81 \uc606", answer.text)
        self.assertIn(
            "\ub9c8\uc9c0\ub9c9 \ud655\uc778 \uc2dc\uac01\uc740 2026-04-30 \uc624\uc804 9\uc2dc\uc785\ub2c8\ub2e4.",
            answer.text,
        )

    def test_chat_falls_back_to_template_when_no_hits(self) -> None:
        service = MemoryQueryService(FakeMemoryRepository([]))

        answer, hits = service.chat("user-3", "\uc9c0\uac11 \uc5b4\ub514 \uc788\uc5c8\uc5b4?", 3)

        self.assertEqual(hits, [])
        self.assertEqual(answer.mode, "template")
        self.assertEqual(answer.cited_memory_ids, [])
        self.assertIn("\uba54\ubaa8\ub9ac", answer.text)

    def test_check_health_delegates_to_repository(self) -> None:
        repository = FakeMemoryRepository([])
        service = MemoryQueryService(repository)

        service.check_health()

        self.assertTrue(repository.health_checked)

    def test_recent_memories_uses_repository_order(self) -> None:
        records = [
            MemoryRecord(
                memory_id="mem-recent-01",
                user_id="user-7",
                image_key="captures/recent-01.jpg",
                image_url=None,
                captured_at="2026-05-01T08:00:00Z",
                caption="wallet on shelf",
                scene_summary=None,
                detected_objects=["wallet"],
                tags=["home"],
                ocr_text=None,
                note=None,
                position_hint="on shelf",
                location=MemoryLocation(name="bedroom"),
            ),
            MemoryRecord(
                memory_id="mem-recent-02",
                user_id="user-7",
                image_key="captures/recent-02.jpg",
                image_url=None,
                captured_at="2026-05-02T08:00:00Z",
                caption="earbuds on desk",
                scene_summary=None,
                detected_objects=["earbuds"],
                tags=["workspace"],
                ocr_text=None,
                note=None,
                position_hint="on desk",
                location=MemoryLocation(name="workspace"),
            ),
        ]
        repository = FakeMemoryRepository(records)
        service = MemoryQueryService(repository, default_top_k=5)

        items = service.recent_memories("user-7", 10)

        self.assertEqual(repository.last_user_id, "user-7")
        self.assertEqual(repository.last_limit, 10)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].memory_id, "mem-recent-01")


if __name__ == "__main__":
    unittest.main()
