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

    async def close(self):
        if self.nc:
            await self.nc.drain()
            logger.info("NATS connection closed")


async def main():
    orchestrator = AgentOrchestrator()
    await orchestrator.connect()

    # --- Test 1: Course Recommendation ---
    logger.info("=" * 50)
    logger.info("Test 1: Course Recommendation")
    logger.info("=" * 50)
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
                    {
                        "course_id": "c-001",
                        "title": "Python Basics",
                        "completed": True,
                        "score": 85,
                    }
                ],
            },
            timeout=10,
        )
        output = json.loads(result["output"])
        logger.info(
            f"Recommendations for {output['user_id']}: "
            f"{len(output['recommendations'])} found"
        )
        for rec in output["recommendations"]:
            logger.info(f"  - {rec['title']} (score: {rec['score']}) — {rec['reason']}")
    except Exception as e:
        logger.error(f"Course Recommendation failed: {e}")

    # --- Test 2: Assignment Check ---
    logger.info("=" * 50)
    logger.info("Test 2: Assignment Check")
    logger.info("=" * 50)
    try:
        result = await orchestrator.send_task(
            "tasks.assignment.check",
            {
                "assignment_id": "a-042",
                "user_id": "u-001",
                "course_id": "c-005",
                "assignment_type": "test",
                "answer": {"choices": ["b", "c", "a", "d", "b"], "code": "", "essay": ""},
            },
            timeout=10,
        )
        output = json.loads(result["output"])
        logger.info(
            f"Assignment {output['assignment_id']}: "
            f"{'PASSED' if output['passed'] else 'FAILED'} "
            f"({output['score']}/{output['max_score']})"
        )
        logger.info(f"  Feedback: {output['feedback']}")
    except Exception as e:
        logger.error(f"Assignment Check failed: {e}")

    # --- Test 3: Progress Analysis ---
    logger.info("=" * 50)
    logger.info("Test 3: Progress Analysis")
    logger.info("=" * 50)
    try:
        result = await orchestrator.send_task(
            "tasks.progress.analyze",
            {
                "user_id": "u-001",
                "course_id": "c-005",
                "activity_log": [
                    {"date": "2026-05-01", "type": "lesson", "title": "Intro", "completed": True},
                    {"date": "2026-05-03", "type": "assignment", "title": "HW1", "score": 90, "completed": True},
                    {"date": "2026-05-10", "type": "assignment", "title": "HW2", "score": 45, "completed": True},
                    {"date": "2026-05-15", "type": "lesson", "title": "Advanced", "completed": False},
                ],
            },
            timeout=10,
        )
        output = json.loads(result["output"])
        logger.info(
            f"Progress for {output['user_id']} in {output['course_id']}: "
            f"completion={output['completion_pct']}%, "
            f"avg_score={output['avg_score']}, "
            f"trend={output['trend']}"
        )
        for rec in output.get("recommendations", []):
            logger.info(f"  Recommendation: {rec}")
    except Exception as e:
        logger.error(f"Progress Analysis failed: {e}")

    # --- Test 4: Certificate Generation ---
    logger.info("=" * 50)
    logger.info("Test 4: Certificate Generation")
    logger.info("=" * 50)
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
        logger.info(
            f"Certificate generated: {output['certificate_id']}"
        )
        logger.info(f"  URL: {output['certificate_url']}")
        logger.info(f"  Valid until: {output['valid_until']}")
    except Exception as e:
        logger.error(f"Certificate Generation failed: {e}")

    await orchestrator.close()
    logger.info("All tests completed.")


if __name__ == "__main__":
    asyncio.run(main())
