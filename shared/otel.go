package shared

import (
	"context"
	"log"
	"os"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
)

func InitTracer(serviceName string) (*sdktrace.TracerProvider, error) {
	jaegerURL := os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
	if jaegerURL == "" {
		jaegerURL = "http://localhost:4318"
	}

	exporter, err := otlptracehttp.New(
		context.Background(),
		otlptracehttp.WithEndpointURL(jaegerURL),
		otlptracehttp.WithTimeout(5*time.Second),
	)
	if err != nil {
		return nil, err
	}

	res, err := resource.New(
		context.Background(),
		resource.WithAttributes(
			semconv.ServiceName(serviceName),
			semconv.ServiceVersion("1.0.0"),
			attribute.String("service.group", "e-learning"),
		),
	)
	if err != nil {
		return nil, err
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sdktrace.AlwaysSample()),
	)

	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(
		propagation.NewCompositeTextMapPropagator(
			propagation.TraceContext{},
			propagation.Baggage{},
		),
	)

	return tp, nil
}

func ShutdownTracer(tp *sdktrace.TracerProvider) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := tp.Shutdown(ctx); err != nil {
		log.Printf("Tracer provider shutdown error: %v", err)
	}
}

type TraceCarrier struct {
	Headers map[string]string
}

func (c *TraceCarrier) Get(key string) string {
	if c.Headers == nil {
		return ""
	}
	return c.Headers[key]
}

func (c *TraceCarrier) Set(key string, value string) {
	if c.Headers == nil {
		c.Headers = make(map[string]string)
	}
	c.Headers[key] = value
}

func (c *TraceCarrier) Keys() []string {
	if c.Headers == nil {
		return nil
	}
	keys := make([]string, 0, len(c.Headers))
	for k := range c.Headers {
		keys = append(keys, k)
	}
	return keys
}

func InjectTraceContext(ctx context.Context) map[string]string {
	carrier := &TraceCarrier{}
	otel.GetTextMapPropagator().Inject(ctx, carrier)
	return carrier.Headers
}

func ExtractTraceContext(ctx context.Context, headers map[string]string) context.Context {
	if headers == nil {
		return ctx
	}
	carrier := &TraceCarrier{Headers: headers}
	return otel.GetTextMapPropagator().Extract(ctx, carrier)
}

var Tracer = otel.Tracer("e-learning")
