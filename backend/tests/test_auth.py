import json
import os
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.main import PreferencesUpdate, ProfileUpdate, app, configured_origins, supabase_config


class ApiAuthTests(unittest.TestCase):
    def test_health_reports_supabase_not_configured_without_environment(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            response = TestClient(app).get("/health/ready")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["supabase_project_configured"])
        self.assertFalse(payload["capabilities"]["database"])

    def test_protected_identity_route_requires_bearer_token(self) -> None:
        response = TestClient(app).get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_identity_route_fails_closed_without_supabase_configuration(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            response = TestClient(app).get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer invalid-token"},
            )
        self.assertEqual(response.status_code, 503)

    def test_blank_profile_names_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ProfileUpdate(display_name="   ")

    def test_client_cannot_assign_another_user_id_to_profile(self) -> None:
        with self.assertRaises(ValueError):
            ProfileUpdate(display_name="Learner", user_id="00000000-0000-0000-0000-000000000001")

    def test_client_cannot_assign_another_user_id_to_preferences(self) -> None:
        with self.assertRaises(ValueError):
            PreferencesUpdate(
                goal="Learn Python",
                language="Python",
                reminders_enabled=False,
                user_id="00000000-0000-0000-0000-000000000001",
            )

    def test_wildcard_cors_configuration_is_rejected(self) -> None:
        with patch.dict(os.environ, {"CODEQUEST_CORS_ORIGINS": "*"}):
            with self.assertRaises(RuntimeError):
                configured_origins()

    def test_non_tls_non_loopback_supabase_url_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "http://localhost.attacker.invalid",
                "SUPABASE_PUBLISHABLE_KEY": "test-key",
            },
        ):
            with self.assertRaises(HTTPException) as caught:
                supabase_config()
        self.assertEqual(caught.exception.status_code, 503)

    def test_cors_allows_only_configured_local_origin(self) -> None:
        client = TestClient(app)
        response = client.get(
            "/health/live",
            headers={"Origin": "http://localhost:8000"},
        )
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:8000")

    def test_cors_preflight_allows_bearer_profile_requests(self) -> None:
        response = TestClient(app).options(
            "/api/v1/profile",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("POST", response.headers["access-control-allow-methods"])
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:8000")

    def test_profile_query_uses_verified_identity_and_forwards_user_token(self) -> None:
        verified_id = "6ad5dc6f-6b14-4cc5-a227-c3b6e3a2f819"
        token = "test-user-access-token"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/v1/user":
                self.assertEqual(request.headers["authorization"], f"Bearer {token}")
                return httpx.Response(
                    200,
                    json={"id": verified_id, "email": "learner@example.test", "user_metadata": {}},
                )
            self.assertEqual(request.url.path, "/rest/v1/profiles")
            self.assertEqual(request.url.params["user_id"], f"eq.{verified_id}")
            self.assertEqual(request.headers["authorization"], f"Bearer {token}")
            return httpx.Response(
                200,
                json=[{"user_id": verified_id, "display_name": "Learner"}],
            )

        async_client = httpx.AsyncClient
        async_client = httpx.AsyncClient
        async_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with (
            patch.dict(
                os.environ,
                {
                    "SUPABASE_URL": "https://example.supabase.co",
                    "SUPABASE_PUBLISHABLE_KEY": "test-publishable-key",
                },
            ),
            patch(
                "backend.app.main.httpx.AsyncClient",
                side_effect=lambda *args, **kwargs: async_client(transport=transport, **kwargs),
            ),
        ):
            response = TestClient(app).get(
                "/api/v1/profile",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_id"], verified_id)

    def test_profile_write_derives_owner_from_verified_token(self) -> None:
        verified_id = "6ad5dc6f-6b14-4cc5-a227-c3b6e3a2f819"
        token = "test-user-access-token"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/v1/user":
                return httpx.Response(200, json={"id": verified_id, "user_metadata": {}})
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.headers["prefer"], "resolution=merge-duplicates,return=representation")
            body = request.read()
            self.assertIn(f'"user_id":"{verified_id}"'.encode(), body)
            self.assertIn(b'"display_name":"Learner"', body)
            return httpx.Response(
                201,
                json=[{"user_id": verified_id, "display_name": "Learner"}],
            )

        async_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with (
            patch.dict(
                os.environ,
                {
                    "SUPABASE_URL": "https://example.supabase.co",
                    "SUPABASE_PUBLISHABLE_KEY": "test-publishable-key",
                },
            ),
            patch(
                "backend.app.main.httpx.AsyncClient",
                side_effect=lambda *args, **kwargs: async_client(transport=transport, **kwargs),
            ),
        ):
            response = TestClient(app).post(
                "/api/v1/profile",
                headers={"Authorization": f"Bearer {token}"},
                json={"display_name": "Learner"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_id"], verified_id)

    def test_preference_write_derives_owner_and_validates_payload(self) -> None:
        verified_id = "6ad5dc6f-6b14-4cc5-a227-c3b6e3a2f819"
        token = "test-user-access-token"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/v1/user":
                return httpx.Response(200, json={"id": verified_id, "user_metadata": {}})
            self.assertEqual(request.url.path, "/rest/v1/learning_preferences")
            self.assertEqual(request.headers["authorization"], f"Bearer {token}")
            payload = json.loads(request.read())
            self.assertEqual(payload["user_id"], verified_id)
            self.assertEqual(payload["goal"], "Learn Python")
            self.assertEqual(payload["reminders_enabled"], True)
            return httpx.Response(201, json=[{
                "user_id": verified_id,
                "goal": "Learn Python",
                "language": "Python",
                "reminders_enabled": True,
            }])

        async_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with (
            patch.dict(
                os.environ,
                {
                    "SUPABASE_URL": "https://example.supabase.co",
                    "SUPABASE_PUBLISHABLE_KEY": "test-publishable-key",
                },
            ),
            patch(
                "backend.app.main.httpx.AsyncClient",
                side_effect=lambda *args, **kwargs: async_client(transport=transport, **kwargs),
            ),
        ):
            response = TestClient(app).post(
                "/api/v1/preferences",
                headers={"Authorization": f"Bearer {token}"},
                json={"goal": " Learn Python ", "language": "Python", "reminders_enabled": True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_id"], verified_id)


if __name__ == "__main__":
    unittest.main()
