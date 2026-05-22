import asyncio
import json
import logging
import os
import subprocess
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import httpx
import nats
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent
log_dir = BASE_DIR / "logs"
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(log_dir / "web_monitor.log")),
    ],
)
logger = logging.getLogger("web_monitor")

app = FastAPI(title="E-Learning Monitor")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_MON_URL = os.getenv("NATS_MON_URL", "http://localhost:8222")
KUBECONFIG = os.getenv("KUBECONFIG", "")

task_history: list[dict] = []
agent_tasks = defaultdict(int)
agent_last_seen: dict[str, float] = {}
agent_specs: dict[str, str] = {}
agent_details: dict[str, dict] = {}
task_counter = 0
nc: nats.NATS | None = None


async def nats_listener():
    global nc, task_counter
    try:
        nc = await nats.connect(servers=[NATS_URL])
    except Exception as e:
        logger.error(f"Failed to connect to NATS: {e}")
        return
    logger.info(f"Connected to NATS at {NATS_URL}")

    async def on_completed(msg):
        global task_counter
        try:
            data = json.loads(msg.data.decode())
            task_id = data.get("task_id", "?")
            success = data.get("success", False)
            output_raw = data.get("output", "")
            error = data.get("error", "")
            task_counter += 1

            entry = {
                "id": task_id[:8],
                "task_id": task_id,
                "success": success,
                "error": error,
                "timestamp": datetime.now().isoformat(),
            }

            if output_raw:
                try:
                    output = json.loads(output_raw)
                    entry["output"] = output
                except json.JSONDecodeError:
                    entry["output"] = output_raw[:200]
            else:
                entry["output"] = None

            sender = None
            for k, v in msg.header.items():
                if k.lower() == "nats-message-id" or k.lower() == "client-ip":
                    continue
                if isinstance(v, list):
                    for val in v:
                        if val and val != "":
                            sender = val[:50]
                elif v and v != "":
                    sender = v[:50]

            task_history.append(entry)
            if len(task_history) > 500:
                task_history[:] = task_history[-500:]
        except Exception as e:
            logger.error(f"Failed to process completed task: {e}")

    async def on_bid(msg):
        try:
            bid = json.loads(msg.data.decode())
            agent_id = bid.get("agent_id", "")
            if agent_id:
                agent_tasks[agent_id] = max(agent_tasks.get(agent_id, 0), bid.get("tasks_processed", 0))
                agent_last_seen[agent_id] = time.time()
                if bid.get("specialization"):
                    agent_specs[agent_id] = bid["specialization"]
                agent_details[agent_id] = {
                    "cpu_load": bid.get("cpu_load"),
                    "uptime_seconds": bid.get("uptime_seconds"),
                    "goroutines": bid.get("goroutines"),
                    "score": bid.get("score"),
                }
        except Exception:
            pass

    await nc.subscribe("tasks.completed", cb=on_completed)
    await nc.subscribe("tasks.auction.bid.*", cb=on_bid)
    logger.info("Monitoring tasks.completed and tasks.auction.bid.* ...")

    try:
        while True:
            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"NATS listener error: {e}")


@app.on_event("startup")
async def startup():
    asyncio.create_task(nats_listener())


@app.on_event("shutdown")
async def shutdown():
    global nc
    if nc:
        await nc.drain()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    online_agents = len(agent_last_seen)
    total_tasks = task_counter
    recent = task_history[-20:] if task_history else []
    failed = sum(1 for t in task_history if not t["success"])
    success_rate = ((total_tasks - failed) / total_tasks * 100) if total_tasks > 0 else 0

    agent_stats = []
    for agent_id, count in sorted(agent_tasks.items(), key=lambda x: -x[1]):
        last_seen = agent_last_seen.get(agent_id)
        ago = ""
        if last_seen:
            secs = int(time.time() - last_seen)
            if secs < 60:
                ago = f"{secs}s"
            else:
                ago = f"{secs//60}m{secs%60}s"
        agent_stats.append({
            "id": agent_id[-20:],
            "tasks": count,
            "last_seen": ago,
            "spec": agent_specs.get(agent_id, "?"),
        })

    return templates.TemplateResponse(request, "dashboard.html", {
        "online_agents": online_agents,
        "total_tasks": total_tasks,
        "failed_tasks": failed,
        "success_rate": f"{success_rate:.1f}",
        "recent": (recent[::-1])[:10],
        "agent_stats": agent_stats,
        "page": "dashboard",
    })


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    return templates.TemplateResponse(request, "tasks.html", {
        "tasks": task_history[::-1],
        "page": "tasks",
    })


@app.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request):
    agents = []
    for agent_id, count in sorted(agent_tasks.items(), key=lambda x: -x[1]):
        last_seen = agent_last_seen.get(agent_id)
        ago = ""
        if last_seen:
            secs = int(time.time() - last_seen)
            ago = f"{secs}s" if secs < 60 else f"{secs//60}m{secs%60}s"
        detail = agent_details.get(agent_id, {})
        agents.append({
            "id": agent_id,
            "id_short": agent_id[-20:],
            "tasks": count,
            "last_seen": ago,
            "spec": agent_specs.get(agent_id, "?"),
            "cpu_load": detail.get("cpu_load", "?"),
            "uptime": detail.get("uptime_seconds", "?"),
            "goroutines": detail.get("goroutines", "?"),
        })
    return templates.TemplateResponse(request, "agents.html", {
        "agents": agents,
        "page": "agents",
    })


@app.get("/run", response_class=HTMLResponse)
async def run_page(request: Request):
    return templates.TemplateResponse(request, "run.html", {
        "page": "run",
    })


@app.post("/run")
async def run_task(
    request: Request,
    task_type: str = Form(...),
    user_id: str = Form("u-001"),
    user_name: str = Form("Тестовый студент"),
    course_name: str = Form("ML with Python"),
    assignment_type: str = Form("essay"),
    score: int = Form(85),
    passed: bool = Form(True),
    trend: str = Form("stable"),
    avg_score: float = Form(80.0),
):
    global nc
    payload_map = {
        "feedback": {
            "subject": "tasks.feedback.generate",
            "payload": {
                "user_id": user_id, "user_name": user_name,
                "skill_level": "intermediate", "interests": ["python"],
                "course_name": course_name,
                "assignment_type": assignment_type,
                "score": score, "max_score": 100,
                "passed": passed, "trend": trend, "avg_score": avg_score,
            },
        },
        "recommend": {
            "subject": "tasks.course.recommend",
            "payload": {
                "user_id": user_id,
                "profile": {"interests": ["python"], "skill_level": "intermediate", "preferred_lang": "ru"},
                "history": [],
            },
        },
        "certificate": {
            "subject": "tasks.certificate.generate",
            "payload": {
                "user_id": user_id, "user_name": user_name,
                "course_id": "c-005", "course_name": course_name,
                "completion_date": datetime.now().strftime("%Y-%m-%d"),
                "grade": "A", "credits": 5, "requirements_met": True,
            },
        },
    }

    cfg = payload_map.get(task_type)
    if not cfg or not nc:
        return templates.TemplateResponse(request, "run.html", {
            "page": "run",
            "error": "Invalid task type or NATS not connected",
        })

    task = {
        "id": str(uuid.uuid4()),
        "type": task_type,
        "payload": json.dumps(cfg["payload"], ensure_ascii=False),
    }
    await nc.publish(cfg["subject"], json.dumps(task).encode())
    logger.info(f"Manual task {task['id'][:8]} sent to {cfg['subject']}")
    return templates.TemplateResponse(request, "run.html", {
        "page": "run",
        "success": f"Task {task['id'][:8]} sent to {cfg['subject']}",
    })


@app.get("/k8s", response_class=HTMLResponse)
async def k8s_page(request: Request):
    pods = []
    try:
        result = subprocess.run(
            ["kubectl", "get", "pods", "-o", "json", "-l", "app=assignment-checker"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            for item in data.get("items", []):
                pod = item.get("metadata", {})
                status = item.get("status", {})
                container_statuses = status.get("containerStatuses", [{}])
                cs = container_statuses[0] if container_statuses else {}
                pods.append({
                    "name": pod.get("name", "?")[-25:],
                    "node": pod.get("nodeName", "?"),
                    "phase": status.get("phase", "?"),
                    "ready": cs.get("ready", False),
                    "restarts": cs.get("restartCount", 0),
                    "ip": status.get("podIP", "?"),
                    "start": pod.get("creationTimestamp", "?"),
                })
    except Exception as e:
        logger.warning(f"K8s not available: {e}")

    hpa = {}
    try:
        result = subprocess.run(
            ["kubectl", "get", "hpa", "assignment-checker-hpa", "-o", "json"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            spec = data.get("spec", {})
            status = data.get("status", {})
            current = status.get("currentMetrics", [{}])
            cpu = current[0].get("resource", {}).get("current", {}).get("averageUtilization", "?") if current else "?"
            hpa = {
                "min": spec.get("minReplicas", "?"),
                "max": spec.get("maxReplicas", "?"),
                "current": status.get("currentReplicas", "?"),
                "desired": status.get("desiredReplicas", "?"),
                "cpu_target": spec.get("metrics", [{}])[0].get("resource", {}).get("target", {}).get("averageUtilization", "?"),
                "cpu_current": cpu,
            }
    except Exception as e:
        logger.warning(f"HPA not available: {e}")

    return templates.TemplateResponse(request, "k8s.html", {
        "pods": pods,
        "hpa": hpa,
        "page": "k8s",
    })


@app.get("/api/stats")
async def api_stats():
    return JSONResponse({
        "total_tasks": task_counter,
        "history_count": len(task_history),
        "agents_count": len(agent_last_seen),
        "agent_tasks": dict(agent_tasks),
        "timestamp": datetime.now().isoformat(),
    })


@app.get("/api/health")
async def api_health():
    return JSONResponse({"status": "ok", "nats_connected": nc is not None and nc.is_connected})


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
