"""
Scene Matcher Module (Stage 2)

Stage 1 gave us parsed movie + narration subtitles.
Stage 2 matches each narration line to the closest movie dialogue,
then builds a "cut plan" (movie start/end times to keep for each line).

Later stages can use this cut plan with ffmpeg to actually cut the video.
"""

from __future__ import annotations

import re
import sys
from difflib import SequenceMatcher

from srt_parser import parse_narration_srt, parse_srt

# Words that are too common to help with matching
_STOP_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "to",
    "of",
    "in",
    "on",
    "at",
    "for",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "this",
    "that",
    "these",
    "those",
    "it",
    "he",
    "she",
    "they",
    "we",
    "you",
    "i",
    "me",
    "my",
    "his",
    "her",
    "their",
    "our",
    "with",
    "from",
    "as",
    "by",
    "into",
    "about",
    "over",
    "there",
    "here",
    "scene",
    "finally",
}


def _normalize_text(text: str) -> str:
    """
    Make text easier to compare:
    - lowercase
    - remove punctuation
    - keep only letters/numbers/spaces
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _light_stem(word: str) -> str:
    """
    Very light English stem so welcome/welcomes/welcoming align.
    Not a full Porter stemmer — just enough for subtitle matching.
    """
    if len(word) <= 3:
        return word
    for suffix in ("ing", "ies", "ied", "ers", "est", "ed", "es", "ly", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _tokens(text: str) -> set[str]:
    """Split normalized text into useful stemmed words (skip tiny / stop words)."""
    words = _normalize_text(text).split()
    out: set[str] = set()
    for w in words:
        if len(w) <= 2 or w in _STOP_WORDS:
            continue
        out.add(_light_stem(w))
    return out


def _bigrams(text: str) -> set[str]:
    """Ordered bigrams from word order (after stem + stop filter)."""
    words = []
    for w in _normalize_text(text).split():
        if len(w) <= 2 or w in _STOP_WORDS:
            continue
        words.append(_light_stem(w))
    return {f"{words[i]}_{words[i + 1]}" for i in range(len(words) - 1)}


def similarity_score(text_a: str, text_b: str) -> float:
    """
    Score how similar two subtitle / scene texts are (0.0 to 1.0).

    Mix:
      1) Jaccard on stemmed keywords
      2) Coverage — how much of narration (A) appears in scene (B)
         (helps when VO paraphrases a longer scene)
      3) Bigram overlap (phrase-ish signal)
      4) SequenceMatcher on normalized strings
    """
    tokens_a = _tokens(text_a)
    tokens_b = _tokens(text_b)

    if tokens_a or tokens_b:
        overlap = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b) or 1
        jaccard = overlap / union
        coverage = overlap / (len(tokens_a) or 1)
    else:
        jaccard = 0.0
        coverage = 0.0

    big_a = _bigrams(text_a)
    big_b = _bigrams(text_b)
    if big_a and big_b:
        bigram = len(big_a & big_b) / (len(big_a | big_b) or 1)
    else:
        bigram = 0.0

    seq = SequenceMatcher(
        None,
        _normalize_text(text_a),
        _normalize_text(text_b),
    ).ratio()

    # Coverage weighted high: narration→scene paraphrase matching
    return (0.35 * jaccard) + (0.30 * coverage) + (0.15 * bigram) + (0.20 * seq)


def find_best_movie_match(
    narration_entry: dict,
    movie_entries: list[dict],
    used_movie_indexes: set[int] | None = None,
    min_score: float = 0.12,
) -> dict | None:
    """
    Find the best movie subtitle for one narration line.

    Args:
        narration_entry: one narration dict from Stage 1
        movie_entries: full movie subtitle list
        used_movie_indexes: movie indexes already taken (avoid reuse)
        min_score: ignore very weak matches below this score

    Returns:
        A match dict, or None if nothing is good enough.
    """
    used_movie_indexes = used_movie_indexes or set()
    best = None
    best_score = -1.0

    for movie in movie_entries:
        if movie["index"] in used_movie_indexes:
            continue

        score = similarity_score(narration_entry["text"], movie["text"])
        if score > best_score:
            best_score = score
            best = movie

    if best is None or best_score < min_score:
        return None

    return {
        "movie_index": best["index"],
        "movie_text": best["text"],
        "movie_start": best["start"],
        "movie_end": best["end"],
        "score": round(best_score, 3),
    }


def match_scenes(
    movie_entries: list[dict],
    narration_entries: list[dict],
    min_score: float = 0.12,
    pad_seconds: float = 0.35,
) -> list[dict]:
    """
    Match every narration line to a movie dialogue window.

    Returns a cut plan list. Each item looks like:
    {
        "narration_index": 1,
        "narration_text": "...",
        "narration_start": 0.5,
        "narration_end": 3.0,
        "movie_index": 2,
        "movie_text": "...",
        "movie_start": 3.65,   # padded start (for a softer cut)
        "movie_end": 6.55,     # padded end
        "score": 0.42,
        "matched": True,
    }

    If a narration line has no good match, matched=False and movie_* are None.
    """
    if not movie_entries:
        raise ValueError("Movie subtitle list is empty — matching nahi ho sakta.")
    if not narration_entries:
        raise ValueError("Narration subtitle list is empty — matching nahi ho sakta.")

    used_movie_indexes: set[int] = set()
    cut_plan: list[dict] = []

    for narration in narration_entries:
        match = find_best_movie_match(
            narration,
            movie_entries,
            used_movie_indexes=used_movie_indexes,
            min_score=min_score,
        )

        if match is None:
            cut_plan.append(
                {
                    "narration_index": narration["index"],
                    "narration_text": narration["text"],
                    "narration_start": narration["start"],
                    "narration_end": narration["end"],
                    "movie_index": None,
                    "movie_text": None,
                    "movie_start": None,
                    "movie_end": None,
                    "score": 0.0,
                    "matched": False,
                }
            )
            continue

        used_movie_indexes.add(match["movie_index"])

        # Small padding so cuts don't feel too abrupt
        movie_start = max(0.0, match["movie_start"] - pad_seconds)
        movie_end = match["movie_end"] + pad_seconds

        cut_plan.append(
            {
                "narration_index": narration["index"],
                "narration_text": narration["text"],
                "narration_start": narration["start"],
                "narration_end": narration["end"],
                "movie_index": match["movie_index"],
                "movie_text": match["movie_text"],
                "movie_start": round(movie_start, 3),
                "movie_end": round(movie_end, 3),
                "score": match["score"],
                "matched": True,
            }
        )

    return cut_plan


def summarize_cut_plan(cut_plan: list[dict]) -> dict:
    """Return simple stats: total lines, matched count, unmatched count."""
    matched = sum(1 for item in cut_plan if item["matched"])
    return {
        "total_narration_lines": len(cut_plan),
        "matched": matched,
        "unmatched": len(cut_plan) - matched,
    }


def _print_cut_plan(cut_plan: list[dict]) -> None:
    """Print the cut plan in a readable way for CLI testing."""
    stats = summarize_cut_plan(cut_plan)
    print("\n=== Stage 2 Cut Plan ===")
    print(
        f"Total narration lines: {stats['total_narration_lines']} | "
        f"Matched: {stats['matched']} | Unmatched: {stats['unmatched']}"
    )

    for item in cut_plan:
        if item["matched"]:
            print(
                f"\n  Narration [{item['narration_index']}] "
                f"({item['narration_start']:.2f}s-{item['narration_end']:.2f}s)"
            )
            print(f"    VO: {item['narration_text']}")
            print(
                f"    -> Movie [{item['movie_index']}] "
                f"{item['movie_start']:.2f}s-{item['movie_end']:.2f}s "
                f"(score={item['score']:.3f})"
            )
            print(f"       Dialogue: {item['movie_text']}")
        else:
            print(
                f"\n  Narration [{item['narration_index']}] "
                f"NO MATCH | {item['narration_text']}"
            )


def main() -> None:
    """
    Command-line test helper.

    Usage:
        python scene_matcher.py <movie.srt> <narration.srt>
    """
    if len(sys.argv) != 3:
        print("Usage: python scene_matcher.py <movie_srt_path> <narration_srt_path>")
        sys.exit(1)

    movie_path = sys.argv[1]
    narration_path = sys.argv[2]

    try:
        movie_entries = parse_srt(movie_path)
        narration_entries = parse_narration_srt(narration_path)
        cut_plan = match_scenes(movie_entries, narration_entries)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    _print_cut_plan(cut_plan)


if __name__ == "__main__":
    main()
