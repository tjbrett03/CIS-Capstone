"""Readability scoring for finished narratives.

Wraps textstat's Flesch Reading Ease and translates the raw score into a
plain-language grade band. Compares the result against the selected
audience's target reading level so the staff member sees immediately
whether the draft is pitched correctly.
"""
import re

import textstat


# Flesch Reading Ease → approximate U.S. grade band.
# Thresholds follow the standard Flesch interpretation.
_BANDS = [
    (90, 4, 5, "4th–5th grade"),
    (80, 5, 6, "5th–6th grade"),
    (70, 6, 7, "6th–7th grade"),
    (60, 7, 8, "7th–8th grade"),
    (50, 9, 10, "9th–10th grade"),
    (30, 11, 13, "11th grade – college"),
    (0,  14, 16, "college graduate"),
]


def _band(score: float) -> tuple[int, int, str]:
    for threshold, lo, hi, label in _BANDS:
        if score >= threshold:
            return lo, hi, label
    return _BANDS[-1][1], _BANDS[-1][2], _BANDS[-1][3]


def _audience_range(audience_level: str) -> tuple[int, int]:
    # Audience strings look like "6–8th grade" or "10–12th grade".
    m = re.search(r"(\d+)\D+(\d+)", audience_level)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 6, 12  # safe default if format ever changes


def score(text: str, audience_level: str) -> dict:
    """Return Flesch score plus a plain-language comparison to the target audience."""
    if not text or not text.strip():
        return {
            "score": None,
            "grade_label": "unavailable",
            "audience_target": audience_level,
            "match": "unavailable",
            "summary": "Readability could not be calculated.",
        }

    flesch = round(textstat.flesch_reading_ease(text), 1)
    lo, hi, label = _band(flesch)
    target_lo, target_hi = _audience_range(audience_level)

    # Bands match if they overlap at all.
    if hi < target_lo:
        match = "too_simple"
        verdict = f"easier than the target audience ({audience_level}) — consider adding more specific detail."
    elif lo > target_hi:
        match = "too_complex"
        verdict = f"harder than the target audience ({audience_level}) — consider shorter sentences or simpler words."
    else:
        match = "matches"
        verdict = f"appropriate for the target audience ({audience_level})."

    return {
        "score": flesch,
        "grade_label": label,
        "audience_target": audience_level,
        "match": match,
        "summary": f"Reading level: {label} — {verdict}",
    }
