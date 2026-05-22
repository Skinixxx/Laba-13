import json
import logging
import os
import signal
import sys
from pathlib import Path

import nats
from opentelemetry import trace as otel_trace
from opentelemetry.propagate import inject, extract

from fallback import generate_feedback
from llm_client import OllamaClient
from prompt_templates import SYSTEM_PROMPT

log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(log_dir / "llm_feedback.log")),
    ],
)
logger = logging.getLogger("llm_feedback")

OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

try:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({
        "service.name": "llm-feedback",
        "service.version": "1.0.0",
    })
    exporter = OTLPSpanExporter(endpoint=OTEL_ENDPOINT + "/v1/traces")
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    otel_trace.set_tracer_provider(provider)
    tracer = otel_trace.get_tracer("llm-feedback")
    logger.info(f"Tracer initialized (OTLP: {OTEL_ENDPOINT})")
except Exception as e:
    tracer = otel_trace.NoOpTracer()
    logger.warning(f"Tracer not available, using NoOp: {e}")


def extract_trace_context(headers: dict) -> object:
    ctx = {}
    for key, vals in headers.items():
        if isinstance(vals, list) and len(vals) > 0:
            ctx[key] = vals[0]
        else:
            ctx[key] = vals
    return extract(ctx)


def inject_trace_context() -> dict:
    headers = {}
    inject(headers)
    return headers


OLLAMA_URL = os.getenv("OLLAMA_URL", "").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "tinyllama")

ollama = OllamaClient(base_url=OLLAMA_URL or "http://localhost:11434", model=OLLAMA_MODEL)
ollama_available = False


def build_prompt(data: dict) -> tuple[str, str]:
    system = SYSTEM_PROMPT.format(
        user_name=data.get("user_name", "Студент"),
        skill_level=data.get("skill_level", "средний"),
        interests=", ".join(data.get("interests", [])),
        course_name=data.get("course_name", "Курс"),
        assignment_type=data.get("assignment_type", "unknown"),
        score=data.get("score", 0),
        max_score=data.get("max_score", 100),
        passed=data.get("passed", False),
        trend=data.get("trend", "stable"),
        avg_score=data.get("avg_score", 0),
    )
    prompt = f"Студент: {data.get('user_name', 'Студент')}\n"
    prompt += f"Тип задания: {data.get('assignment_type', 'unknown')}\n"
    prompt += f"Баллы: {data.get('score', 0)}/{data.get('max_score', 100)}\n"
    prompt += f"Результат: {'Пройдено' if data.get('passed') else 'Не пройдено'}\n"
    prompt += f"Тренд: {data.get('trend', 'stable')}\n"

    if data.get("assignment_type") == "essay":
        prompt += f"Ключевые слова: {data.get('keywords', '')}\n"
        prompt += f"Количество слов: {data.get('word_count', 0)}\n"
        prompt += f"Текст эссе: {data.get('essay_text', '')[:500]}\n"
    elif data.get("assignment_type") == "code":
        prompt += f"Тесты пройдено: {data.get('passed_tests', 0)}/{data.get('total_tests', 0)}\n"
    elif data.get("assignment_type") == "test":
        prompt += f"Всего вопросов: {data.get('total_questions', 0)}\n"
        prompt += f"Верных ответов: {data.get('correct', 0)}\n"

    prompt += "\nДай развёрнутый отзыв (3-5 предложений на русском языке)."
    return system, prompt


async def main():
    global ollama_available

    if OLLAMA_URL:
        try:
            ollama_available = ollama.is_available()
            if ollama_available:
                models = ollama.list_models()
                logger.info(f"Ollama доступен ({OLLAMA_URL}). Модели: {models}")
            else:
                logger.warning(f"Ollama НЕ доступен ({OLLAMA_URL}). Используется fallback.")
        except Exception as e:
            ollama_available = False
            logger.warning(f"Ollama недоступен: {e}. Используется fallback.")
    else:
        logger.info("OLLAMA_URL не указан. Используется fallback-генератор отзывов.")

    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
    nc = await nats.connect(servers=[nats_url])
    logger.info(f"Connected to NATS at {nats_url}")

    async def handler(msg):
        headers = {}
        for k, v in msg.header.items():
            if len(v) > 0:
                headers[k] = v[0]

        ctx = extract_trace_context(headers)
        with tracer.start_as_current_span("llm-feedback.generate",
                                          context=ctx) as span:
            try:
                task = json.loads(msg.data.decode())
                data = json.loads(task["payload"]) if isinstance(task.get("payload"), str) else task
                span.set_attribute("task.id", task.get("id", ""))
                span.set_attribute("user.id", data.get("user_id", ""))
                span.set_attribute("assignment.type", data.get("assignment_type", ""))
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to parse task: {e}")
                return

            logger.info(
                f"Generating feedback for {data.get('user_name', '?')} "
                f"(type={data.get('assignment_type', '?')}, "
                f"score={data.get('score', '?')}/{data.get('max_score', '?')})"
            )

            feedback = ""

            if ollama_available:
                system_prompt, user_prompt = build_prompt(data)
                try:
                    result = ollama.generate(user_prompt, system=system_prompt)
                    if result:
                        feedback = result
                        logger.info("Feedback generated via Ollama")
                        span.set_attribute("llm.source", "ollama")
                except Exception as e:
                    logger.error(f"Ollama generation failed: {e}")

            if not feedback:
                feedback = generate_feedback(**data)
                logger.info("Feedback generated via fallback")
                span.set_attribute("llm.source", "fallback")

            span.set_attribute("feedback.length", len(feedback))
            span.set_attribute("feedback.source", "ollama" if ollama_available and feedback != generate_feedback.__name__ else "fallback")

            output = {
                "user_id": data.get("user_id", ""),
                "feedback": feedback,
                "generated_at": __import__("datetime").datetime.now().isoformat(),
            }

            result = {
                "task_id": task.get("id", ""),
                "success": True,
                "output": json.dumps(output, ensure_ascii=False),
            }

            response = json.dumps(result, ensure_ascii=False).encode()
            headers = inject_trace_context()
            await nc.publish("tasks.completed", response, headers=headers)

            logger.info(f"Feedback sent for task {task.get('id', '')[:8]} ({len(feedback)} chars)")

    await nc.subscribe("tasks.feedback.generate", cb=handler)
    logger.info("LLM Feedback Agent ready. Waiting for tasks...")

    stop = asyncio.Future()

    def shutdown():
        if not stop.done():
            stop.set_result(True)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown)
        except NotImplementedError:
            signal.signal(sig, lambda s, f: shutdown())

    await stop
    logger.info("Shutting down...")
    await nc.drain()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
