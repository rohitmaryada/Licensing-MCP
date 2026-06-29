"""
Observability setup for the Licensing Intelligence agent host.

Architecture: OpenTelemetry SDK as the instrumentation API, Prometheus as the backend.

Why this split?
- You write metric code once against the OTel API (meter.create_counter, etc.)
- The "exporter" determines where data goes: Prometheus here, but swap it for
  Datadog or CloudWatch in a different environment without touching instrument code.
- This is exactly what MathWorks' infra team would want: vendor-neutral instrumentation
  that can be routed to whatever backend the platform team chooses.

Signal coverage:
  Traces  → FastAPI auto-instrumentation (every HTTP request gets a span)
  Metrics → Custom instruments on tool calls, agent loop, HTTP layer
  Logs    → Standard Python logging (not wired to OTel here — left as exercise)

In production:
  - Swap ConsoleSpanExporter for OtlpGrpcSpanExporter pointing at a Tempo/Jaeger collector
  - Add exemplars to histograms to link a slow P95 sample back to its trace ID
  - Add Thanos sidecar alongside Prometheus for long-term retention and multi-cluster
"""

import time
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    make_asgi_app,
    REGISTRY,
)
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource

# ── Resource ──────────────────────────────────────────────────────────────────
# Attaches service identity to every span and metric series.
# In production: pull these from env vars injected by Kubernetes Downward API.

RESOURCE = Resource.create({
    "service.name": "licensing-mcp-agent",
    "service.version": "1.0.0",
    "deployment.environment": "development",
})


# ── Traces ────────────────────────────────────────────────────────────────────
# FastAPIInstrumentor (called in app.py) auto-creates spans for every route.
# ConsoleSpanExporter prints them to stdout — swap for OtlpGrpcSpanExporter
# to send to Grafana Tempo or Jaeger in production.

def setup_tracing() -> None:
    provider = TracerProvider(resource=RESOURCE)
    provider.add_span_processor(
        BatchSpanProcessor(ConsoleSpanExporter())
    )
    trace.set_tracer_provider(provider)


# ── HTTP metrics ──────────────────────────────────────────────────────────────
# Standard RED metrics (Rate, Errors, Duration) for the agent HTTP surface.
# These are the first thing an on-call engineer checks on a dashboard.

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "status"],
)

HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    # Buckets tuned for an interactive agent: 100ms–10s range is where latency matters.
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)


# ── MCP tool call metrics ─────────────────────────────────────────────────────
# The MCP server is a subprocess (stdio transport) — not directly scrapeable.
# We instrument the bridge layer: every tool call flows through MCPBridge.call_tool(),
# so that's our single instrumentation point for the full tool surface.

MCP_TOOL_CALLS = Counter(
    "mcp_tool_calls_total",
    "Total MCP tool calls by tool name and outcome",
    ["tool_name", "outcome"],   # outcome: "success" | "error"
)

MCP_TOOL_DURATION = Histogram(
    "mcp_tool_duration_seconds",
    "MCP tool call round-trip duration in seconds",
    ["tool_name"],
    # Tools talk to SQLite locally: should be <100ms. Alert if P95 > 2s.
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)


# ── Agent loop metrics ────────────────────────────────────────────────────────
# Each user turn may require N round-trips to the Claude API (tool_use loops).
# Tracking iterations surfaces runaway agents and unexpected complexity.

AGENT_LOOP_ITERATIONS = Counter(
    "agent_loop_iterations_total",
    "Claude API round-trips per agent turn",
)

AGENT_TURNS = Counter(
    "agent_turns_total",
    "Total agent turns (one per user message)",
    ["outcome"],  # outcome: "success" | "max_loops_hit"
)


# ── Session metrics ───────────────────────────────────────────────────────────

ACTIVE_SESSIONS = Gauge(
    "agent_sessions_active",
    "Number of currently authenticated sessions with active MCP bridges",
)


# ── Prometheus ASGI app ───────────────────────────────────────────────────────
# Mount this at /metrics in app.py. Prometheus scrapes it on its pull interval.
# Pull model = Prometheus decides when to collect, not the service.
# Contrast with push model (StatsD, InfluxDB line protocol) — each has tradeoffs.

metrics_app = make_asgi_app()


# ── Helper: HTTP middleware timer ─────────────────────────────────────────────

class _Timer:
    """Context manager for recording histogram observations."""
    def __init__(self, histogram: Histogram, labels: dict):
        self._histogram = histogram
        self._labels = labels
        self._start: float = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_):
        elapsed = time.perf_counter() - self._start
        self._histogram.labels(**self._labels).observe(elapsed)


def time_http(method: str, endpoint: str) -> _Timer:
    return _Timer(HTTP_DURATION, {"method": method, "endpoint": endpoint})
