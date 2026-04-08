from __future__ import annotations

from briarwood.local_intelligence.models import SourceDocument


LOCAL_INTELLIGENCE_SYSTEM_PROMPT = """
You are Briarwood's Local Intelligence extractor.
Your job is to read town-level source documents and produce trust-oriented,
structured signals that may affect home values, rent growth, liquidity, future
supply, neighborhood quality, regulatory risk, climate or resilience risk, and
infrastructure or amenity trajectory.

Rules:
- Separate facts from inference.
- Only create signals supported by the source text.
- Keep evidence excerpts short and attributable.
- Prefer explicit statuses such as proposed, approved, funded, in progress,
  completed, or rejected.
- If status is unclear, choose the lowest-confidence defensible status.
- Facts must be directly grounded in the source text, not inferred.
- Inference is optional and must be clearly separate from facts.
- Never invent approvals, timelines, impact, or dimensions not supported by the source.
- Weak, ambiguous, or blog-style mentions should produce lower confidence or zero signals.
- If the document is too weak to support a structured signal, return none.
""".strip()


def build_extraction_prompt(document: SourceDocument) -> str:
    """Build a backend-agnostic extraction prompt for one source document."""

    return (
        f"Town: {document.town}, {document.state}\n"
        f"Source type: {document.source_type.value}\n"
        f"Title: {document.title}\n"
        f"Published at: {document.published_at.isoformat() if document.published_at else 'unknown'}\n\n"
        "Extract town-level signals that matter for Briarwood's underwriting and explainability.\n"
        "Return structured signals only when supported by the text below.\n"
        "You may return zero, one, or multiple signals.\n"
        "Each fact must be directly stated or tightly quoted from the text.\n"
        "If you are uncertain, lower confidence and keep inference blank.\n\n"
        f"{document.cleaned_text or document.raw_text}"
    )
