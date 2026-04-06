#!/usr/bin/env python3
"""Unified verification entrypoint for local development and CI."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class StepResult:
    name: str
    status: str
    detail: str = ""


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _python_module_cmd(name: str, *args: str) -> list[str]:
    return [sys.executable, "-m", name, *args]


def _run(cmd: list[str], *, name: str) -> StepResult:
    try:
        completed = subprocess.run(cmd, cwd=ROOT, check=False)
    except Exception as exc:  # pragma: no cover
        return StepResult(name=name, status="failed", detail=str(exc))
    if completed.returncode == 0:
        return StepResult(name=name, status="passed")
    return StepResult(name=name, status="failed", detail=f"exit code {completed.returncode}")


def _run_with_env(cmd: list[str], *, name: str, extra_env: dict[str, str]) -> StepResult:
    env_full = {**os.environ, **extra_env}
    try:
        completed = subprocess.run(cmd, cwd=ROOT, check=False, env=env_full)
    except Exception as exc:  # pragma: no cover
        return StepResult(name=name, status="failed", detail=str(exc))
    if completed.returncode == 0:
        return StepResult(name=name, status="passed")
    return StepResult(name=name, status="failed", detail=f"exit code {completed.returncode}")


def _optional_tool_result(name: str, *, strict_tools: bool) -> StepResult:
    detail = f"{name} 未安装"
    if strict_tools:
        return StepResult(name=name, status="failed", detail=detail)
    return StepResult(name=name, status="skipped", detail=detail)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run compile, test, and optional static checks.")
    parser.add_argument(
        "--strict-tools",
        action="store_true",
        help="Treat missing optional tools such as ruff and mypy as failures.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        help="Write a JSON summary report to the given path.",
    )
    args = parser.parse_args()

    results: list[StepResult] = []

    print("[verify] compileall")
    results.append(
        _run(
            _python_module_cmd("compileall", "inkscape_wps", "tests"),
            name="compileall",
        )
    )

    if _module_available("pytest"):
        print("[verify] pytest")
        results.append(
            _run_with_env(
                _python_module_cmd("pytest", "-q"),
                name="pytest",
                extra_env={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
            )
        )
    else:
        print("[verify] unittest")
        results.append(
            _run(
                _python_module_cmd("unittest", "discover", "-s", "tests", "-p", "test_*.py"),
                name="unittest",
            )
        )

    ruff = shutil.which("ruff")
    if ruff:
        print("[verify] ruff")
        results.append(_run([ruff, "check", "inkscape_wps", "tests"], name="ruff"))
    elif _module_available("ruff"):
        print("[verify] ruff")
        results.append(
            _run(
                _python_module_cmd("ruff", "check", "inkscape_wps", "tests"),
                name="ruff",
            )
        )
    else:
        results.append(_optional_tool_result("ruff", strict_tools=args.strict_tools))

    mypy = shutil.which("mypy")
    if mypy:
        print("[verify] mypy")
        results.append(_run([mypy], name="mypy"))
    elif _module_available("mypy"):
        print("[verify] mypy")
        results.append(_run(_python_module_cmd("mypy"), name="mypy"))
    else:
        results.append(_optional_tool_result("mypy", strict_tools=args.strict_tools))

    failed = [r for r in results if r.status == "failed"]

    print("\nVerification summary:")
    for result in results:
        suffix = f" ({result.detail})" if result.detail else ""
        print(f"- {result.name}: {result.status}{suffix}")

    if args.report_json:
        report_path = args.report_json
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "python": sys.version.split()[0],
            "strict_tools": bool(args.strict_tools),
            "failed": bool(failed),
            "results": [asdict(result) for result in results],
        }
        report = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        report_path.write_text(report, encoding="utf-8")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
