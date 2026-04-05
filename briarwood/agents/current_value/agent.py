from __future__ import annotations

from datetime import date, datetime, timedelta

from briarwood.agents.current_value.schemas import (
    CurrentValueComponents,
    CurrentValueInput,
    CurrentValueOutput,
    CurrentValueTraceItem,
    CurrentValueWeights,
)
from briarwood.agents.market_history.schemas import HistoricalValuePoint


class CurrentValueAgent:
    """Estimate a defensible Briarwood Current Value for today's market."""

    _COMPONENT_BASE_WEIGHTS = {
        "comparable_sales": 0.40,
        "market_adjusted": 0.24,
        "backdated_listing": 0.12,
        "income": 0.08,
        "town_prior": 0.16,
    }

    def run(self, input_data: CurrentValueInput) -> CurrentValueOutput:
        assumptions: list[str] = []
        unsupported_claims: list[str] = []
        warnings: list[str] = []

        comparable_sales_value = input_data.comparable_sales_value
        comparable_sales_confidence = input_data.comparable_sales_confidence or 0.0
        if comparable_sales_value is not None:
            assumptions.append("Comparable-sales value uses file-backed nearby sales and is weighted as the primary property-specific anchor when available.")
        else:
            unsupported_claims.append("Comparable-sales value is unavailable because no usable local sale comps were supplied.")

        market_adjustment_factor, property_detail_count = self._property_adjustment_factor(input_data)
        if property_detail_count:
            assumptions.append(
                "Property-specific adjustment is conservative and bounded, using only available beds, baths, lot size, property type, and year built."
            )
        else:
            unsupported_claims.append(
                "Property-level adjustment is minimal because detailed property characteristics are thin."
            )

        market_adjusted_value = None
        market_component_confidence = 0.0
        if input_data.market_value_today is not None and input_data.market_history_points:
            raw_market_value = input_data.market_value_today * (1 + market_adjustment_factor)
            market_adjusted_value = raw_market_value
            # Confidence scales with data quality; detail count modulates weight rather than bounding value.
            market_component_confidence = self._market_component_confidence(
                history_points=len(input_data.market_history_points),
                property_detail_count=property_detail_count,
            )
            # Warn when market signal diverges materially from ask — the number is now fully visible in BCV.
            if input_data.ask_price > 0:
                market_divergence_pct = (raw_market_value - input_data.ask_price) / input_data.ask_price
                if abs(market_divergence_pct) > 0.15:
                    direction = "above" if raw_market_value > input_data.ask_price else "below"
                    warnings.append(
                        f"Independent market data (ZHVI-based) is {abs(market_divergence_pct):.0%} {direction} ask. "
                        "This signal is included fully in BCV and may cause BCV to diverge from ask."
                    )
        else:
            unsupported_claims.append("Market-adjusted value is unavailable because market history is missing.")

        listing_date, listing_date_quality = self._resolve_listing_date(input_data)
        if listing_date is None:
            unsupported_claims.append("Backdated listing alignment is unavailable because listing date could not be established.")
        elif listing_date_quality == "days_on_market":
            assumptions.append("Listing date was inferred from days on market because a direct listing date was not available.")

        backdated_listing_value = None
        backdated_component_confidence = 0.0
        if listing_date is not None and input_data.market_value_today is not None and input_data.market_history_points:
            listing_market_value, listing_gap_days = self._market_value_at_date(
                input_data.market_history_points,
                listing_date,
            )
            if listing_market_value is not None and listing_market_value > 0:
                growth_factor = input_data.market_value_today / listing_market_value
                backdated_listing_value = input_data.ask_price * growth_factor
                backdated_component_confidence = self._backdated_component_confidence(
                    listing_date_quality=listing_date_quality,
                    listing_gap_days=listing_gap_days,
                )
                if listing_gap_days > 31:
                    warnings.append(
                        "Backdated listing alignment used a coarse history match because the listing date did not line up closely with a market history point."
                    )
            else:
                unsupported_claims.append("Backdated listing alignment could not locate a usable market value at the listing date.")

        income_supported_value = None
        income_component_confidence = 0.0
        if input_data.effective_annual_rent is not None and input_data.effective_annual_rent > 0:
            income_supported_value = input_data.effective_annual_rent / input_data.cap_rate_assumption
            assumptions.append(
                f"Income-supported value uses effective annual rent and a generic cap-rate assumption of {input_data.cap_rate_assumption:.1%}."
            )
            income_component_confidence = 0.60
            if market_adjusted_value is not None:
                anchor_ratio = income_supported_value / market_adjusted_value
                if anchor_ratio < 0.50 or anchor_ratio > 1.75:
                    warnings.append(
                        "Income-supported value was de-emphasized because it sits far from the market-anchored value."
                    )
                    income_component_confidence *= 0.35
            else:
                income_component_confidence *= 0.85
        else:
            unsupported_claims.append("Income-supported value is unavailable because rent support is missing.")

        town_prior_value = self._town_prior_value(input_data)
        town_prior_confidence = self._town_prior_confidence(input_data)
        if town_prior_value is not None and town_prior_confidence > 0:
            assumptions.append(
                "Town prior uses the subject town's median pricing structure as a bounded secondary anchor, never as a hard override."
            )
            if input_data.comparable_sales_count and input_data.comparable_sales_count >= 4:
                assumptions.append("Town prior was intentionally de-emphasized because direct comp depth is already healthy.")
        else:
            unsupported_claims.append("Town prior is unavailable or too weak to inform BCV.")

        weighted_components = {
            "comparable_sales": self._COMPONENT_BASE_WEIGHTS["comparable_sales"] * comparable_sales_confidence,
            "market_adjusted": self._COMPONENT_BASE_WEIGHTS["market_adjusted"] * market_component_confidence,
            "backdated_listing": self._COMPONENT_BASE_WEIGHTS["backdated_listing"] * backdated_component_confidence,
            "income": self._COMPONENT_BASE_WEIGHTS["income"] * income_component_confidence,
            "town_prior": self._COMPONENT_BASE_WEIGHTS["town_prior"] * town_prior_confidence,
        }
        available_components = {
            "comparable_sales": comparable_sales_value,
            "market_adjusted": market_adjusted_value,
            "backdated_listing": backdated_listing_value,
            "income": income_supported_value,
            "town_prior": town_prior_value,
        }
        weights = self._normalize_weights(weighted_components, available_components)

        if sum(weights.values()) == 0:
            warnings.append("Independent value components were too thin, so the ask price was used as a temporary anchor.")
            briarwood_current_value = input_data.ask_price
            confidence = 0.1
        else:
            briarwood_current_value = (
                (comparable_sales_value or 0.0) * weights["comparable_sales"]
                + (market_adjusted_value or 0.0) * weights["market_adjusted"]
                + (backdated_listing_value or 0.0) * weights["backdated_listing"]
                + (income_supported_value or 0.0) * weights["income"]
                + (town_prior_value or 0.0) * weights["town_prior"]
            )
            confidence = self._overall_confidence(
                weights=weights,
                component_confidences={
                    "comparable_sales": comparable_sales_confidence,
                    "market_adjusted": market_component_confidence,
                    "backdated_listing": backdated_component_confidence,
                    "income": income_component_confidence,
                    "town_prior": town_prior_confidence,
                },
            )

        value_low, value_high = self._value_range(
            current_value=briarwood_current_value,
            confidence=confidence,
        )
        mispricing_amount = briarwood_current_value - input_data.ask_price
        mispricing_pct = mispricing_amount / input_data.ask_price if input_data.ask_price else 0.0
        pricing_view = self._pricing_view(mispricing_pct)

        if confidence < 0.45:
            warnings.append("Current value confidence is low because one or more core valuation inputs are missing or weak.")

        return CurrentValueOutput(
            ask_price=input_data.ask_price,
            briarwood_current_value=round(briarwood_current_value, 2),
            value_low=round(value_low, 2),
            value_high=round(value_high, 2),
            mispricing_amount=round(mispricing_amount, 2),
            mispricing_pct=round(mispricing_pct, 4),
            pricing_view=pricing_view,
            components=CurrentValueComponents(
                comparable_sales_value=self._round_or_none(comparable_sales_value),
                market_adjusted_value=self._round_or_none(market_adjusted_value),
                backdated_listing_value=self._round_or_none(backdated_listing_value),
                income_supported_value=self._round_or_none(income_supported_value),
                town_prior_value=self._round_or_none(town_prior_value),
            ),
            weights=CurrentValueWeights(
                comparable_sales_weight=round(weights["comparable_sales"], 4),
                market_adjusted_weight=round(weights["market_adjusted"], 4),
                backdated_listing_weight=round(weights["backdated_listing"], 4),
                income_weight=round(weights["income"], 4),
                town_prior_weight=round(weights["town_prior"], 4),
            ),
            value_drivers=self._value_drivers(
                component_values=available_components,
                weights=weights,
                component_confidences={
                    "comparable_sales": comparable_sales_confidence,
                    "market_adjusted": market_component_confidence,
                    "backdated_listing": backdated_component_confidence,
                    "income": income_component_confidence,
                    "town_prior": town_prior_confidence,
                },
            ),
            confidence=round(confidence, 2),
            town_context_confidence=round(town_prior_confidence, 2) if town_prior_confidence > 0 else None,
            modeled_fields=[],
            non_modeled_fields=[],
            assumptions=assumptions,
            unsupported_claims=unsupported_claims,
            warnings=warnings,
        )

    def _town_prior_value(self, input_data: CurrentValueInput) -> float | None:
        if input_data.town_median_ppsf is not None and input_data.sqft is not None and input_data.sqft > 0:
            base_value = input_data.town_median_ppsf * input_data.sqft
            size_adjustment = 1.0
            lot_adjustment = 1.0
            if input_data.town_median_sqft not in (None, 0):
                size_ratio = input_data.sqft / input_data.town_median_sqft
                size_adjustment = max(0.94, min(1.06, 1 + ((size_ratio - 1.0) * 0.10)))
            if input_data.lot_size not in (None, 0) and input_data.town_median_lot_size not in (None, 0):
                lot_ratio = input_data.lot_size / input_data.town_median_lot_size
                lot_adjustment = max(0.94, min(1.08, 1 + ((lot_ratio - 1.0) * 0.12)))
            return base_value * size_adjustment * lot_adjustment
        if input_data.town_median_price is not None:
            return input_data.town_median_price
        return None

    def _town_prior_confidence(self, input_data: CurrentValueInput) -> float:
        confidence = float(input_data.town_context_confidence or 0.0)
        if confidence <= 0:
            return 0.0
        if input_data.comparable_sales_count is not None:
            if input_data.comparable_sales_count >= 5:
                confidence *= 0.45
            elif input_data.comparable_sales_count >= 3:
                confidence *= 0.60
            elif input_data.comparable_sales_count == 2:
                confidence *= 0.75
        elif (input_data.comparable_sales_confidence or 0.0) >= 0.80:
            confidence *= 0.60

        if input_data.town_median_ppsf is None and input_data.town_median_price is None:
            return 0.0
        return round(max(0.0, min(confidence, 0.78)), 2)

    def _property_adjustment_factor(self, input_data: CurrentValueInput) -> tuple[float, int]:
        adjustment = 0.0
        detail_count = 0

        if input_data.beds is not None:
            detail_count += 1
            adjustment += max(-0.03, min((input_data.beds - 3) * 0.015, 0.03))
        if input_data.baths is not None:
            detail_count += 1
            adjustment += max(-0.02, min((input_data.baths - 2.0) * 0.01, 0.02))
        if input_data.lot_size is not None:
            detail_count += 1
            lot_delta = ((input_data.lot_size / 0.10) - 1.0) * 0.02
            adjustment += max(-0.025, min(lot_delta, 0.025))
        if input_data.year_built is not None:
            detail_count += 1
            year_delta = ((input_data.year_built - 1980) / 80) * 0.02
            adjustment += max(-0.02, min(year_delta, 0.02))
        if input_data.property_type:
            detail_count += 1
            property_type = input_data.property_type.strip().lower()
            adjustment += {
                "single family": 0.01,
                "single-family": 0.01,
                "townhouse": -0.005,
                "condo": -0.01,
                "multi family": 0.015,
                "multifamily": 0.015,
            }.get(property_type, 0.0)

        return max(-0.08, min(adjustment, 0.08)), detail_count

    def _market_component_confidence(self, *, history_points: int, property_detail_count: int) -> float:
        history_quality = min(history_points / 12, 1.0)
        property_quality = property_detail_count / 5
        return min(0.92, 0.50 + history_quality * 0.25 + property_quality * 0.17)

    def _resolve_listing_date(self, input_data: CurrentValueInput) -> tuple[date | None, str | None]:
        if parsed_date := self._parse_date(input_data.listing_date):
            return parsed_date, "explicit"

        if input_data.days_on_market is not None:
            return date.today() - timedelta(days=input_data.days_on_market), "days_on_market"

        dated_entries: list[date] = []
        for entry in input_data.price_history:
            event = str(entry.get("event", "")).lower()
            if "list" not in event:
                continue
            parsed_date = self._parse_date(entry.get("date"))
            if parsed_date is not None:
                dated_entries.append(parsed_date)
        if dated_entries:
            return max(dated_entries), "price_history"
        return None, None

    def _market_value_at_date(
        self,
        points: list[HistoricalValuePoint],
        target_date: date,
    ) -> tuple[float | None, int]:
        dated_points = [
            (self._parse_date(point.date), point.value)
            for point in points
            if self._parse_date(point.date) is not None
        ]
        dated_points = [(point_date, value) for point_date, value in dated_points if point_date is not None]
        if not dated_points:
            return None, 10_000
        dated_points.sort(key=lambda item: item[0])

        first_date, first_value = dated_points[0]
        last_date, last_value = dated_points[-1]
        if target_date <= first_date:
            return first_value, (first_date - target_date).days
        if target_date >= last_date:
            return last_value, (target_date - last_date).days

        for left, right in zip(dated_points, dated_points[1:]):
            left_date, left_value = left
            right_date, right_value = right
            if left_date <= target_date <= right_date:
                if target_date == left_date:
                    return left_value, 0
                if target_date == right_date:
                    return right_value, 0
                total_days = (right_date - left_date).days
                elapsed_days = (target_date - left_date).days
                interpolated = left_value + ((right_value - left_value) * (elapsed_days / total_days))
                nearest_gap = min(elapsed_days, total_days - elapsed_days)
                return interpolated, nearest_gap
        return None, 10_000

    def _backdated_component_confidence(
        self,
        *,
        listing_date_quality: str | None,
        listing_gap_days: int,
    ) -> float:
        quality_bonus = {
            "explicit": 0.15,
            "price_history": 0.10,
            "days_on_market": 0.03,
            None: 0.0,
        }[listing_date_quality]
        gap_bonus = 0.15 if listing_gap_days <= 31 else 0.08 if listing_gap_days <= 90 else 0.0
        return min(0.88, 0.50 + quality_bonus + gap_bonus)

    def _normalize_weights(
        self,
        weighted_components: dict[str, float],
        available_components: dict[str, float | None],
    ) -> dict[str, float]:
        filtered = {
            key: weight
            for key, weight in weighted_components.items()
            if available_components[key] is not None and weight > 0
        }
        total_weight = sum(filtered.values())
        if total_weight == 0:
            return {key: 0.0 for key in weighted_components}
        return {
            key: round(filtered.get(key, 0.0) / total_weight, 6)
            for key in weighted_components
        }

    def _overall_confidence(
        self,
        *,
        weights: dict[str, float],
        component_confidences: dict[str, float],
    ) -> float:
        weighted_confidence = sum(weights[key] * component_confidences[key] for key in weights)
        active_components = sum(1 for weight in weights.values() if weight > 0)
        if active_components == 1:
            weighted_confidence *= 0.85
        return max(0.1, min(weighted_confidence, 0.92))

    def _value_range(self, *, current_value: float, confidence: float) -> tuple[float, float]:
        band_pct = 0.06 + (1 - confidence) * 0.18
        return max(0.0, current_value * (1 - band_pct)), current_value * (1 + band_pct)

    def _pricing_view(self, mispricing_pct: float) -> str:
        if mispricing_pct >= 0.08:
            return "appears undervalued"
        if mispricing_pct >= -0.03:
            return "appears fairly priced"
        if mispricing_pct >= -0.10:
            return "appears fully valued"
        return "appears overpriced"

    def _parse_date(self, value: object) -> date | None:
        if not isinstance(value, str) or not value.strip():
            return None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
        return None

    def _round_or_none(self, value: float | None) -> float | None:
        if value is None:
            return None
        return round(value, 2)

    def _value_drivers(
        self,
        *,
        component_values: dict[str, float | None],
        weights: dict[str, float],
        component_confidences: dict[str, float],
    ) -> list[CurrentValueTraceItem]:
        labels = {
            "comparable_sales": "Comparable sales",
            "market_adjusted": "Market-adjusted anchor",
            "backdated_listing": "Backdated listing anchor",
            "income": "Income-supported anchor",
            "town_prior": "Town-aware prior",
        }
        notes = {
            "comparable_sales": "Most property-specific value input when verified comps exist.",
            "market_adjusted": "Town-level market history adjusted by basic property facts.",
            "backdated_listing": "Ask anchored to listing date and market drift.",
            "income": "Generic cap-rate conversion from effective rent support.",
            "town_prior": "Town baseline anchor using local median pricing structure, bounded so direct comps still dominate.",
        }
        drivers: list[CurrentValueTraceItem] = []
        for key in ("comparable_sales", "market_adjusted", "backdated_listing", "income", "town_prior"):
            value = component_values.get(key)
            weight = weights.get(key, 0.0)
            confidence = component_confidences.get(key, 0.0)
            drivers.append(
                CurrentValueTraceItem(
                    component=labels[key],
                    value=round(value, 2) if value is not None else None,
                    normalized_weight=round(weight, 4),
                    confidence=round(confidence, 2),
                    contribution_value=round(value * weight, 2) if value is not None and weight > 0 else None,
                    note=notes[key],
                )
            )
        return drivers
