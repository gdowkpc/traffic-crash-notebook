from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fitz


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("pages", nargs="+", type=int)
    arguments = parser.parse_args()

    output_directory = arguments.output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(f"Refusing to overwrite rendered pages: {output_directory}")
    output_directory.mkdir(parents=True)

    document = fitz.open(arguments.pdf.resolve())
    try:
        for page_number in arguments.pages:
            if page_number < 1 or page_number > document.page_count:
                raise ValueError(f"Page {page_number} is outside 1-{document.page_count}")
            page = document.load_page(page_number - 1)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            output_path = output_directory / f"page-{page_number:02d}.png"
            pixmap.save(output_path)
            print(output_path)
    finally:
        document.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
