"""Advisory grounding verifier for LLM-rendered narratives.

The Phase 3 plan calls for a verifier that runs on completed sentences during
streaming, flagging numeric or entity claims that aren't backed by either an
LLM-emitted `[[Module:field:value]]` anchor or a value present in the
structured_inputs payload. This module implements the per-sentence verification
logic; Step 5 ships it in **advisory mode** — we emit a report event but do
not strip, regenerate, or otherwise mutate the user-facing text.

A note on streaming: the briarwood LLM client returns the full draft from a
synchronous `complete()` call, so "sentence-boundary verification during
streaming" reduces to splitting the completed draft into sentences and running
the verifier per sentence. The wall-clock effect on the user is identical
because the adapter chunks the cleaned text into word-sized text_delta frames
itself.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

# `[[Module:field:value]]` marker. Module + field are bare identifiers; value
# can contain anything except `[]`. Mirrors the stripper in
# briarwood/agent/composer.py — keep these patterns in sync.
_ANCHOR_RE = re.compile(r"\[\[([^\[\]:]+):([^\[\]:]+):([^\[\]]+)\]\]")

# Sentence terminator regex for splitting LLM drafts. Conservative: only break
# on `.`, `?`, `!` followed by whitespace; do not split inside abbreviations or
# decimal numbers because a cited value like `$1.2M` contains a `.`.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")

# Numeric token extractor. Order matters in the alternation below — currency
# and percentages need to win over the bare-integer fallback. Each capture is
# normalized into a comparable string downstream.
_NUMBER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("currency_short", re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s?([KkMmBb])")),
    ("currency", re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)")),
    ("percent", re.compile(r"(-?\d+(?:\.\d+)?)\s?%")),
    ("multiplier", re.compile(r"(\d+(?:\.\d+)?)\s?[xX]\b")),
    ("bare_int", re.compile(r"(?<![\w.$%])(\d{3,})(?![\w%])")),
]

# Phrases that signal an explicitly ungrounded response — these are OK and not
# violations, but the UI may render them differently (Step 6 muted variant).
_UNGROUNDED_SENTINELS = (
    "we don't have a model output",
    "we do not have a model output",
    "no model output for that",
    "no model output available",
)

# Hedging words the prompt forbids. Counted as soft violations (kind:
# `forbidden_hedge`) so we can measure prompt drift without blocking output.
_FORBIDDEN_HEDGES = (
    "generally speaking",
    "typically",
    "as of my last update",
    "in most cases",
    "it depends on many factors",
    "broadly speaking",
)


@dataclass
class Anchor:
    """An LLM-emitted `[[Module:field:value]]` citation marker."""

    module: str
    field: str
    value: str

    @property
    def normalized_value(self) -> str:
        return _normalize_token(self.value)


@dataclass
class Violation:
    """A grounding rule that the LLM's draft did not satisfy."""

    kind: str          # "ungrounded_number" | "ungrounded_entity" | "forbidden_hedge"
    sentence: str
    value: str
    reason: str


@dataclass
class VerifierReport:
    tier: str | None = None
    sentences_total: int = 0
    sentences_with_violations: int = 0
    ungrounded_declaration: bool = False
    anchor_count: int = 0
    anchors: list[Anchor] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "sentences_total": self.sentences_total,
            "sentences_with_violations": self.sentences_with_violations,
            "ungrounded_declaration": self.ungrounded_declaration,
            "anchor_count": self.anchor_count,
            "anchors": [asdict(a) for a in self.anchors],
            "violations": [asdict(v) for v in self.violations],
        }


# ---------- Helpers ----------


def _normalize_token(s: str) -> str:
    """Reduce a number-like string to a comparable canonical form. Strips $,
    commas, percent signs, trailing 'x', shortened K/M/B suffixes (expanding
    them), and trims trailing zeros after a decimal."""
    raw = s.strip().lower()
    raw = raw.replace("$", "").replace(",", "").replace("%", "").replace(" ", "")
    mult = 1.0
    if raw.endswith("k"):
        mult = 1_000
        raw = raw[:-1]
    elif raw.endswith("m"):
        mult = 1_000_000
        raw = raw[:-1]
    elif raw.endswith("b"):
        mult = 1_000_000_000
        raw = raw[:-1]
    elif raw.endswith("x"):
        raw = raw[:-1]
    try:
        n = float(raw) * mult
    except ValueError:
        return raw
    if n.is_integer():
        return str(int(n))
    # Round to four decimal places to absorb float noise from percent <-> fraction
    # conversions (e.g. 0.1 vs 0.10000000000000009).
    return f"{round(n, 4)}"


def _flatten_input_values(payload: Any) -> set[str]:
    """Walk a nested structured_inputs dict/list and collect every numeric
    value as a normalized token. We compare extracted draft numbers against
    this set as a coarse "is this number grounded?" check.

    Strings that look numeric are included; pure prose is skipped — entity
    matching is handled separately.
    """
    out: set[str] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)
        elif isinstance(node, bool):
            return  # bools are ints in Python; skip so True/False aren't read as 1/0
        elif isinstance(node, (int, float)):
            tok = _normalize_token(str(node))
            out.add(tok)
            # Also record common rounded variants the LLM may surface (e.g.
            # write 820000 as $820k, or 0.105 as 10.5%).
            if isinstance(node, float):
                out.add(_normalize_token(str(round(node * 100, 2))))
            if isinstance(node, (int, float)) and abs(node) >= 1000:
                out.add(_normalize_token(f"{round(node / 1000)}k"))
                out.add(_normalize_token(f"{round(node / 1_000_000, 2)}m"))
        elif isinstance(node, str):
            stripped = node.strip()
            if stripped:
                tok = _normalize_token(stripped)
                if tok and tok != stripped.lower():
                    out.add(tok)

    _walk(payload)
    out.discard("")
    return out


def _flatten_input_strings(payload: Any) -> set[str]:
    """Collect every lowercased string value from the payload — used for the
    entity-grounding check. We don't tokenize; sentence comparison is a
    substring check, so the set holds full strings."""
    out: set[str] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)
        elif isinstance(node, str):
            stripped = node.strip()
            if stripped:
                out.add(stripped.lower())

    _walk(payload)
    return out


def extract_anchors(text: str) -> list[Anchor]:
    """Parse `[[Module:field:value]]` citation markers from an LLM draft."""
    return [
        Anchor(module=m.group(1).strip(), field=m.group(2).strip(), value=m.group(3).strip())
        for m in _ANCHOR_RE.finditer(text)
    ]


def extract_numbers(sentence: str) -> list[tuple[str, str]]:
    """Pull number-like tokens out of a sentence. Returns `(raw_match, kind)`
    tuples so callers can both reason about token type and surface the
    original substring in violation reports."""
    found: list[tuple[str, str]] = []
    spans: list[tuple[int, int]] = []
    for kind, pat in _NUMBER_PATTERNS:
        for m in pat.finditer(sentence):
            start, end = m.span()
            if any(s <= start < e or s < end <= e for s, e in spans):
                continue
            spans.append((start, end))
            found.append((m.group(0).strip(), kind))
    return found


def split_sentences(text: str) -> list[str]:
    """Split a draft into sentences for per-sentence verification. We treat
    newlines as hard breaks (the prompts produce one-sentence-per-line for
    bullet lists) and the standard `[.!?]\\s+[A-Z"']` boundary for prose.
    Empty pieces are dropped."""
    if not text:
        return []
    pieces: list[str] = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        for piece in _SENTENCE_SPLIT_RE.split(raw):
            stripped = piece.strip()
            if stripped:
                pieces.append(stripped)
    return pieces


# ---------- Verifier ----------


def verify_sentence(
    sentence: str,
    *,
    grounded_numbers: set[str],
    grounded_strings: set[str],
    anchors: list[Anchor],
) -> list[Violation]:
    """Check a single sentence against the grounding evidence. Returns the
    list of violations for that sentence (empty list = clean)."""
    violations: list[Violation] = []
    anchor_values = {a.normalized_value for a in anchors}

    for raw, _kind in extract_numbers(sentence):
        token = _normalize_token(raw)
        if token in anchor_values or token in grounded_numbers:
            continue
        # Allow tokens that match within 0.5% rounding tolerance of any input.
        if _is_close_to_any(token, grounded_numbers, tolerance=0.005):
            continue
        violations.append(
            Violation(
                kind="ungrounded_number",
                sentence=sentence,
                value=raw,
                reason="number not present in structured_inputs or anchors",
            )
        )

    lower = sentence.lower()
    for hedge in _FORBIDDEN_HEDGES:
        if hedge in lower:
            violations.append(
                Violation(
                    kind="forbidden_hedge",
                    sentence=sentence,
                    value=hedge,
                    reason="hedge phrase forbidden by base prompt",
                )
            )

    return violations


def _is_close_to_any(
    token: str, candidates: Iterable[str], *, tolerance: float
) -> bool:
    """Numeric near-match: token within `tolerance` of any candidate. Both
    tokens must parse as floats; non-numeric tokens never match. Used to
    absorb rounding (e.g. 820000 vs 820123)."""
    try:
        t = float(token)
    except ValueError:
        return False
    if t == 0:
        return "0" in candidates
    for cand in candidates:
        try:
            c = float(cand)
        except ValueError:
            continue
        if c == 0:
            continue
        if abs(c - t) / max(abs(c), abs(t)) <= tolerance:
            return True
    return False


def strip_violating_sentences(
    draft: str,
    report: VerifierReport,
    *,
    kinds: tuple[str, ...] = ("ungrounded_number", "ungrounded_entity"),
) -> tuple[str, int]:
    """Drop sentences whose violations match any of the given kinds.

    Returns `(cleaned_text, stripped_count)`. Sentence equality is checked
    against the marker-stripped form (verifier already stores it that way).
    Used by the strict-regen flow in composer.py — when it removes more than
    the composer's threshold, the composer retries once with a stricter prompt.
    """
    if not draft or not report.violations:
        return draft, 0
    bad: set[str] = {v.sentence for v in report.violations if v.kind in kinds}
    if not bad:
        return draft, 0
    kept: list[str] = []
    stripped = 0
    for sentence in split_sentences(draft):
        canonical = _ANCHOR_RE.sub("", sentence).strip()
        if canonical in bad:
            stripped += 1
            continue
        kept.append(sentence)
    return " ".join(kept).strip(), stripped


def verify_response(
    text: str,
    structured_inputs: dict[str, Any] | None,
    *,
    tier: str | None = None,
) -> VerifierReport:
    """Run the verifier across an entire LLM draft. Returns a report with
    per-sentence violation counts and an aggregate list of violations.

    Designed to be cheap (regex + set membership) so the overhead is negligible
    against the LLM call itself. Tolerant of empty inputs — a verifier on an
    empty draft yields a clean (zero-everything) report."""
    sentences = split_sentences(text)
    anchors = extract_anchors(text)
    grounded_numbers = _flatten_input_values(structured_inputs or {})
    grounded_strings = _flatten_input_strings(structured_inputs or {})

    report = VerifierReport(tier=tier, anchor_count=len(anchors), anchors=anchors)
    report.sentences_total = len(sentences)

    text_lower = text.lower()
    if any(s in text_lower for s in _UNGROUNDED_SENTINELS):
        report.ungrounded_declaration = True

    for sentence in sentences:
        # Strip anchors before running the per-sentence checks so the marker
        # text itself doesn't leak into number extraction.
        cleaned = _ANCHOR_RE.sub("", sentence).strip()
        if not cleaned:
            continue
        violations = verify_sentence(
            cleaned,
            grounded_numbers=grounded_numbers,
            grounded_strings=grounded_strings,
            anchors=anchors,
        )
        if violations:
            report.sentences_with_violations += 1
            report.violations.extend(violations)

    return report
