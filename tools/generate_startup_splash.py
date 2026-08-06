from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ICON = PROJECT_ROOT / "assets" / "windows" / "TrafficCrashNotebook.png"
OUTPUT_IMAGE = (
    PROJECT_ROOT / "assets" / "windows" / "TrafficCrashNotebookSplash.png"
)


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    filename = "segoeuib.ttf" if bold else "segoeui.ttf"
    candidates = (
        Path("C:/Windows/Fonts") / filename,
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        if bold
        else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    raise RuntimeError(f"No suitable font was found for the splash asset: {filename}")


def generate() -> Path:
    if not SOURCE_ICON.is_file():
        raise FileNotFoundError(f"TIU source icon was not found: {SOURCE_ICON}")

    canvas = Image.new("RGB", (720, 380), "#050708")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (3, 3, 716, 376),
        radius=20,
        outline="#315f78",
        width=3,
        fill="#050708",
    )
    draw.rectangle((4, 4, 16, 375), fill="#315f78")

    with Image.open(SOURCE_ICON) as source:
        logo = source.convert("RGB").resize((218, 218), Image.Resampling.LANCZOS)
    canvas.paste(logo, (43, 80))

    draw.line((283, 72, 283, 308), fill="#315f78", width=2)
    draw.text((321, 86), "TRAFFIC CRASH", font=_font(31, bold=True), fill="white")
    draw.text((317, 126), "NOTEBOOK", font=_font(51, bold=True), fill="white")
    draw.rectangle((321, 199, 644, 203), fill="#315f78")
    draw.text((321, 230), "Starting...", font=_font(22), fill="#e9f0f4")
    draw.text(
        (321, 276),
        "Portable Windows application",
        font=_font(15),
        fill="#9fb0ba",
    )

    OUTPUT_IMAGE.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT_IMAGE, format="PNG", optimize=True)
    if OUTPUT_IMAGE.stat().st_size <= 0:
        raise RuntimeError("The generated splash image is empty.")
    return OUTPUT_IMAGE


if __name__ == "__main__":
    try:
        print(generate())
    except Exception as error:
        raise SystemExit(f"Splash generation failed: {error}") from error
