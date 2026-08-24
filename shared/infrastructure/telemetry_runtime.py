from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


class TelemetryRuntime:
    def __init__(self, service_name: str) -> None:
        self._provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
        self._provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

    def start(self) -> None:
        trace.set_tracer_provider(self._provider)

    def stop(self) -> None:
        self._provider.shutdown()
