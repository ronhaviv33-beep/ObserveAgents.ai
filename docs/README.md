# ObserveAgents Documentation

ObserveAgents is an AI agent visibility and runtime evidence platform: see what AI agents are doing, detect risky behavior, understand cost and performance, and investigate via runtime evidence — from telemetry ingestion to Agent Inventory, Agent Timeline, risk findings, and rule matches.

## Core docs

| Doc | What it covers |
|---|---|
| [architecture.md](architecture.md) | Overall platform architecture |
| [customer-integration-guide.md](customer-integration-guide.md) | Customer-facing integration guide (stakeholder + technical rollout) |
| [otel-deployment-guide.md](otel-deployment-guide.md) | Complete OpenTelemetry deployment guide |
| [telemetry_ingestion.md](telemetry_ingestion.md) | Batch telemetry ingestion: queue/worker, dedup, risk scoring, metrics, Agent Timeline |
| [telemetry_post_merge_validation.md](telemetry_post_merge_validation.md) | Post-merge validation checklist for the telemetry ingestion pipeline |
| [sdk-guide.md](sdk-guide.md) | ObserveAgents Python SDK guide |
| [runtime-flow.md](runtime-flow.md) | Runtime processing and intelligence flow |

## Specialized specs (internal)

| Doc | What it covers |
|---|---|
| [asset_intelligence.md](asset_intelligence.md) | Capability/finding derivation, catalog, and API |
| [ai_agent_runtime_security_intelligence.md](ai_agent_runtime_security_intelligence.md) | Runtime security finding types |
| [ai_agent_detection_rules_alerts_design.md](ai_agent_detection_rules_alerts_design.md) | Detection Rules & Alerts design |
| [gateway_control_center_architecture.md](gateway_control_center_architecture.md) | Observe-to-Control candidate model |
| [product_discovery_model.md](product_discovery_model.md) | Runtime + Ecosystem discovery product model |
| [soc_agents_model.md](soc_agents_model.md) | Detect → Triage → Respond operating lens |
| [roadmap.md](roadmap.md) | Phased forward roadmap |

Design/planning docs, the UI contract ([ui_contract.md](ui_contract.md), [ui_redesign_plan.md](ui_redesign_plan.md)), and the demo dataset doc ([demo_seed_data.md](demo_seed_data.md)) also live in this directory. Superseded docs are kept under [archive/](archive/).
