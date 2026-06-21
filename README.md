# EdgeSentry

> An end-to-end edge-to-cloud ML platform: a Raspberry Pi Pico reads sensor data,
> a cloud pipeline on Kubernetes uses an LLM to turn anomalies into plain-English
> incident summaries — with guardrails, drift detection, and full observability.

![status](https://img.shields.io/badge/status-in--development-yellow)
<!-- TODO: add CI badge once GitHub Actions is set up (step 12) -->
<!-- TODO: add license badge -->

## What it does

EdgeSentry monitors a physical environment with a low-cost edge device and uses
an LLM to make the data human-readable. Instead of a human watching dashboards,
the system detects anomalies and explains — in plain English — what happened,
why it likely happened, and how serious it is.

The headline idea: **edge hardware → streaming pipeline → LLM reasoning → observability**,
built with production-grade tooling on a tight (8GB RAM) local setup.

## Architecture

```
[Pico + DHT22]            physical edge device, reads temp/humidity
      | USB serial (JSON lines)
      v
[Bridge script]           runs on host; serial -> MQTT (adapter layer)
      | MQTT
      v
[Mosquitto broker]        message queue, in-cluster
      | subscribe
      v
[FastAPI ingestion]       validates, stores, detects drift, calls LLM
      |                   (runs on k3d / local Kubernetes)
      +--> [LLM layer]    swappable: Ollama (local 3B) | Anthropic API (fallback)
      +--> [Guardrails]   PII scrub, injection filter, output validation
      +--> [Storage]      time-series readings
      v
[Prometheus + Grafana]    pipeline metrics + device fleet health
[Langfuse]                LLM tracing (latency, cost, quality)
```
<!-- TODO: replace ASCII diagram with a proper image (docs/architecture.md) -->

## Tech stack

| Layer            | Tooling                                          |
|------------------|--------------------------------------------------|
| Edge device      | Raspberry Pi Pico, DHT22, MicroPython            |
| Transport        | USB serial → bridge → MQTT (Mosquitto)           |
| Backend          | Python, FastAPI, Pydantic                        |
| LLM              | Ollama (llama3.2:3b) with Anthropic API fallback |
| Orchestration    | Kubernetes (k3d), Helm                           |
| Infra-as-code    | Terraform                                        |
| Observability    | Prometheus, Grafana, Langfuse                    |
| CI/CD            | GitHub Actions                                   |

## Repository layout

```
firmware/      MicroPython code that runs on the Pico
bridge/        host-side serial-to-MQTT adapter
simulator/     fake device for development/CI (no hardware needed)
services/      the FastAPI ingestion service + LLM + guardrails
deploy/        Mosquitto, Helm chart, Terraform
observability/ Prometheus config + Grafana dashboards
docs/          architecture notes + decision records (ADRs)
```

## Status / roadmap

- [x] Repo + tooling setup
- [ ] Firmware: DHT22 read + edge pre-filter
- [ ] Serial-to-MQTT bridge
- [ ] Device simulator
- [ ] FastAPI ingestion + data contract
- [ ] LLM summarizer + guardrails
- [ ] Drift detection
- [ ] Kubernetes deploy (Mosquitto, Helm, Terraform)
- [ ] Observability (Prometheus, Grafana, Langfuse)
- [ ] CI/CD pipeline with LLM eval gate

## Getting started

<!-- TODO: fill in as components land -->
_Coming soon — instructions will be added as each component is built._

## Design decisions

Key architectural choices are documented as ADRs in [`docs/adr/`](docs/adr/):
<!-- TODO: link these once written -->
- Why a serial bridge instead of direct wifi
- Why filter readings on the edge device
- Why a swappable LLM backend

## License

<!-- TODO: choose a license (MIT is a common, permissive choice) -->