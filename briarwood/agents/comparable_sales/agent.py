from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Protocol
import json

from briarwood.agents.comparable_sales.schemas import (
    AdjustedComparable,
    ComparableSale,
    ComparableSalesOutput,
    ComparableSalesRequest,
)
from briarwood.agents.market_history.schemas import HistoricalValuePoint


class ComparableSalesProvider(Protocol):
    def get_sales(self, *, town: str, state: str) -> list[ComparableSale]:
        ...


class FileBackedComparableSalesProvider:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.metadata: dict[str, object] = {}
        self._rows = self._load_rows()

    def _load_rows(self) -> list[ComparableSale]:
        if not self.path.exists():
            return []
        with self.path.open() as fh:
            raw = json.load(fh)
        if isinstance(raw, dict):
            self.metadata = raw.get("metadata", {}) if isinstance(raw.get("metadata"), dict) else {}
        rows = raw.get("sales", raw)
        if not isinstance(rows, list):
            return []
        return [ComparableSale.model_validate(item) for item in rows if isinstance(item, dict)]

    def get_sales(self, *, town: str, state: str) -> list[ComparableSale]:
        town_key = town.strip().lower()
        state_key = state.strip().upper()
        return [
            row
            for row in self._rows
            if row.town.strip().lower() == town_key and row.state.strip().upper() == state_key
        ]


class ComparableSalesAgent:
    """Form a conservative property-level value anchor from comparable nearby sales."""

    def __init__(self, provider: ComparableSalesProvider) -> None:
        self.provider = provider

    def run(self, payload: ComparableSalesRequest | dict[str, object]) -> ComparableSalesOutput:
        request = payload if isinstance(payload, ComparableSalesRequest) else ComparableSalesRequest.model_validate(payload)
        assumptions: list[str] = []
        warnings: list[str] = []
        unsupported_claims: list[str] = []
        provider_sales = [] if request.manual_comp_only else self.provider.get_sales(town=request.town, state=request.state)
        manual_sales = [ComparableSale.model_validate(item) for item in request.manual_sales]
        raw_sales = manual_sales + provider_sales
        if not raw_sales:
            return self._empty_output(
                town=request.town,
                state=request.state,
                summary_override=(
                    f"Briarwood could not form a comparable-sales value for {request.town}, {request.state} because no manual comps were entered."
                    if request.manual_comp_only
                    else None
                ),
                unsupported_claims=[
                    "This view is not yet supported by manually entered comparable sales."
                    if request.manual_comp_only
                    else "No file-backed comparable sales were available for this town."
                ],
            )

        history_points = self._parse_history_points(request.market_history_points)
        adjusted: list[AdjustedComparable] = []
        rejected_count = 0
        rejection_reasons: dict[str, int] = {}

        for sale in raw_sales:
            eligible, rejection_reason = self._passes_gate(request, sale)
            if not eligible:
                rejected_count += 1
                if rejection_reason:
                    rejection_reasons[rejection_reason] = rejection_reasons.get(rejection_reason, 0) + 1
                continue

            similarity_score, why_comp, cautions = self._similarity_profile(request, sale)
            if similarity_score < 0.30:
                rejected_count += 1
                rejection_reasons["similarity_too_low"] = rejection_reasons.get("similarity_too_low", 0) + 1
                continue

            time_adjusted_price, time_adjustment_pct = self._time_adjust_price(
                sale_price=sale.sale_price,
                sale_date=sale.sale_date,
                history_points=history_points,
                market_value_today=request.market_value_today,
            )
            subject_adjustment_pct, adjustment_notes = self._subject_adjustment_pct(request, sale)
            adjusted_price = time_adjusted_price * (1 + subject_adjustment_pct)
            fit_label = self._fit_label(similarity_score)
            sale_age_days = max((date.today() - self._parse_date(sale.sale_date)).days, 0)

            adjusted.append(
                AdjustedComparable(
                    address=sale.address,
                    property_type=sale.property_type,
                    sale_date=sale.sale_date,
                    source_name=sale.source_name,
                    source_quality=sale.source_quality,
                    source_ref=sale.source_ref,
                    reviewed_at=sale.reviewed_at,
                    comp_status=sale.comp_status,
                    capex_lane=sale.capex_lane,
                    address_verification_status=sale.address_verification_status,
                    sale_verification_status=sale.sale_verification_status,
                    verification_source_type=sale.verification_source_type,
                    verification_source_name=sale.verification_source_name,
                    verification_source_id=sale.verification_source_id,
                    last_verified_by=sale.last_verified_by,
                    last_verified_at=sale.last_verified_at,
                    verification_notes=sale.verification_notes,
                    sale_price=round(sale.sale_price, 2),
                    time_adjusted_price=round(time_adjusted_price, 2),
                    adjusted_price=round(adjusted_price, 2),
                    comp_confidence_weight=round(self._confidence_weight_for_sale(sale), 3),
                    similarity_score=round(similarity_score, 3),
                    fit_label=fit_label,
                    bedrooms=sale.beds,
                    bathrooms=sale.baths,
                    sqft=sale.sqft,
                    lot_size=sale.lot_size,
                    distance_to_subject_miles=sale.distance_to_subject_miles,
                    year_built=sale.year_built,
                    stories=sale.stories,
                    garage_spaces=sale.garage_spaces,
                    sale_age_days=sale_age_days,
                    time_adjustment_pct=round(time_adjustment_pct, 4),
                    subject_adjustment_pct=round(subject_adjustment_pct, 4),
                    why_comp=why_comp,
                    cautions=cautions,
                    adjustments_summary=adjustment_notes,
                    source_summary=self._source_summary(sale),
                    location_tags=sale.location_tags,
                    condition_profile=sale.condition_profile,
                    micro_location_notes=sale.micro_location_notes,
                )
            )

        adjusted.sort(key=lambda row: (row.fit_label != "strong", -row.similarity_score, row.sale_age_days))
        comps_used = adjusted[:5]
        if not comps_used:
            return self._empty_output(
                town=request.town,
                state=request.state,
                rejected_count=rejected_count,
                rejection_reasons=rejection_reasons,
                unsupported_claims=[
                    "Comparable sale records exist, but Briarwood did not find enough close matches after property-type, size, and recency filters."
                ],
            )

        weighted_value = self._weighted_value(comps_used)
        confidence = self._confidence(request, comps_used, history_points=history_points)
        freshest_sale_date = max((comp.sale_date for comp in comps_used), default=None)
        median_sale_age_days = self._median_sale_age_days(comps_used)
        dataset_name = self._dataset_name()
        dataset_as_of = self._dataset_as_of()
        curation_summary = self._curation_summary(comps_used)
        verification_summary = self._verification_summary(comps_used, rejected_count, rejection_reasons)
        assumptions.append(
            "Comparable-sale value uses same-town sale comps, conservative similarity filters, and town-level market history for time adjustment when available."
        )
        assumptions.append(
            "Questioned or unverified comp addresses are screened out of the active comp set until they are manually confirmed."
        )
        assumptions.append(
            "Until MLS data is connected, Briarwood treats county/public-record sale verification as the strongest available comp evidence tier above manually seeded local review."
        )
        if dataset_name:
            assumptions.append(
                f"Comp set is currently sourced from the {dataset_name} dataset{f' (reviewed {dataset_as_of})' if dataset_as_of else ''}."
            )
        if manual_sales:
            assumptions.append(f"{len(manual_sales)} manually entered comps were included in the active comp set.")
        if request.sqft is None or request.sqft <= 0:
            warnings.append(
                "Subject square footage is missing, so comp matching leans more heavily on beds, baths, lot size, and sale recency."
            )
        if not history_points or request.market_value_today is None:
            warnings.append(
                "Comparable sales were not time-adjusted with market history because the town-level market series was incomplete."
            )
        if len([comp for comp in comps_used if comp.fit_label == "strong"]) == 0:
            warnings.append("Comparable-sales value is built from usable comps, but Briarwood did not find a truly strong match in the current comp set.")
        if not any(comp.sale_verification_status in {"public_record_verified", "mls_verified"} for comp in comps_used):
            warnings.append(
                "Active comps have not yet been tied to a public-record or MLS-verified sale record, so the comp database should still be treated as a reviewed seed set."
            )
        support_note = self._support_note(comps_used)
        if support_note:
            warnings.append(support_note)

        summary = (
            f"Briarwood formed a comparable-sales value around ${weighted_value:,.0f} using {len(comps_used)} "
            f"same-town sale comps that best matched the subject on type, size, recency, and overall fit."
        )
        if manual_sales:
            summary = (
                f"This valuation is supported by {len(comps_used)} manually entered comparable sales. "
                f"{summary}"
            )
        return ComparableSalesOutput(
            comparable_value=round(weighted_value, 2),
            comp_count=len(comps_used),
            confidence=round(confidence, 2),
            comps_used=comps_used,
            rejected_count=rejected_count,
            rejection_reasons=rejection_reasons,
            freshest_sale_date=freshest_sale_date,
            median_sale_age_days=median_sale_age_days,
            dataset_name=dataset_name,
            dataset_as_of=dataset_as_of,
            curation_summary=curation_summary,
            verification_summary=verification_summary,
            assumptions=assumptions,
            unsupported_claims=unsupported_claims,
            warnings=warnings,
            summary=summary,
        )

    def _empty_output(
        self,
        *,
        town: str,
        state: str,
        rejected_count: int = 0,
        rejection_reasons: dict[str, int] | None = None,
        summary_override: str | None = None,
        unsupported_claims: list[str],
    ) -> ComparableSalesOutput:
        return ComparableSalesOutput(
            comparable_value=None,
            comp_count=0,
            confidence=0.0,
            comps_used=[],
            rejected_count=rejected_count,
            rejection_reasons=rejection_reasons or {},
            freshest_sale_date=None,
            median_sale_age_days=None,
            dataset_name=self._dataset_name(),
            dataset_as_of=self._dataset_as_of(),
            curation_summary=None,
            verification_summary=None,
            assumptions=[],
            unsupported_claims=unsupported_claims,
            warnings=[],
            summary=summary_override or f"Briarwood could not form a comparable-sales value for {town}, {state}.",
        )

    def _passes_gate(self, request: ComparableSalesRequest, sale: ComparableSale) -> tuple[bool, str | None]:
        if sale.address_verification_status in {"questioned", "unverified"}:
            return False, "address_verification_failed"
        if sale.sale_verification_status == "questioned":
            return False, "sale_verification_failed"

        if request.property_type and sale.property_type:
            if self._property_type_family(request.property_type) != self._property_type_family(sale.property_type):
                return False, "property_type_mismatch"

        if request.beds is not None and sale.beds is not None and abs(request.beds - sale.beds) > 2:
            return False, "bed_count_too_far"
        if request.baths is not None and sale.baths is not None and abs(request.baths - sale.baths) > 1.5:
            return False, "bath_count_too_far"

        if request.sqft and sale.sqft:
            sqft_gap = abs(request.sqft - sale.sqft) / max(request.sqft, 1)
            if sqft_gap > 0.35:
                return False, "sqft_gap_too_wide"

        if request.lot_size and sale.lot_size:
            lot_gap = abs(request.lot_size - sale.lot_size) / max(request.lot_size, 0.01)
            if lot_gap > 1.0:
                return False, "lot_gap_too_wide"

        sale_age_days = max((date.today() - self._parse_date(sale.sale_date)).days, 0)
        if sale_age_days > 1460:
            return False, "sale_too_old"

        if request.market_value_today and request.market_value_today > 0 and sale.sale_price:
            price_ratio = sale.sale_price / request.market_value_today
            if price_ratio < 0.35 or price_ratio > 2.50:
                return False, "price_range_too_far"

        return True, None

    def _similarity_profile(
        self,
        request: ComparableSalesRequest,
        sale: ComparableSale,
    ) -> tuple[float, list[str], list[str]]:
        score = 1.0
        why_comp: list[str] = ["Same-town sale comp."]
        cautions: list[str] = []

        if request.property_type and sale.property_type:
            request_type_family = self._property_type_family(request.property_type)
            sale_type_family = self._property_type_family(sale.property_type)
            if request_type_family == sale_type_family:
                why_comp.append("Matches the subject's broader property-type family.")

        if request.architectural_style and sale.architectural_style:
            request_style = request.architectural_style.strip().lower()
            sale_style = sale.architectural_style.strip().lower()
            if request_style == sale_style:
                score += 0.03
                why_comp.append(f"Shares the subject's {sale.architectural_style} style.")
            else:
                score -= 0.03
                cautions.append("Architectural style differs from subject.")

        if request.beds is not None and sale.beds is not None:
            bed_diff = abs(request.beds - sale.beds)
            score -= min(bed_diff * 0.10, 0.25)
            if bed_diff == 0:
                why_comp.append("Matches subject bed count.")
            elif bed_diff == 1:
                why_comp.append("Within one bedroom of subject.")
            else:
                cautions.append("Bedroom count stretches beyond the closest tier.")
        else:
            score -= 0.05
            cautions.append("Bed-count comparison is incomplete.")

        if request.baths is not None and sale.baths is not None:
            bath_diff = abs(request.baths - sale.baths)
            score -= min(bath_diff * 0.08, 0.18)
            if bath_diff <= 0.5:
                why_comp.append("Bath count is close to subject.")
            elif bath_diff > 1.0:
                cautions.append("Bath count requires a meaningful adjustment.")
        else:
            score -= 0.05
            cautions.append("Bath-count comparison is incomplete.")

        if request.sqft and sale.sqft:
            sqft_gap = abs(request.sqft - sale.sqft) / max(request.sqft, 1)
            score -= min(sqft_gap * 0.45, 0.28)
            if sqft_gap <= 0.1:
                why_comp.append("Living area is within roughly 10% of subject.")
            elif sqft_gap <= 0.2:
                why_comp.append("Living area is still in a usable range.")
            else:
                cautions.append("Living-area gap is large enough to need heavier adjustment.")
        elif request.sqft is not None and request.sqft <= 0:
            score -= 0.10
            cautions.append("Subject square footage is missing, so size matching is weaker.")
        else:
            score -= 0.08
            cautions.append("Living-area comparison is incomplete.")

        if request.lot_size and sale.lot_size:
            lot_gap = abs(request.lot_size - sale.lot_size) / max(request.lot_size, 0.01)
            score -= min(lot_gap * 0.15, 0.10)
            if lot_gap <= 0.2:
                why_comp.append("Lot profile is reasonably similar.")
            elif lot_gap > 0.5:
                cautions.append("Lot profile differs meaningfully from subject.")

        if sale.distance_to_subject_miles is not None:
            if sale.distance_to_subject_miles <= 0.5:
                score += 0.02
                why_comp.append("Very close to the subject geographically.")
            elif sale.distance_to_subject_miles > 2.0:
                score -= 0.03
                cautions.append("Comp is farther from the subject.")

        if request.year_built and sale.year_built:
            year_gap = abs(request.year_built - sale.year_built)
            score -= min((year_gap / 40) * 0.08, 0.10)
            if year_gap <= 10:
                why_comp.append("Vintage is close to subject.")
            elif year_gap > 25:
                cautions.append("Vintage gap may reflect condition differences.")

        if request.stories is not None and sale.stories is not None:
            story_gap = abs(request.stories - sale.stories)
            score -= min(story_gap * 0.04, 0.06)
            if story_gap == 0:
                why_comp.append("Story count matches subject.")
            elif story_gap >= 1:
                cautions.append("Story count differs from subject.")

        if request.garage_spaces is not None and sale.garage_spaces is not None:
            garage_gap = abs(request.garage_spaces - sale.garage_spaces)
            score -= min(garage_gap * 0.02, 0.04)
            if garage_gap == 0:
                why_comp.append("Garage utility is similar to subject.")

        subject_tags = self._description_tags(request.listing_description)
        if subject_tags and sale.location_tags:
            overlap = [tag for tag in sale.location_tags if tag in subject_tags]
            if overlap:
                score += min(len(overlap) * 0.02, 0.06)
                why_comp.append(f"Shares key setting traits: {', '.join(overlap[:2]).replace('_', ' ')}.")
            else:
                cautions.append("Micro-location traits differ from the subject's listing profile.")

        if sale.condition_profile:
            subject_condition = request.condition_profile or self._condition_tag(request.listing_description)
            if subject_condition and subject_condition == sale.condition_profile:
                score += 0.02
                why_comp.append(f"Condition profile looks similarly {sale.condition_profile}.")
            elif subject_condition and subject_condition != sale.condition_profile:
                cautions.append("Condition profile may differ from subject.")

        if sale.capex_lane:
            subject_capex_lane = request.capex_lane or self._capex_lane_for_condition(
                request.condition_profile or self._condition_tag(request.listing_description)
            )
            if subject_capex_lane and subject_capex_lane == sale.capex_lane:
                score += 0.015
                why_comp.append(f"Capex lane is similarly {sale.capex_lane}.")
            elif subject_capex_lane and subject_capex_lane != sale.capex_lane:
                cautions.append("Likely capex burden differs from subject.")

        sale_age_days = max((date.today() - self._parse_date(sale.sale_date)).days, 0)
        if sale_age_days <= 365:
            why_comp.append("Sale is reasonably recent.")
        elif sale_age_days <= 730:
            score -= 0.05
        else:
            score -= 0.12
            cautions.append("Sale is older and depends more on time adjustment.")

        return max(0.0, min(score, 1.0)), why_comp[:4], cautions[:3]

    def _property_type_family(self, value: str | None) -> str:
        if not value:
            return "unknown"
        normalized = value.strip().lower().replace("-", " ")
        normalized = " ".join(normalized.split())
        if "single family" in normalized:
            return "single_family"
        if "condo" in normalized or "condominium" in normalized:
            return "condo"
        if "townhouse" in normalized or "townhome" in normalized:
            return "townhouse"
        if "multi family" in normalized or "multifamily" in normalized:
            return "multi_family"
        if "co op" in normalized or "coop" in normalized or "co-op" in normalized:
            return "co_op"
        return normalized

    def _subject_adjustment_pct(self, request: ComparableSalesRequest, sale: ComparableSale) -> tuple[float, list[str]]:
        pct = 0.0
        notes: list[str] = []

        if request.sqft and sale.sqft:
            sqft_delta = (request.sqft - sale.sqft) / max(sale.sqft, 1)
            sqft_pct = max(-0.08, min(sqft_delta * 0.45, 0.08))
            pct += sqft_pct
            if abs(sqft_pct) >= 0.01:
                notes.append(f"Living-area adjustment: {sqft_pct:+.1%}.")

        if request.beds is not None and sale.beds is not None:
            bed_pct = max(-0.025, min((request.beds - sale.beds) * 0.01, 0.025))
            pct += bed_pct
            if abs(bed_pct) >= 0.01:
                notes.append(f"Bedroom adjustment: {bed_pct:+.1%}.")

        if request.baths is not None and sale.baths is not None:
            bath_pct = max(-0.025, min((request.baths - sale.baths) * 0.008, 0.025))
            pct += bath_pct
            if abs(bath_pct) >= 0.008:
                notes.append(f"Bathroom adjustment: {bath_pct:+.1%}.")

        if request.lot_size and sale.lot_size:
            lot_delta = (request.lot_size - sale.lot_size) / max(sale.lot_size, 0.01)
            lot_pct = max(-0.04, min(lot_delta * 0.18, 0.04))
            pct += lot_pct
            if abs(lot_pct) >= 0.01:
                notes.append(f"Lot adjustment: {lot_pct:+.1%}.")

        if request.year_built and sale.year_built:
            year_pct = max(-0.02, min(((request.year_built - sale.year_built) / 40) * 0.01, 0.02))
            pct += year_pct
            if abs(year_pct) >= 0.005:
                notes.append(f"Vintage adjustment: {year_pct:+.1%}.")

        if request.stories is not None and sale.stories is not None:
            story_pct = max(-0.02, min((request.stories - sale.stories) * 0.01, 0.02))
            pct += story_pct
            if abs(story_pct) >= 0.005:
                notes.append(f"Story-count adjustment: {story_pct:+.1%}.")

        if request.garage_spaces is not None and sale.garage_spaces is not None:
            garage_pct = max(-0.015, min((request.garage_spaces - sale.garage_spaces) * 0.008, 0.015))
            pct += garage_pct
            if abs(garage_pct) >= 0.005:
                notes.append(f"Garage adjustment: {garage_pct:+.1%}.")

        subject_condition = request.condition_profile or self._condition_tag(request.listing_description)
        if subject_condition and sale.condition_profile and subject_condition != sale.condition_profile:
            condition_pct = self._condition_adjustment_pct(subject_condition, sale.condition_profile)
            pct += condition_pct
            if abs(condition_pct) >= 0.01:
                notes.append(f"Condition adjustment: {condition_pct:+.1%}.")

        if not notes:
            notes.append("Only minor subject adjustments were required.")
        return max(-0.12, min(pct, 0.12)), notes[:4]

    def _time_adjust_price(
        self,
        *,
        sale_price: float,
        sale_date: str,
        history_points: list[HistoricalValuePoint],
        market_value_today: float | None,
    ) -> tuple[float, float]:
        if not history_points or market_value_today is None:
            return sale_price, 0.0

        sale_market_value = self._market_value_at_date(history_points, self._parse_date(sale_date))
        if sale_market_value is None or sale_market_value <= 0:
            return sale_price, 0.0

        adjusted = sale_price * (market_value_today / sale_market_value)
        pct = (adjusted / sale_price) - 1 if sale_price else 0.0
        return adjusted, pct

    def _market_value_at_date(self, points: list[HistoricalValuePoint], target_date: date) -> float | None:
        dated_points = [(self._parse_date(point.date), point.value) for point in points]
        dated_points.sort(key=lambda item: item[0])
        if not dated_points:
            return None
        if target_date <= dated_points[0][0]:
            return dated_points[0][1]
        if target_date >= dated_points[-1][0]:
            return dated_points[-1][1]
        for left, right in zip(dated_points, dated_points[1:]):
            left_date, left_value = left
            right_date, right_value = right
            if left_date <= target_date <= right_date:
                if target_date == left_date:
                    return left_value
                if target_date == right_date:
                    return right_value
                total_days = (right_date - left_date).days
                elapsed_days = (target_date - left_date).days
                return left_value + ((right_value - left_value) * (elapsed_days / total_days))
        return None

    def _weighted_value(self, comps: list[AdjustedComparable]) -> float:
        total_weight = sum(self._effective_weight(comp) for comp in comps) or 1.0
        return sum(comp.adjusted_price * self._effective_weight(comp) for comp in comps) / total_weight

    def _confidence(
        self,
        request: ComparableSalesRequest,
        comps: list[AdjustedComparable],
        *,
        history_points: list[HistoricalValuePoint],
    ) -> float:
        strong_count = len([comp for comp in comps if comp.fit_label == "strong"])
        avg_similarity = sum(comp.similarity_score for comp in comps) / len(comps)
        avg_curation_weight = sum(self._curation_weight(comp.comp_status) for comp in comps) / len(comps)
        avg_sale_verification_weight = sum(self._sale_verification_weight(comp.sale_verification_status) for comp in comps) / len(comps)
        avg_comp_confidence_weight = sum(comp.comp_confidence_weight for comp in comps) / len(comps)
        subject_completeness = sum(
            value is not None and value != 0
            for value in (request.beds, request.baths, request.sqft, request.lot_size, request.year_built)
        ) / 5
        history_bonus = 0.08 if history_points and request.market_value_today is not None else 0.0
        strong_bonus = min(strong_count * 0.06, 0.12)
        confidence = max(
            0.2,
            min(
                0.9,
                0.26
                + min(len(comps) / 4, 1.0) * 0.18
                + avg_similarity * 0.24
                + avg_curation_weight * 0.10
                + avg_sale_verification_weight * 0.10
                + avg_comp_confidence_weight * 0.08
                + subject_completeness * 0.14
                + strong_bonus
                + history_bonus,
            ),
        )
        if not any(comp.sale_verification_status in {"public_record_verified", "mls_verified"} for comp in comps):
            confidence = min(confidence, 0.62)
        if not any(comp.sale_verification_status in {"public_record_matched", "public_record_verified", "mls_verified"} for comp in comps):
            confidence = min(confidence, 0.56)
        completeness = sum(self._comp_field_completeness(comp) for comp in comps) / len(comps)
        confidence *= 0.75 + (completeness * 0.25)
        return confidence

    def _fit_label(self, similarity_score: float) -> str:
        if similarity_score >= 0.82:
            return "strong"
        if similarity_score >= 0.62:
            return "usable"
        return "stretch"

    def _parse_history_points(self, raw_points: list[dict[str, object]]) -> list[HistoricalValuePoint]:
        points: list[HistoricalValuePoint] = []
        for item in raw_points:
            if isinstance(item, HistoricalValuePoint):
                points.append(item)
            elif isinstance(item, dict):
                points.append(HistoricalValuePoint.model_validate(item))
        points.sort(key=lambda item: item.date)
        return points

    def _parse_date(self, value: str) -> date:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return date.today()

    def _dataset_name(self) -> str | None:
        metadata = getattr(self.provider, "metadata", {})
        value = metadata.get("dataset_name") if isinstance(metadata, dict) else None
        return str(value) if value else None

    def _dataset_as_of(self) -> str | None:
        metadata = getattr(self.provider, "metadata", {})
        value = metadata.get("as_of") if isinstance(metadata, dict) else None
        return str(value) if value else None

    def _source_summary(self, sale: ComparableSale) -> str | None:
        parts: list[str] = []
        if sale.comp_status:
            parts.append(sale.comp_status)
        if sale.address_verification_status:
            parts.append(sale.address_verification_status)
        if sale.sale_verification_status:
            parts.append(sale.sale_verification_status)
        if sale.source_name:
            parts.append(sale.source_name)
        if sale.source_quality:
            parts.append(f"{sale.source_quality} quality")
        if sale.verification_source_type:
            parts.append(sale.verification_source_type)
        if sale.verification_source_name:
            parts.append(sale.verification_source_name)
        if sale.verification_source_id:
            parts.append(sale.verification_source_id)
        if sale.source_ref:
            parts.append(sale.source_ref)
        if sale.last_verified_at:
            parts.append(f"verified {sale.last_verified_at}")
        elif sale.reviewed_at:
            parts.append(f"reviewed {sale.reviewed_at}")
        return " | ".join(parts) if parts else None

    def _comp_field_completeness(self, comp: AdjustedComparable) -> float:
        fields = [comp.bedrooms, comp.bathrooms, comp.sqft, comp.lot_size, comp.year_built, comp.sale_date]
        present = sum(value not in (None, "", 0) for value in fields)
        return present / len(fields)

    def _support_note(self, comps: list[AdjustedComparable]) -> str | None:
        count = len(comps)
        avg_completeness = sum(self._comp_field_completeness(comp) for comp in comps) / len(comps) if comps else 0.0
        if count == 0:
            return "No comp support."
        if count <= 2:
            return "Comp confidence is very limited because the active comp set is small."
        if count <= 4:
            return (
                "Comp confidence is moderate, but still sensitive to missing detail."
                if avg_completeness < 0.8
                else "Comp confidence is moderate based on the current comp count."
            )
        if avg_completeness < 0.75:
            return "Comp count is stronger, but confidence is still reduced because several comps are incomplete."
        return "This valuation is supported by a stronger comp sample."

    def _condition_adjustment_pct(self, subject_condition: str, comp_condition: str) -> float:
        rank = {
            "needs_work": 0,
            "dated": 1,
            "maintained": 2,
            "updated": 3,
            "renovated": 4,
        }
        subject_rank = rank.get(subject_condition, 2)
        comp_rank = rank.get(comp_condition, 2)
        return max(-0.05, min((subject_rank - comp_rank) * 0.015, 0.05))

    def _capex_lane_for_condition(self, condition: str | None) -> str | None:
        if condition == "renovated":
            return "light"
        if condition in {"updated", "maintained", "dated"}:
            return "moderate"
        if condition == "needs_work":
            return "heavy"
        return None

    def _median_sale_age_days(self, comps: list[AdjustedComparable]) -> int | None:
        if not comps:
            return None
        sorted_days = sorted(comp.sale_age_days for comp in comps)
        midpoint = len(sorted_days) // 2
        if len(sorted_days) % 2 == 1:
            return sorted_days[midpoint]
        return round((sorted_days[midpoint - 1] + sorted_days[midpoint]) / 2)

    def _curation_summary(self, comps: list[AdjustedComparable]) -> str:
        if not comps:
            return "No curated comp status available."
        status_counts: dict[str, int] = {}
        for comp in comps:
            key = comp.comp_status or "unspecified"
            status_counts[key] = status_counts.get(key, 0) + 1
        ordered = sorted(status_counts.items(), key=lambda item: (-item[1], item[0]))
        return ", ".join(f"{count} {status}" for status, count in ordered)

    def _verification_summary(
        self,
        comps: list[AdjustedComparable],
        rejected_count: int,
        rejection_reasons: dict[str, int],
    ) -> str:
        if not comps:
            return "No verified comps were retained."
        verified_kept = len([comp for comp in comps if comp.address_verification_status == "verified"])
        public_record_verified = len(
            [comp for comp in comps if comp.sale_verification_status in {"public_record_verified", "mls_verified"}]
        )
        public_record_matched = len([comp for comp in comps if comp.sale_verification_status == "public_record_matched"])
        seeded_only = len(
            [comp for comp in comps if comp.sale_verification_status not in {"public_record_matched", "public_record_verified", "mls_verified"}]
        )
        questioned_rejected = rejection_reasons.get("address_verification_failed", 0)
        sale_questioned_rejected = rejection_reasons.get("sale_verification_failed", 0)
        parts = [f"{verified_kept} address-verified kept"]
        if public_record_verified:
            parts.append(f"{public_record_verified} public-record/MLS verified")
        elif public_record_matched:
            parts.append(f"{public_record_matched} public-record matched")
        if seeded_only:
            parts.append(f"{seeded_only} seed/review only")
        if questioned_rejected:
            parts.append(f"{questioned_rejected} address concerns screened out")
        elif rejected_count == 0:
            parts.append("no address-control failures")
        if sale_questioned_rejected:
            parts.append(f"{sale_questioned_rejected} sale-record concerns screened out")
        summary = " | ".join(parts)
        return summary

    def _effective_weight(self, comp: AdjustedComparable) -> float:
        return (
            comp.similarity_score
            * comp.comp_confidence_weight
            * self._curation_weight(comp.comp_status)
            * self._sale_verification_weight(comp.sale_verification_status)
        )

    def _confidence_weight_for_sale(self, sale: ComparableSale) -> float:
        verification_weight = self._simple_verification_weight(sale.verification_status)
        completeness = self._sale_field_completeness(sale)
        recency = self._recency_weight(sale.sale_date)
        return max(0.35, min((0.45 * verification_weight) + (0.30 * recency) + (0.25 * completeness), 1.0))

    def _curation_weight(self, status: str | None) -> float:
        return {
            "approved": 1.0,
            "reviewed": 0.92,
            "seeded": 0.8,
        }.get(status or "", 0.75)

    def _sale_verification_weight(self, status: str | None) -> float:
        return {
            "mls_verified": 1.0,
            "public_record_verified": 0.97,
            "public_record_matched": 0.9,
            "seeded": 0.72,
            "questioned": 0.0,
        }.get(status or "", 0.68)

    def _simple_verification_weight(self, status: str | None) -> float:
        return {
            "broker_verified": 1.0,
            "public_record": 0.94,
            "manual": 0.78,
            "estimated": 0.55,
        }.get(status or "", 0.7)

    def _recency_weight(self, sale_date: str) -> float:
        sale_age_days = max((date.today() - self._parse_date(sale_date)).days, 0)
        if sale_age_days <= 180:
            return 1.0
        if sale_age_days <= 365:
            return 0.94
        if sale_age_days <= 730:
            return 0.82
        if sale_age_days <= 1095:
            return 0.68
        return 0.5

    def _sale_field_completeness(self, sale: ComparableSale) -> float:
        fields = [
            sale.sale_price,
            sale.sale_date,
            sale.sqft,
            sale.beds,
            sale.baths,
            sale.lot_size,
            sale.year_built,
            sale.latitude,
            sale.longitude,
        ]
        present = sum(value not in (None, "", 0) for value in fields)
        return present / len(fields)

    def _description_tags(self, description: str | None) -> set[str]:
        if not description:
            return set()
        lowered = description.lower()
        tag_map = {
            "beach_access": ("beach", "shore"),
            "marina_access": ("marina",),
            "downtown_access": ("downtown",),
            "updated": ("new kitchen", "renovated", "updated"),
            "well_maintained": ("maintained", "cared for", "impeccably"),
        }
        tags: set[str] = set()
        for tag, needles in tag_map.items():
            if any(needle in lowered for needle in needles):
                tags.add(tag)
        return tags

    def _condition_tag(self, description: str | None) -> str | None:
        tags = self._description_tags(description)
        if "updated" in tags:
            return "updated"
        if "well_maintained" in tags:
            return "maintained"
        return None
