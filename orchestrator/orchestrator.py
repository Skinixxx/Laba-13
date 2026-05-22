import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

import nats
from opentelemetry import trace as otel_trace
from opentelemetry.propagate import inject, extract

from tracer import init_tracer

log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(log_dir / "orchestrator.log")),
    ],
)
logger = logging.getLogger("orchestrator")


class AgentOrchestrator:
    def __init__(self, nats_url: str = "nats://localhost:4222"):
        self.nc: Optional[nats.NATS] = None
        self.nats_url = nats_url
        self.results: dict[str, asyncio.Future] = {}
        self.task_counter = 0
        self.tracer = otel_trace.get_tracer("orchestrator")

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
        self, subject: str, payload: dict, timeout: int = 30,
        parent_ctx: Optional[object] = None,
        step_name: str = "",
    ) -> dict:
        task_id = str(uuid.uuid4())
        self.task_counter += 1

        task = {
            "id": task_id,
            "type": subject,
            "payload": json.dumps(payload, ensure_ascii=False),
        }

        span_name = step_name or f"send.{subject}"
        ctx = parent_ctx or otel_trace.get_current_span().get_span_context()

        with self.tracer.start_as_current_span(
            span_name, context=ctx,
            kind=otel_trace.SpanKind.PRODUCER,
        ) as span:
            span.set_attribute("task.id", task_id)
            span.set_attribute("messaging.system", "nats")
            span.set_attribute("messaging.destination", subject)

            headers = {}
            inject(headers)
            span.set_attribute("trace.id", hex(span.get_span_context().trace_id))

            future: asyncio.Future = asyncio.Future()
            self.results[task_id] = future

            await self.nc.publish(
                subject, json.dumps(task).encode(),
                headers=headers,
            )
            logger.info(
                f"Sent task {task_id} to {subject} "
                f"(total sent: {self.task_counter})"
            )

            try:
                result = await asyncio.wait_for(future, timeout)
                logger.info(
                    f"Task {task_id} completed: success={result.get('success')}"
                )
                span.set_attribute("task.success", result.get("success", False))
                return result
            except asyncio.TimeoutError:
                self.results.pop(task_id, None)
                logger.error(f"Task {task_id} timed out after {timeout}s")
                span.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR,
                                                   "timeout"))
                raise

    async def run_pipeline(self, user_data: dict) -> dict:
        pipeline_id = str(uuid.uuid4())
        logger.info("=" * 60)
        logger.info(f"PIPELINE {pipeline_id} — START")
        logger.info(f"User: {user_data['user_id']} ({user_data['user_name']})")
        logger.info("=" * 60)

        with self.tracer.start_as_current_span(
            f"pipeline.{pipeline_id[:8]}",
            kind=otel_trace.SpanKind.INTERNAL,
        ) as pipeline_span:
            pipeline_span.set_attribute("pipeline.id", pipeline_id)
            pipeline_span.set_attribute("user.id", user_data["user_id"])
            pipeline_span.set_attribute("user.name", user_data["user_name"])

            pipeline_ctx = otel_trace.set_span_in_context(pipeline_span)

            # --- Step 1: Course Recommendation ---
            logger.info("--- Step 1/4: Course Recommendation ---")
            r1 = await self.send_task(
                "tasks.course.recommend", {
                    "user_id": user_data["user_id"],
                    "profile": user_data["profile"],
                    "history": user_data["history"],
                },
                parent_ctx=pipeline_ctx,
                step_name="step.course_recommend",
            )
            rec_out = json.loads(r1["output"])
            top_course = rec_out["recommendations"][0]
            pipeline_span.set_attribute("recommended.course", top_course["title"])
            logger.info(f"  Selected: {top_course['title']} (score: {top_course['score']})")

            # --- Step 2: Assignment Check (через аукцион) ---
            logger.info("--- Step 2/4: Assignment Check (auction) ---")
            r2 = await self.run_auction(
                "tasks.auction.check", {
                    "assignment_id": user_data["assignment_id"],
                    "user_id": user_data["user_id"],
                    "course_id": top_course["course_id"],
                    "assignment_type": user_data["assignment_type"],
                    "answer": user_data["answer"],
                },
                parent_ctx=pipeline_ctx,
                step_name="step.assignment_check",
                auction_timeout=0.5,
            )
            check_out = json.loads(r2["output"])
            pipeline_span.set_attribute("assignment.passed", check_out["passed"])
            pipeline_span.set_attribute("assignment.score", check_out["score"])
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

            r3 = await self.send_task(
                "tasks.progress.analyze", {
                    "user_id": user_data["user_id"],
                    "course_id": top_course["course_id"],
                    "activity_log": augmented_log,
                },
                parent_ctx=pipeline_ctx,
                step_name="step.progress_analysis",
            )
            prog_out = json.loads(r3["output"])
            pipeline_span.set_attribute("progress.completion_pct",
                                        prog_out["completion_pct"])
            pipeline_span.set_attribute("progress.trend", prog_out["trend"])
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
                grade = "A" if check_out["score"] >= 90 else "B" if check_out["score"] >= 75 else "C"

                r4 = await self.send_task(
                    "tasks.certificate.generate", {
                        "user_id": user_data["user_id"],
                        "user_name": user_data["user_name"],
                        "course_id": top_course["course_id"],
                        "course_name": top_course["title"],
                        "completion_date": "2026-05-22",
                        "grade": grade,
                        "credits": 5,
                        "requirements_met": True,
                    },
                    parent_ctx=pipeline_ctx,
                    step_name="step.certificate_generate",
                )
                cert_out = json.loads(r4["output"])
                pipeline_span.set_attribute("certificate.id",
                                            cert_out["certificate_id"])
                pipeline_span.set_attribute("certificate.grade",
                                            cert_out["grade"])
                logger.info(f"  Certificate issued: {cert_out['certificate_id']}")
                logger.info(f"  Grade: {cert_out['grade']}, URL: {cert_out['certificate_url']}")
            else:
                pipeline_span.set_attribute("certificate.issued", False)
                logger.warning("  Certificate not issued — requirements not met")

            # --- Step 5: LLM Feedback ---
            logger.info("--- Step 5/5: LLM Feedback ---")
            try:
                r5 = await self.send_task(
                    "tasks.feedback.generate", {
                        "user_id": user_data["user_id"],
                        "user_name": user_data["user_name"],
                        "skill_level": user_data["profile"]["skill_level"],
                        "interests": user_data["profile"]["interests"],
                        "course_name": top_course["title"],
                        "assignment_type": user_data["assignment_type"],
                        "score": check_out["score"],
                        "max_score": check_out["max_score"],
                        "passed": check_out["passed"],
                        "trend": prog_out["trend"],
                        "avg_score": prog_out["avg_score"],
                        "essay_text": user_data.get("answer", {}).get("essay", ""),
                        "word_count": len(user_data.get("answer", {}).get("essay", "").split()),
                        "keywords": "функция, аргумент, возврат, рекурсия",
                    },
                    parent_ctx=pipeline_ctx,
                    step_name="step.llm_feedback",
                    timeout=15,
                )
                feedback_out = json.loads(r5["output"])
                pipeline_span.set_attribute("feedback.length", len(feedback_out["feedback"]))
                logger.info(f"  Feedback generated ({len(feedback_out['feedback'])} chars)")
                logger.info(f"  Preview: {feedback_out['feedback'][:150]}...")
            except Exception as e:
                logger.warning(f"  LLM Feedback skipped: {e}")
                feedback_out = None

        result = {
            "pipeline_id": pipeline_id,
            "user_id": user_data["user_id"],
            "recommendation": top_course,
            "assignment_check": check_out,
            "progress_analysis": prog_out,
            "certificate": cert_out,
            "feedback": feedback_out["feedback"] if feedback_out else None,
        }

        logger.info("=" * 60)
        logger.info(f"PIPELINE {pipeline_id} — FINISHED")
        logger.info("=" * 60)
        return result

    async def run_auction(
        self, subject: str, task_payload: dict, timeout: int = 30,
        parent_ctx: Optional[object] = None,
        step_name: str = "",
        auction_timeout: float = 0.5,
    ) -> dict:
        auction_id = str(uuid.uuid4())
        bid_subject = f"tasks.auction.bid.{auction_id}"

        bids = []

        async def on_bid(msg):
            try:
                bid = json.loads(msg.data.decode())
                bids.append(bid)
            except json.JSONDecodeError:
                pass

        sub = await self.nc.subscribe(bid_subject, cb=on_bid)
        auction_payload = {"auction_id": auction_id}
        if "assignment_type" in task_payload:
            auction_payload["assignment_type"] = task_payload["assignment_type"]
        await self.nc.publish(
            subject,
            json.dumps(auction_payload).encode(),
        )

        await asyncio.sleep(auction_timeout)

        try:
            await sub.unsubscribe()
        except Exception:
            pass

        if not bids:
            logger.error(f"Auction {auction_id[:8]}: no bids received")
            return await self.send_task(
                "tasks.assignment.check", task_payload,
                timeout, parent_ctx, step_name,
            )

        winner = min(bids, key=lambda b: b["score"])
        winner_spec = winner.get("specialization", "?")
        winner_match = winner.get("match_bonus", 0)
        logger.info(
            f"Auction {auction_id[:8]}: {len(bids)} bids, "
            f"winner={winner['agent_id']} score={winner['score']:.2f} "
            f"cpu={winner.get('cpu_load', '?'):.2f} tasks={winner.get('tasks_processed', '?')} "
            f"spec={winner_spec} match={winner_match:.1f}"
        )
        for bid in sorted(bids, key=lambda b: b["score"]):
            logger.info(
                f"  bidder={bid['agent_id']} score={bid['score']:.2f} "
                f"spec={bid.get('specialization', '?')} match={bid.get('match_bonus', 0):.1f}"
            )

        direct_subject = f"tasks.assignment.check.direct.{winner['agent_id']}"
        return await self.send_task(
            direct_subject, task_payload,
            timeout, parent_ctx, step_name,
        )

    async def close(self):
        if self.nc:
            await self.nc.drain()
            logger.info("NATS connection closed")


async def test_individual(orchestrator):
    with orchestrator.tracer.start_as_current_span(
        "test.individual", kind=otel_trace.SpanKind.INTERNAL,
    ) as root_span:
        ctx = otel_trace.set_span_in_context(root_span)
        logger.info("=" * 50)
        logger.info("INDIVIDUAL TESTS")
        logger.info("=" * 50)

        # --- Test 1: Course Recommendation ---
        logger.info("\n--- Test 1: Course Recommendation ---")
        try:
            result = await orchestrator.send_task(
                "tasks.course.recommend", {
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
                timeout=10, parent_ctx=ctx,
                step_name="individual.course_recommend",
            )
            output = json.loads(result["output"])
            logger.info(f"Recommendations for {output['user_id']}: "
                        f"{len(output['recommendations'])} found")
            for rec in output["recommendations"]:
                logger.info(f"  - {rec['title']} (score: {rec['score']}) — {rec['reason']}")
        except Exception as e:
            logger.error(f"Course Recommendation failed: {e}")

        # --- Test 2: Assignment Check (через аукцион) ---
        logger.info("\n--- Test 2: Assignment Check (auction) ---")
        try:
            result = await orchestrator.run_auction(
                "tasks.auction.check", {
                    "assignment_id": "a-042",
                    "user_id": "u-001",
                    "course_id": "c-005",
                    "assignment_type": "test",
                    "answer": {"choices": ["b", "c", "a", "d", "b"],
                               "code": "", "essay": ""},
                },
                timeout=10, parent_ctx=ctx,
                step_name="individual.assignment_check",
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
                "tasks.progress.analyze", {
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
                timeout=10, parent_ctx=ctx,
                step_name="individual.progress_analysis",
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
                "tasks.certificate.generate", {
                    "user_id": "u-001",
                    "user_name": "Иван Иванов",
                    "course_id": "c-005",
                    "course_name": "ML with Python",
                    "completion_date": "2026-05-20",
                    "grade": "A",
                    "credits": 5,
                    "requirements_met": True,
                },
                timeout=10, parent_ctx=ctx,
                step_name="individual.certificate_gen",
            )
            output = json.loads(result["output"])
            logger.info(f"Certificate generated: {output['certificate_id']}")
            logger.info(f"  URL: {output['certificate_url']}")
            logger.info(f"  Valid until: {output['valid_until']}")
        except Exception as e:
            logger.error(f"Certificate Generation failed: {e}")

        # --- Test 5: LLM Feedback ---
        logger.info("\n--- Test 5: LLM Feedback ---")
        try:
            result = await orchestrator.send_task(
                "tasks.feedback.generate", {
                    "user_id": "u-001",
                    "user_name": "Иван Иванов",
                    "skill_level": "intermediate",
                    "interests": ["python", "machine learning"],
                    "course_name": "ML with Python",
                    "assignment_type": "test",
                    "score": 100,
                    "max_score": 100,
                    "passed": True,
                    "trend": "improving",
                    "avg_score": 92.5,
                    "total_questions": 5,
                    "correct": 5,
                    "wrong_questions": "",
                },
                timeout=15, parent_ctx=ctx,
                step_name="individual.llm_feedback",
            )
            output = json.loads(result["output"])
            feedback = output["feedback"]
            logger.info(f"Feedback generated ({len(feedback)} chars)")
            logger.info(f"  First 200 chars: {feedback[:200]}...")
        except Exception as e:
            logger.error(f"LLM Feedback failed: {e}")


async def test_pipeline(orchestrator):
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
            "answer": {
                "choices": [], "code": "",
                "essay": (
                    "Функция — это основной строительный блок программы. "
                    "Она принимает аргумент, выполняет действия и возвращает "
                    "результат. В Python рекурсия — это вызов функции из неё "
                    "самой. Аргумент и возврат значения — ключевые понятия."
                ),
            },
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
        feedback_text = result.get("feedback")
        if feedback_text:
            logger.info(f"  LLM Feedback: {len(feedback_text)} chars generated")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)


async def main():
    tracer = init_tracer()
    logger.info(f"Tracer initialized (service: orchestrator)")

    orchestrator = AgentOrchestrator()
    await orchestrator.connect()

    await test_individual(orchestrator)
    await test_pipeline(orchestrator)

    await orchestrator.close()
    logger.info("\nAll tests completed.")


if __name__ == "__main__":
    asyncio.run(main())
