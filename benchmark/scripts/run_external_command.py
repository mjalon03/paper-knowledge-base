"""Record an external parser command without coupling it to the main environment."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from benchmark.adapters.models import NormalizedResult


def run_external_command(
    *,
    tool: str,
    version: str | None,
    input_pdf: Path,
    output_dir: Path,
    command: list[str],
) -> NormalizedResult:
    """Keep stdout/stderr and command metadata even when a tool fails."""

    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=60 * 60,
        )
        elapsed = round(time.monotonic() - started, 3)
        (raw_dir / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
        (raw_dir / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
        return NormalizedResult(
            tool=tool,
            tool_version=version,
            input_file=input_pdf.name,
            runtime_seconds=elapsed,
            success=completed.returncode == 0,
            error=(
                None
                if completed.returncode == 0
                else f"command exited with status {completed.returncode}"
            ),
            native_output=str(raw_dir),
            runtime_metadata={"command": command, "returncode": completed.returncode},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return NormalizedResult(
            tool=tool,
            tool_version=version,
            input_file=input_pdf.name,
            runtime_seconds=round(time.monotonic() - started, 3),
            success=False,
            error=f"{type(error).__name__}: {error}",
            native_output=str(raw_dir),
            runtime_metadata={"command": command},
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a parser command and save command-level benchmark evidence."
    )
    parser.add_argument("--tool", required=True)
    parser.add_argument("--version")
    parser.add_argument("--input-pdf", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise SystemExit("Provide a parser command after '--'.")
    result = run_external_command(
        tool=args.tool,
        version=args.version,
        input_pdf=args.input_pdf,
        output_dir=args.output_dir,
        command=command,
    )
    result.write_json(args.output_dir / "normalized" / f"{args.input_pdf.stem}.json")
    (args.output_dir / "runtime.json").write_text(
        json.dumps(result.runtime_metadata, indent=2) + "\n", encoding="utf-8"
    )
    if not result.success:
        raise SystemExit(result.error)


if __name__ == "__main__":
    main()
