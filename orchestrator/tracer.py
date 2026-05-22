import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositeHTTPPropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


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

    set_global_textmap(CompositeHTTPPropagator([
        TraceContextTextMapPropagator(),
    ]))

    return trace.get_tracer("orchestrator", "1.0.0")
