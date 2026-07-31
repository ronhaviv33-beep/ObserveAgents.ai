"""
ObserveAgents Python SDK — low-level helpers for POST /runtime-events.

The recommended way to send runtime evidence to ObserveAgents is OpenTelemetry:
instrument your runtime with standard OTel libraries and export OTLP (directly or
through an OpenTelemetry Collector) to ObserveAgents ingestion. See
docs/otel-deployment-guide.md.

This package keeps only the content-free runtime-events building blocks
(`observeagents.events`, `observeagents.client`, `observeagents.privacy`,
`observeagents.ids`); it contains no provider-specific wrapper.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
