from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from typing import Any, Callable

from briarwood.agent.tools import SAVED_PROPERTIES_DIR
from briarwood.data_sources.attom_client import AttomClient
from briarwood.data_sources.google_maps_client import GoogleMapsClient


@dataclass(frozen=True)
class PropertyEnrichmentBundle:
    """Unified evidence bundle for post-promotion property enrichment."""

    property_id: str
    address: str | None
    town: str | None
    state: str | None
    summary: dict[str, Any]
    source_coverage: dict[str, str]
    listing_source: dict[str, Any]
    google: dict[str, Any]
    attom: dict[str, Any]
    town_intelligence: dict[str, Any] | None
    warnings: list[str]
    fetched_at: str


def enrich_property(
    property_id: str,
    *,
    attom_client: AttomClient | None = None,
    google_client: GoogleMapsClient | None = None,
    town_researcher: Callable[[str, str], dict[str, Any]] | None = None,
    include_town_research: bool = True,
    save_artifact: bool = True,
) -> PropertyEnrichmentBundle:
    """Assemble deterministic source evidence for one saved property."""

    property_dir = SAVED_PROPERTIES_DIR / property_id
    inputs_path = property_dir / "inputs.json"
    summary_path = property_dir / "summary.json"
    if not inputs_path.exists():
        raise FileNotFoundError(f"Missing saved inputs for property '{property_id}'")
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing saved summary for property '{property_id}'")

    inputs_payload = json.loads(inputs_path.read_text())
    summary = json.loads(summary_path.read_text())
    subject = dict(inputs_payload.get("facts") or {})
    source_metadata = dict(inputs_payload.get("source_metadata") or {})
    source_coverage = {
        key: str((value or {}).get("status") or "unknown")
        for key, value in (source_metadata.get("source_coverage") or {}).items()
        if isinstance(value, dict)
    }

    address = _first_non_empty(subject.get("address"), summary.get("address"))
    town = _first_non_empty(subject.get("town"), summary.get("town"))
    state = _first_non_empty(subject.get("state"), summary.get("state"))
    warnings: list[str] = []

    google_data = _collect_google_data(
        address=address,
        town=town,
        state=state,
        subject=subject,
        client=google_client or GoogleMapsClient(),
        warnings=warnings,
    )
    attom_data = _collect_attom_data(
        property_id=property_id,
        address=address,
        town=town,
        state=state,
        client=attom_client or AttomClient(),
        warnings=warnings,
    )
    town_intelligence = _collect_town_intelligence(
        town=town,
        state=state,
        include_town_research=include_town_research,
        town_researcher=town_researcher,
        warnings=warnings,
    )

    bundle = PropertyEnrichmentBundle(
        property_id=property_id,
        address=address,
        town=town,
        state=state,
        summary=summary,
        source_coverage=source_coverage,
        listing_source={
            "source_url": _first_non_empty(summary.get("source_url"), subject.get("source_url")),
            "provenance": list(source_metadata.get("provenance") or []),
            "missing_input_count": summary.get("missing_input_count"),
        },
        google=google_data,
        attom=attom_data,
        town_intelligence=town_intelligence,
        warnings=list(dict.fromkeys(warnings)),
        fetched_at=datetime.now().isoformat(timespec="seconds"),
    )
    if save_artifact:
        artifact_path = property_dir / "enrichment.json"
        artifact_path.write_text(json.dumps(asdict(bundle), indent=2) + "\n")
    return bundle


def load_saved_enrichment(property_id: str) -> dict[str, Any]:
    """Read the last saved enrichment artifact for a property, if present."""

    artifact_path = SAVED_PROPERTIES_DIR / property_id / "enrichment.json"
    if not artifact_path.exists():
        raise FileNotFoundError(f"Missing enrichment artifact for property '{property_id}'")
    return json.loads(artifact_path.read_text())


def _collect_google_data(
    *,
    address: str | None,
    town: str | None,
    state: str | None,
    subject: dict[str, Any],
    client: GoogleMapsClient,
    warnings: list[str],
) -> dict[str, Any]:
    if not client.is_configured:
        warnings.append("Google Maps enrichment unavailable: GOOGLE_MAPS_API_KEY is not configured.")
        return {}

    latitude = _as_float(subject.get("latitude"))
    longitude = _as_float(subject.get("longitude"))
    geocode_payload: dict[str, Any] = {}
    if latitude is None or longitude is None:
        geocode_query = _join_non_empty([address, town, state], separator=", ")
        geocode = client.geocode(geocode_query)
        if geocode.ok:
            geocode_payload = dict(geocode.normalized_payload or {})
            latitude = _as_float(geocode_payload.get("latitude"))
            longitude = _as_float(geocode_payload.get("longitude"))
        elif geocode.error:
            warnings.append(f"Google geocode unavailable: {geocode.error}")

    nearby_payload: dict[str, Any] = {}
    street_view_url = None
    if latitude is not None and longitude is not None:
        nearby = client.nearby_places(latitude=latitude, longitude=longitude)
        if nearby.ok:
            nearby_payload = dict(nearby.normalized_payload or {})
        elif nearby.error:
            warnings.append(f"Google nearby places unavailable: {nearby.error}")
        street_view_url = client.street_view_image_url(latitude=latitude, longitude=longitude)

    return {
        "geocode": geocode_payload,
        "nearby_places": nearby_payload,
        "street_view_image_url": street_view_url,
    }


def _collect_attom_data(
    *,
    property_id: str,
    address: str | None,
    town: str | None,
    state: str | None,
    client: AttomClient,
    warnings: list[str],
) -> dict[str, Any]:
    if not client.api_key:
        warnings.append("ATTOM enrichment unavailable: ATTOM_API_KEY is not configured.")
        return {}
    address1, address2 = _attom_query_parts(address=address, town=town, state=state)
    if not address1 or not address2:
        warnings.append("ATTOM enrichment skipped: address context is incomplete.")
        return {}

    property_detail = client.property_detail(property_id, address1=address1, address2=address2)
    sale_history = client.sale_history_snapshot(property_id, address1=address1, address2=address2)
    assessment = client.assessment_detail(property_id, address1=address1, address2=address2)
    rental_avm = client.rental_avm(property_id, address1=address1, address2=address2)

    responses = {
        "property_detail": property_detail,
        "sale_history_snapshot": sale_history,
        "assessment_detail": assessment,
        "rental_avm": rental_avm,
    }
    payload: dict[str, Any] = {}
    for name, response in responses.items():
        if response.ok:
            payload[name] = dict(response.normalized_payload or {})
        elif response.error:
            warnings.append(f"ATTOM {name} unavailable: {response.error}")
    return payload


def _collect_town_intelligence(
    *,
    town: str | None,
    state: str | None,
    include_town_research: bool,
    town_researcher: Callable[[str, str], dict[str, Any]] | None,
    warnings: list[str],
) -> dict[str, Any] | None:
    if not include_town_research:
        return None
    if not town or not state:
        warnings.append("Town research skipped: town/state context is incomplete.")
        return None
    if town_researcher is None:
        from briarwood.agent.tools import research_town

        def town_researcher(input_town: str, input_state: str) -> dict[str, Any]:
            return research_town(input_town, input_state, [])

    try:
        return town_researcher(town, state)
    except Exception as exc:
        warnings.append(f"Town research unavailable: {exc}")
        return None


def _attom_query_parts(*, address: str | None, town: str | None, state: str | None) -> tuple[str | None, str | None]:
    if not address:
        return None, None
    street = address
    if "," in address:
        street = address.split(",", 1)[0].strip()
    locality = _join_non_empty([town, state], separator=", ")
    return street or None, locality or None


def _join_non_empty(values: list[str | None], *, separator: str) -> str:
    return separator.join(part.strip() for part in values if isinstance(part, str) and part.strip())


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


__all__ = ["PropertyEnrichmentBundle", "enrich_property", "load_saved_enrichment"]
