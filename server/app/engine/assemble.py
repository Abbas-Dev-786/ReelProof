from __future__ import annotations

import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from ..config import settings


def assemble_slideshow(captioned_image_paths: list[str], music_url: str, beat_duration: float) -> str:
    """
    Concat N captioned stills into a timed 9:16 MP4 with background music.

    Each still is held for beat_duration seconds with a subtle zoom (ken-burns).
    Audio is trimmed/looped to match total duration and mixed in.

    Returns the local path of the final MP4.
    """
    os.makedirs(settings.output_dir, exist_ok=True)

    n = len(captioned_image_paths)
    total_duration = n * beat_duration
    out_path = os.path.join(settings.output_dir, "reel_slideshow.mp4")

    # --- Download music ---
    music_suffix = Path(music_url.split("?")[0]).suffix or ".mp3"
    with tempfile.NamedTemporaryFile(delete=False, suffix=music_suffix, dir=settings.output_dir) as f:
        urllib.request.urlretrieve(music_url, f.name)
        music_path = f.name

    # --- Build ffmpeg input args ---
    # Each image as a looped video source for beat_duration seconds
    input_args: list[str] = []
    for img_path in captioned_image_paths:
        input_args += ["-loop", "1", "-t", str(beat_duration), "-i", img_path]

    # Music input
    input_args += ["-i", music_path]
    music_index = n  # music is the last input

    # --- Build zoompan filter for each still (subtle ken-burns) ---
    fps = 25
    frames_per_beat = int(beat_duration * fps)
    zoom_filters = []
    for i in range(n):
        zoom_filters.append(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,"
            f"zoompan=z='min(zoom+0.0008,1.05)':d={frames_per_beat}:s=1080x1920,"
            f"setsar=1,fps={fps}[v{i}]"
        )

    # Concat all beat videos
    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    filter_complex = (
        ";".join(zoom_filters)
        + f";{concat_inputs}concat=n={n}:v=1:a=0[vout]"
        # Trim/loop music to match total duration
        + f";[{music_index}:a]atrim=0:{total_duration},asetpts=PTS-STARTPTS,volume=0.4[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        *input_args,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        out_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg slideshow assembly failed:\n{result.stderr[-2000:]}")

    os.unlink(music_path)
    return out_path
