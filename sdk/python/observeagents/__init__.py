"""
ObserveAgents Python SDK — the first low-friction adapter over POST /runtime-events.

Wrap your OpenAI client with `ObserveOpenAI` and every chat-completion call emits one
safe `llm_call` runtime event (metadata only, never content) to ObserveAgents, where the
existing intelligence engine derives assets, findings, detection rules, and control
candidates. See docs/python_sdk_mvp_implementation_plan.md.
"""
from observeagents.openai import ObserveOpenAI

__version__ = "0.1.0"

__all__ = ["ObserveOpenAI", "__version__"]
