#!/usr/bin/env python3
"""youtube-summarizer: Generate a Fabric-ready Markdown note from a YouTube URL.

This script fetches video metadata and English subtitles with yt-dlp, converts
subtitle content to plain text in memory by default, and then calls a Fabric
pattern (`extract_article_wisdom`) to produce a structured wisdom article.

Typical usage:
    python yt_to_wisdom_md.py <youtube_url> [output_dir]
    python yt_to_wisdom_md.py <youtube_url> [output_dir] --download

If `output_dir` is omitted it defaults to `~/fabric/youtube`.
The final Markdown note is always written to disk. The `--download` switch
controls whether subtitle/intermediate files are also persisted.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen


# -------- helpers --------

def run(cmd: list[str], input_text: str | None = None) -> str:
    """Run a subprocess command and return its stdout as a stripped string."""
    result = subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def slugify(text: str) -> str:
    """Create a filesystem/URL friendly slug from arbitrary text."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = text.strip("-")
    return text or "video"


def yaml_str(value: Any) -> str:
    """Serialize a Python value to a YAML-compatible string."""
    return json.dumps(value, ensure_ascii=False)


def subtitle_to_text(subtitle_content: str) -> str:
    """Convert subtitle content (SRT/VTT-like) to plain text."""
    lines: list[str] = []
    for raw_line in subtitle_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.upper().startswith("WEBVTT"):
            continue
        if line.startswith(("NOTE", "Kind:", "Language:")):
            continue
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}", line):
            continue
        if "-->" in line:
            continue
        lines.append(re.sub(r"<[^>]+>", "", line))
    return "\n".join(lines)


def normalize_date(yt_date: str | None) -> str | None:
    """Normalize a YouTube date string to ISO format where possible."""
    if not yt_date:
        return None
    if re.fullmatch(r"\d{8}", yt_date):
        try:
            dt = datetime.strptime(yt_date, "%Y%m%d")
            return dt.date().isoformat()
        except ValueError:
            return None
    return yt_date


def select_english_caption_track(meta: dict[str, Any]) -> dict[str, Any] | None:
    """Choose a best-effort English subtitle track from metadata."""
    subtitles = meta.get("subtitles") or {}
    automatic = meta.get("automatic_captions") or {}
    preferred_ext_order = {"srt": 0, "vtt": 1, "ttml": 2, "srv3": 3, "json3": 4}

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

    return None


def fetch_subtitle_content(track: dict[str, Any]) -> tuple[str, str]:
    """Fetch subtitle content bytes from selected track URL."""
    url = track.get("url")
    if not url:
        raise RuntimeError("Selected subtitle track is missing a URL.")

    ext = str(track.get("ext") or "vtt").lower()
    with urlopen(url) as response:  # noqa: S310
        raw_bytes = response.read()

    return raw_bytes.decode("utf-8", errors="replace"), ext


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate Fabric-ready markdown note from a YouTube video."
    )
    parser.add_argument("youtube_url", help="YouTube video URL")
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=None,
        help="Output directory for markdown (default: ~/fabric/youtube)",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Persist subtitle/intermediate files alongside the markdown output.",
    )
    return parser.parse_args()


def extract_transcript(
    meta: dict[str, Any],
    download: bool,
    out_dir: Path,
    video_id: str,
) -> tuple[str, str]:
    """Extract transcript text from English captions and optionally persist subtitle artifacts."""
    track = select_english_caption_track(meta)
    if not track:
        print("[!] No English subtitles found. Transcript will be empty.", file=sys.stderr)
        return "", "none"

    subtitle_content, subtitle_ext = fetch_subtitle_content(track)
    transcript_text = subtitle_to_text(subtitle_content)

    if download:
        subtitle_path = out_dir / f"{video_id}.en.{subtitle_ext}"
        subtitle_path.write_text(subtitle_content, encoding="utf-8")
        transcript_path = out_dir / f"{video_id}.txt"
        transcript_path.write_text(transcript_text, encoding="utf-8")
        print(f"[+] Saved subtitle: {subtitle_path}")
        print(f"[+] Saved transcript text: {transcript_path}")

    return transcript_text, "auto"


def build_markdown_lines(
    title: str,
    webpage_url: str,
    created_date: str,
    source_date: str | None,
    duration: Any,
    language: str,
    uploader: str,
    tags: Any,
    description: str,
    transcript_quality: str,
    body_md: str,
) -> list[str]:
    """Build the markdown front matter and body lines for output."""
    md_lines: list[str] = []
    md_lines.append("---")
    md_lines.append(f"title: {yaml_str(title)}")
    md_lines.append(f"source_type: {yaml_str('youtube_podcast')}")
    md_lines.append(f"original_url: {yaml_str(webpage_url)}")
    md_lines.append(f"created: {yaml_str(created_date)}")
    md_lines.append(f"source_date: {yaml_str(source_date) if source_date else 'null'}")
    md_lines.append(f"duration_seconds: {duration if duration is not None else 'null'}")
    md_lines.append(f"language: {yaml_str(language)}")
    md_lines.append(f"uploader: {yaml_str(uploader)}")
    md_lines.append("people: []")

    md_lines.append("topics:")
    if isinstance(tags, list) and tags:
        for tag in tags:
            md_lines.append(f"  - {yaml_str(tag)}")
    else:
        md_lines.append('  - "youtube"')

    md_lines.append("tags:")
    md_lines.append('  - "YouTube"')

    short_desc = description.strip().split("\n")[0][:280]
    md_lines.append(f"description: {yaml_str(short_desc)}")
    md_lines.append(f"transcript_source: {yaml_str('yt-dlp')}")
    md_lines.append(f"transcript_quality: {yaml_str(transcript_quality)}")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append(body_md)
    return md_lines


# -------- main --------

def main() -> None:
    """CLI entry point."""
    args = parse_args()
    url = args.youtube_url
    out_dir = Path(args.output_dir) if args.output_dir else Path.home() / "fabric" / "youtube"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[+] Fetching metadata for {url} with yt-dlp...")
    meta_json_str = run(["yt-dlp", "-J", url])
    meta: dict[str, Any] = json.loads(meta_json_str)

    title = meta.get("title") or "Untitled"
    uploader = meta.get("uploader") or meta.get("channel") or "Unknown"
    source_date = normalize_date(meta.get("upload_date"))
    duration = meta.get("duration")
    tags = meta.get("tags") or []
    description = meta.get("description") or ""
    webpage_url = meta.get("webpage_url") or url
    language = meta.get("language") or "en"
    video_id = meta.get("id") or slugify(title)
    created_date = datetime.now().date().isoformat()

    transcript_text, transcript_quality = extract_transcript(
        meta,
        download=args.download,
        out_dir=out_dir,
        video_id=video_id,
    )

    print("[+] Calling Fabric (extract_article_wisdom) on transcript...")
    fabric_input = f"INPUT:\n\n{title}\n\n{transcript_text}"
    body_md = run(
        ["fabric-ai", "--pattern", "extract_article_wisdom"],
        input_text=fabric_input,
    )

    print("[+] Building YAML front matter...")
    md_lines = build_markdown_lines(
        title=title,
        webpage_url=webpage_url,
        created_date=created_date,
        source_date=source_date,
        duration=duration,
        language=language,
        uploader=uploader,
        tags=tags,
        description=description,
        transcript_quality=transcript_quality,
        body_md=body_md,
    )

    slug = slugify(title)
    md_path = out_dir / f"{created_date}--{slug}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"[+] Wrote Markdown note: {md_path}")


if __name__ == "__main__":
    main()
