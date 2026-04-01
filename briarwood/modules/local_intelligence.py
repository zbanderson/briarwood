from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace

from briarwood.evidence import build_section_evidence
from briarwood.schemas import (
    LocalIntelligenceConfidence,
    LocalIntelligenceOutput,
    LocalIntelligenceProject,
    LocalIntelligenceScores,
    LocalIntelligenceSummary,
    ModuleResult,
    PropertyInput,
)


PROJECT_MARKERS = (
    "application",
    "proposal",
    "project",
    "redevelopment",
    "site plan",
    "variance",
    "subdivision",
    "overlay",
    "zone change",
    "zoning amendment",
)

STATUS_PATTERNS = {
    "approved": re.compile(r"\b(approved|adopted|granted|memorialized)\b", re.IGNORECASE),
    "rejected": re.compile(r"\b(denied|rejected|withdrawn)\b", re.IGNORECASE),
    "pending": re.compile(r"\b(carried|continued|pending|hearing opened|tabled)\b", re.IGNORECASE),
    "proposed": re.compile(r"\b(proposed|submitted|application filed|concept review)\b", re.IGNORECASE),
}

TYPE_PATTERNS = {
    "mixed_use": re.compile(r"\b(mixed-use|mixed use)\b", re.IGNORECASE),
    "residential": re.compile(r"\b(residential|apartment|condominium|townhome|townhouse|multifamily)\b", re.IGNORECASE),
    "commercial": re.compile(r"\b(commercial|retail|office)\b", re.IGNORECASE),
}

POSITIVE_SENTIMENT = (
    "consistent with master plan",
    "favorable",
    "support",
    "benefit",
    "approved",
    "redevelopment area",
)

NEGATIVE_SENTIMENT = (
    "concern",
    "traffic",
    "opposition",
    "flooding",
    "denied",
    "parking issue",
)


class LocalIntelligenceModule:
    """Extract lightweight development and zoning signals from town-level documents."""

    name = "local_intelligence"

    def run(self, property_input: PropertyInput) -> ModuleResult:
        raw_documents = list(property_input.local_documents)
        parsed_documents = [self._normalize_document(doc, property_input.town) for doc in raw_documents]
        projects: list[LocalIntelligenceProject] = []
        confidence_notes: list[str] = []

        for document in parsed_documents:
            doc_projects = self._extract_projects(document["text"])
            if not doc_projects:
                continue
            confidence_notes.append(
                f"Parsed {len(doc_projects)} project mentions from a {document['document_type']} dated {document['meeting_date'] or 'unknown date'}."
            )
            projects.extend(doc_projects)

        summary = self._build_summary(projects)
        scores = self._build_scores(projects, property_input.town_population)
        confidence = self._build_confidence(projects, parsed_documents, property_input.town_population)
        narrative = self._build_narrative(projects, summary, scores, confidence.score)

        output = LocalIntelligenceOutput(
            projects=projects,
            summary=summary,
            scores=scores,
            narrative=narrative,
            confidence=replace(
                confidence,
                notes=_dedupe(confidence.notes + confidence_notes),
            ),
        )

        if raw_documents:
            summary_text = narrative[0] if narrative else (
                f"Briarwood found {summary.total_projects} local projects in the provided town documents."
            )
        else:
            summary_text = (
                "Local development intelligence is unavailable because no town planning, zoning, or redevelopment documents were provided."
            )

        extra_missing = ["local_documents"] if not raw_documents else []
        notes = list(output.confidence.notes)
        notes.append(
            "Local intelligence is a heuristic text-extraction layer from town documents, not a full zoning or entitlement review."
        )

        return ModuleResult(
            module_name=self.name,
            metrics={
                "total_projects": summary.total_projects,
                "total_units": summary.total_units,
                "approved_projects": summary.approved_projects,
                "rejected_projects": summary.rejected_projects,
                "pending_projects": summary.pending_projects,
                "development_activity_score": scores.development_activity_score,
                "supply_pipeline_score": scores.supply_pipeline_score,
                "regulatory_trend_score": scores.regulatory_trend_score,
                "sentiment_score": scores.sentiment_score,
            },
            score=scores.development_activity_score,
            confidence=output.confidence.score,
            summary=summary_text,
            payload=output,
            section_evidence=build_section_evidence(
                property_input,
                categories=["market_history", "scarcity_inputs"],
                notes=notes,
                extra_missing_inputs=extra_missing,
            ),
        )

    def _normalize_document(self, document: dict[str, object], town: str) -> dict[str, str]:
        return {
            "text": str(document.get("text") or ""),
            "town": str(document.get("town") or town),
            "meeting_date": str(document.get("meeting_date") or document.get("date") or ""),
            "document_type": str(document.get("document_type") or "town document"),
        }

    def _extract_projects(self, text: str) -> list[LocalIntelligenceProject]:
        chunks = _text_chunks(text)
        projects: list[LocalIntelligenceProject] = []
        seen: set[tuple[str, str | None, int | None]] = set()
        for chunk in chunks:
            if not any(marker in chunk.lower() for marker in PROJECT_MARKERS):
                continue
            project = self._project_from_chunk(chunk)
            if project is None:
                continue
            key = (project.name.lower(), project.status, project.units)
            if key in seen:
                continue
            seen.add(key)
            projects.append(project)
        return projects

    def _project_from_chunk(self, chunk: str) -> LocalIntelligenceProject | None:
        status = _extract_status(chunk)
        units = _extract_units(chunk)
        project_type = _extract_type(chunk)
        location = _extract_location(chunk)
        name = _extract_name(chunk, location)
        if name is None:
            return None

        confidence = 0.35
        if units is not None:
            confidence += 0.2
        if status is not None:
            confidence += 0.2
        if project_type is not None:
            confidence += 0.1
        if location is not None:
            confidence += 0.1

        notes: list[str] = []
        if "variance" in chunk.lower() or "overlay" in chunk.lower() or "amendment" in chunk.lower():
            notes.append("Includes zoning or entitlement language.")
        if units is None:
            notes.append("Unit count was not explicit in the source text.")

        return LocalIntelligenceProject(
            name=name,
            type=project_type,
            units=units,
            status=status,
            location=location,
            notes=" ".join(notes) or None,
            confidence=round(min(confidence, 0.95), 2),
        )

    def _build_summary(self, projects: list[LocalIntelligenceProject]) -> LocalIntelligenceSummary:
        status_counts = Counter(project.status or "unknown" for project in projects)
        total_units = sum(project.units or 0 for project in projects)
        return LocalIntelligenceSummary(
            total_projects=len(projects),
            total_units=total_units,
            approved_projects=status_counts.get("approved", 0),
            rejected_projects=status_counts.get("rejected", 0),
            pending_projects=status_counts.get("pending", 0) + status_counts.get("proposed", 0),
        )

    def _build_scores(
        self,
        projects: list[LocalIntelligenceProject],
        town_population: int | None,
    ) -> LocalIntelligenceScores:
        total_projects = len(projects)
        total_units = sum(project.units or 0 for project in projects)
        approved = sum(1 for project in projects if project.status == "approved")
        rejected = sum(1 for project in projects if project.status == "rejected")

        development_activity_score = _clamp((total_projects * 12) + (total_units * 0.45))

        if town_population and town_population > 0:
            units_per_1000 = (total_units / town_population) * 1000
            supply_pipeline_score = _clamp(units_per_1000 * 18)
        else:
            supply_pipeline_score = _clamp(total_units * 0.5)

        decision_count = approved + rejected
        if decision_count == 0:
            regulatory_trend_score = 50.0
        else:
            approval_ratio = approved / decision_count
            regulatory_trend_score = _clamp(20 + (approval_ratio * 80))

        sentiment_score = _sentiment_score(projects)

        return LocalIntelligenceScores(
            development_activity_score=round(development_activity_score, 1),
            supply_pipeline_score=round(supply_pipeline_score, 1),
            regulatory_trend_score=round(regulatory_trend_score, 1),
            sentiment_score=round(sentiment_score, 1),
        )

    def _build_confidence(
        self,
        projects: list[LocalIntelligenceProject],
        documents: list[dict[str, str]],
        town_population: int | None,
    ) -> LocalIntelligenceConfidence:
        notes: list[str] = []
        score = 0.0
        if documents:
            score += min(len(documents) / 3, 1.0) * 0.35
            notes.append(f"Based on {len(documents)} provided local documents.")
        if projects:
            score += min(len(projects) / 5, 1.0) * 0.25
        explicit_units = sum(1 for project in projects if project.units is not None)
        if projects:
            unit_ratio = explicit_units / len(projects)
            score += unit_ratio * 0.2
            if unit_ratio < 0.6:
                notes.append("Some unit counts were inferred or missing.")
        status_ratio = (
            sum(1 for project in projects if project.status is not None) / len(projects)
            if projects
            else 0.0
        )
        score += status_ratio * 0.15
        if status_ratio < 0.6 and projects:
            notes.append("Several project statuses were unclear from the source text.")
        if town_population is None:
            notes.append("Town-size normalization was unavailable, so supply scoring uses a generic scale.")
            score = min(score, 0.76)
        if not projects:
            notes.append("No project-level signals were extracted from the supplied text.")
            score = 0.0
        return LocalIntelligenceConfidence(score=round(min(score, 0.95), 2), notes=notes)

    def _build_narrative(
        self,
        projects: list[LocalIntelligenceProject],
        summary: LocalIntelligenceSummary,
        scores: LocalIntelligenceScores,
        confidence: float,
    ) -> list[str]:
        bullets: list[str] = []
        if summary.total_projects == 0:
            return [
                "Briarwood did not extract enough development or zoning signals to form a local pipeline view."
            ]

        if scores.development_activity_score >= 65:
            bullets.append("The town shows meaningful redevelopment or project activity in the supplied planning documents.")
        elif scores.development_activity_score <= 35:
            bullets.append("The supplied documents show a relatively light development pipeline.")

        if summary.total_units > 0:
            bullets.append(
                f"The current document set points to roughly {summary.total_units} pipeline units across {summary.total_projects} projects."
            )

        if scores.regulatory_trend_score >= 65:
            bullets.append("Approval outcomes look generally supportive, suggesting a more permissive local process than average.")
        elif scores.regulatory_trend_score <= 40:
            bullets.append("Approval outcomes look mixed to restrictive, which may limit easy forward supply growth.")

        if confidence < 0.5:
            bullets.append("This local intelligence view is still low-confidence because the document set is thin or only partially structured.")

        return bullets[:4]


def _text_chunks(text: str) -> list[str]:
    paragraphs = [chunk.strip() for chunk in re.split(r"\n{2,}|(?<=\.)\s{2,}", text) if chunk.strip()]
    if paragraphs:
        return paragraphs
    return [line.strip() for line in text.splitlines() if line.strip()]


def _extract_units(text: str) -> int | None:
    matches = re.findall(
        r"\b(\d{1,4})\s+(?:(?:residential|market-rate|market rate|affordable|rental)\s+)?(?:unit|units|apartments|condos|townhomes|townhouses)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not matches:
        return None
    return max(int(value) for value in matches)


def _extract_status(text: str) -> str | None:
    for status, pattern in STATUS_PATTERNS.items():
        if pattern.search(text):
            return status
    return None


def _extract_type(text: str) -> str | None:
    for label, pattern in TYPE_PATTERNS.items():
        if pattern.search(text):
            return label.replace("_", "-")
    return None


def _extract_location(text: str) -> str | None:
    address_match = re.search(
        r"\b\d{1,5}\s+[A-Z][A-Za-z0-9'.-]*(?:\s+[A-Z][A-Za-z0-9'.-]*){0,4}\s(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Place|Pl|Court|Ct)\b",
        text,
    )
    if address_match:
        return address_match.group(0)
    location_match = re.search(r"\b(?:at|for|located at)\s+([^.;]{6,60})", text, flags=re.IGNORECASE)
    if location_match:
        return location_match.group(1).strip()
    return None


def _extract_name(text: str, location: str | None) -> str | None:
    quoted = re.search(r"['\"]([^'\"]{4,80})['\"]", text)
    if quoted:
        return quoted.group(1).strip()
    named = re.search(
        r"\b(?:project|application|redevelopment plan|site plan|proposal)\s+(?:for|of)\s+([^.;]{4,80})",
        text,
        flags=re.IGNORECASE,
    )
    if named:
        return named.group(1).strip(" -")
    if location:
        return f"{location} project"
    if len(text.split()) >= 4:
        return " ".join(text.split()[:6]).strip(" -")
    return None


def _sentiment_score(projects: list[LocalIntelligenceProject]) -> float:
    if not projects:
        return 50.0
    positive_hits = 0
    negative_hits = 0
    for project in projects:
        notes = (project.notes or "").lower()
        positive_hits += sum(1 for phrase in POSITIVE_SENTIMENT if phrase in notes)
        negative_hits += sum(1 for phrase in NEGATIVE_SENTIMENT if phrase in notes)
        if project.status == "approved":
            positive_hits += 1
        elif project.status == "rejected":
            negative_hits += 1
    net = positive_hits - negative_hits
    return _clamp(50 + (net * 8))


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
