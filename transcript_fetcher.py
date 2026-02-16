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


def clean_srt_to_text(srt_path: Path) -> str:
    """
    Convert SRT file to clean linear text:
    - Remove HTML tags
    - Remove cue numbers
    - Remove timestamps
    - Collapse whitespace
    """
    text_lines = []

    timestamp_pattern = re.compile(r"\d{2}:\d{2}:\d{2},\d{3}")
    cue_number_pattern = re.compile(r"^\d+$")
    html_tag_pattern = re.compile(r"<[^>]+>")

    with srt_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            # Remove cue numbers
            if cue_number_pattern.match(line):
                continue

            # Remove timestamp lines
            if timestamp_pattern.search(line):
                continue

            # Remove HTML tags
            line = html_tag_pattern.sub("", line)

            text_lines.append(line)

    # Merge lines into flowing text
    cleaned = " ".join(text_lines)

    # Normalize whitespace
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

    # Find the actual English SRT file that was downloaded
    srt_files = list(Path(".").glob("*.en.srt"))

    if not srt_files:
        raise FileNotFoundError("No English SRT subtitle file found.")

    # If multiple, choose the most recently modified
    srt_path = max(srt_files, key=lambda p: p.stat().st_mtime)

    cleaned_text = clean_srt_to_text(srt_path)

    txt_path = Path(f"{safe_title}.txt")
    txt_path.write_text(cleaned_text, encoding="utf-8")

    print(f"\n✓ Detected subtitle file: {srt_path}")
    print(f"✓ Saved pure text transcript: {txt_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python transcript_fetcher.py <YouTube_URL>")
        sys.exit(1)

    download_and_process(sys.argv[1])