from datetime import datetime, timezone
from sqlalchemy import Integer, String, Float, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

# Cost per 1M tokens (USD) — update as pricing changes
COST_PER_1M = {
    # Anthropic
    "claude-opus-4":          {"prompt": 15.00,  "completion": 75.00},
    "claude-sonnet-4":        {"prompt": 3.00,   "completion": 15.00},
    "claude-haiku-4":         {"prompt": 0.80,   "completion": 4.00},
    # OpenAI
    "gpt-4.1":                {"prompt": 2.00,   "completion": 8.00},
    "gpt-4.1-mini":           {"prompt": 0.40,   "completion": 1.60},
    "gpt-4o":                 {"prompt": 2.50,   "completion": 10.00},
    "gpt-4o-mini":            {"prompt": 0.15,   "completion": 0.60},
    "gpt-4-turbo":            {"prompt": 10.00,  "completion": 30.00},
    "gpt-3.5-turbo":          {"prompt": 0.50,   "completion": 1.50},
    "o3":                     {"prompt": 10.00,  "completion": 40.00},
    "o4-mini":                {"prompt": 1.10,   "completion": 4.40},
    # Google
    "gemini-2.0-pro":         {"prompt": 1.25,   "completion": 5.00},
    "gemini-2.0-flash":       {"prompt": 0.075,  "completion": 0.30},
    "gemini-1.5-pro":         {"prompt": 1.25,   "completion": 5.00},
    # Local / open-source (negligible marginal cost)
    "llama-3.1-70b-local":    {"prompt": 0.20,   "completion": 0.20},
    "llama-3.1-8b-local":     {"prompt": 0.05,   "completion": 0.05},
}

_DEFAULT_PRICING = {"prompt": 0.15, "completion": 0.60}  # gpt-4o-mini as safe default


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = COST_PER_1M.get(model, _DEFAULT_PRICING)
    prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
    completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]
    return round(prompt_cost + completion_cost, 8)


class BudgetRule(Base):
    __tablename__ = "budget_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    team: Mapped[str] = mapped_column(String(128))           # team name or "*" for global
    agent: Mapped[str | None] = mapped_column(String(128), nullable=True)  # None = team-wide
    limit_usd: Mapped[float] = mapped_column(Float)
    period: Mapped[str] = mapped_column(String(16))          # "daily" | "monthly"
    action: Mapped[str] = mapped_column(String(16))          # "alert" | "block"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Telemetry(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    team: Mapped[str] = mapped_column(String(128))
    agent: Mapped[str] = mapped_column(String(128))
    model: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
