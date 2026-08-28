"""Network-free OpenAI provider readiness tests."""

import json
from types import SimpleNamespace
import time

import pytest

import config
import db
import main
from ai_filter import REAL_API_TEST_LIMIT, SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA, build_triage_input, gemini_dry_run, openai_dry_run
from ai_providers import AIProviderError, GeminiProvider, GeminiTriageResponse, MockAIProvider, OpenAIProvider, create_provider
from tests.test_ai_filter import _candidate


VALID = json.dumps({"triage_status": "REVIEW", "triage_score": 6, "confidence": "MEDIUM", "primary_reason": "Needs more evidence.", "opportunity_type": "unmet_demand", "key_opportunity": "Validate differentiation.", "main_risks": ["competition unknown"], "needs_deep_analysis": True})


def test_gemini_response_schema_reserves_required_chinese_fields():
    fields = GeminiTriageResponse.model_fields
    assert fields["display_title_zh"].is_required()
    assert fields["primary_reason_zh"].is_required()
    assert fields["key_opportunity_zh"].is_required()
    assert fields["main_risks_zh"].is_required()
    assert fields["display_title_zh"].annotation is str


class _Responses:
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [SimpleNamespace(output_text=VALID)])
        self.calls = []
    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _Client:
    def __init__(self, outcomes=None):
        self.responses = _Responses(outcomes)


def test_openai_provider_initialization_model_timeout_and_schema():
    client = _Client()
    provider = OpenAIProvider("secret-not-printed", "gpt-5.4-nano", client)
    output = provider.analyze({"title": "test"}, "prompt", TRIAGE_JSON_SCHEMA)
    request = client.responses.calls[0]
    assert json.loads(output)["triage_score"] == 6
    assert provider.model_name == "gpt-5.4-nano"
    assert provider.TIMEOUT_SECONDS == 30
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["schema"] == TRIAGE_JSON_SCHEMA
    assert "secret-not-printed" not in repr(request)


def test_retry_once_but_authentication_does_not_retry():
    retry_client = _Client([RuntimeError("temporary"), SimpleNamespace(output_text=VALID)])
    provider = OpenAIProvider("key", "model", retry_client)
    assert provider.analyze({}, "", TRIAGE_JSON_SCHEMA) == VALID
    assert len(retry_client.responses.calls) == 2

    AuthenticationError = type("AuthenticationError", (Exception,), {})
    auth_client = _Client([AuthenticationError("bad key"), SimpleNamespace(output_text=VALID)])
    with pytest.raises(AIProviderError):
        OpenAIProvider("key", "model", auth_client).analyze({}, "", TRIAGE_JSON_SCHEMA)
    assert len(auth_client.responses.calls) == 1


def test_empty_response_fails_safely():
    with pytest.raises(AIProviderError):
        OpenAIProvider("key", "model", _Client([SimpleNamespace(output_text="")])).analyze({}, "", TRIAGE_JSON_SCHEMA)


def test_factory_selection_and_missing_key():
    assert isinstance(create_provider("mock"), MockAIProvider)
    assert isinstance(create_provider("unknown"), MockAIProvider)
    assert isinstance(create_provider("openai", api_key="key", client=_Client()), OpenAIProvider)
    with pytest.raises(AIProviderError, match="not configured"):
        create_provider("openai")


def test_dry_run_without_key_is_ready_and_never_calls_network():
    candidates = [_candidate(1, "demand_opportunity"), _candidate(2, "validated_product"), _candidate(3, "inspiration_product")]
    result = openai_dry_run(candidates, model="gpt-5.4-nano")
    assert result["request_ready"] is True
    assert result["network_request_sent"] is False
    assert len(result["selected"]) <= REAL_API_TEST_LIMIT == 5
    assert len({item.candidate_type for item in result["selected"]}) == 3


def test_model_default_and_configuration_helpers(monkeypatch):
    assert config.OPENAI_TRIAGE_MODEL == "gpt-5.4-nano"
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    assert config.is_openai_configured() is False


def test_input_allowlist_still_excludes_raw_data():
    payload = build_triage_input(_candidate(summary="<b>" + "x" * 700 + "</b>"))
    assert len(payload["description"]) == 500
    assert "raw_data" not in payload and "<b>" not in payload["description"]


class _GeminiModels:
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [SimpleNamespace(text=VALID)])
        self.calls = []
    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _GeminiClient:
    def __init__(self, outcomes=None):
        self.models = _GeminiModels(outcomes)


def test_gemini_provider_structured_output_model_timeout_and_no_key_leak():
    client = _GeminiClient()
    provider = GeminiProvider("secret-gemini", "gemini-3.5-flash-lite", client)
    assert provider.analyze({"title": "test"}, SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA) == VALID
    request = client.models.calls[0]
    assert provider.model_name == "gemini-3.5-flash-lite"
    assert provider.TIMEOUT_SECONDS == 60
    assert request["config"]["response_mime_type"] == "application/json"
    assert request["config"]["response_schema"] is GeminiTriageResponse
    assert request["config"]["system_instruction"] == SYSTEM_PROMPT
    assert request["config"]["thinking_config"].thinking_level.value == "MINIMAL"
    assert request["config"]["response_schema"].model_fields["display_title_zh"].annotation is str
    assert "secret-gemini" not in repr(request)


def test_gemini_retry_once_and_auth_does_not_retry():
    client = _GeminiClient([RuntimeError("temporary"), SimpleNamespace(text=VALID)])
    assert GeminiProvider("key", "model", client).analyze({}, SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA) == VALID
    assert len(client.models.calls) == 2
    AuthenticationError = type("AuthenticationError", (Exception,), {})
    auth = _GeminiClient([AuthenticationError("bad"), SimpleNamespace(text=VALID)])
    with pytest.raises(AIProviderError):
        GeminiProvider("key", "model", auth).analyze({}, SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA)
    assert len(auth.models.calls) == 1


def test_gemini_empty_response_and_missing_key_fail_safely():
    with pytest.raises(AIProviderError):
        GeminiProvider("key", "model", _GeminiClient([SimpleNamespace(text="")])).analyze({}, SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA)
    with pytest.raises(AIProviderError, match="not configured"):
        create_provider("gemini")


def test_gemini_factory_and_dry_run_share_schema_prompt_and_diversity():
    assert isinstance(create_provider("gemini", api_key="key", client=_GeminiClient()), GeminiProvider)
    candidates = [_candidate(1, "demand_opportunity"), _candidate(2, "validated_product"), _candidate(3, "inspiration_product")]
    result = gemini_dry_run(candidates)
    assert result["request_ready"] is True
    assert result["network_request_sent"] is False
    assert len(result["selected"]) <= REAL_API_TEST_LIMIT == 5
    provider = GeminiProvider("", "model", allow_unconfigured=True)
    request = provider.build_request(build_triage_input(candidates[0]), SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA)
    assert request["config"]["response_schema"] is GeminiTriageResponse
    assert request["config"]["system_instruction"] == SYSTEM_PROMPT


def test_gemini_schema_is_compatible_and_preserves_shared_fields_and_enums():
    schema = GeminiTriageResponse.model_json_schema()
    serialized = json.dumps(schema)
    for keyword in ("additionalProperties", "maxLength", "maxItems", "minimum", "maximum"):
        assert keyword not in serialized
    properties = schema["properties"]
    assert properties["triage_status"]["enum"] == ["PASS", "REVIEW", "REJECT"]
    assert properties["confidence"]["enum"] == ["HIGH", "MEDIUM", "LOW"]
    assert properties["opportunity_type"]["enum"] == [
        "product_improvement", "unmet_demand", "design_inspiration",
        "consumer_trend", "unknown",
    ]
    assert properties["main_risks"]["type"] == "array"
    assert properties["main_risks"]["items"]["type"] == "string"


def test_openai_keeps_raw_json_schema_when_gemini_uses_pydantic_schema():
    openai_request = OpenAIProvider("key", "model", _Client()).build_request({}, "prompt", TRIAGE_JSON_SCHEMA)
    gemini_request = GeminiProvider("key", "model", _GeminiClient()).build_request({}, "prompt", TRIAGE_JSON_SCHEMA)
    assert openai_request["text"]["format"]["schema"] is TRIAGE_JSON_SCHEMA
    assert gemini_request["config"]["response_schema"] is GeminiTriageResponse


def test_gemini_accepts_an_independent_pydantic_schema_without_affecting_defaults():
    from deep_analysis import DeepAnalysisResponse
    provider = GeminiProvider("key", "model", _GeminiClient())
    deep_request = provider.build_request({}, "deep", DeepAnalysisResponse)
    triage_request = provider.build_request({}, SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA)
    assert deep_request["config"]["response_schema"] is DeepAnalysisResponse
    assert triage_request["config"]["response_schema"] is GeminiTriageResponse


def test_gemini_config_defaults(monkeypatch):
    assert config.DEFAULT_GEMINI_TRIAGE_MODEL == "gemini-3.5-flash-lite"
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    assert config.is_gemini_configured() is False


def test_gemini_http_options_apply_timeout_and_disable_sdk_retry():
    options = GeminiProvider.build_http_options()
    assert options.timeout == 60000
    assert options.retry_options.attempts == 1
    assert 400 not in options.retry_options.http_status_codes
    assert 403 not in options.retry_options.http_status_codes


def test_gemini_504_has_at_most_one_project_retry():
    ServerError = type("ServerError", (Exception,), {})
    first = ServerError("deadline")
    first.code = 504
    second = ServerError("deadline")
    second.code = 504
    client = _GeminiClient([first, second, SimpleNamespace(text=VALID)])
    with pytest.raises(AIProviderError):
        GeminiProvider("key", "model", client).analyze({}, SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA)
    assert len(client.models.calls) == 2


def test_gemini_wall_clock_timeout_is_contained_without_project_retry():
    class SlowModels:
        calls = 0
        def generate_content(self, **kwargs):
            self.calls += 1
            time.sleep(0.2)
            return SimpleNamespace(text=VALID)
    client = SimpleNamespace(models=SlowModels())
    provider = GeminiProvider("key", "model", client)
    provider.WALL_CLOCK_SECONDS = 0.01
    with pytest.raises(AIProviderError, match="wall-clock"):
        provider.analyze({}, SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA)
    assert client.models.calls == 1


class _ConnectivityProvider(MockAIProvider):
    provider_name = "gemini"
    model_name = "gemini-3.5-flash-lite"
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0
        self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        self.usage_available = True
    def analyze(self, payload, system_prompt, json_schema=None, *, allow_retry=True):
        self.calls += 1
        if self.fail:
            raise AIProviderError("timeout")
        self.usage = {key: value + 1 for key, value in self.usage.items()}
        if "check" in payload:
            return '{"ok": true}'
        return super().analyze(payload, system_prompt, json_schema)


def test_connectivity_failure_sends_once_and_never_runs_candidate(monkeypatch):
    provider = _ConnectivityProvider(fail=True)
    monkeypatch.setattr(main.socket, "getaddrinfo", lambda *_args: [])
    monkeypatch.setattr(main.socket, "create_connection", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError()))
    assert main.run_gemini_connectivity_validation(
        output=lambda _message: None, provider=provider
    ) is False
    assert provider.calls == 1


def test_connectivity_success_runs_at_most_one_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "connectivity.db")
    candidate = _candidate()
    monkeypatch.setattr(db, "get_all_candidates", lambda: [candidate])
    monkeypatch.setattr(db, "get_candidate_commodity", lambda: {})
    monkeypatch.setattr(db, "get_all_products", lambda: [])
    provider = _ConnectivityProvider()
    assert main.run_gemini_connectivity_validation(
        output=lambda _message: None, provider=provider
    ) is True
    assert provider.calls == 2
