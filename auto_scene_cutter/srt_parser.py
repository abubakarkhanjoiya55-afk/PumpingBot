"""
SRT Parser Module (Stage 1)

Reads .srt subtitle files and turns them into a simple list of dictionaries.
We'll use this later to match movie dialogue with narration/voiceover timing.
"""

import re
import sys
from pathlib import Path

import pysrt


def _clean_text(text: str) -> str:
    """
    Remove HTML-like tags from subtitle text.

    Subtitles often contain tags like <i>, <b>, or <font ...>.
    This strips those so we only keep the readable words.
    """
    # Remove tags such as <i>, </i>, <font color="white">, etc.
    cleaned = re.sub(r"<[^>]+>", "", text)
    # Normalize whitespace (newlines / extra spaces become single spaces)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _time_to_seconds(time_obj) -> float:
    """
    Convert a pysrt time object into total seconds as a float.

    Example: 00:01:30,500  ->  90.5
    pysrt stores milliseconds in `.ordinal`, so we divide by 1000.
    """
    return time_obj.ordinal / 1000.0


def parse_srt(file_path: str) -> list[dict]:
    """
    Parse a movie (or general) .srt subtitle file.

    Args:
        file_path: Path to the .srt file on disk.

    Returns:
        A list of dictionaries. Each dictionary looks like:
        {
            "index": 1,                 # subtitle number
            "text": "Hello there.",     # cleaned subtitle text
            "start": 1.5,               # start time in seconds
            "end": 3.2,                 # end time in seconds
        }

    Raises:
        FileNotFoundError: If the file path does not exist.
        ValueError: If the SRT content cannot be parsed.
    """
    path = Path(file_path)

    # Clear error if the file is missing (instead of a confusing crash later)
    if not path.exists():
        raise FileNotFoundError(f"SRT file not found: {file_path}")

    if not path.is_file():
        raise FileNotFoundError(f"Path is not a file: {file_path}")

    try:
        # Read the raw file first so we can detect empty / junk content
        raw_text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ValueError(f"Could not read SRT file '{file_path}': {exc}") from exc

    if not raw_text.strip():
        raise ValueError(f"SRT file is empty: {file_path}")

    try:
        # pysrt.open reads the whole subtitle file into a list-like object
        subs = pysrt.open(str(path))
    except Exception as exc:
        # Catch malformed / unreadable SRT and re-raise with a clearer message
        raise ValueError(f"Failed to parse SRT file '{file_path}': {exc}") from exc

    # pysrt is often quiet on junk input and returns []. Treat that as malformed.
    if len(subs) == 0:
        raise ValueError(
            f"SRT file appears malformed or contains no valid subtitles: {file_path}"
        )

    entries = []
    for item in subs:
        entries.append(
            {
                "index": item.index,
                "text": _clean_text(item.text),
                "start": _time_to_seconds(item.start),
                "end": _time_to_seconds(item.end),
            }
        )

    return entries


def parse_narration_srt(file_path: str) -> list[dict]:
    """
    Parse a narration / voiceover .srt file.

    This returns the same structure as parse_srt().
    It exists as a separate function so later stages can treat narration
    differently from movie dialogue (for example, matching or cutting logic).

    Args:
        file_path: Path to the narration .srt file on disk.

    Returns:
        Same list-of-dictionaries format as parse_srt().
    """
    # For Stage 1, parsing is identical — we just keep a clear name for later use.
    return parse_srt(file_path)


def _print_entries(label: str, entries: list[dict], limit: int = 5) -> None:
    """Print a short readable preview of parsed subtitle entries."""
    print(f"\n=== {label} ===")
    print(f"Total entries: {len(entries)}")
    print(f"First {min(limit, len(entries))} entries:")

    for entry in entries[:limit]:
        print(
            f"  [{entry['index']}] "
            f"{entry['start']:.3f}s -> {entry['end']:.3f}s | "
            f"{entry['text']}"
        )


def main() -> None:
    """
    Command-line test helper.

    Usage:
        python srt_parser.py <movie.srt> <narration.srt>
    """
    if len(sys.argv) != 3:
        print("Usage: python srt_parser.py <movie_srt_path> <narration_srt_path>")
        sys.exit(1)

    movie_path = sys.argv[1]
    narration_path = sys.argv[2]

    try:
        movie_entries = parse_srt(movie_path)
        narration_entries = parse_narration_srt(narration_path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    _print_entries("Movie SRT", movie_entries)
    _print_entries("Narration SRT", narration_entries)


if __name__ == "__main__":
    main()
