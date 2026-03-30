import unittest

from fastapi.testclient import TestClient

from src.api.main import app


class MiddlewareTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if not any(route.path == "/_test/error" for route in app.router.routes):
            app.add_api_route("/_test/error", self._raise_error, methods=["GET"])
        self.client = TestClient(app)

    @staticmethod
    async def _raise_error() -> None:
        raise RuntimeError("Synthetic error for middleware verification")

    def test_health_returns_request_id(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertIn("x-request-id", response.headers)
        self.assertEqual(response.json()["status"], "ok")

    def test_http_exception_is_wrapped(self) -> None:
        response = self.client.get(
            "/missing-route", headers={"x-request-id": "req-http-1"}
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "http_error")
        self.assertEqual(response.json()["error"]["request_id"], "req-http-1")

    def test_unhandled_exception_is_wrapped(self) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/_test/error", headers={"x-request-id": "req-500-1"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["error"]["code"],
            "internal_server_error",
        )
        self.assertEqual(response.json()["error"]["request_id"], "req-500-1")


if __name__ == "__main__":
    unittest.main()
