import os
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.main import MentorMessage, MentorRequest, generate_mentor_answer


class MentorRequestValidationTests(unittest.TestCase):
    def test_conversation_must_end_with_a_user_question(self) -> None:
        with self.assertRaises(ValidationError):
            MentorRequest(messages=[MentorMessage(role="assistant", content="Answer")])

    def test_conversation_messages_must_alternate(self) -> None:
        with self.assertRaises(ValidationError):
            MentorRequest(messages=[
                MentorMessage(role="user", content="First"),
                MentorMessage(role="user", content="Second"),
            ])

    def test_total_conversation_size_is_bounded(self) -> None:
        with self.assertRaises(ValidationError):
            MentorRequest(messages=[
                MentorMessage(role="user", content="a" * 8000),
                MentorMessage(role="assistant", content="b" * 8000),
                MentorMessage(role="user", content="c" * 8000),
                MentorMessage(role="assistant", content="d" * 1),
                MentorMessage(role="user", content="e" * 1),
            ])


class MentorProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_server_api_key_disables_mentor(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as caught:
                await generate_mentor_answer([MentorMessage(role="user", content="Explain recursion")])

        self.assertEqual(caught.exception.status_code, 503)

    async def test_answer_uses_server_key_and_validated_conversation(self) -> None:
        captured = {}
        response = httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Recursion is when a function calls itself."}}]},
            request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
        )

        class MockClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def post(self, url, headers, json):
                captured.update({"url": url, "headers": headers, "payload": json})
                return response

        messages = [
            MentorMessage(role="user", content="What is recursion?"),
            MentorMessage(role="assistant", content="A function calling itself."),
            MentorMessage(role="user", content="Explain it simply."),
        ]
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "server-only-test-key", "OPENAI_MODEL": "test-model"}),
            patch("backend.app.main.httpx.AsyncClient", return_value=MockClient()),
        ):
            answer = await generate_mentor_answer(messages)

        self.assertEqual(answer, "Recursion is when a function calls itself.")
        self.assertEqual(captured["url"], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer server-only-test-key")
        self.assertEqual(captured["payload"]["model"], "test-model")
        self.assertEqual(len(captured["payload"]["messages"]), 4)
        self.assertEqual(captured["payload"]["messages"][-1]["content"], "Explain it simply.")


if __name__ == "__main__":
    unittest.main()
