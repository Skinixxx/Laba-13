# Лабораторная работа №13 — Мультиагентные системы

**Вариант 23:** Система e-learning (Повышенный)

## Быстрый старт

```bash
# 1. Запустить NATS
docker run -d --name nats -p 4222:4222 nats:latest

# 2. Запустить 4 Go-агента
cd agents/course-recommendation && go run . &
cd agents/assignment-check && go run . &
cd agents/progress-analysis && go run . &
cd agents/certificate-gen && go run . &

# 3. Запустить оркестратор (тесты + pipeline)
cd orchestrator && source venv/bin/activate && python3 orchestrator.py

# 4. Остановить
docker stop nats && docker rm nats
```

## Агенты

| Агент | Роль | Вход | Выход |
|-------|------|------|-------|
| **Course Recommendation** | Рекомендует курсы на основе профиля и истории | UserID, профиль, история | Список рекомендованных курсов |
| **Assignment Check** | Проверяет задания (тесты, код) | AssignmentID, ответ студента | Результат проверки (passed/failed, баллы) |
| **Progress Analysis** | Анализирует прогресс студента | UserID, данные о прохождении | Статистика, отставания, рекомендации |
| **Certificate Generation** | Генерирует сертификаты | UserID, CourseID, результат | PDF-сертификат (ссылка) |

## Список заданий (повышенный уровень)

1. Разработка полной системы из 3–5 агентов на Go ✅
2. Цепочки задач (pipeline) ✅
3. Распределённая трассировка (Jaeger + OpenTelemetry)
4. Агент с состоянием (Redis)
5. Динамическое масштабирование
6. Аукционное распределение задач
7. Интеграция LLM-агента (Ollama)
8. Веб-интерфейс для мониторинга

---

## Задание 1: Разработка полной системы из 3–5 агентов на Go

### План

1. **Структура проекта** — монорепозиторий:
   ```
   ├── agents/
   │   ├── course-recommendation/   # Go-агент рекомендаций
   │   ├── assignment-check/        # Go-агент проверки заданий
   │   ├── progress-analysis/       # Go-агент анализа прогресса
   │   └── certificate-gen/         # Go-агент генерации сертификатов
   ├── orchestrator/                # Python-оркестратор
   ├── docker-compose.yml           # NATS + Redis + Jaeger
   ├── PROMPT_LOG.md
   └── README.md
   ```

2. **Общие типы данных (Go)** — пакет `shared` или `types` с JSON-структурами:
   - `Task` — задание от оркестратора (ID, тип, полезная нагрузка)
   - `Result` — результат от агента (TaskID, Success, Output, Error)

3. **Каналы NATS**:
   - `tasks.course.recommend` → `tasks.course.recommended`
   - `tasks.assignment.check` → `tasks.assignment.checked`
   - `tasks.progress.analyze` → `tasks.progress.analyzed`
   - `tasks.certificate.generate` → `tasks.certificate.generated`
   - `tasks.completed` — общий канал результатов

4. **Реализация каждого агента**:
   - Подписка на свой входящий канал
   - Бизнес-логика (симулированная или реальная)
   - Публикация результата в исходящий канал
   - Graceful shutdown

5. **docker-compose.yml** — NATS как брокер сообщений

### Структура Go-агента (шаблон)

```go
package main

import (
    "encoding/json"
    "log"
    "github.com/nats-io/nats.go"
)

type Task struct {
    ID      string `json:"id"`
    Type    string `json:"type"`
    Payload string `json:"payload"`
}

type Result struct {
    TaskID  string `json:"task_id"`
    Success bool   `json:"success"`
    Output  string `json:"output"`
}

func main() {
    nc, _ := nats.Connect(nats.DefaultURL)
    defer nc.Close()

    nc.Subscribe("tasks.<agent_type>", func(m *nats.Msg) {
        var task Task
        json.Unmarshal(m.Data, &task)
        // обработка
        result := processTask(task)
        response, _ := json.Marshal(result)
        nc.Publish("tasks.completed", response)
    })

    select {}
}
```

### Детальная реализация агентов

---

#### 1. Course Recommendation Agent

**Назначение:** Рекомендует пользователю подходящие курсы на основе его профиля и истории обучения.

**Входные данные (Payload):**
```json
{
  "user_id": "u-001",
  "profile": {
    "interests": ["python", "machine learning", "data science"],
    "skill_level": "intermediate",
    "preferred_lang": "ru"
  },
  "history": [
    {"course_id": "c-001", "title": "Python Basics", "completed": true, "score": 85},
    {"course_id": "c-002", "title": "SQL Fundamentals", "completed": false, "score": 0}
  ]
}
```

**Бизнес-логика:**
1. Загружает внутренний каталог курсов (hardcoded в агента)
2. Фильтрует уже пройденные курсы
3. Для каждого курса вычисляет **score релевантности** по формуле:
   - Совпадение интересов (interests ∩ course_tags) → +40 баллов
   - Соответствие skill_level → +30 баллов
   - Популярность (рейтинг) → +20 баллов
   - Наличие новых материалов → +10 баллов
4. Сортирует по убыванию score, возвращает топ-5

**Выходные данные:**
```json
{
  "task_id": "t-001",
  "success": true,
  "output": {
    "user_id": "u-001",
    "recommendations": [
      {"course_id": "c-005", "title": "ML with Python", "score": 92, "reason": "Совпадает с вашими интересами"},
      {"course_id": "c-008", "title": "Advanced Python", "score": 78, "reason": "Подходит вашему уровню"}
    ]
  }
}
```

---

#### 2. Assignment Check Agent

**Назначение:** Проверяет выполненные задания студентов и выставляет оценку.

**Входные данные (Payload):**
```json
{
  "assignment_id": "a-042",
  "user_id": "u-001",
  "course_id": "c-005",
  "assignment_type": "test",
  "answer": {
    "choices": ["b", "c", "a", "d", "b"],
    "code": "",
    "essay": ""
  }
}
```

**Поддерживаемые типы заданий и логика:**
- **test** — сравнивает ответы с answer_key (внутренний), считает кол-во правильных, вычисляет процент
- **code** — симулирует запуск тест-кейсов (рандомный % прохождения, но с привязкой к сложности)
- **essay** — проверяет длину (>100 символов), наличие ключевых слов из `assignment_keywords`, возвращает скоринг

**Бизнес-правила:**
- score ≥ 80% → passed
- score ≥ 50% → retry allowed
- score < 50% → failed, нужна пересдача
- max 3 попытки на одно задание

**Выходные данные:**
```json
{
  "task_id": "t-002",
  "success": true,
  "output": {
    "assignment_id": "a-042",
    "user_id": "u-001",
    "passed": true,
    "score": 85,
    "max_score": 100,
    "feedback": "Верно: 4/5. Ошибка в вопросе 3 — правильный ответ 'd'",
    "checked_at": "2026-05-22T10:00:00Z"
  }
}
```

---

#### 3. Progress Analysis Agent

**Назначение:** Анализирует прогресс студента по курсу, выявляет отставания и даёт рекомендации.

**Входные данные (Payload):**
```json
{
  "user_id": "u-001",
  "course_id": "c-005",
  "activity_log": [
    {"date": "2026-05-01", "type": "lesson", "title": "Intro", "completed": true},
    {"date": "2026-05-03", "type": "assignment", "title": "HW1", "score": 90, "completed": true},
    {"date": "2026-05-10", "type": "assignment", "title": "HW2", "score": 45, "completed": true},
    {"date": "2026-05-15", "type": "lesson", "title": "Advanced Topics", "completed": false}
  ]
}
```

**Бизнес-логика:**
1. **Completion %** = completed / total × 100
2. **Средний балл** = среднее по assignment score
3. **Тренд** — сравнивает последние 3 задания:
   - Если каждый следующий score ≥ предыдущий → "improving"
   - Если каждый следующий score ≤ предыдущий → "declining"
   - Иначе → "stable"
4. **Weak topics** — задания со score < 60% отмечает как проблемные
5. **Рекомендации** — на основе weak topics предлагает перепройти материалы

**Выходные данные:**
```json
{
  "task_id": "t-003",
  "success": true,
  "output": {
    "user_id": "u-001",
    "course_id": "c-005",
    "completion_pct": 50.0,
    "avg_score": 67.5,
    "trend": "declining",
    "weak_topics": [{"title": "HW2", "score": 45, "suggestion": "Повторить тему Advanced Topics"}],
    "recommendations": ["Пройдите урок Advanced Topics", "Повторите материалы перед HW3"]
  }
}
```

---

#### 4. Certificate Generation Agent

**Назначение:** Генерирует сертификаты о завершении курса (симулирует создание PDF).

**Входные данные (Payload):**
```json
{
  "user_id": "u-001",
  "user_name": "Иван Иванов",
  "course_id": "c-005",
  "course_name": "ML with Python",
  "completion_date": "2026-05-20",
  "grade": "A",
  "credits": 5,
  "requirements_met": true
}
```

**Бизнес-логика:**
1. Валидация — проверяет `requirements_met`
2. Генерирует уникальный `certificate_id` (UUID)
3. Создаёт запись сертификата (в реальной системе — PDF, здесь — структура данных)
4. Устанавливает срок действия (обычно бессрочный, или +3 года)
5. Возвращает метаданные сертификата

**Бизнес-правила:**
- Сертификат выдаётся только при requirements_met = true
- grade рассчитывается по среднему баллу: ≥90 → A, ≥75 → B, ≥60 → C
- certificate_url — симулированный путь `/certificates/{id}.pdf`

**Выходные данные:**
```json
{
  "task_id": "t-004",
  "success": true,
  "output": {
    "certificate_id": "cert-uuuid-xxx",
    "user_id": "u-001",
    "user_name": "Иван Иванов",
    "course_id": "c-005",
    "course_name": "ML with Python",
    "grade": "A",
    "issued_at": "2026-05-22T10:00:00Z",
    "valid_until": "2029-05-22T10:00:00Z",
    "certificate_url": "/certificates/cert-uuuid-xxx.pdf"
  }
}
```

---

## Задание 2: Цепочка задач (Pipeline)

### Описание

Реализована последовательная обработка задачи через всех 4 агентов. Оркестратор управляет цепочкой: результат каждого шага передаётся на вход следующему.

### Pipeline Flow

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant CR as CourseRec Agent
    participant AC as AssignmentCheck Agent
    participant PA as ProgressAnalysis Agent
    participant CG as CertificateGen Agent

    O->>+CR: recommend courses
    CR-->>-O: top course
    O->>+AC: check assignment (course_id from step 1)
    AC-->>-O: check result (score, passed)
    O->>+PA: analyze progress (history + new result)
    PA-->>-O: progress report (completion %, trend)
    O->>+CG: generate certificate (if passed & >=80%)
    CG-->>-O: certificate metadata
```

### Детали реализации (в `orchestrator.py:run_pipeline()`)

| Шаг | Агент | Вход (откуда данные) | Выход (куда дальше) |
|-----|-------|---------------------|-------------------|
| 1 | CourseRec | user profile + history из запроса | top_course (course_id, title, score) |
| 2 | AssignmentCheck | assignment_id из запроса + course_id из шага 1 | check_result (passed, score, feedback) |
| 3 | ProgressAnalysis | activity_log из запроса + дополненный результатом шага 2 | progress (completion_pct, avg_score, trend) |
| 4 | CertificateGen | user_name, course_name из шага 1, grade из шага 2 | certificate (certificate_id, URL, valid_until) |

### Pipeline ID

Каждый pipeline получает уникальный `pipeline_id` (UUID), который логируется на всех шагах для сквозной трассировки.

---

### Прогресс выполнения

**Задание 1 — выполнено:**
- [x] 1.1. Инициализировать Go-модули для всех 4 агентов
- [x] 1.2. Реализовать агента **Course Recommendation**
- [x] 1.3. Реализовать агента **Assignment Check**
- [x] 1.4. Реализовать агента **Progress Analysis**
- [x] 1.5. Реализовать агента **Certificate Generation**
- [x] 1.6. Написать оркестратор на Python (nats-py + asyncio)
- [x] 1.7. Создать docker-compose.yml c NATS
- [x] 1.8. Протестировать взаимодействие всех компонентов

### Как запустить (Задание 1)

```bash
# 1. NATS
docker run -d --name nats -p 4222:4222 nats:latest

# 2. Агенты (4 терминала или фон)
cd agents/course-recommendation && go run . &
cd agents/assignment-check && go run . &
cd agents/progress-analysis && go run . &
cd agents/certificate-gen && go run . &

# 3. Оркестратор (индивидуальные тесты)
cd orchestrator && source venv/bin/activate && python3 orchestrator.py

# 4. Очистка
docker stop nats && docker rm nats
```

**Задание 2 — выполнено:**
- [x] 2.1. Реализовать `run_pipeline()` в оркестраторе
- [x] 2.2. Chain: CourseRec → AssignmentCheck → ProgressAnalysis → CertificateGen
- [x] 2.3. Сквозной pipeline_id для трассировки
- [x] 2.4. Условная генерация сертификата (passed + completion >= 80%)

### Как запустить (Задание 2)

```bash
# 1. NATS
docker run -d --name nats -p 4222:4222 nats:latest

# 2. Агенты
cd agents/course-recommendation && go run . &
cd agents/assignment-check && go run . &
cd agents/progress-analysis && go run . &
cd agents/certificate-gen && go run . &

# 3. Pipeline-тест (выполнит все 4 шага цепочки)
cd orchestrator && source venv/bin/activate && python3 orchestrator.py
# В логе искать:
#   PIPELINE <uuid> — START
#   Step 1/4 → Step 2/4 → Step 3/4 → Step 4/4
#   Certificate issued: <uuid> (grade: B)

# 4. Очистка
docker stop nats && docker rm nats
```
