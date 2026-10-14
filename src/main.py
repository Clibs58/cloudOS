"""Flask entry point for CloudOS web dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from flask import Flask, Response, jsonify, render_template, request

from cloudos.config import ConfigStore
from cloudos.engine import CloudOSEngine

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
)

config_store = ConfigStore(ROOT / "config.json")
_app_config = config_store.get()
engine = CloudOSEngine.from_config(_app_config)
if _app_config.get("demo", {}).get("load_on_startup", True):
    engine.load_demo()


def _snap_dict():
    s = engine.snapshot()
    cap = s.capacity
    alloc = s.allocated_total
    return {
        "tick": s.tick,
        "capacity": {
            "cpu": cap.cpu,
            "ram_gb": cap.ram_gb,
            "gpu": cap.gpu,
            "storage_gb": cap.storage_gb,
        },
        "used": {
            "cpu": alloc.cpu,
            "ram_gb": alloc.ram_gb,
            "gpu": alloc.gpu,
            "storage_gb": alloc.storage_gb,
        },
        "available": {
            "cpu": s.available.cpu,
            "ram_gb": s.available.ram_gb,
            "gpu": s.available.gpu,
            "storage_gb": s.available.storage_gb,
        },
        "processes": s.processes,
        "scheduler": s.scheduler,
        "deadlock_safe": s.deadlock_safe,
        "memory_status": s.memory_status,
        "log": s.log,
        "safe_sequence": s.safe_sequence,
        "safe_sequence_names": s.safe_sequence_names,
        "deadlock_detected": s.deadlock_detected,
        "deadlocked_pids": s.deadlocked_pids,
        "deadlock_avoidance": s.deadlock_avoidance,
        "metrics": s.metrics,
        "gantt": s.gantt,
        "active_cores": s.active_cores,
        "aging_enabled": s.aging_enabled,
        "paging_stats": s.paging_stats,
        "memory_frames": s.memory_frames,
        "quantum": s.quantum,
    }


def _state_with_config():
    return {**_snap_dict(), "config": config_store.get()}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def get_state():
    return jsonify(_state_with_config())


@app.get("/api/config")
def get_config():
    return jsonify(config_store.get())


@app.put("/api/config")
def put_config():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON body required"}), 400
    payload = {k: v for k, v in data.items() if not str(k).startswith("_")}
    try:
        saved = config_store.save(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    apply_sim = bool(data.get("_apply", True))
    reload_demo = bool(data.get("_reload_demo", True))
    if apply_sim:
        engine.apply_runtime_config(saved, reset_simulation=True)
        if reload_demo:
            engine.load_demo()
        else:
            engine.set_scheduler(engine.default_scheduler)

    return jsonify(_state_with_config())


@app.post("/api/capacity")
def update_capacity():
    data = request.get_json(silent=True) or {}
    cpu = int(data.get("cpu", engine.capacity.cpu))
    ram_gb = int(data.get("ram_gb", engine.capacity.ram_gb))
    gpu = int(data.get("gpu", engine.capacity.gpu))
    storage_gb = int(data.get("storage_gb", engine.capacity.storage_gb))
    high_thresh = data.get("high_threshold")
    crit_thresh = data.get("critical_threshold")
    res = engine.update_capacity(
        cpu,
        ram_gb,
        gpu,
        storage_gb,
        high_threshold=float(high_thresh) if high_thresh is not None else None,
        critical_threshold=float(crit_thresh) if crit_thresh is not None else None,
    )
    if not res.get("ok"):
        return jsonify({"error": res.get("error"), **_state_with_config()}), 400

    save_config = bool(data.get("save_config", False))
    if save_config:
        try:
            cfg = config_store.get()
            cfg["capacity"] = {"cpu": cpu, "ram_gb": ram_gb, "gpu": gpu, "storage_gb": storage_gb}
            if high_thresh is not None or crit_thresh is not None:
                cfg.setdefault("memory", {})
                if high_thresh is not None:
                    cfg["memory"]["high_threshold"] = float(high_thresh)
                if crit_thresh is not None:
                    cfg["memory"]["critical_threshold"] = float(crit_thresh)
            config_store.save(cfg)
        except Exception as e:
            return jsonify({"error": f"Failed to save config.json: {e}", **_state_with_config()}), 400

    return jsonify(_state_with_config())


@app.post("/api/step")
def step():
    engine.step()
    return jsonify(_state_with_config())


@app.post("/api/step_back")
def step_back():
    res = engine.step_back()
    if res is None:
        return jsonify({"error": "Cannot step back further (no prior state in history)", **_state_with_config()}), 400
    return jsonify(_state_with_config())


@app.post("/api/run")
def run_ticks():
    data = request.get_json(silent=True) or {}
    n = int(data.get("ticks", 1))
    engine.run_ticks(n)
    return jsonify(_state_with_config())


@app.post("/api/scheduler")
def set_scheduler():
    data = request.get_json(silent=True) or {}
    name = data.get("algorithm", "Round Robin")
    quantum = data.get("quantum")
    engine.set_scheduler(name, int(quantum) if quantum is not None else None)
    return jsonify(_state_with_config())



@app.post("/api/process")
def add_process():
    data = request.get_json(silent=True) or {}
    result = engine.add_process(
        name=str(data.get("name", "Workload")),
        cpu=int(data.get("cpu", 1)),
        ram_gb=int(data.get("ram_gb", 1)),
        gpu=int(data.get("gpu", 0)),
        storage_gb=int(data.get("storage_gb", 50)),
        burst_time=int(data.get("burst_time", 10)),
        priority=int(data.get("priority", 5)),
    )
    if not result.get("ok"):
        return jsonify({"error": result.get("error"), **_state_with_config()}), 400
    return jsonify(_state_with_config())


@app.post("/api/demo")
def load_demo():
    engine.load_demo()
    return jsonify(_state_with_config())


@app.post("/api/reset")
def reset():
    engine.reset()
    return jsonify(_state_with_config())


@app.post("/api/banker/request")
def banker_request():
    data = request.get_json(silent=True) or {}
    pid = int(data.get("pid", 0))
    cpu = int(data.get("cpu", 0))
    ram_gb = int(data.get("ram_gb", 0))
    gpu = int(data.get("gpu", 0))
    storage_gb = int(data.get("storage_gb", 0))
    res = engine.request_resources(pid, cpu, ram_gb, gpu, storage_gb)
    if not res.get("ok"):
        return jsonify({"error": res.get("error"), **_state_with_config()}), 400
    return jsonify(_state_with_config())


@app.post("/api/banker/release")
def banker_release():
    data = request.get_json(silent=True) or {}
    pid = int(data.get("pid", 0))
    cpu = int(data.get("cpu", 0))
    ram_gb = int(data.get("ram_gb", 0))
    gpu = int(data.get("gpu", 0))
    storage_gb = int(data.get("storage_gb", 0))
    res = engine.release_resources(pid, cpu, ram_gb, gpu, storage_gb)
    if not res.get("ok"):
        return jsonify({"error": res.get("error"), **_state_with_config()}), 400
    return jsonify(_state_with_config())


@app.post("/api/banker/toggle_avoidance")
def toggle_avoidance():
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", not engine.deadlock_avoidance_enabled))
    engine.set_deadlock_avoidance(enabled)
    return jsonify(_state_with_config())


@app.get("/api/banker/explain")
def explain_banker():
    explanation = engine.explain_banker_safety()
    return jsonify(explanation)


@app.post("/api/scenario")
def load_scenario():
    data = request.get_json(silent=True) or {}
    name = str(data.get("scenario", "default"))
    engine.load_scenario(name)
    return jsonify(_state_with_config())


@app.post("/api/random_workload")
def random_workload():
    data = request.get_json(silent=True) or {}
    count = int(data.get("count", 4))
    engine.generate_random_workload(count)
    return jsonify(_state_with_config())


@app.post("/api/compare_schedulers")
def compare_schedulers():
    comparison = engine.compare_all_schedulers()
    return jsonify(comparison)


@app.post("/api/settings/multicore")
def set_multicore():
    data = request.get_json(silent=True) or {}
    cores = int(data.get("cores", 1))
    engine.set_active_cores(cores)
    return jsonify(_state_with_config())


@app.post("/api/settings/aging")
def set_aging():
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled", False))
    interval = int(data.get("interval", 5))
    engine.set_aging(enabled, interval)
    return jsonify(_state_with_config())


@app.post("/api/memory/policy")
def set_memory_policy():
    data = request.get_json(silent=True) or {}
    policy = str(data.get("policy", "LRU"))
    engine.memory_manager.set_policy(policy)
    return jsonify(_state_with_config())


@app.post("/api/process/io")
def trigger_io():
    data = request.get_json(silent=True) or {}
    pid = int(data.get("pid", 0))
    duration = int(data.get("duration", 3))
    res = engine.trigger_io(pid, duration)
    if not res.get("ok"):
        return jsonify({"error": res.get("error"), **_state_with_config()}), 400
    return jsonify(_state_with_config())


@app.get("/api/export/metrics")
def export_metrics():
    csv_data = engine.export_metrics_csv()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=cloudos_metrics.csv"},
    )


@app.get("/api/export/gantt")
def export_gantt():
    csv_data = engine.export_gantt_csv()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=cloudos_gantt.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
