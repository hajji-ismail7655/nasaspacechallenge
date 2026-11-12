#!/usr/bin/env python3
import json, os, time, urllib.request, urllib.error
from pathlib import Path

env_file = Path(".env")
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

HUB_URL = os.environ.get("HUB_URL", "http://127.0.0.1:8765")
AGENT_ID = os.environ.get("AGENT_ID", "coordinator")

def post(endpoint, payload):
    url = f"{HUB_URL}{endpoint}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

# register
post("/register", {"agent_id": AGENT_ID, "role": "coordinator"})
print("registered", flush=True)

subtasks = [
    "Implement Best Processing Module in Python per README goals.",
    "Implement Optimized Processing Module in C++ per README goals.",
    "Implement frontend in React (Next.js router, SSR) per README goals.",
    "Implement backend in Rust with similarity formula per README goals.",
    "Set up Redis for user-input weights + final result caching per README goals.",
    "Set up PostgreSQL persistence per README goals.",
]
task_queue = list(subtasks)
known_workers = set()
assigned = {}   # worker -> task
results = {}    # worker -> result payload
start = time.time()
MAX_RUN = 90

while time.time() - start < MAX_RUN:
    res = post("/poll", {"agent_id": AGENT_ID})
    agents = res.get("active_agents", {})
    msgs = res.get("messages", [])

    # handle incoming messages
    for m in msgs:
        print(f"MSG from {m.get('from')} type={m.get('type')}: {str(m.get('payload'))[:200]}", flush=True)
        if m.get("type") == "result":
            results[m.get("from")] = m.get("payload")
        if m.get("type") == "query":
            # echo back a status
            post("/send", {"from": AGENT_ID, "to": m.get("from"), "type": "status", "payload": "acknowledged"})

    # detect new workers
    for aid, info in agents.items():
        if aid == AGENT_ID:
            continue
        if aid not in known_workers:
            known_workers.add(aid)
            task = task_queue.pop(0) if task_queue else "Assist with project integration per README goals."
            assigned[aid] = task
            r = post("/send", {"from": AGENT_ID, "to": aid, "type": "task", "payload": task})
            print(f"Assigned task to {aid}: {task} -> {r}", flush=True)

    time.sleep(1)

# synthesize
synth = {
    "assigned": assigned,
    "results": results,
    "workers": list(known_workers),
    "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
}
Path("SYNTHESIS.json").write_text(json.dumps(synth, indent=2))
# broadcast final
post("/send", {"from": AGENT_ID, "to": "all", "type": "status", "payload": "Coordination complete. Synthesis written to SYNTHESIS.json"})
print("DONE. workers=%s results=%d" % (list(known_workers), len(results)), flush=True)
