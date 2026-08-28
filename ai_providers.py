"""Provider abstractions for AI triage; Phase 8.1 implements mock only."""

from abc import ABC, abstractmethod
import json
from typing import Literal

from pydantic import BaseModel
import threading


class BaseAIProvider(ABC):
    provider_name: str
    model_name: str

    @abstractmethod
    def analyze(self, payload: dict, system_prompt: str, json_schema: dict | None = None) -> str:
        """Return a JSON string matching the triage schema."""


class MockAIProvider(BaseAIProvider):
    """Deterministic engineering mock that never accesses a network."""

    provider_name = "mock"
    model_name = "mock"

    def analyze(self, payload: dict, system_prompt: str, json_schema: dict | None = None) -> str:
        signals = set(payload.get("signals", []))
        hard = {"complex_electronics", "wireless", "high_regulation", "large_or_heavy", "bulky_shipping", "weapon_or_blade"}.intersection(signals)
        score = max(1, min(10, round(payload.get("candidate_score", 0) / 10)))
        has_opportunity = bool(signals - {"public_trend_list", "new_release_signal"})
        if hard:
            score = min(score, 3)
        if score >= 8 and has_opportunity and not hard:
            status, needs = "PASS", True
        elif score >= 5 and not hard:
            score, status, needs = min(score, 7), "REVIEW", True
        else:
            score, status, needs = min(score, 4), "REJECT", False
        type_map = {"validated_product": "product_improvement", "demand_opportunity": "unmet_demand", "inspiration_product": "design_inspiration", "consumer_trend": "consumer_trend"}
        return json.dumps({"triage_status": status, "triage_score": score, "confidence": "MEDIUM", "primary_reason": "Deterministic mock triage based on existing candidate evidence.", "opportunity_type": type_map.get(payload.get("candidate_type"), "unknown"), "key_opportunity": "Validate the existing low-cost micro-innovation signal in deeper research.", "main_risks": sorted(hard)[:3], "needs_deep_analysis": needs})


class AIProviderError(RuntimeError):
    """A contained AI provider configuration or request failure."""


class GeminiTriageResponse(BaseModel):
    """Gemini-compatible expression of the shared triage result fields."""

    triage_status: Literal["PASS", "REVIEW", "REJECT"]
    triage_score: int
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    primary_reason: str
    opportunity_type: Literal[
        "product_improvement",
        "unmet_demand",
        "design_inspiration",
        "consumer_trend",
        "unknown",
    ]
    key_opportunity: str
    main_risks: list[str]
    needs_deep_analysis: bool
    display_title_zh: str
    primary_reason_zh: str
    key_opportunity_zh: str
    main_risks_zh: list[str]


class OpenAIProvider(BaseAIProvider):
    """Responses API provider with Structured Outputs and bounded retry."""

    provider_name = "openai"
    TIMEOUT_SECONDS = 30
    MAX_RETRIES = 1

    def __init__(self, api_key: str, model: str, client=None, *, allow_unconfigured: bool = False):
        if not api_key and not allow_unconfigured:
            raise AIProviderError("OpenAI API key not configured")
        self.model_name = model
        self.api_calls_sent = 0
        self.api_calls_successful = 0
        self.api_calls_failed = 0
        self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        self.usage_available = False
        if client is not None:
            self.client = client
        elif allow_unconfigured:
            self.client = None
        else:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise AIProviderError("OpenAI SDK not installed") from exc
            self.client = OpenAI(api_key=api_key, timeout=self.TIMEOUT_SECONDS, max_retries=0)

    def build_request(self, payload: dict, system_prompt: str, json_schema: dict) -> dict:
        return {
            "model": self.model_name,
            "instructions": system_prompt,
            "input": json.dumps(payload, ensure_ascii=False),
            "text": {"format": {"type": "json_schema", "name": "ai_triage", "strict": True, "schema": json_schema}},
            "store": False,
        }

    def analyze(self, payload: dict, system_prompt: str, json_schema: dict | None = None) -> str:
        if self.client is None:
            raise AIProviderError("OpenAI API key not configured")
        request = self.build_request(payload, system_prompt, json_schema or {})
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = self.client.responses.create(**request)
                output = getattr(response, "output_text", "")
                if not output:
                    raise AIProviderError("OpenAI returned an invalid empty response")
                return output
            except Exception as exc:
                if isinstance(exc, AIProviderError):
                    raise
                if "authentication" in type(exc).__name__.casefold() or attempt >= self.MAX_RETRIES:
                    raise AIProviderError(f"OpenAI request failed: {type(exc).__name__}") from exc
        raise AIProviderError("OpenAI request failed")


class GeminiProvider(BaseAIProvider):
    """Google GenAI provider with shared structured output and bounded retry."""

    provider_name = "gemini"
    TIMEOUT_SECONDS = 60
    WALL_CLOCK_SECONDS = 65
    MAX_RETRIES = 1

    def __init__(self, api_key: str, model: str, client=None, *, allow_unconfigured: bool = False):
        if not api_key and not allow_unconfigured:
            raise AIProviderError("Gemini API key not configured")
        self.model_name = model
        self.api_calls_sent = 0
        self.api_calls_successful = 0
        self.api_calls_failed = 0
        self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        self.usage_available = False
        if client is not None:
            self.client = client
        elif allow_unconfigured:
            self.client = None
        else:
            try:
                from google import genai
                from google.genai import types
            except ImportError as exc:
                raise AIProviderError("Google GenAI SDK not installed") from exc
            self.client = genai.Client(
                api_key=api_key,
                http_options=self.build_http_options(),
            )

    @classmethod
    def build_http_options(cls):
        """Build official SDK options: milliseconds and no implicit retry."""
        from google.genai import types
        return types.HttpOptions(
            timeout=cls.TIMEOUT_SECONDS * 1000,
            retry_options=types.HttpRetryOptions(
                attempts=1,
                http_status_codes=[408, 429, 500, 502, 503, 504],
            ),
        )

    def _generate_with_wall_clock(self, request: dict):
        state = {}

        def invoke():
            try:
                state["response"] = self.client.models.generate_content(**request)
            except Exception as exc:
                state["error"] = exc

        worker = threading.Thread(target=invoke, daemon=True)
        worker.start()
        worker.join(self.WALL_CLOCK_SECONDS)
        if worker.is_alive():
            raise AIProviderError("Gemini request exceeded wall-clock limit")
        if "error" in state:
            raise state["error"]
        return state["response"]

    def build_request(self, payload: dict, system_prompt: str, json_schema: object) -> dict:
        from google.genai import types
        response_schema = (
            json_schema
            if isinstance(json_schema, type) and issubclass(json_schema, BaseModel)
            else GeminiTriageResponse
        )
        return {
            "model": self.model_name,
            "contents": json.dumps(payload, ensure_ascii=False),
            "config": {
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "response_schema": response_schema,
                "thinking_config": types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.MINIMAL
                ),
            },
        }

    def analyze(self, payload: dict, system_prompt: str, json_schema: dict | None = None, *, allow_retry: bool = True) -> str:
        if self.client is None:
            raise AIProviderError("Gemini API key not configured")
        request = self.build_request(payload, system_prompt, json_schema or {})
        retry_count = self.MAX_RETRIES if allow_retry else 0
        for attempt in range(retry_count + 1):
            try:
                self.api_calls_sent += 1
                response = self._generate_with_wall_clock(request)
                output = getattr(response, "text", "")
                if not output:
                    raise AIProviderError("Gemini returned an invalid empty response")
                self.api_calls_successful += 1
                usage = getattr(response, "usage_metadata", None)
                if usage is not None:
                    input_tokens = getattr(usage, "prompt_token_count", None)
                    output_tokens = getattr(usage, "candidates_token_count", None)
                    total_tokens = getattr(usage, "total_token_count", None)
                    if any(value is not None for value in (input_tokens, output_tokens, total_tokens)):
                        self.usage_available = True
                        self.usage["input_tokens"] += input_tokens or 0
                        self.usage["output_tokens"] += output_tokens or 0
                        self.usage["total_tokens"] += total_tokens or 0
                return output
            except Exception as exc:
                self.api_calls_failed += 1
                if isinstance(exc, AIProviderError):
                    raise
                name = type(exc).__name__.casefold()
                code = getattr(exc, "code", getattr(exc, "status_code", None))
                non_retryable = code in {400, 401, 403} or any(
                    term in name for term in ("authentication", "permission", "unauthenticated")
                )
                if non_retryable or attempt >= retry_count:
                    detail = f" status {code}" if code is not None else ""
                    raise AIProviderError(
                        f"Gemini request failed: {type(exc).__name__}{detail}"
                    ) from exc
        raise AIProviderError("Gemini request failed")


def create_provider(mode: str, *, api_key: str = "", model: str = "gpt-5.4-nano", client=None, dry_run: bool = False) -> BaseAIProvider:
    """Select a provider explicitly; unknown modes safely use mock."""
    if mode.casefold() == "openai":
        return OpenAIProvider(api_key, model, client, allow_unconfigured=dry_run)
    if mode.casefold() == "gemini":
        return GeminiProvider(api_key, model, client, allow_unconfigured=dry_run)
    return MockAIProvider()
