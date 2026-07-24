from __future__ import annotations

import subprocess
import tempfile
import urllib.request
from pathlib import Path

from ..config import settings
from .captions import caption_drawtext_filter


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
    voiceover_url: str | None = None,
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

    # --- Download audio sources ---
    music_suffix = Path(music_url.split("?")[0]).suffix or ".mp3"
    with tempfile.NamedTemporaryFile(delete=False, suffix=music_suffix, dir=target_dir) as f:
        urllib.request.urlretrieve(music_url, f.name)
        music_path = Path(f.name)
    voiceover_path: Path | None = None
    if voiceover_url:
        voiceover_suffix = Path(voiceover_url.split("?")[0]).suffix or ".mp3"
        voiceover_path = _download_asset(voiceover_url, target_dir, voiceover_suffix)

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
    music_index = n
    if voiceover_path:
        input_args += ["-i", str(voiceover_path)]

    filter_complex = (
        video_filter
        # Trim looped music to match the exact reel duration.
        + f";[{music_index}:a]atrim=duration={total_duration},asetpts=PTS-STARTPTS,volume=0.4[music]"
    )
    if voiceover_path:
        filter_complex += (
            f";[{music_index + 1}:a]atrim=duration={total_duration},asetpts=PTS-STARTPTS,"
            "volume=1.0[voice];[music][voice]amix=inputs=2:duration=longest:"
            "weights='0.4 1.0',alimiter=limit=0.95[aout]"
        )
    else:
        filter_complex += ";[music]anull[aout]"

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
        if voiceover_path:
            voiceover_path.unlink(missing_ok=True)


def _download_asset(url: str, target_dir: Path, suffix: str) -> Path:
    """Download an input asset to a controlled temporary file for ffmpeg."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=target_dir) as file:
        destination = Path(file.name)
    try:
        urllib.request.urlretrieve(url, destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def _has_audio_stream(video_path: Path) -> bool:
    """Return whether a local video has an audio stream without decoding it."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for POV clip {video_path.name}: {result.stderr[-1000:]}")
    return bool(result.stdout.strip())


def assemble_pov_montage(
    clip_urls: list[str],
    music_url: str,
    clip_duration: int,
    output_dir: str | Path | None = None,
    captions: list[str] | None = None,
    voiceover_url: str | None = None,
) -> str:
    """Normalize, concatenate, and score image-to-video clips into a vertical MP4.

    Clip audio is retained when a provider supplies it. Silent clips receive a
    matching silent stream, allowing ffmpeg's concat filter to remain stable;
    the result is then mixed with the campaign's music bed.
    """
    if not clip_urls:
        raise ValueError("Cannot assemble a POV montage without video clips")
    if clip_duration <= 0:
        raise ValueError("clip_duration must be greater than zero")
    if captions is not None and len(captions) != len(clip_urls):
        raise ValueError("POV captions must match the number of video clips")

    target_dir = Path(output_dir or settings.output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    downloaded_paths: list[Path] = []
    try:
        for index, url in enumerate(clip_urls):
            suffix = Path(url.split("?")[0]).suffix or ".mp4"
            downloaded_paths.append(_download_asset(url, target_dir, f"-clip-{index}{suffix}"))

        music_suffix = Path(music_url.split("?")[0]).suffix or ".mp3"
        music_path = _download_asset(music_url, target_dir, f"-music{music_suffix}")
        downloaded_paths.append(music_path)
        voiceover_path: Path | None = None
        if voiceover_url:
            voiceover_suffix = Path(voiceover_url.split("?")[0]).suffix or ".mp3"
            voiceover_path = _download_asset(voiceover_url, target_dir, voiceover_suffix)
            downloaded_paths.append(voiceover_path)

        filter_parts: list[str] = []
        concat_inputs: list[str] = []
        fps = settings.slideshow_fps
        for index, clip_path in enumerate(downloaded_paths[: len(clip_urls)]):
            caption_filter = f",{caption_drawtext_filter(captions[index])}" if captions else ""
            filter_parts.append(
                f"[{index}:v:0]scale={settings.slideshow_width}:{settings.slideshow_height}:"
                f"force_original_aspect_ratio=increase,crop={settings.slideshow_width}:"
                f"{settings.slideshow_height},setsar=1,fps={fps},format=yuv420p,"
                f"trim=duration={clip_duration},setpts=PTS-STARTPTS{caption_filter}[v{index}]"
            )
            if _has_audio_stream(clip_path):
                filter_parts.append(
                    f"[{index}:a:0]aresample=48000,aformat=channel_layouts=stereo,"
                    f"atrim=duration={clip_duration},asetpts=PTS-STARTPTS[a{index}]"
                )
            else:
                filter_parts.append(
                    f"anullsrc=channel_layout=stereo:sample_rate=48000,"
                    f"atrim=duration={clip_duration},asetpts=PTS-STARTPTS[a{index}]"
                )
            concat_inputs.extend([f"[v{index}]", f"[a{index}]"])

        clip_count = len(clip_urls)
        music_index = clip_count
        total_duration = clip_count * clip_duration
        filter_parts.append(
            f"{''.join(concat_inputs)}concat=n={clip_count}:v=1:a=1[clips_v][clips_a]"
        )
        filter_parts.append(
            f"[{music_index}:a]atrim=duration={total_duration},asetpts=PTS-STARTPTS,"
            "volume=0.35[music]"
        )
        if voiceover_path:
            voiceover_index = music_index + 1
            filter_parts.append(
                f"[{voiceover_index}:a]atrim=duration={total_duration},asetpts=PTS-STARTPTS,"
                "volume=1.0[voice]"
            )
            filter_parts.append(
                "[clips_a][music][voice]amix=inputs=3:duration=longest:weights='0.55 0.35 1.0',"
                "alimiter=limit=0.95[aout]"
            )
        else:
            filter_parts.append(
                "[clips_a][music]amix=inputs=2:duration=first:weights='0.55 0.35',"
                "alimiter=limit=0.95[aout]"
            )

        output_path = target_dir / "reel_pov_montage.mp4"
        # Keep the music looping; voiceover is supplied once and mixed separately.
        input_args = [
            argument
            for clip_path in downloaded_paths[:clip_count]
            for argument in ("-i", str(clip_path))
        ]
        input_args.extend(["-stream_loop", "-1", "-i", str(music_path)])
        if voiceover_path:
            input_args.extend(["-i", str(voiceover_path)])
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                *input_args,
                "-filter_complex",
                ";".join(filter_parts),
                "-map",
                "[clips_v]",
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
                "-movflags",
                "+faststart",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg POV montage assembly failed:\n{result.stderr[-2000:]}")
        return str(output_path)
    finally:
        for path in downloaded_paths:
            path.unlink(missing_ok=True)
