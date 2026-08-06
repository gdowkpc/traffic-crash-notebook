from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CANVAS_SIZE = 1024
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
TEXT = "TIU"


def _windows_font_path() -> Path:
    windows_directory = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = (
        windows_directory / "Fonts" / "segoeuib.ttf",
        windows_directory / "Fonts" / "seguisb.ttf",
        windows_directory / "Fonts" / "arialbd.ttf",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("A supported bold Windows font was not found.")


def _fitted_font(
    draw: ImageDraw.ImageDraw,
    font_path: Path,
) -> tuple[ImageFont.FreeTypeFont, tuple[int, int, int, int]]:
    maximum_width = int(CANVAS_SIZE * 0.80)
    maximum_height = int(CANVAS_SIZE * 0.48)
    for font_size in range(620, 199, -2):
        font = ImageFont.truetype(str(font_path), font_size)
        bounds = draw.textbbox((0, 0), TEXT, font=font)
        if (
            bounds[2] - bounds[0] <= maximum_width
            and bounds[3] - bounds[1] <= maximum_height
        ):
            return font, bounds
    raise RuntimeError("The TIU text could not be fitted into the icon canvas.")


def generate_icon(destination: Path) -> None:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging_path = destination.with_name(f"{destination.stem}.generated.ico")
    png_destination = destination.with_suffix(".png")
    png_staging_path = png_destination.with_name(
        f"{png_destination.stem}.generated.png"
    )

    image = Image.new(
        "RGBA",
        (CANVAS_SIZE, CANVAS_SIZE),
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(image)
    inset = 22
    draw.rounded_rectangle(
        (inset, inset, CANVAS_SIZE - inset, CANVAS_SIZE - inset),
        radius=120,
        fill=(0, 0, 0, 255),
    )

    font, bounds = _fitted_font(draw, _windows_font_path())
    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]
    text_x = (CANVAS_SIZE - text_width) / 2 - bounds[0]
    text_y = (CANVAS_SIZE - text_height) / 2 - bounds[1]
    draw.text(
        (text_x, text_y),
        TEXT,
        font=font,
        fill=(255, 255, 255, 255),
    )

    icon_source = image.resize((256, 256), Image.Resampling.LANCZOS)
    try:
        icon_source.save(png_staging_path, format="PNG", optimize=True)
        with Image.open(png_staging_path) as generated_png:
            if generated_png.size != (256, 256):
                raise RuntimeError("The generated PNG icon has an invalid size.")
        icon_source.save(
            staging_path,
            format="ICO",
            sizes=[(size, size) for size in ICON_SIZES],
            bitmap_format="png",
        )
        if not staging_path.is_file() or staging_path.stat().st_size < 1_000:
            raise RuntimeError("The generated Windows icon is missing or incomplete.")
        with Image.open(staging_path) as generated:
            available_sizes = set(generated.info.get("sizes", ()))
        expected_sizes = {(size, size) for size in ICON_SIZES}
        if not expected_sizes.issubset(available_sizes):
            raise RuntimeError(
                "The generated Windows icon is missing required resolutions: "
                f"{sorted(expected_sizes - available_sizes)}"
            )
        png_staging_path.replace(png_destination)
        staging_path.replace(destination)
    finally:
        if staging_path.exists():
            staging_path.unlink()
        if png_staging_path.exists():
            png_staging_path.unlink()


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    destination = (
        project_root
        / "assets"
        / "windows"
        / "TrafficCrashNotebook.ico"
    )
    generate_icon(destination)
    print(f"Generated {destination}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Icon generation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
