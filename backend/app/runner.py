import ast
import base64
import json
import os
import re
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException


MISSION_CASES: dict[int, tuple[tuple[str, str, bool], ...]] = {
    1: (
        ("add_numbers(3, 5)", "8", True),
        ("add_numbers(-2, 7)", "5", True),
        ("add_numbers(0, 0)", "0", True),
        ("add_numbers(1000000000, 1000000000)", "2000000000", False),
    ),
    2: (
        ("even_or_odd(4)", "'Even'", True),
        ("even_or_odd(7)", "'Odd'", True),
        ("even_or_odd(-2)", "'Even'", False),
    ),
    3: (
        ("largest_of_three(4, 9, 2)", "9", True),
        ("largest_of_three(-3, -1, -8)", "-1", False),
    ),
    4: (
        ("reverse_string('hello')", "'olleh'", True),
        ("reverse_string('')", "''", False),
    ),
    5: (
        ("count_vowels('education')", "5", True),
        ("count_vowels('Rhythm')", "0", False),
    ),
    6: (
        ("is_palindrome('level')", "True", True),
        ("is_palindrome('Python')", "False", False),
    ),
    7: (
        ("find_max([3, 8, 2, 5])", "8", True),
        ("find_max([-4, -9, -1])", "-1", False),
    ),
    8: (
        ("unique_values([1, 2, 1, 3])", "[1, 2, 3]", True),
        ("unique_values([])", "[]", False),
    ),
    9: (
        ("fizzbuzz(5)", "[1, 2, 'Fizz', 4, 'Buzz']", True),
        ("fizzbuzz(15)[-1]", "'FizzBuzz'", False),
    ),
    10: (
        ("balanced('(a+b)()')", "True", True),
        ("balanced('(()')", "False", False),
    ),
    11: (
        ("two_sum([2, 7, 11, 15], 9)", "[0, 1]", True),
        ("two_sum([3, 2, 4], 6)", "[1, 2]", False),
    ),
    12: (
        ("word_counts('hi hi there')", "{'hi': 2, 'there': 1}", True),
        ("word_counts('A a B')", "{'a': 2, 'b': 1}", False),
    ),
    13: (
        ("binary_search([1, 3, 5, 7], 5)", "True", True),
        ("binary_search([1, 3, 5, 7], 2)", "False", False),
    ),
    14: (
        ("merge_ranges([(1, 3), (2, 6), (8, 10)])", "[(1, 6), (8, 10)]", True),
        ("merge_ranges([])", "[]", False),
    ),
    15: (
        ("top_k_words('beta alpha beta gamma alpha', 3)", "['alpha', 'beta', 'gamma']", True),
        ("top_k_words('one one two', 1)", "['one']", False),
    ),
}


def build_harness(code: str, mission_id: int) -> str:
    cases = MISSION_CASES[mission_id]
    encoded_code = repr(code)
    encoded_cases = repr(cases)
    return f"""
import ast
import json
import traceback

namespace = {{}}
try:
    exec({encoded_code}, namespace)
except Exception:
    print(json.dumps({{"ok": False, "error": traceback.format_exc(), "results": []}}))
else:
    results = []
    for call, expected, public in {encoded_cases}:
        try:
            actual = eval(call, namespace)
            passed = actual == ast.literal_eval(expected)
            results.append({{"passed": passed, "public": public, "actual": repr(actual)[:500] if public else None}})
        except Exception:
            results.append({{"passed": False, "public": public, "actual": traceback.format_exc()[:1000] if public else None}})
    print(json.dumps({{"ok": all(result["passed"] for result in results), "error": "", "results": results}}))
"""


RUNNER_LANGUAGES = {
    "python": ("RUNNER_PYTHON_LANGUAGE_ID", "71"),
    "java": ("RUNNER_JAVA_LANGUAGE_ID", "62"),
    "cpp": ("RUNNER_CPP_LANGUAGE_ID", "54"),
}


def runner_config(language: str) -> tuple[str, str, int]:
    url = os.getenv("RUNNER_API_URL", "").strip().rstrip("/")
    token = os.getenv("RUNNER_API_KEY", "").strip()
    if language not in RUNNER_LANGUAGES:
        raise HTTPException(status_code=422, detail="This language is not supported by the isolated runner.")
    env_name, default_id = RUNNER_LANGUAGES[language]
    language_id = os.getenv(env_name, default_id).strip()
    if not url or not token:
        raise HTTPException(status_code=503, detail=f"Isolated {language} runner is not configured.")
    parsed_url = urlsplit(url)
    local_http = parsed_url.scheme == "http" and parsed_url.hostname in {"localhost", "127.0.0.1"}
    secure_remote = parsed_url.scheme == "https" and bool(parsed_url.hostname)
    if not (local_http or secure_remote) or parsed_url.username or parsed_url.password:
        raise HTTPException(status_code=503, detail="Runner endpoint configuration is invalid.")
    if not language_id.isdigit():
        raise HTTPException(status_code=503, detail=f"Runner {language} language configuration is invalid.")
    return url, token, int(language_id)


def decode_output(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        return base64.b64decode(value).decode("utf-8", errors="replace")
    except (ValueError, base64.binascii.Error):
        return ""


def build_native_sum_harness(code: str, language: str) -> tuple[str, list[tuple[str, str]]]:
    cases = [
        ("3", "5", "8"),
        ("-2", "7", "5"),
        ("0", "0", "0"),
        ("1000000000", "1000000000", "2000000000"),
    ]
    uncommented = re.sub(r"/\*[\s\S]*?\*/|//[^\r\n]*", "", code)
    has_main = bool(
        re.search(r"\bmain\s*\(", uncommented)
        if language == "cpp"
        else re.search(r"\bstatic\s+void\s+main\s*\(", uncommented)
    )
    if has_main:
        if language == "java":
            class_match = re.search(r"\bclass\s+([A-Za-z_$][\w$]*)", uncommented)
            public_class_match = re.search(
                r"\bpublic\s+class\s+([A-Za-z_$][\w$]*)",
                uncommented,
            )
            if not class_match or class_match.group(1) != "Main":
                raise HTTPException(
                    status_code=422,
                    detail="Java program must use the Judge0-compatible Main class and main method.",
                )
            if public_class_match and public_class_match.group(1) != "Main":
                raise HTTPException(
                    status_code=422,
                    detail="Java public class must be named Main to match the runner file name.",
                )
        return code, [(f"{left}\n{right}\n", expected) for left, right, expected in cases]

    if language == "cpp":
        source = (
            "#include <iostream>\n"
            + code
            + "\nint main() {\n"
            + "".join(
                f"std::cout << add_numbers({left}LL, {right}LL) << '\\n';\n"
                for left, right, _ in cases
            )
            + "return 0;\n}\n"
        )
    else:
        class_match = re.search(r"\bclass\s+([A-Za-z_$][\w$]*)", code)
        if not class_match:
            raise HTTPException(
                status_code=422,
                detail="Java solution must define add_numbers in a class, or provide a main method that reads two numbers.",
            )
        class_name = class_match.group(1)
        public_class_match = re.search(
            r"\bpublic\s+class\s+([A-Za-z_$][\w$]*)",
            uncommented,
        )
        if class_name == "Main" or public_class_match:
            raise HTTPException(
                status_code=422,
                detail="Java function solutions must use a package-private solution class such as Solution so the runner can add Main.",
            )
        source = (
            code
            + "\npublic class Main {\npublic static void main(String[] args) {\n"
            + "".join(
                f'System.out.println(new {class_name}().add_numbers({left}, {right}));\n'
                for left, right, _ in cases
            )
            + "}\n}\n"
        )
    return source, [("", expected) for _, _, expected in cases]


async def submit_to_runner(
    url: str,
    token: str,
    language_id: int,
    source: str,
    language: str,
    stdin: str = "",
) -> str:
    payload = {
        "language_id": language_id,
        "source_code": base64.b64encode(source.encode("utf-8")).decode("ascii"),
        "stdin": base64.b64encode(stdin.encode("utf-8")).decode("ascii"),
        "cpu_time_limit": 3.0,
        "cpu_extra_time": 1.0,
        "wall_time_limit": 6.0,
        "memory_limit": 128000,
        "stack_limit": 64000,
        "max_processes_and_or_threads": 20,
        "enable_network": False,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0), follow_redirects=False) as client:
            response = await client.post(
                f"{url}/submissions?base64_encoded=true&wait=true",
                headers={"X-Auth-Token": token, "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Code execution timed out.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Isolated runner is unavailable.") from exc
    if response.status_code in (401, 403):
        raise HTTPException(status_code=503, detail="Runner credentials were rejected.")
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="Runner could not execute this submission.")
    try:
        execution = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Runner returned an invalid response.") from exc
    if not isinstance(execution, dict):
        raise HTTPException(status_code=502, detail="Runner returned an invalid response.")
    status = execution.get("status")
    status_id = status.get("id") if isinstance(status, dict) else None
    if status_id != 3:
        detail = decode_output(execution.get("compile_output")) or decode_output(
            execution.get("stderr")
        ) or (status.get("description") if isinstance(status, dict) else "Execution failed.")
        language_name = {"python": "Python", "java": "Java", "cpp": "C++"}[language]
        if status_id == 5:
            raise HTTPException(status_code=408, detail="Submission exceeded the execution time limit.")
        if status_id == 6:
            raise HTTPException(status_code=422, detail=f"{language_name} compilation failed: {detail[:1500]}")
        raise HTTPException(status_code=422, detail=f"{language_name} execution failed: {str(detail)[:1500]}")
    stdout = decode_output(execution.get("stdout"))
    if len(stdout) > 20000:
        raise HTTPException(status_code=422, detail="Runner output exceeded the allowed limit.")
    return stdout


async def run_native_sum(code: str, language: str) -> dict[str, object]:
    url, token, language_id = runner_config(language)
    source, test_inputs = build_native_sum_harness(code, language)
    results = []
    if test_inputs and test_inputs[0][0]:
        for test_stdin, expected in test_inputs:
            stdout = await submit_to_runner(url, token, language_id, source, language, test_stdin)
            actual = stdout.strip()
            results.append({"passed": actual == expected, "actual": actual[:500], "expected": expected})
    else:
        stdout = await submit_to_runner(url, token, language_id, source, language)
        actual_values = [line.strip() for line in stdout.splitlines() if line.strip()]
        expected_values = [expected for _, expected in test_inputs]
        results = [
            {
                "passed": index < len(actual_values) and actual_values[index] == expected,
                "actual": actual_values[index][:500] if index < len(actual_values) else "",
                "expected": expected,
            }
            for index, expected in enumerate(expected_values)
        ]
        if len(actual_values) != len(expected_values):
            raise HTTPException(status_code=422, detail="Runner returned an incomplete test report.")
    public_results = results[:3]
    passed = all(result["passed"] for result in results)
    sample_only = len(results) > 1 and results[0]["passed"] and any(
        not result["passed"] for result in results[1:]
    )
    return {
        "passed": passed,
        "sample_only": sample_only,
        "public_results": public_results,
        "public_passed": sum(result["passed"] for result in public_results),
        "public_total": len(public_results),
        "total_passed": sum(result["passed"] for result in results),
        "total_tests": len(results),
    }


async def run_mission(code: str, mission_id: int, language: str = "python") -> dict[str, object]:
    if mission_id not in MISSION_CASES:
        raise HTTPException(status_code=404, detail="Mission does not exist.")
    if language in {"java", "cpp"}:
        if mission_id != 1:
            raise HTTPException(
                status_code=422,
                detail=f"{language.upper()} runner currently supports the sum-of-two-numbers mission.",
            )
        return await run_native_sum(code, language)
    if language != "python":
        raise HTTPException(status_code=422, detail="This language is not supported by the isolated runner.")
    url, token, language_id = runner_config(language)
    source = build_harness(code, mission_id)
    stdout = await submit_to_runner(url, token, language_id, source, language)
    try:
        report = json.loads(stdout)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Runner returned an invalid test report.") from exc
    if not isinstance(report, dict) or not isinstance(report.get("results"), list):
        raise HTTPException(status_code=502, detail="Runner returned an invalid test report.")
    results = report["results"]
    if len(results) != len(MISSION_CASES[mission_id]) or any(
        not isinstance(result, dict) or not isinstance(result.get("passed"), bool)
        for result in results
    ):
        raise HTTPException(status_code=502, detail="Runner returned an incomplete test report.")
    public_results = [
        {
            "passed": result["passed"],
            "actual": result.get("actual") if MISSION_CASES[mission_id][index][2] else None,
        }
        for index, result in enumerate(results)
        if MISSION_CASES[mission_id][index][2]
    ]
    return {
        "passed": all(result["passed"] for result in results),
        "public_results": public_results,
        "public_passed": sum(result["passed"] for result in public_results),
        "public_total": len(public_results),
        "total_passed": sum(result["passed"] for result in results),
        "total_tests": len(results),
    }
