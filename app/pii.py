"""PII scanner for finished narratives.

Scans Claude's output text against six categories of personally identifiable
information common in nonprofit program narratives. Returns structured
findings with category, reason, and suggested replacement so the UI can
highlight and explain each flag.

Hybrid approach: Presidio (spaCy NER) for names/locations/orgs, custom regex
and keyword lists for legal, health, and immigration patterns Presidio does
not handle well.

Errs on the side of over-flagging — staff dismiss false positives in
seconds; missed disclosures cause real harm.
"""
import re
from typing import Optional

from presidio_analyzer import AnalyzerEngine

_analyzer: Optional[AnalyzerEngine] = None


def _engine() -> AnalyzerEngine:
    # Lazy by default; call warmup() at app boot to absorb the spaCy load cost
    # before the first request instead of on the first scan.
    global _analyzer
    if _analyzer is None:
        _analyzer = AnalyzerEngine()
    return _analyzer


def warmup() -> None:
    """Load the Presidio engine eagerly. Call from create_app() so the spaCy
    model is in memory before the first interview completes."""
    _engine()


# --- Category metadata -----------------------------------------------------

CATEGORIES = {
    1: "Direct identifier",
    2: "Location identifier",
    3: "Relationship identifier",
    4: "Case or legal identifier",
    5: "Health or behavioral identifier",
    6: "Immigration or legal status",
    7: "Date combined with specific event",
}


# --- Custom keyword/regex sources ------------------------------------------

# Category 3: relationship words. A capitalized name following any of these
# is almost certainly a family-member identifier.
RELATIONSHIP_WORDS = [
    "daughter", "son", "child", "kid", "baby",
    "husband", "wife", "spouse", "partner", "boyfriend", "girlfriend",
    "mother", "father", "mom", "dad", "parent",
    "sister", "brother", "sibling",
    "grandmother", "grandfather", "grandma", "grandpa",
    "aunt", "uncle", "cousin", "niece", "nephew",
]
# Case-insensitive only on the relationship word; the name capture stays
# case-sensitive so lowercase words like 'who'/'and' can't be miscaptured.
RELATIONSHIP_RE = re.compile(
    r"\b(?i:" + "|".join(RELATIONSHIP_WORDS) + r")\s+([A-Z][a-z]+)\b"
)

# Category 2: facility-name patterns. Catches things Presidio's LOCATION
# entity often misses (treatment centers, shelters, recovery programs).
FACILITY_KEYWORDS = [
    "Recovery Center", "Treatment Center", "Rehabilitation Center", "Rehab Center",
    "Recovery Program", "Treatment Program",
    "Shelter", "Halfway House", "Sober House", "Sober Living",
    "Detox", "Hospital", "Clinic", "Medical Center",
    "Counseling Center", "Mental Health Center",
]
# Single alternation regex: optional 0-3 capitalized words preceding a facility keyword.
FACILITY_RE = re.compile(
    r"\b(?:[A-Z][a-z]+\s+){0,3}(?:"
    + "|".join(re.escape(k) for k in FACILITY_KEYWORDS)
    + r")\b"
)

# Category 4: court-name patterns and case-number formats.
COURT_PATTERN = re.compile(
    r"\b(?:[A-Z][a-z]+\s+){1,3}(?:County|Superior|District|Circuit|Municipal|Family|Juvenile)\s+Court\b"
)
CASE_NUMBER_PATTERN = re.compile(
    r"\bcase\s+(?:no\.?|number|#)\s*[A-Z0-9\-]{4,}\b", re.IGNORECASE
)
LEGAL_DATE_KEYWORDS = ["hearing", "trial", "sentencing", "arraignment", "verdict", "plea"]
LEGAL_KEYWORDS_RE = re.compile(
    r"\b(?:" + "|".join(LEGAL_DATE_KEYWORDS) + r")\b", re.IGNORECASE
)

# Category 5: medication names (common in addiction/mental health contexts)
# and diagnosis cue words. Extend as patterns emerge.
MEDICATIONS = [
    "Suboxone", "Methadone", "Naloxone", "Narcan", "Vivitrol", "Buprenorphine",
    "Prozac", "Zoloft", "Lexapro", "Paxil", "Celexa", "Effexor", "Wellbutrin",
    "Xanax", "Klonopin", "Ativan", "Valium", "Adderall", "Ritalin", "Vyvanse",
    "Lithium", "Seroquel", "Abilify", "Risperdal",
]
MEDICATION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(m) for m in MEDICATIONS) + r")\b",
    re.IGNORECASE,
)
DIAGNOSIS_PATTERNS = [
    re.compile(r"\bdiagnosed\s+with\s+[A-Za-z\s,]+", re.IGNORECASE),
    re.compile(r"\b(?:PTSD|ADHD|OCD|MDD|GAD)\b"),
    re.compile(
        r"\b(?:bipolar|schizophrenia|schizoaffective|borderline\s+personality|"
        r"major\s+depressive|generalized\s+anxiety|panic\s+disorder|"
        r"eating\s+disorder|substance\s+use\s+disorder)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b\w+\s+(?:disorder|syndrome)\b", re.IGNORECASE),
    re.compile(r"\bprescribed\s+\w+", re.IGNORECASE),
]

# Category 6: immigration and legal-status phrases.
IMMIGRATION_PHRASES = [
    "undocumented", "no documentation", "no papers", "no status",
    "immigration status", "afraid of authorities", "afraid to call the police",
    "ICE", "deportation", "deported", "asylum", "visa expired", "overstayed",
]
LEGAL_STATUS_PHRASES = [
    "on parole", "on probation", "on house arrest", "incarcerated",
    "released from prison", "released from jail", "in custody",
]
IMMIGRATION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in IMMIGRATION_PHRASES) + r")\b",
    re.IGNORECASE,
)
LEGAL_STATUS_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in LEGAL_STATUS_PHRASES) + r")\b",
    re.IGNORECASE,
)

# Category 7: date + life event. Detect a month name or numeric date paired
# with employer/job-change vocabulary in the same sentence.
MONTH_PATTERN = re.compile(
    r"\b(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\b",
    re.IGNORECASE,
)
NUMERIC_DATE_PATTERN = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
EMPLOYMENT_PATTERN = re.compile(
    r"\b(?:lost\s+(?:her|his|their)\s+job|fired|laid\s+off|hired\s+at|"
    r"started\s+working|left\s+(?:her|his|their)\s+job|"
    r"at\s+the\s+\w+|employer|workplace|factory|warehouse|company)\b",
    re.IGNORECASE,
)


# --- Suggestions -----------------------------------------------------------
# Per-category replacement guidance shown alongside each flag.

SUGGESTIONS = {
    1: "Replace the name with a pronoun ('she', 'he', 'they') or a generic descriptor ('a program participant').",
    2: "Remove the specific name and describe the type of place instead ('a residential treatment program', 'a local shelter').",
    3: "Remove the family member's name. The relationship word alone is sufficient ('her daughter', 'his son').",
    4: "Remove the specific court, case number, or date. Describe the proceeding generically ('a court hearing', 'a custody case').",
    5: "Remove the specific medication or diagnosis. Describe the situation more broadly ('mental health treatment', 'medication support').",
    6: "Remove any reference to immigration or legal status. This information should never appear in a public narrative without explicit, informed consent.",
    7: "Remove either the specific date or the specific event detail. The combination can identify someone in a small community.",
}


# --- Scanner ---------------------------------------------------------------

def _finding(text: str, start: int, end: int, category: int, reason: str, suggestion: str = None) -> dict:
    return {
        "text": text[start:end],
        "start": start,
        "end": end,
        "category": category,
        "category_name": CATEGORIES[category],
        "reason": reason,
        "suggestion": suggestion if suggestion is not None else SUGGESTIONS[category],
    }


def _scan_presidio(text: str) -> list[dict]:
    """Names, locations, organizations via spaCy NER."""
    findings = []
    results = _engine().analyze(
        text=text,
        entities=["PERSON", "LOCATION", "ORGANIZATION", "PHONE_NUMBER", "EMAIL_ADDRESS"],
        language="en",
    )
    for r in results:
        if r.entity_type == "PERSON":
            findings.append(_finding(
                text, r.start, r.end, 1,
                "Detected as a personal name. Names — including first names alone — can identify someone in a small community where program participation is known.",
            ))
        elif r.entity_type in ("LOCATION", "ORGANIZATION"):
            span = text[r.start:r.end]
            # spaCy tags short ALL-CAPS tokens as LOCATION because they look
            # like state abbreviations or airport codes. Reclassify those as
            # Cat 1 (initials / nickname).
            if span.isalpha() and span.isupper() and len(span) <= 4:
                findings.append(_finding(
                    text, r.start, r.end, 1,
                    "Detected as a short identifier — could be initials, a nickname, or a place abbreviation. Review which applies and whether it identifies the person.",
                    suggestion="If this is initials or a nickname, replace with a pronoun or generic descriptor. If it's a place abbreviation, remove it or describe the location more generally.",
                ))
            else:
                findings.append(_finding(
                    text, r.start, r.end, 2,
                    f"Detected as a specific {r.entity_type.lower()}. Identifying a place narrows the audience to a small pool in a small community.",
                ))
        elif r.entity_type == "PHONE_NUMBER":
            findings.append(_finding(
                text, r.start, r.end, 1,
                "Phone number detected. Direct contact information should never appear in a public narrative.",
            ))
        elif r.entity_type == "EMAIL_ADDRESS":
            findings.append(_finding(
                text, r.start, r.end, 1,
                "Email address detected. Direct contact information should never appear in a public narrative.",
            ))
    return findings


def _scan_relationship_names(text: str) -> list[dict]:
    """Capitalized name following a relationship word — e.g. 'daughter Sofia'."""
    findings = []
    for m in RELATIONSHIP_RE.finditer(text):
        if m.group(1) in _NAME_BLACKLIST:
            continue
        findings.append(_finding(
            text, m.start(1), m.end(1), 3,
            f"Proper name following a relationship word ('{m.group(0).split()[0].lower()}'). Family members — especially minors — cannot consent to being named in public narratives.",
        ))
    return findings


# Capitalized words that aren't names but commonly appear after relationship
# words at sentence boundaries — skip these to reduce false positives.
_NAME_BLACKLIST = {
    "Who", "What", "When", "Where", "Why", "How", "Whose", "Which",
    "She", "He", "They", "Her", "His", "Their", "Them",
    "The", "A", "An", "And", "Or", "But", "So", "Then", "Now",
    "I", "We", "You", "It",
    "Is", "Was", "Were", "Has", "Had", "Have",
}


def _scan_facilities(text: str) -> list[dict]:
    """Treatment centers, shelters, etc. that Presidio LOCATION often misses."""
    findings = []
    for m in FACILITY_RE.finditer(text):
        findings.append(_finding(
            text, m.start(), m.end(), 2,
            "Specific facility or program name. Naming a facility identifies the person's history without their explicit consent.",
        ))
    return findings


def _scan_legal(text: str) -> list[dict]:
    findings = []
    for m in COURT_PATTERN.finditer(text):
        findings.append(_finding(
            text, m.start(), m.end(), 4,
            "Specific court name. A named court — especially in a small jurisdiction — can identify the person involved.",
        ))
    for m in CASE_NUMBER_PATTERN.finditer(text):
        findings.append(_finding(
            text, m.start(), m.end(), 4,
            "Case or docket number. Unique identifiers tie the narrative directly to a public legal record.",
        ))
    # Date paired with legal-proceeding word in the same sentence.
    for sent_start, sent_end, sentence in _sentences(text):
        has_date = MONTH_PATTERN.search(sentence) or NUMERIC_DATE_PATTERN.search(sentence)
        legal_hit = LEGAL_KEYWORDS_RE.search(sentence)
        if has_date and legal_hit:
            findings.append(_finding(
                text, sent_start, sent_end, 4,
                f"Specific date combined with a legal proceeding ('{legal_hit.group(0).lower()}'). The combination can identify someone via public court records.",
            ))
    return findings


def _scan_health(text: str) -> list[dict]:
    findings = []
    for m in MEDICATION_RE.finditer(text):
        findings.append(_finding(
            text, m.start(), m.end(), 5,
            f"Medication name ('{m.group(0)}'). Specific medications are identifiable health information.",
        ))
    for pattern in DIAGNOSIS_PATTERNS:
        for m in pattern.finditer(text):
            findings.append(_finding(
                text, m.start(), m.end(), 5,
                "Specific diagnosis or treatment detail. May exceed what the person consented to share publicly.",
            ))
    return findings


def _scan_status(text: str) -> list[dict]:
    findings = []
    for m in IMMIGRATION_RE.finditer(text):
        findings.append(_finding(
            text, m.start(), m.end(), 6,
            "Reference to immigration status. This information should not appear in a public narrative without explicit, informed consent.",
        ))
    for m in LEGAL_STATUS_RE.finditer(text):
        findings.append(_finding(
            text, m.start(), m.end(), 6,
            "Reference to criminal legal status. May reveal information beyond what was intentionally shared.",
        ))
    return findings


def _scan_date_event(text: str) -> list[dict]:
    """Sentence-level: specific date paired with employment/life event."""
    findings = []
    for sent_start, sent_end, sentence in _sentences(text):
        has_date = MONTH_PATTERN.search(sentence) or NUMERIC_DATE_PATTERN.search(sentence)
        employment_hit = EMPLOYMENT_PATTERN.search(sentence)
        if has_date and employment_hit:
            findings.append(_finding(
                text, sent_start, sent_end, 7,
                "Specific date paired with employment or life event. The combination can identify someone in a small community.",
            ))
    return findings


def _sentences(text: str):
    """Yield (start, end, sentence_text) for each sentence in text."""
    for m in re.finditer(r"[^.!?]+[.!?]?", text):
        s = m.group().strip()
        if s:
            yield m.start(), m.end(), s


def _dedupe(findings: list[dict]) -> list[dict]:
    """Resolve overlapping findings.

    More specific categories (3=relationship, 4=legal, 5=health, 6=status,
    7=date+event) win over broader ones (1=name, 2=location) on the same
    span — staff get the most informative reason and suggestion.
    """
    if not findings:
        return findings
    priority = {3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 1: 1, 2: 1}
    findings.sort(key=lambda f: (f["start"], priority.get(f["category"], 2)))
    kept = []
    for f in findings:
        if any(_overlaps(f, k) for k in kept):
            continue
        kept.append(f)
    return kept


def _overlaps(a: dict, b: dict) -> bool:
    return not (a["end"] <= b["start"] or b["end"] <= a["start"])


def scan(text: str) -> list[dict]:
    """Return a list of PII findings sorted by position in the text."""
    if not text or not text.strip():
        return []
    findings = []
    findings.extend(_scan_presidio(text))
    findings.extend(_scan_relationship_names(text))
    findings.extend(_scan_facilities(text))
    findings.extend(_scan_legal(text))
    findings.extend(_scan_health(text))
    findings.extend(_scan_status(text))
    findings.extend(_scan_date_event(text))
    deduped = _dedupe(findings)
    deduped.sort(key=lambda f: f["start"])
    return deduped
