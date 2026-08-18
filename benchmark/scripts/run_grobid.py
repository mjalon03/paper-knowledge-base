"""Run GROBID's official REST endpoint and preserve the returned TEI XML."""

from __future__ import annotations

import argparse
import json
import mimetypes
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree.ElementTree import ParseError

from benchmark.adapters.grobid import normalize_tei
from benchmark.adapters.models import NormalizedResult


def _multipart_pdf(path: Path) -> tuple[bytes, str]:
    boundary = f"----paper-benchmark-{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(path.name)[0] or "application/pdf"
    chunks = [
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="input"; filename="{path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode(),
        path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), boundary


def run_grobid(
    input_pdf: Path, output_dir: Path, endpoint: str, version: str | None
) -> Path:
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{input_pdf.stem}.tei.xml"
    started = time.monotonic()
    try:
        payload, boundary = _multipart_pdf(input_pdf)
        request = Request(
            f"{endpoint.rstrip('/')}/api/processFulltextDocument",
            data=payload,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urlopen(request, timeout=300) as response:
            raw_path.write_bytes(response.read())
        result = normalize_tei(
            raw_path,
            input_file=input_pdf,
            runtime_seconds=round(time.monotonic() - started, 3),
            tool_version=version,
        )
    except (HTTPError, URLError, OSError, TimeoutError, ParseError) as error:
        result = NormalizedResult(
            tool="grobid",
            tool_version=version,
            input_file=input_pdf.name,
            runtime_seconds=round(time.monotonic() - started, 3),
            success=False,
            error=f"{type(error).__name__}: {error}",
        )
    result.write_json(output_dir / "normalized" / f"{input_pdf.stem}.json")
    (output_dir / "runtime.json").write_text(
        json.dumps(result.runtime_metadata, indent=2) + "\n", encoding="utf-8"
    )
    if not result.success:
        raise SystemExit(result.error)
    return raw_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--endpoint", default="http://localhost:8070")
    parser.add_argument("--version", default="0.9.1")
    args = parser.parse_args()
    raw_path = run_grobid(args.input_pdf, args.output_dir, args.endpoint, args.version)
    print(f"raw_tei={raw_path}")


if __name__ == "__main__":
    main()
