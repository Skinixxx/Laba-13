import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def init_tracer():
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

    resource = Resource.create({
        "service.name": "orchestrator",
        "service.version": "1.0.0",
        "service.group": "e-learning",
    })

    exporter = OTLPSpanExporter(endpoint=endpoint + "/v1/traces")
    span_processor = BatchSpanProcessor(exporter)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(span_processor)
    trace.set_tracer_provider(provider)

    return trace.get_tracer("orchestrator", "1.0.0")
