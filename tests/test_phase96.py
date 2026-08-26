from ai_providers import AIProviderError, MockAIProvider
from daily_ranker import OpportunityInput
from models import AITriageResult
from phase96 import run_coverage


def opportunity(index: int, source: str = "reddit_arctic_shift", kind: str = "demand_opportunity") -> OpportunityInput:
    return OpportunityInput(
        candidate_id=f"candidate-{index}", title=f"Candidate {index}",
        summary="A specific simple product opportunity with enough context.",
        opportunity_type="Software" if kind == "software" else "Physical",
        candidate_type=kind, source_platform=source,
        source_url=f"https://example.com/{index}", candidate_score=80 - index,
    )


class RecordingProvider(MockAIProvider):
    provider_name = "gemini"
    model_name = "gemini-3.5-flash-lite"

    def __init__(self, fail_first: int = 0):
        self.calls = 0
        self.fail_first = fail_first

    def analyze(self, payload, system_prompt, json_schema=None):
        self.calls += 1
        if self.calls <= self.fail_first:
            raise AIProviderError("test failure")
        return super().analyze(payload, system_prompt, json_schema)


def test_coverage_scans_new_candidates_and_skips_all_existing_statuses():
    candidates = [opportunity(i) for i in range(4)]
    existing = {"candidate-0": "PASS", "candidate-1": "REVIEW", "candidate-2": "REJECT"}
    saved: list[AITriageResult] = []
    result = run_coverage(
        candidates, provider=RecordingProvider(),
        has_result=lambda candidate_id, provider, model: candidate_id in existing,
        save_result=lambda item: saved.append(item) or True,
    )
    assert result.skipped_existing == 3
    assert result.selected == result.successful == 1
    assert saved[0].candidate_id == "candidate-3"


def test_coverage_stops_after_three_consecutive_failures_and_never_forces():
    calls = []

    def save(item, **kwargs):
        calls.append(kwargs)
        return True

    result = run_coverage(
        [opportunity(i) for i in range(12)], provider=RecordingProvider(fail_first=20),
        batch_size=50, has_result=lambda *_: False, save_result=save,
    )
    assert result.selected == result.failed == 3
    assert result.stopped_by_blocker is True
    assert calls == []


def test_all_six_sources_and_software_use_the_same_triage_path():
    sources = (
        "reddit_arctic_shift", "amazon", "kickstarter", "indiegogo",
        "yanko_design", "product_hunt",
    )
    candidates = [
        opportunity(i, source, "software" if source == "product_hunt" else "validated_product")
        for i, source in enumerate(sources)
    ]
    saved = []
    result = run_coverage(
        candidates, provider=RecordingProvider(), batch_size=10,
        has_result=lambda *_: False, save_result=lambda item: saved.append(item) or True,
    )
    assert result.successful == 6
    assert {item.candidate_id for item in saved} == {item.candidate_id for item in candidates}

