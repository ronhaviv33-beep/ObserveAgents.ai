"""
ObserveAgents Python SDK — the first low-friction adapter over POST /runtime-events.

Wrap your OpenAI or Anthropic client with `ObserveOpenAI` / `ObserveAnthropic` and every
call emits one safe `llm_call` runtime event (metadata only, never content) to
ObserveAgents, where the existing intelligence engine derives assets, findings,
detection rules, and control candidates. See docs/sdk-guide.md.
"""
from observeagents.anthropic import ObserveAnthropic
from observeagents.openai import ObserveOpenAI

__version__ = "0.2.0"

__all__ = ["ObserveOpenAI", "ObserveAnthropic", "__version__"]
