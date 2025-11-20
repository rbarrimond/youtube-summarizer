#!/usr/bin/env python3
"""youtube-summarizer: Generate a Fabric-ready Markdown note from a YouTube URL.

This script uses `yt-dlp` to fetch video metadata and (auto) subtitles, converts
the subtitles (SRT) to plain text, and then calls a Fabric pattern
(`extract_article_wisdom`) to distill the transcript into a structured wisdom
article. The output is a Markdown file with YAML front matter capturing key
attributes (title, dates, topics, transcript quality, etc.).

Typical usage:
    python yt_to_wisdom_md.py <youtube_url> [output_dir]

If `output_dir` is omitted it defaults to `~/fabric/youtube`.
"""
import subprocess
import json
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List

# -------- helpers --------

def run(cmd: list[str], input_text: str | None = None) -> str:
    """Run a subprocess command and return its stdout as a stripped string.

    Parameters:
        cmd: The command and arguments to execute.
        input_text: Optional text piped to the process' stdin.

    Returns:
        The standard output (with trailing whitespace removed).

    Raises:
        subprocess.CalledProcessError: If the command exits with a non-zero status.
    """
    result = subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()

def slugify(text: str) -> str:
    """Create a filesystem/URL friendly slug from arbitrary text.

    Steps performed:
        * Lowercase and trim
        * Remove non word/space/hyphen chars
        * Collapse whitespace/underscores/hyphens to single hyphen
        * Strip leading/trailing hyphens

    Returns "video" if the resulting slug would be empty.
    """
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text or "video"

def yaml_str(value: Any) -> str:
    """Serialize a Python value to a YAML-compatible string.

    Uses `json.dumps` to avoid adding a YAML dependency; JSON quoting is valid
    YAML. Ensures UTF-8 characters are preserved.
    """
    # JSON-style quoting is valid YAML and keeps us dependency-free
    return json.dumps(value, ensure_ascii=False)

def srt_to_text(srt_path: Path) -> str:
    """Convert an SRT subtitle file to plain text.

    Removes numerical indices, timestamps, and blank lines, returning a single
    string with newline-separated subtitle lines.

    Parameters:
        srt_path: Path to the `.srt` file.

    Returns:
        Concatenated subtitle text with minimal noise.
    """
    text = srt_path.read_text(encoding="utf-8", errors="ignore")
    lines: List[str] = []
    for line in text.splitlines():
        if re.match(r"^\d+$", line.strip()):  # index
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2},\d{3}", line.strip()):  # timestamp
            continue
        if not line.strip():
            continue
        lines.append(line.strip())
    return "\n".join(lines)

def normalize_date(yt_date: str | None) -> str | None:
    """Normalize a YouTube date string to ISO format where possible.

    yt-dlp typically supplies dates as `YYYYMMDD`. When that pattern matches we
    parse and convert to `YYYY-MM-DD`. If parsing fails or input is falsy, `None`
    is returned. Any non-matching format is passed through unchanged.

    Parameters:
        yt_date: Raw date string from metadata (may be None).

    Returns:
        ISO date string, original string, or None if invalid/falsy.
    """
    if not yt_date:
        return None
    # yt-dlp typically uses YYYYMMDD
    if re.fullmatch(r"\d{8}", yt_date):
        try:
            dt = datetime.strptime(yt_date, "%Y%m%d")
            return dt.date().isoformat()
        except ValueError:
            return None
    return yt_date

# -------- main --------

def main() -> None:
    """CLI entry point.

    Expects `<youtube_url>` and optional `[output_dir]`. Produces a Markdown
    note whose filename is `<created_date>--<slug>.md` in the output directory.
    Prints progress messages to stdout/stderr.
    """
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <youtube_url> [output_dir]", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    # default output directory: ~/fabric/youtube
    out_dir = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path.home() / "fabric" / "youtube"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[+] Fetching metadata for {url} with yt-dlp...")
    meta_json_str = run(["yt-dlp", "-J", url])
    meta: Dict[str, Any] = json.loads(meta_json_str)

    title = meta.get("title") or "Untitled"
    uploader = meta.get("uploader") or meta.get("channel") or "Unknown"
    upload_date_raw = meta.get("upload_date")
    source_date = normalize_date(upload_date_raw)
    duration = meta.get("duration")  # seconds
    tags = meta.get("tags") or []
    description = meta.get("description") or ""
    webpage_url = meta.get("webpage_url") or url
    language = meta.get("language") or "en"
    video_id = meta.get("id") or slugify(title)

    created_date = datetime.now().date().isoformat()

    print("[+] Downloading auto subtitles with yt-dlp...")
    srt_template = str(out_dir / f"{video_id}.%(ext)s")
    run([
        "yt-dlp",
        url,
        "--skip-download",
        "--write-auto-subs",
        "--sub-lang", "en",
        "--convert-subs", "srt",
        "-o", srt_template,
    ])

    srt_files = list(out_dir.glob(f"{video_id}*.srt"))
    if not srt_files:
        print("[!] No subtitles found. Transcript will be empty.", file=sys.stderr)
        transcript_text = ""
        transcript_quality = "none"
    else:
        transcript_text = srt_to_text(srt_files[0])
        transcript_quality = "auto"

    print("[+] Calling Fabric (extract_article_wisdom) on transcript...")
    # You’ve been doing this manually; this just automates it:
    # give the pattern the title and the full transcript.
    fabric_input = f"INPUT:\n\n{title}\n\n{transcript_text}"
    body_md = run(
        ["fabric", "--pattern", "extract_article_wisdom"],
        input_text=fabric_input,
    )

    print("[+] Building YAML front matter...")
    md_lines: List[str] = []
    md_lines.append("---")
    md_lines.append(f"title: {yaml_str(title)}")
    md_lines.append(f"source_type: {yaml_str('youtube_podcast')}")
    md_lines.append(f"original_url: {yaml_str(webpage_url)}")
    md_lines.append(f"created: {yaml_str(created_date)}")
    md_lines.append(f"source_date: {yaml_str(source_date) if source_date else 'null'}")
    md_lines.append(f"duration_seconds: {duration if duration is not None else 'null'}")
    md_lines.append(f"language: {yaml_str(language)}")
    md_lines.append(f"uploader: {yaml_str(uploader)}")

    # people/topics left empty for now; you can fill or extend later
    md_lines.append("people: []")

    # map yt-dlp tags into topics, minimal for now
    md_lines.append("topics:")
    if isinstance(tags, list) and tags:
        for tag in tags:
            md_lines.append(f"  - {yaml_str(tag)}")
    else:
        md_lines.append('  - "youtube"')

    # basic tags set; feel free to expand
    md_lines.append("tags:")
    md_lines.append('  - "YouTube"')

    # description: first line of YT description, short-ish
    short_desc = description.strip().split("\n")[0][:280]
    md_lines.append(f"description: {yaml_str(short_desc)}")

    md_lines.append(f"transcript_source: {yaml_str('yt-dlp')}")
    md_lines.append(f"transcript_quality: {yaml_str(transcript_quality)}")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append(body_md)

    slug = slugify(title)
    md_path = out_dir / f"{created_date}--{slug}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"[+] Wrote Markdown note: {md_path}")

if __name__ == "__main__":
    main()