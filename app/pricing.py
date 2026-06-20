"""
PricingRegistry — centralized model pricing abstraction.

Wraps the COST_PER_1M table in models.py and provides a clean, versioned API
for cost calculations with estimated/exact flagging. Use the module-level
`registry` singleton; do not instantiate PricingRegistry directly.
"""
from __future__ import annotations

from app.models import COST_PER_1M, PRICING_LAST_UPDATED, _DEFAULT_PRICING, _normalize_model


class PricingRegistry:
    """Central registry for LLM pricing across all providers."""

    def get_price(self, model: str, token_type: str) -> tuple[float, bool]:
        """
        Return (price_per_million_tokens, is_estimated).
        token_type: "input" | "output"
        is_estimated=True when the model falls back to default pricing.
        """
        normalized = _normalize_model(model)
        pricing = COST_PER_1M.get(model) or COST_PER_1M.get(normalized)
        is_estimated = pricing is None
        if is_estimated:
            pricing = _DEFAULT_PRICING
        key = "prompt" if token_type == "input" else "completion"
        return pricing[key], is_estimated

    def calculate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> tuple[float, bool]:
        """
        Calculate total cost for a single request.
        Returns (cost_usd, is_estimated).
        """
        input_price, is_estimated = self.get_price(model, "input")
        output_price, _ = self.get_price(model, "output")
        input_cost  = (prompt_tokens / 1_000_000) * input_price
        output_cost = (completion_tokens / 1_000_000) * output_price
        return round(input_cost + output_cost, 8), is_estimated

    def get_provider(self, model: str) -> str:
        """Infer provider from model name."""
        m = _normalize_model(model or "").lower()
        if "claude" in m:
            return "anthropic"
        if m.startswith(("gpt", "o1", "o3", "o4")):
            return "openai"
        if "gemini" in m:
            return "google"
        if "llama" in m or "local" in m:
            return "local"
        return "unknown"

    def get_all_models(self) -> list[str]:
        return list(COST_PER_1M.keys())

    def last_updated(self) -> str:
        return PRICING_LAST_UPDATED

    def get_pricing_table(self) -> dict:
        """Return pricing structured by provider for display."""
        by_provider: dict[str, dict] = {}
        for model, pricing in COST_PER_1M.items():
            provider = self.get_provider(model)
            by_provider.setdefault(provider, {})[model] = {
                "input_cost_per_million":  pricing["prompt"],
                "output_cost_per_million": pricing["completion"],
            }
        return by_provider


# Module-level singleton — import this, not the class.
registry = PricingRegistry()
