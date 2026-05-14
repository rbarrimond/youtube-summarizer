#!/usr/bin/env python3

"""
Transcript Fetcher

Given a YouTube URL:
1. Downloads English subtitles (auto or manual) using yt-dlp
2. Converts them to SRT
3. Produces:
   - <title>.en.srt  (temporal layer)
   - <title>.txt     (clean semantic layer)

Usage:
    python transcript_fetcher.py "https://youtu.be/VIDEO_ID"
"""

import re
import sys
from pathlib import Path
from typing import Any
from yt_dlp import YoutubeDL


def clean_subtitle_to_text(sub_path: Path) -> str:
    """
    Convert SRT or VTT file to clean linear text:
    - Remove HTML tags
    - Remove cue numbers
    - Remove timestamps
    - Remove WEBVTT headers
    - Collapse whitespace
    """

    text_lines = []

    timestamp_pattern = re.compile(r"\d{2}:\d{2}:\d{2}[.,]\d{3}")
    cue_number_pattern = re.compile(r"^\d+$")
    html_tag_pattern = re.compile(r"<[^>]+>")

    with sub_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            # Skip WEBVTT header
            if line.upper().startswith("WEBVTT"):
                continue

            # Skip cue numbers
            if cue_number_pattern.match(line):
                continue

            # Skip timestamps (handles both , and . milliseconds)
            if timestamp_pattern.search(line):
                continue

            # Remove HTML tags
            line = html_tag_pattern.sub("", line)

            text_lines.append(line)

    cleaned = " ".join(text_lines)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def download_and_process(url: str):
    """Download subtitles and process them into SRT and clean text."""

    ydl_opts: dict[str, Any] = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en"],
        "subtitlesformat": "best",
        "convertsubtitles": "srt",
        "outtmpl": "%(title)s.%(ext)s",
        "quiet": False,
    }

    with YoutubeDL(ydl_opts) as ydl: # pyright: ignore[reportArgumentType]
        info = ydl.extract_info(url, download=True)
        title = info.get("title")

    if not title:
        raise RuntimeError("Could not extract video title.")

    # Sanitize title for filesystem safety
    safe_title = re.sub(r"[^\w\-. ]", "_", title).strip()

    # Find English subtitle files (.srt or .vtt)
    subtitle_files = list(Path(".").glob("*.en.srt")) + list(Path(".").glob("*.en.vtt"))

    if not subtitle_files:
        raise FileNotFoundError("No English subtitle file (.srt or .vtt) found.")

    # Choose most recently modified subtitle file
    sub_path = max(subtitle_files, key=lambda p: p.stat().st_mtime)

    cleaned_text = clean_subtitle_to_text(sub_path)

    txt_path = Path(f"{safe_title}.txt")
    txt_path.write_text(cleaned_text, encoding="utf-8")

    print(f"\n✓ Detected subtitle file: {sub_path}")
    print(f"✓ Saved pure text transcript: {txt_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python transcript_fetcher.py <YouTube_URL>")
        sys.exit(1)

    download_and_process(sys.argv[1])
    