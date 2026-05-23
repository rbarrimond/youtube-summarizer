#!/usr/bin/env python3

"""
Transcript Fetcher

Given a YouTube URL:
1. Fetches English subtitles (auto or manual) using yt-dlp
2. Cleans subtitle content to linear text in memory by default
3. Optional download mode produces:
   - <title>.en.<ext>  (subtitle layer)
   - <title>.txt       (clean semantic layer)

Usage:
    python transcript_fetcher.py "https://youtu.be/VIDEO_ID"
    python transcript_fetcher.py "https://youtu.be/VIDEO_ID" --download --output-dir ./out
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Mapping
from urllib.request import urlopen

from yt_dlp import YoutubeDL


def clean_subtitle_to_text(subtitle_content: str) -> str:
    """Convert SRT/VTT subtitle content to clean linear text."""
    text_lines = []

    timestamp_pattern = re.compile(r"\d{2}:\d{2}:\d{2}[.,]\d{3}")
    cue_number_pattern = re.compile(r"^\d+$")
    html_tag_pattern = re.compile(r"<[^>]+>")

    for raw_line in subtitle_content.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        # Skip WEBVTT header and metadata lines.
        if line.upper().startswith("WEBVTT"):
            continue
        if line.startswith(("NOTE", "Kind:", "Language:")):
            continue

        if cue_number_pattern.match(line):
            continue

        if timestamp_pattern.search(line) or "-->" in line:
            continue

        line = html_tag_pattern.sub("", line)
        text_lines.append(line)

    cleaned = " ".join(text_lines)
    return re.sub(r"\s+", " ", cleaned).strip()


def sanitize_title(title: str) -> str:
    """Sanitize title for filesystem safety."""
    return re.sub(r"[^\w\-. ]", "_", title).strip()


def select_english_caption_track(info: Mapping[str, Any]) -> dict[str, Any]:
    """Choose the best English subtitle track from manual/automatic captions."""
    subtitles = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}
    preferred_ext_order = {"srt": 0, "vtt": 1, "ttml": 2, "srv3": 3, "json3": 4}

    # Prefer manual subtitles first, then automatic captions.
    for source in (subtitles, automatic):
        for key in ("en", "en-US", "en-GB"):
            tracks = source.get(key)
            if tracks:
                break
        else:
            tracks = next((v for k, v in source.items() if str(k).startswith("en")), None)

        if tracks:
            sorted_tracks = sorted(
                tracks,
                key=lambda t: preferred_ext_order.get(str(t.get("ext", "")).lower(), 99),
            )
            return sorted_tracks[0]

    raise FileNotFoundError("No English subtitle track found in video metadata.")


def fetch_subtitle_content(track: dict[str, Any]) -> tuple[str, str]:
    """Fetch subtitle bytes from track URL and decode as UTF-8."""
    url = track.get("url")
    if not url:
        raise RuntimeError("Selected subtitle track is missing a URL.")

    ext = str(track.get("ext") or "vtt").lower()
    with urlopen(url) as response:  # noqa: S310
        raw_bytes = response.read()

    return raw_bytes.decode("utf-8", errors="replace"), ext


def process_transcript(url: str, download: bool, output_dir: Path | None) -> None:
    """Fetch subtitles, clean text in memory, and optionally download artifacts."""
    ydl_opts: dict[str, Any] = {
        "skip_download": True,
        "quiet": True,
    }

    with YoutubeDL(ydl_opts) as ydl:  # pyright: ignore[reportArgumentType]
        info = ydl.extract_info(url, download=False)
        title = info.get("title")

    if not title:
        raise RuntimeError("Could not extract video title.")

    safe_title = sanitize_title(str(title))
    track = select_english_caption_track(info)
    subtitle_content, subtitle_ext = fetch_subtitle_content(track)
    cleaned_text = clean_subtitle_to_text(subtitle_content)

    if download:
        target_dir = output_dir or Path(".")
        target_dir.mkdir(parents=True, exist_ok=True)

        sub_path = target_dir / f"{safe_title}.en.{subtitle_ext}"
        txt_path = target_dir / f"{safe_title}.txt"

        sub_path.write_text(subtitle_content, encoding="utf-8")
        txt_path.write_text(cleaned_text, encoding="utf-8")

        print(f"Saved subtitle: {sub_path}", file=sys.stderr)
        print(f"Saved pure text transcript: {txt_path}", file=sys.stderr)

    print(cleaned_text)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Fetch and clean YouTube subtitles.")
    parser.add_argument("youtube_url", help="YouTube video URL")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Persist subtitle and cleaned transcript files to disk.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for downloaded files when --download is set "
            "(defaults to current directory)."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    process_transcript(args.youtube_url, download=args.download, output_dir=args.output_dir)
