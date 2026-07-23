from __future__ import annotations

import subprocess
import tempfile
import urllib.request
from pathlib import Path

from ..config import settings


def _build_video_filter(
    n: int, beat_duration: float, transition_duration: float
) -> tuple[str, float]:
    """Build the still-to-video filter graph and return its final duration."""
    if n < 1:
        raise ValueError("A slideshow needs at least one frame")

    fps = settings.slideshow_fps
    segments = [
        (
            f"[{index}:v]scale={settings.slideshow_width}:{settings.slideshow_height}:force_original_aspect_ratio=increase,"
            f"crop={settings.slideshow_width}:{settings.slideshow_height},"
            f"zoompan=z='min(zoom+0.0008,1.05)':d=1:s={settings.slideshow_width}x{settings.slideshow_height},"
            f"setsar=1,fps={fps}[v{index}]"
        )
        for index in range(n)
    ]

    if n == 1:
        return ";".join(segments) + ";[v0]null[vout]", beat_duration

    filters = segments[:]
    previous = "v0"
    current_duration = beat_duration
    for index in range(1, n):
        output = f"xf{index}"
        offset = current_duration - transition_duration
        filters.append(
            f"[{previous}][v{index}]xfade=transition=fade:duration={transition_duration}:offset={offset}[{output}]"
        )
        previous = output
        current_duration += beat_duration - transition_duration

    filters.append(f"[{previous}]null[vout]")
    return ";".join(filters), current_duration


def assemble_slideshow(
    captioned_image_paths: list[str],
    music_url: str,
    beat_duration: float,
    output_dir: str | Path | None = None,
) -> str:
    """
    Concat N captioned stills into a timed 9:16 MP4 with background music.

    Each still is held for beat_duration seconds with a subtle zoom (ken-burns).
    Audio is trimmed/looped to match total duration and mixed in.

    Returns the local path of the final MP4.
    """
    if not captioned_image_paths:
        raise ValueError("Cannot assemble a slideshow without captioned images")
    if beat_duration <= 0:
        raise ValueError("beat_duration must be greater than zero")

    target_dir = Path(output_dir or settings.output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    image_paths = [Path(path).resolve() for path in captioned_image_paths]
    missing = [str(path) for path in image_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Captioned image files not found: {', '.join(missing)}")

    n = len(image_paths)
    transition_duration = min(settings.slideshow_transition_sec, beat_duration / 3)
    video_filter, total_duration = _build_video_filter(n, beat_duration, transition_duration)
    out_path = target_dir / "reel_slideshow.mp4"

    # --- Download music ---
    music_suffix = Path(music_url.split("?")[0]).suffix or ".mp3"
    with tempfile.NamedTemporaryFile(delete=False, suffix=music_suffix, dir=target_dir) as f:
        urllib.request.urlretrieve(music_url, f.name)
        music_path = Path(f.name)

    # --- Build ffmpeg input args ---
    # Each image as a looped video source for beat_duration seconds
    input_args: list[str] = []
    fps = settings.slideshow_fps
    for img_path in image_paths:
        input_args += [
            "-loop",
            "1",
            "-framerate",
            str(fps),
            "-t",
            str(beat_duration),
            "-i",
            str(img_path),
        ]

    # Music repeats if the provider returned a shorter track than the reel.
    input_args += ["-stream_loop", "-1", "-i", str(music_path)]
    music_index = n  # music is the last input

    filter_complex = (
        video_filter
        # Trim looped music to match the exact reel duration.
        + f";[{music_index}:a]atrim=duration={total_duration},asetpts=PTS-STARTPTS,volume=0.4[aout]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        *input_args,
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(out_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg slideshow assembly failed:\n{result.stderr[-2000:]}")
        return str(out_path)
    finally:
        music_path.unlink(missing_ok=True)
