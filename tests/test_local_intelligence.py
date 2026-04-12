import json
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory

from briarwood.local_intelligence import LocalIntelligenceService
from briarwood.local_intelligence.adapters import OpenAILocalIntelligenceExtractor
from briarwood.local_intelligence.collector import MunicipalDocumentCollector, MunicipalSourceSeed
from briarwood.local_intelligence.classification import classify_town_signal
from briarwood.local_intelligence.models import (
    ImpactDirection,
    ReconciliationStatus,
    SignalStatus,
    SignalType,
    SourceDocument,
    SourceType,
    TimeHorizon,
    TownSignal,
)
from briarwood.local_intelligence.normalize import normalize_source_documents
from briarwood.local_intelligence.reconcile import reconcile_signals
from briarwood.local_intelligence.summarize import build_town_summary
from briarwood.local_intelligence.storage import JsonLocalSignalStore
from briarwood.dash_app.view_models import build_town_pulse_view_model_from_payload
from briarwood.modules.local_intelligence import LocalIntelligenceModule
from briarwood.schemas import PropertyInput

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "local_intelligence"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def sample_property() -> PropertyInput:
    return PropertyInput(
        property_id="local-1",
        address="1 Main St",
        town="Belmar",
        state="NJ",
        county="Monmouth",
        beds=3,
        baths=2.0,
        sqft=1500,
        purchase_price=700000,
        town_population=5600,
        local_documents=[
            {
                "meeting_date": "2026-02-11",
                "document_type": "planning board minutes",
                "text": (
                    "Application for 1201 Main Street mixed-use redevelopment with 24 residential units was approved. "
                    "Board members found the project consistent with the master plan."
                ),
            },
            {
                "meeting_date": "2026-02-25",
                "document_type": "zoning board minutes",
                "text": (
                    "The proposal for 500 River Road residential project with 12 units was denied after traffic concern and parking issue were discussed."
                ),
            },
        ],
    )


class _FakeResponse:
    def __init__(self, output_text: str | None) -> None:
        self.output_text = output_text


class _FakeResponsesAPI:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def create(self, **_: object) -> _FakeResponse:
        return self._response


class _FakeOpenAIClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.responses = _FakeResponsesAPI(response)


class LocalIntelligenceTests(unittest.TestCase):
    def test_json_signal_store_persists_signals_across_runs(self) -> None:
        now = datetime.now(timezone.utc)
        signal = TownSignal(
            id="sig-store-1",
            town="Belmar",
            state="NJ",
            signal_type=SignalType.INFRASTRUCTURE,
            title="Boardwalk resiliency grant",
            canonical_key="tsk-1",
            source_document_id="doc-store-1",
            source_type=SourceType.NEWS,
            source_date=now,
            source_url="https://example.com/news",
            status=SignalStatus.FUNDED,
            time_horizon=TimeHorizon.NEAR_TERM,
            impact_direction=ImpactDirection.POSITIVE,
            impact_magnitude=4,
            confidence=0.82,
            facts=["Grant approved."],
            inference="May improve resilience.",
            affected_dimensions=["neighborhood_quality"],
            evidence_excerpt="A resiliency grant was approved.",
            created_at=now,
            updated_at=now,
            first_seen_at=now,
            last_seen_at=now,
        )
        with TemporaryDirectory() as temp_dir:
            store = JsonLocalSignalStore(Path(temp_dir))
            store.save_town_signals(town="Belmar", state="NJ", signals=[signal])
            loaded = store.load_town_signals(town="Belmar", state="NJ")

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].title, signal.title)
        self.assertEqual(loaded[0].source_url, "https://example.com/news")

    def test_reconciliation_detects_status_transition(self) -> None:
        now = datetime.now(timezone.utc)
        existing = TownSignal(
            id="sig-existing",
            town="Belmar",
            state="NJ",
            signal_type=SignalType.SUPPLY,
            title="1201 Main Street redevelopment",
            canonical_key="tsk-redev-1",
            source_document_id="doc-old",
            source_type=SourceType.PLANNING_BOARD_MINUTES,
            source_date=now - timedelta(days=30),
            status=SignalStatus.PROPOSED,
            time_horizon=TimeHorizon.MEDIUM_TERM,
            impact_direction=ImpactDirection.MIXED,
            impact_magnitude=4,
            confidence=0.6,
            facts=["Project was proposed."],
            inference=None,
            affected_dimensions=["future_supply"],
            evidence_excerpt="The project was proposed.",
            created_at=now - timedelta(days=30),
            updated_at=now - timedelta(days=30),
            first_seen_at=now - timedelta(days=30),
            last_seen_at=now - timedelta(days=30),
        )
        incoming = existing.model_copy(
            update={
                "id": "sig-new",
                "source_document_id": "doc-new",
                "status": SignalStatus.APPROVED,
                "confidence": 0.8,
                "facts": ["Project was approved."],
                "evidence_excerpt": "The project was approved.",
                "updated_at": now,
            }
        )

        reconciled = reconcile_signals([incoming], existing_signals=[existing])

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0].reconciliation_status, ReconciliationStatus.STATUS_TRANSITION)
        self.assertEqual(reconciled[0].previous_status, SignalStatus.PROPOSED)
        self.assertEqual(reconciled[0].status, SignalStatus.APPROVED)

    def test_reconciliation_detects_unchanged_recurring_signal(self) -> None:
        now = datetime.now(timezone.utc)
        existing = TownSignal(
            id="sig-existing",
            town="Belmar",
            state="NJ",
            signal_type=SignalType.INFRASTRUCTURE,
            title="Boardwalk resiliency grant",
            canonical_key="tsk-boardwalk",
            source_document_id="doc-old",
            source_type=SourceType.NEWS,
            source_date=now - timedelta(days=10),
            source_url="https://example.com/old",
            status=SignalStatus.FUNDED,
            time_horizon=TimeHorizon.NEAR_TERM,
            impact_direction=ImpactDirection.POSITIVE,
            impact_magnitude=4,
            confidence=0.82,
            facts=["Grant approved."],
            inference="Could support resilience.",
            affected_dimensions=["neighborhood_quality"],
            evidence_excerpt="A resiliency grant was approved.",
            created_at=now - timedelta(days=10),
            updated_at=now - timedelta(days=10),
            first_seen_at=now - timedelta(days=10),
            last_seen_at=now - timedelta(days=10),
        )
        incoming = existing.model_copy(update={"id": "sig-new", "source_document_id": "doc-new"})

        reconciled = reconcile_signals([incoming], existing_signals=[existing])

        self.assertEqual(reconciled[0].reconciliation_status, ReconciliationStatus.UNCHANGED)
        self.assertEqual(reconciled[0].occurrence_count, 2)

    def test_service_loads_and_saves_persisted_signal_history(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = JsonLocalSignalStore(Path(temp_dir))
            service = LocalIntelligenceService(store=store)

            first_run = service.analyze(
                town="Belmar",
                state="NJ",
                raw_documents=[_fixture("planning_minutes.json")],
            )
            second_run = service.analyze(
                town="Belmar",
                state="NJ",
                raw_documents=[_fixture("planning_minutes.json")],
            )

            self.assertTrue(first_run.signals)
            self.assertTrue(second_run.signals)
            self.assertEqual(second_run.signals[0].reconciliation_status, ReconciliationStatus.UNCHANGED)
            persisted = store.load_town_signals(town="Belmar", state="NJ")
            self.assertTrue(persisted)

    def test_service_auto_collects_municipal_documents_when_none_are_supplied(self) -> None:
        registry = {
            ("avon by the sea", "NJ"): [
                MunicipalSourceSeed(
                    title="Planning Board Minutes",
                    url="https://example.com/avon/planning-minutes.html",
                    source_type=SourceType.PLANNING_BOARD_MINUTES,
                )
            ]
        }

        def fake_fetcher(_url: str) -> tuple[bytes, str | None]:
            html = (
                "<html><body>"
                "Application for 123 Main Street mixed-use redevelopment with 18 residential units was approved. "
                "Board members found the proposal consistent with the master plan."
                "</body></html>"
            )
            return html.encode("utf-8"), "text/html"

        with TemporaryDirectory() as temp_dir:
            collector = MunicipalDocumentCollector(
                registry=registry,
                fetcher=fake_fetcher,
                cache_root=Path(temp_dir),
            )
            service = LocalIntelligenceService(
                store=JsonLocalSignalStore(Path(temp_dir) / "signals"),
                collector=collector,
            )
            run = service.analyze(
                town="Avon by the Sea",
                state="NJ",
                raw_documents=[],
            )

        self.assertTrue(run.documents)
        self.assertTrue(run.signals)
        self.assertTrue(any("Auto-collected" in warning for warning in run.warnings))
        self.assertNotIn("local_documents", run.missing_inputs)

    def test_municipal_document_collector_uses_cache_after_first_fetch(self) -> None:
        registry = {
            ("avon by the sea", "NJ"): [
                MunicipalSourceSeed(
                    title="Town Hall Minutes",
                    url="https://example.com/avon/town-hall.html",
                    source_type=SourceType.ORDINANCE,
                )
            ]
        }
        fetch_count = {"count": 0}

        def fake_fetcher(_url: str) -> tuple[bytes, str | None]:
            fetch_count["count"] += 1
            return b"<html><body>Regular meeting minutes and ordinance discussion.</body></html>", "text/html"

        with TemporaryDirectory() as temp_dir:
            collector = MunicipalDocumentCollector(
                registry=registry,
                fetcher=fake_fetcher,
                cache_root=Path(temp_dir),
            )
            first = collector.collect(town="Avon by the Sea", state="NJ")
            second = collector.collect(town="Avon by the Sea", state="NJ")

        self.assertEqual(fetch_count["count"], 1)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, first)

    def test_summary_aggregation_prioritizes_recent_confirmed_signals(self) -> None:
        now = datetime.now(timezone.utc)
        summary = build_town_summary(
            town="Belmar",
            state="NJ",
            signals=[
                TownSignal(
                    id="sig-1",
                    town="Belmar",
                    state="NJ",
                    signal_type=SignalType.INFRASTRUCTURE,
                    title="Boardwalk resiliency grant",
                    source_document_id="doc-1",
                    source_type=SourceType.NEWS,
                    source_date=now - timedelta(days=10),
                    status=SignalStatus.FUNDED,
                    time_horizon=TimeHorizon.NEAR_TERM,
                    impact_direction=ImpactDirection.POSITIVE,
                    impact_magnitude=4,
                    confidence=0.86,
                    facts=["Grant approved for resiliency work."],
                    inference="Could support resilience and town quality.",
                    affected_dimensions=["neighborhood_quality"],
                    evidence_excerpt="A $4.2 million resiliency grant was approved.",
                    created_at=now,
                    updated_at=now,
                ),
                TownSignal(
                    id="sig-2",
                    town="Belmar",
                    state="NJ",
                    signal_type=SignalType.REGULATION_CHANGE,
                    title="Short-term rental ordinance",
                    source_document_id="doc-2",
                    source_type=SourceType.ORDINANCE,
                    source_date=now - timedelta(days=2),
                    status=SignalStatus.REVIEWED,
                    time_horizon=TimeHorizon.LONG_TERM,
                    impact_direction=ImpactDirection.MIXED,
                    impact_magnitude=3,
                    confidence=0.61,
                    facts=["Ordinance introduced and under review."],
                    inference=None,
                    affected_dimensions=["regulatory_risk"],
                    evidence_excerpt="The ordinance is under review and has not yet been adopted.",
                    created_at=now,
                    updated_at=now,
                ),
                TownSignal(
                    id="sig-3",
                    town="Belmar",
                    state="NJ",
                    signal_type=SignalType.CLIMATE_RISK,
                    title="Flood exposure discussion",
                    source_document_id="doc-3",
                    source_type=SourceType.NEWS,
                    source_date=now - timedelta(days=30),
                    status=SignalStatus.MENTIONED,
                    time_horizon=TimeHorizon.LONG_TERM,
                    impact_direction=ImpactDirection.NEGATIVE,
                    impact_magnitude=3,
                    confidence=0.42,
                    facts=["Flooding concerns were discussed."],
                    inference=None,
                    affected_dimensions=["climate_risk"],
                    evidence_excerpt="Residents raised flooding concerns.",
                    created_at=now,
                    updated_at=now,
                ),
            ],
        )

        self.assertIn("Boardwalk resiliency grant", summary.bullish_signals[0])
        self.assertIn("Short-term rental ordinance", summary.watch_items[0])
        self.assertEqual(summary.confidence_label, "Medium")

    def test_signal_classification_uses_cautious_bucket_rules(self) -> None:
        now = datetime.now(timezone.utc)
        proposed_positive = TownSignal(
            id="sig-watch-1",
            town="Belmar",
            state="NJ",
            signal_type=SignalType.DEVELOPMENT,
            title="North end hotel concept",
            source_document_id="doc-watch-1",
            source_type=SourceType.NEWS,
            source_date=now,
            status=SignalStatus.PROPOSED,
            time_horizon=TimeHorizon.MEDIUM_TERM,
            impact_direction=ImpactDirection.POSITIVE,
            impact_magnitude=3,
            confidence=0.84,
            facts=["The project was proposed."],
            inference=None,
            affected_dimensions=["future_supply"],
            evidence_excerpt="The project was proposed.",
            created_at=now,
            updated_at=now,
        )
        approved_negative = proposed_positive.model_copy(
            update={
                "id": "sig-risk-1",
                "title": "Flood insurance requirement expansion",
                "status": SignalStatus.APPROVED,
                "impact_direction": ImpactDirection.NEGATIVE,
                "facts": ["The ordinance was approved."],
                "evidence_excerpt": "The ordinance was approved.",
            }
        )

        self.assertEqual(classify_town_signal(proposed_positive), "watch")
        self.assertEqual(classify_town_signal(approved_negative), "bearish")

    def test_summary_builder_handles_no_signal_case(self) -> None:
        summary = build_town_summary(town="Belmar", state="NJ", signals=[])
        self.assertEqual(summary.bullish_signals, [])
        self.assertEqual(summary.bearish_signals, [])
        self.assertEqual(summary.watch_items, [])
        self.assertEqual(summary.confidence_label, "Low")

    def test_normalization_maps_legacy_document_shape(self) -> None:
        documents = normalize_source_documents(
            sample_property().local_documents,
            town="Belmar",
            state="NJ",
        )

        self.assertEqual(len(documents), 2)
        self.assertEqual(documents[0].source_type.value, "planning_board_minutes")
        self.assertTrue(documents[0].cleaned_text)
        self.assertEqual(documents[0].state, "NJ")

    def test_openai_extractor_valid_extraction(self) -> None:
        document = SourceDocument.model_validate(_fixture("planning_minutes.json"))
        client = _FakeOpenAIClient(
            _FakeResponse(
                json.dumps(
                    {
                        "signals": [
                            {
                                "signal_type": "supply",
                                "title": "1201 Main Street mixed-use redevelopment",
                                "status": "approved",
                                "time_horizon": "medium_term",
                                "impact_direction": "mixed",
                                "impact_magnitude": 4,
                                "confidence": 0.82,
                                "facts": [
                                    "The document says 24 residential units were approved.",
                                    "The board noted streetscape improvements."
                                ],
                                "inference": "The approval may add moderate future supply while also improving the corridor.",
                                "affected_dimensions": ["future_supply", "home_values", "amenity_trajectory"],
                                "evidence_excerpt": "Application for 1201 Main Street mixed-use redevelopment with 24 residential units was approved.",
                                "location": "1201 Main Street",
                                "units": 24,
                                "rationale": "Approved planning-board item with explicit unit count."
                            }
                        ]
                    }
                )
            )
        )
        extractor = OpenAILocalIntelligenceExtractor(client=client)

        signals = extractor.extract(document)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].signal_type, SignalType.SUPPLY)
        self.assertEqual(signals[0].status, SignalStatus.APPROVED)
        self.assertEqual(signals[0].metadata["units"], 24)

    def test_openai_extractor_handles_empty_extraction(self) -> None:
        document = SourceDocument.model_validate(_fixture("news_article.json"))
        extractor = OpenAILocalIntelligenceExtractor(client=_FakeOpenAIClient(_FakeResponse(json.dumps({"signals": []}))))

        signals = extractor.extract(document)

        self.assertEqual(signals, [])

    def test_openai_extractor_handles_malformed_extraction_response(self) -> None:
        document = SourceDocument.model_validate(_fixture("ordinance.json"))
        extractor = OpenAILocalIntelligenceExtractor(client=_FakeOpenAIClient(_FakeResponse("{bad json")))

        with self.assertLogs("briarwood.local_intelligence.adapters", level="WARNING") as captured:
            signals = extractor.extract(document)

        self.assertEqual(signals, [])
        self.assertTrue(any("invalid json" in line.lower() for line in captured.output))

    def test_service_reconciles_duplicate_signal_detection_against_existing(self) -> None:
        document = SourceDocument.model_validate(_fixture("planning_minutes.json"))
        extractor = OpenAILocalIntelligenceExtractor(
            client=_FakeOpenAIClient(
                _FakeResponse(
                    json.dumps(
                        {
                            "signals": [
                                {
                                    "signal_type": "supply",
                                    "title": "1201 Main Street redevelopment plan",
                                    "status": "approved",
                                    "time_horizon": "medium_term",
                                    "impact_direction": "mixed",
                                    "impact_magnitude": 4,
                                    "confidence": 0.77,
                                    "facts": ["The document states 24 residential units were approved."],
                                    "inference": "This may add moderate supply.",
                                    "affected_dimensions": ["future_supply", "home_values"],
                                    "evidence_excerpt": "Application for 1201 Main Street mixed-use redevelopment with 24 residential units was approved.",
                                    "location": "1201 Main Street",
                                    "units": 24
                                }
                            ]
                        }
                    )
                )
            )
        )
        existing_signal = TownSignal(
            id="sig-existing",
            town="Belmar",
            state="NJ",
            signal_type=SignalType.SUPPLY,
            title="1201 Main Street mixed-use redevelopment",
            source_document_id="older-doc",
            source_type=SourceType.PLANNING_BOARD_MINUTES,
            source_date=document.published_at,
            status=SignalStatus.APPROVED,
            time_horizon=TimeHorizon.MEDIUM_TERM,
            impact_direction=ImpactDirection.MIXED,
            impact_magnitude=4,
            confidence=0.81,
            facts=["Existing signal for the same project."],
            inference="Earlier extraction run.",
            affected_dimensions=["future_supply"],
            evidence_excerpt="Application for 1201 Main Street mixed-use redevelopment with 24 residential units was approved.",
            created_at=document.published_at,
            updated_at=document.published_at,
            metadata={"location": "1201 Main Street", "units": 24},
        )

        run = LocalIntelligenceService(extractor=extractor).analyze(
            town="Belmar",
            state="NJ",
            raw_documents=[document],
            existing_signals=[existing_signal],
        )

        self.assertEqual(len(run.signals), 1)
        self.assertIn("related_source_document_ids", run.signals[0].metadata)

    def test_local_intelligence_extracts_projects_and_scores(self) -> None:
        result = LocalIntelligenceModule().run(sample_property())

        self.assertEqual(result.metrics["total_projects"], 2)
        self.assertEqual(result.metrics["total_units"], 36)
        self.assertGreater(result.metrics["development_activity_score"], 0)
        self.assertGreater(result.metrics["regulatory_trend_score"], 0)
        self.assertGreater(result.confidence, 0.4)
        self.assertTrue(result.payload.projects)
        self.assertTrue(any(project.status == "approved" for project in result.payload.projects))
        self.assertTrue(result.payload.narrative)

    def test_town_pulse_view_model_renders_from_current_payload_flow(self) -> None:
        result = LocalIntelligenceModule().run(sample_property())
        pulse = build_town_pulse_view_model_from_payload(result.payload, town="Belmar", state="NJ")

        self.assertIsNotNone(pulse)
        assert pulse is not None
        self.assertEqual(pulse.section_title, "Town Pulse")
        self.assertTrue(pulse.key_signals)
        self.assertLessEqual(len(pulse.key_signals), 4)
        self.assertIn(pulse.confidence_label, {"Low", "Medium", "High"})
        self.assertTrue(any(item.source_type for item in pulse.key_signals))
        self.assertTrue(any(item.source_date_text for item in pulse.key_signals))

    def test_local_intelligence_handles_missing_documents(self) -> None:
        property_input = sample_property()
        property_input.local_documents = []
        with TemporaryDirectory() as temp_dir:
            service = LocalIntelligenceService(store=JsonLocalSignalStore(Path(temp_dir)))
            result = LocalIntelligenceModule(service=service).run(property_input)

        self.assertEqual(result.metrics["total_projects"], 0)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("unavailable", result.summary.lower())


if __name__ == "__main__":
    unittest.main()
