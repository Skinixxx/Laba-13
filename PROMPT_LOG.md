# PROMT LOG

## Вариант 23 — Система e-learning
**Уровень:** Повышенный

**Описание области:** Рекомендация курсов, Проверка заданий, Анализ прогресса, Генерация сертификатов.

**Технологии:** Go (агенты), Python (оркестратор), NATS (брокер), Docker

---

## Задание 1 — Разработка полной системы из 3–5 агентов на Go

**Промпт 1:** Изучил PDF. Вариант 23, e-learning, повышенный. Предлагаю сперва подумать, потом сделать README с планом Задания 1.

**Результат:**
- Создан PROMPT_LOG.md, README.md с планом
- Определены 4 агента: CourseRec, AssignmentCheck, ProgressAnalysis, CertificateGen
- Расписаны входные/выходные данные и бизнес-логика каждого

**Промпт 2:** План устраивает, приступить к реализации.

**Результат:**
- Создана структура проекта: `shared/` + 4 агента + `orchestrator/` + `docker-compose.yml`
- `shared` — общий Go-пакет с типами (Task, Result, структуры для каждого агента)
- **Course Recommendation Agent** — скоринг релевантности (интересы/уровень/рейтинг), каталог 10 курсов
- **Assignment Check Agent** — тесты (answer key), код (тест-кейсы), эссе (ключевые слова)
- **Progress Analysis Agent** — completion %, тренд (improving/declining/stable), weak topics
- **Certificate Generation Agent** — UUID, метаданные, срок действия 3 года
- **Orchestrator (Python)** — nats-py + asyncio, send_task с Future/таймаутом
- **docker-compose.yml** — NATS + 4 Dockerfile'а для агентов
- Все 4 Go-агента скомпилированы, Python-зависимости установлены

**Промпт 3:** Сначала локально систему протестируем.

**Результат:**
- Запущен NATS в Docker + 4 агента + оркестратор

| Тест | Результат |
|------|-----------|
| Course Recommendation | 5 рекомендаций, топ "Машинное обучение с Python" (score: 79) |
| Assignment Check | PASSED (100/100) |
| Progress Analysis | 75% completion, declining trend |
| Certificate Generation | UUID, URL `/certificates/...`, срок до 2029 |

**Промпт 4:** Создай коммит.

**Результат:** Коммит `8dc4445` — 28 файлов, 1670 строк.

---

## Задание 2 — Цепочки задач (pipeline)

**Промпт 1:** Приступаем ко второму заданию. Цепочки задач (pipeline). Составь план.

**Результат:** Предложен pipeline: Старт → Рекомендация курсов → Проверка задания → Анализ прогресса → Генерация сертификата. Оркестратор управляет цепочкой, агенты не меняются. Выбран сценарий с эссе (a-044) для успешного прохождения.

**Промпт 2:** Пайплайн зашел, приступи к реализации.

**Результат:**
- Добавлен метод `run_pipeline()` в оркестратор
- Chain: CourseRec → AssignmentCheck → ProgressAnalysis → CertificateGen
- Результат каждого шага передаётся на вход следующему
- Сертификат выдаётся условно (passed + completion >= 80%)
- Сквозной pipeline_id для трассировки

**Промпт 3:** Протестировать pipeline.

**Результат:**

| Шаг | Агент | Результат |
|-----|-------|-----------|
| 1 | CourseRec | "Машинное обучение с Python" (score: 79) |
| 2 | AssignmentCheck | PASSED (80/100) — эссе |
| 3 | ProgressAnalysis | 100% completion, avg 81.67, trend stable |
| 4 | CertificateGen | **Сертификат выдан** — Grade B |

Pipeline ID `2c362a31` — весь chain отработал, сертификат сгенерирован.

---

## Задание 3 — Распределённая трассировка (Jaeger + OpenTelemetry)

**Промпт 1:** Расписать, что необходимо сделать и как это можно сделать.

**Результат:** Предложен план:
- `shared/otel.go` — инициализация OTel tracer для Go-агентов
- `orchestrator/tracer.py` — инициализация OTel tracer для Python
- NATS headers для W3C TraceContext propagation
- Обновление docker-compose: Jaeger all-in-one (порты 4318/16686)

**Промпт 2:** Реализовать.

**Результат:**
- `shared/otel.go` — InitTracer(serviceName), ShutdownTracer, InjectTraceContext, ExtractTraceContext
- 4 Go-агента обновлены: каждый создаёт span на обработку задачи с атрибутами (task.id, user.id, result)
- `orchestrator/tracer.py` — инициализация OTel с HTTP OTLP exporter
- `orchestrator/orchestrator.py` — span для pipeline, span для каждого шага, inject trace context в NATS headers
- docker-compose.yml — добавлен Jaeger + OTEL_EXPORTER_OTLP_ENDPOINT для всех агентов
- Dockerfile'ы обновлены (shared-модуль включён в контекст сборки)

**Промпт 3:** Протестировать.

**Результат:** Запущены NATS + Jaeger + 4 агента + оркестратор. В Jaeger UI:

| Трейс | Spans | Описание |
|-------|-------|----------|
| Individual tests | 9 spans | `test.individual` → 4 дочерних (по одному на агента) + 4 agent.process spans |
| Pipeline | 9 spans | `pipeline.39c8070e` → 4 step spans + 4 agent.process spans |

Трассировка распределённая: spans от Python-оркестратора и Go-агентов связаны через W3C TraceContext, передаваемый в NATS headers. Jaeger UI доступен на `http://localhost:16686`.
