import asyncio
import json
import logging
import uuid
from typing import Optional

import nats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("orchestrator.log"),
    ],
)
logger = logging.getLogger("orchestrator")


class AgentOrchestrator:
    def __init__(self, nats_url: str = "nats://localhost:4222"):
        self.nc: Optional[nats.NATS] = None
        self.nats_url = nats_url
        self.results: dict[str, asyncio.Future] = {}
        self.task_counter = 0

    async def connect(self):
        self.nc = await nats.connect(servers=[self.nats_url])
        logger.info(f"Connected to NATS at {self.nats_url}")
        await self.nc.subscribe("tasks.completed", cb=self._on_result)

    async def _on_result(self, msg):
        result = json.loads(msg.data.decode())
        task_id = result.get("task_id", "")
        if task_id in self.results:
            logger.info(f"Received result for task {task_id}")
            self.results[task_id].set_result(result)
            del self.results[task_id]

    async def send_task(
        self, subject: str, payload: dict, timeout: int = 30
    ) -> dict:
        task_id = str(uuid.uuid4())
        self.task_counter += 1

        task = {
            "id": task_id,
            "type": subject,
            "payload": json.dumps(payload, ensure_ascii=False),
        }

        future: asyncio.Future = asyncio.Future()
        self.results[task_id] = future

        await self.nc.publish(subject, json.dumps(task).encode())
        logger.info(
            f"Sent task {task_id} to {subject} "
            f"(total sent: {self.task_counter})"
        )

        try:
            result = await asyncio.wait_for(future, timeout)
            logger.info(
                f"Task {task_id} completed: success={result.get('success')}"
            )
            return result
        except asyncio.TimeoutError:
            self.results.pop(task_id, None)
            logger.error(f"Task {task_id} timed out after {timeout}s")
            raise

    async def run_pipeline(self, user_data: dict) -> dict:
        pipeline_id = str(uuid.uuid4())
        logger.info("=" * 60)
        logger.info(f"PIPELINE {pipeline_id} — START")
        logger.info(f"User: {user_data['user_id']} ({user_data['user_name']})")
        logger.info("=" * 60)

        # --- Step 1: Course Recommendation ---
        logger.info("--- Step 1/4: Course Recommendation ---")
        r1 = await self.send_task("tasks.course.recommend", {
            "user_id": user_data["user_id"],
            "profile": user_data["profile"],
            "history": user_data["history"],
        })
        rec_out = json.loads(r1["output"])
        top_course = rec_out["recommendations"][0]
        logger.info(f"  Selected: {top_course['title']} (score: {top_course['score']})")

        # --- Step 2: Assignment Check ---
        logger.info("--- Step 2/4: Assignment Check ---")
        r2 = await self.send_task("tasks.assignment.check", {
            "assignment_id": user_data["assignment_id"],
            "user_id": user_data["user_id"],
            "course_id": top_course["course_id"],
            "assignment_type": user_data["assignment_type"],
            "answer": user_data["answer"],
        })
        check_out = json.loads(r2["output"])
        logger.info(f"  Result: {'PASSED' if check_out['passed'] else 'FAILED'} "
                    f"({check_out['score']}/{check_out['max_score']})")

        # --- Step 3: Progress Analysis ---
        logger.info("--- Step 3/4: Progress Analysis ---")
        augmented_log = list(user_data.get("activity_log", []))
        augmented_log.append({
            "date": "2026-05-22",
            "type": "assignment",
            "title": f"{top_course['title']} — Final",
            "score": check_out["score"],
            "completed": check_out["passed"],
        })
        completed_lessons = sum(1 for e in augmented_log if e["completed"])
        logger.info(f"  Activity log entries: {len(augmented_log)} "
                    f"(completed: {completed_lessons})")

        r3 = await self.send_task("tasks.progress.analyze", {
            "user_id": user_data["user_id"],
            "course_id": top_course["course_id"],
            "activity_log": augmented_log,
        })
        prog_out = json.loads(r3["output"])
        logger.info(f"  Completion: {prog_out['completion_pct']}%, "
                    f"Avg score: {prog_out['avg_score']}, "
                    f"Trend: {prog_out['trend']}")

        # --- Step 4: Certificate Generation ---
        logger.info("--- Step 4/4: Certificate Generation ---")
        can_certify = (
            check_out["passed"]
            and prog_out["completion_pct"] >= 80
        )
        cert_out = None

        if can_certify:
            if check_out["score"] >= 90:
                grade = "A"
            elif check_out["score"] >= 75:
                grade = "B"
            else:
                grade = "C"

            r4 = await self.send_task("tasks.certificate.generate", {
                "user_id": user_data["user_id"],
                "user_name": user_data["user_name"],
                "course_id": top_course["course_id"],
                "course_name": top_course["title"],
                "completion_date": "2026-05-22",
                "grade": grade,
                "credits": 5,
                "requirements_met": True,
            })
            cert_out = json.loads(r4["output"])
            logger.info(f"  Certificate issued: {cert_out['certificate_id']}")
            logger.info(f"  Grade: {cert_out['grade']}, URL: {cert_out['certificate_url']}")
        else:
            logger.warning("  Certificate not issued — requirements not met")

        # --- Pipeline Summary ---
        result = {
            "pipeline_id": pipeline_id,
            "user_id": user_data["user_id"],
            "recommendation": top_course,
            "assignment_check": check_out,
            "progress_analysis": prog_out,
            "certificate": cert_out,
        }

        logger.info("=" * 60)
        logger.info(f"PIPELINE {pipeline_id} — FINISHED")
        logger.info("=" * 60)
        return result

    async def close(self):
        if self.nc:
            await self.nc.drain()
            logger.info("NATS connection closed")


async def test_individual(orchestrator):
    """Run individual agent tests (from Task 1)."""
    logger.info("=" * 50)
    logger.info("INDIVIDUAL TESTS")
    logger.info("=" * 50)

    # --- Test 1: Course Recommendation ---
    logger.info("\n--- Test 1: Course Recommendation ---")
    try:
        result = await orchestrator.send_task(
            "tasks.course.recommend",
            {
                "user_id": "u-001",
                "profile": {
                    "interests": ["python", "machine learning"],
                    "skill_level": "intermediate",
                    "preferred_lang": "ru",
                },
                "history": [
                    {"course_id": "c-001", "title": "Python Basics",
                     "completed": True, "score": 85}
                ],
            },
            timeout=10,
        )
        output = json.loads(result["output"])
        logger.info(f"Recommendations for {output['user_id']}: "
                    f"{len(output['recommendations'])} found")
        for rec in output["recommendations"]:
            logger.info(f"  - {rec['title']} (score: {rec['score']}) — {rec['reason']}")
    except Exception as e:
        logger.error(f"Course Recommendation failed: {e}")

    # --- Test 2: Assignment Check ---
    logger.info("\n--- Test 2: Assignment Check ---")
    try:
        result = await orchestrator.send_task(
            "tasks.assignment.check",
            {
                "assignment_id": "a-042",
                "user_id": "u-001",
                "course_id": "c-005",
                "assignment_type": "test",
                "answer": {"choices": ["b", "c", "a", "d", "b"],
                           "code": "", "essay": ""},
            },
            timeout=10,
        )
        output = json.loads(result["output"])
        logger.info(f"Assignment {output['assignment_id']}: "
                    f"{'PASSED' if output['passed'] else 'FAILED'} "
                    f"({output['score']}/{output['max_score']})")
        logger.info(f"  Feedback: {output['feedback']}")
    except Exception as e:
        logger.error(f"Assignment Check failed: {e}")

    # --- Test 3: Progress Analysis ---
    logger.info("\n--- Test 3: Progress Analysis ---")
    try:
        result = await orchestrator.send_task(
            "tasks.progress.analyze",
            {
                "user_id": "u-001",
                "course_id": "c-005",
                "activity_log": [
                    {"date": "2026-05-01", "type": "lesson", "title": "Intro",
                     "completed": True},
                    {"date": "2026-05-03", "type": "assignment", "title": "HW1",
                     "score": 90, "completed": True},
                    {"date": "2026-05-10", "type": "assignment", "title": "HW2",
                     "score": 45, "completed": True},
                    {"date": "2026-05-15", "type": "lesson", "title": "Advanced",
                     "completed": False},
                ],
            },
            timeout=10,
        )
        output = json.loads(result["output"])
        logger.info(f"Progress for {output['user_id']} in {output['course_id']}: "
                    f"completion={output['completion_pct']}%, "
                    f"avg_score={output['avg_score']}, trend={output['trend']}")
        for rec in output.get("recommendations", []):
            logger.info(f"  Recommendation: {rec}")
    except Exception as e:
        logger.error(f"Progress Analysis failed: {e}")

    # --- Test 4: Certificate Generation ---
    logger.info("\n--- Test 4: Certificate Generation ---")
    try:
        result = await orchestrator.send_task(
            "tasks.certificate.generate",
            {
                "user_id": "u-001",
                "user_name": "Иван Иванов",
                "course_id": "c-005",
                "course_name": "ML with Python",
                "completion_date": "2026-05-20",
                "grade": "A",
                "credits": 5,
                "requirements_met": True,
            },
            timeout=10,
        )
        output = json.loads(result["output"])
        logger.info(f"Certificate generated: {output['certificate_id']}")
        logger.info(f"  URL: {output['certificate_url']}")
        logger.info(f"  Valid until: {output['valid_until']}")
    except Exception as e:
        logger.error(f"Certificate Generation failed: {e}")


async def test_pipeline(orchestrator):
    """Run the full e-learning pipeline (Task 2)."""
    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE TEST: Full e-learning chain")
    logger.info("=" * 60)

    try:
        result = await orchestrator.run_pipeline({
            "user_id": "u-001",
            "user_name": "Иван Иванов",
            "profile": {
                "interests": ["python", "machine learning"],
                "skill_level": "intermediate",
                "preferred_lang": "ru",
            },
            "history": [
                {"course_id": "c-001", "title": "Python Basics",
                 "completed": True, "score": 85}
            ],
            "assignment_id": "a-044",
            "assignment_type": "essay",
            "answer": {"choices": [], "code": "",
                       "essay": "Функция — это основной строительный блок программы. "
                                "Она принимает аргумент, выполняет действия и возвращает "
                                "результат. В Python рекурсия — это вызов функции из неё "
                                "самой. Аргумент и возврат значения — ключевые понятия."},
            "activity_log": [
                {"date": "2026-05-01", "type": "lesson", "title": "Intro to ML",
                 "completed": True},
                {"date": "2026-05-03", "type": "assignment", "title": "HW1 — Data Prep",
                 "score": 90, "completed": True},
                {"date": "2026-05-10", "type": "assignment", "title": "HW2 — Models",
                 "score": 75, "completed": True},
                {"date": "2026-05-15", "type": "lesson", "title": "Advanced Topics",
                 "completed": True},
            ],
        })

        cert = result.get("certificate")
        logger.info(f"\nPipeline {result['pipeline_id']} — SUMMARY:")
        logger.info(f"  Recommended course: {result['recommendation']['title']}")
        logger.info(f"  Assignment: {'PASSED' if result['assignment_check']['passed'] else 'FAILED'}")
        logger.info(f"  Progress: {result['progress_analysis']['completion_pct']}% complete")
        if cert:
            logger.info(f"  Certificate: {cert['certificate_id']} (grade: {cert['grade']})")
        else:
            logger.info("  Certificate: NOT ISSUED")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)


async def main():
    orchestrator = AgentOrchestrator()
    await orchestrator.connect()

    # Run individual tests (Task 1)
    await test_individual(orchestrator)

    # Run pipeline test (Task 2)
    await test_pipeline(orchestrator)

    await orchestrator.close()
    logger.info("\nAll tests completed.")


if __name__ == "__main__":
    asyncio.run(main())
