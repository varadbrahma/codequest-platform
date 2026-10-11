import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.main import app, authenticated_user


class LeaderboardApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.user = {
            "id": "6ad5dc6f-6b14-4cc5-a227-c3b6e3a2f819",
            "email": "learner@example.test",
            "display_name": "Learner",
        }
        app.dependency_overrides[authenticated_user] = lambda: self.user

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_global_board_requires_authentication(self) -> None:
        app.dependency_overrides.clear()

        response = TestClient(app).get("/api/v1/leaderboard")

        self.assertEqual(response.status_code, 401)

    def test_leaderboard_mission_points_only_after_submission(self) -> None:
        with (
            patch("backend.app.main.run_mission", new=AsyncMock(return_value={"passed": True})),
            patch(
                "backend.app.main.record_leaderboard_completion",
                new=AsyncMock(return_value=True),
            ) as award,
        ):
            response = TestClient(app).post(
                "/api/v1/missions/1/run",
                json={"code": "int add_numbers(int a, int b) { return a + b; }", "language": "cpp"},
            )

        self.assertEqual(response.status_code, 200)
        award.assert_not_awaited()
        self.assertNotIn("leaderboard_recorded", response.json())

    def test_passing_submission_records_completion_once(self) -> None:
        with (
            patch("backend.app.main.run_mission", new=AsyncMock(return_value={"passed": True})),
            patch(
                "backend.app.main.record_leaderboard_completion",
                new=AsyncMock(return_value=True),
            ) as award,
        ):
            response = TestClient(app).post(
                "/api/v1/missions/1/run",
                json={
                    "code": "int add_numbers(int a, int b) { return a + b; }",
                    "language": "cpp",
                    "award_completion": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["leaderboard_recorded"])
        self.assertTrue(response.json()["leaderboard_new_completion"])
        award.assert_awaited_once_with(self.user["id"], 1, "Learner-6AD5DC6F")

    def test_database_write_failure_is_reported_without_erasing_pass(self) -> None:
        from fastapi import HTTPException

        with (
            patch("backend.app.main.run_mission", new=AsyncMock(return_value={"passed": True})),
            patch(
                "backend.app.main.record_leaderboard_completion",
                new=AsyncMock(side_effect=HTTPException(503, "Leaderboard storage is not configured.")),
            ),
        ):
            response = TestClient(app).post(
                "/api/v1/missions/1/run",
                json={
                    "code": "int add_numbers(int a, int b) { return a + b; }",
                    "language": "cpp",
                    "award_completion": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["passed"])
        self.assertFalse(response.json()["leaderboard_recorded"])
        self.assertIn("not configured", response.json()["leaderboard_message"])


if __name__ == "__main__":
    unittest.main()
