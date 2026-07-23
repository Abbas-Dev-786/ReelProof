from __future__ import annotations

import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from ..config import settings


def burn_caption(image_url: str, caption: str, beat_index: int) -> str:
    """Download image, burn caption text in 9:16 safe-zone via ffmpeg. Returns local file path."""
    os.makedirs(settings.output_dir, exist_ok=True)

    # Download source image to a temp file
    suffix = Path(image_url.split("?")[0]).suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_in:
        urllib.request.urlretrieve(image_url, tmp_in.name)
        src_path = tmp_in.name

    out_path = os.path.join(settings.output_dir, f"beat_{beat_index:02d}_captioned.png")

    # 9:16 safe-zone: x=w*0.05 keeps text ~5% from left edge
    # fontsize scales to ~5% of height; wrap at ~30 chars per line
    wrapped = _wrap(caption, width=30)
    escaped = _ffmpeg_escape(wrapped)

    cmd = [
        "ffmpeg", "-y",
        "-i", src_path,
        "-vf", (
            f"drawtext=text='{escaped}'"
            ":fontcolor=white"
            ":fontsize=h*0.055"
            ":x=(w-text_w)/2"
            ":y=h*0.80"
            ":box=1"
            ":boxcolor=black@0.55"
            ":boxborderw=12"
            ":line_spacing=6"
        ),
        "-frames:v", "1",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg caption burn failed:\n{result.stderr}")

    os.unlink(src_path)
    return out_path


def _wrap(text: str, width: int = 30) -> str:
    """Naive word-wrap: insert \\n at word boundaries."""
    words = text.split()
    lines, current = [], []
    length = 0
    for word in words:
        if length + len(word) + (1 if current else 0) > width:
            lines.append(" ".join(current))
            current, length = [word], len(word)
        else:
            current.append(word)
            length += len(word) + (1 if len(current) > 1 else 0)
    if current:
        lines.append(" ".join(current))
    return r"\n".join(lines)


def _ffmpeg_escape(text: str) -> str:
    """Escape chars that break ffmpeg drawtext."""
    return text.replace("'", "\\'").replace(":", r"\:").replace("\\n", r"\n")
