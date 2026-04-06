import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.main import app


class ApiTaskRoutesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_enqueue_vision_inference_returns_task_id(self) -> None:
        fake_async_result = MagicMock()
        fake_async_result.id = "task-123"
        fake_async_result.state = "PENDING"

        with patch(
            "src.api.tasks.process_vision_inference.apply_async",
            return_value=fake_async_result,
        ):
            response = self.client.post(
                "/tasks/vision",
                json={
                    "imageKey": "captures/test.png",
                    "userId": "user-1",
                    "requestId": "req-1",
                    "taskType": "metadata",
                },
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["taskId"], "task-123")
        self.assertEqual(response.json()["requestId"], "req-1")

    def test_get_task_returns_completed_payload(self) -> None:
        fake_async_result = MagicMock()
        fake_async_result.state = "SUCCESS"
        fake_async_result.ready.return_value = True
        fake_async_result.successful.return_value = True
        fake_async_result.failed.return_value = False
        fake_async_result.result = {"status": "success", "requestId": "req-1"}

        with patch(
            "src.api.tasks.celery_app.AsyncResult",
            return_value=fake_async_result,
        ):
            response = self.client.get("/tasks/task-123")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["taskStatus"], "completed")
        self.assertEqual(response.json()["result"]["status"], "success")


if __name__ == "__main__":
    unittest.main()
