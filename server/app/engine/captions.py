from __future__ import annotations

import subprocess
import tempfile
import urllib.request
from pathlib import Path
from shutil import which
from textwrap import wrap

from ..config import settings


def caption_renderer_error() -> str | None:
    """Return the missing local caption-rendering prerequisite, if any."""
    ffmpeg = which("ffmpeg")
    if ffmpeg is None:
        return "ffmpeg is required for captions and video assembly"
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"could not inspect ffmpeg filters: {exc}"
    if result.returncode != 0:
        return "ffmpeg could not list its available filters"
    if "drawtext" not in result.stdout:
        return "ffmpeg must include the drawtext filter for captions"
    return None


def caption_drawtext_filter(caption: str) -> str:
    """Return the shared, 9:16-safe ffmpeg drawtext filter for a caption."""
    wrapped = _wrap(caption)
    escaped = _ffmpeg_escape(wrapped)
    return (
        f"drawtext=text='{escaped}'"
        ":fontcolor=white"
        ":fontsize=h*0.055"
        ":x=(w-text_w)/2"
        ":y=(h-text_h)*0.82"
        ":box=1"
        ":boxcolor=black@0.55"
        ":boxborderw=12"
        ":line_spacing=6"
        ":fix_bounds=1"
    )


def title_drawtext_filter(title: str) -> str:
    """Return a centered drawtext filter for the opening title card."""
    wrapped = _wrap(title, width=18)
    escaped = _ffmpeg_escape(wrapped)
    lines = wrapped.splitlines() or [""]
    longest_line = max(len(line) for line in lines)
    line_count = len(lines)

    # Size against the rendered frame rather than assuming every title fits the
    # default title size. The estimates leave room for wide glyphs and spacing.
    safe_width = settings.slideshow_width * 0.8
    safe_height = settings.slideshow_height * 0.55
    width_size = safe_width / max(longest_line * 0.62, 1)
    height_size = (safe_height - 10 * (line_count - 1)) / max(line_count * 1.2, 1)
    font_size = max(12, min(settings.slideshow_height * 0.065, width_size, height_size))
    return (
        f"drawtext=text='{escaped}'"
        ":fontcolor=white"
        f":fontsize={font_size:.2f}"
        ":x=(w-text_w)/2"
        ":y=(h-text_h)/2"
        ":line_spacing=10"
        ":fix_bounds=1"
    )


def render_title_card(title: str, output_dir: str | Path | None = None) -> str:
    """Render a text-only 9:16 opening card. Returns its local file path."""
    target_dir = Path(output_dir or settings.output_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / "slideshow_title_card.png"

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        (
            f"color=c=0x15131f:s={settings.slideshow_width}x"
            f"{settings.slideshow_height}"
        ),
        "-vf",
        title_drawtext_filter(title),
        "-frames:v",
        "1",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg title-card render failed:\n{result.stderr}")
    return str(out_path)


def burn_caption(
    image_url: str, caption: str, beat_index: int, output_dir: str | Path | None = None
) -> str:
    """Download image, burn caption text in 9:16 safe-zone via ffmpeg. Returns local file path."""
    target_dir = Path(output_dir or settings.output_path)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Download source image to a temp file
    suffix = Path(image_url.split("?")[0]).suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_in:
        urllib.request.urlretrieve(image_url, tmp_in.name)
        src_path = tmp_in.name

    out_path = target_dir / f"beat_{beat_index:02d}_captioned.png"

    video_filter = (
        f"scale={settings.slideshow_width}:{settings.slideshow_height}:force_original_aspect_ratio=increase,"
        f"crop={settings.slideshow_width}:{settings.slideshow_height},"
        f"{caption_drawtext_filter(caption)}"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        src_path,
        "-vf",
        video_filter,
        "-frames:v",
        "1",
        str(out_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg caption burn failed:\n{result.stderr}")
        return str(out_path)
    finally:
        Path(src_path).unlink(missing_ok=True)


def _wrap(text: str, width: int = 16) -> str:
    """Wrap captions into bounded lines, including unusually long words."""
    normalized = " ".join(text.split())
    if not normalized:
        return ""
    return "\n".join(
        wrap(
            normalized,
            width=width,
            break_long_words=True,
            break_on_hyphens=False,
        )
    )


def _ffmpeg_escape(text: str) -> str:
    """Escape chars that break ffmpeg drawtext."""
    return (
        text.replace("\\", r"\\")
        .replace("'", r"\'")
        .replace(":", r"\:")
        .replace("%", r"\%")
    )
