"""Create and verify an image-only PDF from the first pages of a source paper."""

from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf


def create_image_only_pdf(source: Path, destination: Path, pages: int, dpi: int) -> int:
    source_document = pymupdf.open(source)
    output_document = pymupdf.open()
    try:
        for page in source_document[:pages]:
            pixmap = page.get_pixmap(dpi=dpi, alpha=False)
            image_page = output_document.new_page(
                width=page.rect.width,
                height=page.rect.height,
            )
            image_page.insert_image(image_page.rect, stream=pixmap.tobytes("png"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        output_document.save(destination, garbage=4, deflate=True)
    finally:
        source_document.close()
        output_document.close()

    verification = pymupdf.open(destination)
    try:
        extracted_characters = sum(
            len(page.get_text("text").strip()) for page in verification
        )
    finally:
        verification.close()
    if extracted_characters:
        raise RuntimeError(
            f"Synthetic scan unexpectedly has {extracted_characters} extractable characters"
        )
    return extracted_characters


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args()
    if args.pages < 1 or args.dpi < 72:
        raise SystemExit("--pages must be positive and --dpi must be at least 72")
    extracted_characters = create_image_only_pdf(
        args.source, args.destination, args.pages, args.dpi
    )
    print(
        f"created={args.destination} pages={args.pages} dpi={args.dpi} "
        f"extracted_characters={extracted_characters}"
    )


if __name__ == "__main__":
    main()
