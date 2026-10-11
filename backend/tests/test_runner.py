import base64
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException

from backend.app.runner import (
    build_native_sum_harness,
    run_native_sum,
    runner_config,
    submit_to_runner,
)


class NativeRunnerHarnessTests(unittest.TestCase):
    def test_cpp_function_harness_checks_multiple_cases(self) -> None:
        source, cases = build_native_sum_harness(
            "long long add_numbers(long long a, long long b) { return a + b; }",
            "cpp",
        )

        self.assertIn("add_numbers(3LL, 5LL)", source)
        self.assertIn("add_numbers(1000000000LL, 1000000000LL)", source)
        self.assertEqual(len(cases), 4)

    def test_java_function_harness_uses_judge0_main_entry_point(self) -> None:
        source, cases = build_native_sum_harness(
            "class Solution { static long add_numbers(long a, long b) { return a + b; } }",
            "java",
        )

        self.assertIn("new Solution().add_numbers(3, 5)", source)
        self.assertIn("public class Main", source)
        self.assertEqual(len(cases), 4)

    def test_java_stdin_program_must_use_main_class_convention(self) -> None:
        source = (
            "public class Main { public static void main(String[] args) { "
            "java.util.Scanner input = new java.util.Scanner(System.in); "
            "System.out.println(input.nextInt() + input.nextInt()); } }"
        )
        generated, cases = build_native_sum_harness(source, "java")

        self.assertEqual(generated, source)
        self.assertEqual(cases[0], ("3\n5\n", "8"))

        with self.assertRaises(HTTPException) as caught:
            build_native_sum_harness(
                "class Solution { public static void main(String[] args) {} }",
                "java",
            )

        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("Main class", caught.exception.detail)

    def test_java_function_solution_cannot_conflict_with_runner_main(self) -> None:
        with self.assertRaises(HTTPException) as caught:
            build_native_sum_harness(
                "class Main { static long add_numbers(long a, long b) { return a + b; } }",
                "java",
            )

        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("solution class", caught.exception.detail)

    def test_stdin_program_is_run_with_each_input_case(self) -> None:
        source, cases = build_native_sum_harness(
            "#include <iostream>\nint main() { long long a, b; std::cin >> a >> b; std::cout << a + b; }",
            "cpp",
        )

        self.assertIn("std::cin >> a >> b", source)
        self.assertEqual(cases[0], ("3\n5\n", "8"))

    def test_runner_configuration_requires_server_settings(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as caught:
                runner_config("java")

        self.assertEqual(caught.exception.status_code, 503)


class Judge0AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_uses_base64_and_resource_limits(self) -> None:
        request_data = {}
        response = httpx.Response(
            200,
            json={"status": {"id": 3, "description": "Accepted"}, "stdout": base64.b64encode(b"8\n").decode()},
            request=httpx.Request("POST", "https://judge.example/submissions"),
        )

        class MockClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def post(self, url, headers, json):
                request_data.update({"url": url, "headers": headers, "payload": json})
                return response

        with patch("backend.app.runner.httpx.AsyncClient", return_value=MockClient()):
            stdout = await submit_to_runner(
                "https://judge.example",
                "server-secret",
                54,
                "int main() {}",
                "cpp",
            )

        self.assertEqual(stdout, "8\n")
        self.assertEqual(request_data["payload"]["language_id"], 54)
        self.assertFalse(request_data["payload"]["enable_network"])
        self.assertEqual(request_data["payload"]["cpu_time_limit"], 3.0)
        decoded_source = base64.b64decode(request_data["payload"]["source_code"]).decode()
        self.assertEqual(decoded_source, "int main() {}")

    async def test_compilation_failure_is_reported(self) -> None:
        error = base64.b64encode(b"missing semicolon").decode()
        response = httpx.Response(
            200,
            json={"status": {"id": 6, "description": "Compilation Error"}, "compile_output": error},
            request=httpx.Request("POST", "https://judge.example/submissions"),
        )

        class MockClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def post(self, *args, **kwargs):
                return response

        with patch("backend.app.runner.httpx.AsyncClient", return_value=MockClient()):
            with self.assertRaises(HTTPException) as caught:
                await submit_to_runner(
                    "https://judge.example",
                    "server-secret",
                    62,
                    "class Main {}",
                    "java",
                )

        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("Java compilation failed", caught.exception.detail)
        self.assertIn("missing semicolon", caught.exception.detail)

    async def test_native_sum_runner_reports_results_from_isolated_service(self) -> None:
        output = "8\n5\n0\n2000000000\n"
        with (
            patch.dict(os.environ, {"RUNNER_API_URL": "https://judge.example", "RUNNER_API_KEY": "secret"}),
            patch("backend.app.runner.submit_to_runner", new=AsyncMock(return_value=output)),
        ):
            result = await run_native_sum(
                "long long add_numbers(long long a, long long b) { return a + b; }",
                "cpp",
            )

        self.assertTrue(result["passed"])
        self.assertEqual(result["total_passed"], 4)
        self.assertEqual(result["public_total"], 3)


if __name__ == "__main__":
    unittest.main()
