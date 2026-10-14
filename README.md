# CloudOS Studio — Intelligent Cloud Resource Allocation & Process Scheduling Simulator

A modern, full-featured web-based Operating Systems laboratory and simulation platform modeling **multi-resource allocation** (CPU, RAM, GPU, storage), **CPU scheduling** (FCFS, Round Robin, SJF, SRTF, Preemptive & Non-Preemptive Priority), **deadlock avoidance & detection** (Banker's Algorithm), **multi-core execution**, **virtual memory paging** (LRU/FIFO), and **performance metrics benchmarking**.

## Key OS Concepts Demonstrated

| Concept | Module | Capabilities |
|---------|--------|--------------|
| **Performance Metrics** | `src/cloudos/engine.py` | Turnaround, Waiting, Response times, CPU Utilization %, Throughput |
| **Execution Timeline** | `templates/index.html`, `static/app.js` | Interactive multi-core Gantt chart with color-coded process blocks |
| **CPU Scheduling** | `src/cloudos/scheduler.py` | FCFS, Round Robin, SJF, SRTF, Priority, Preemptive Priority |
| **Deadlock Avoidance** | `src/cloudos/banker.py` | Banker's safety check, incremental requests, step-by-step matrix proof |
| **Deadlock Demo Mode** | `src/cloudos/banker.py` | Circular wait detection, avoidance toggle ON/OFF, before/after demo |
| **Starvation Prevention** | `src/cloudos/engine.py` | Dynamic priority aging after configurable wait interval |
| **Multi-Core Dispatch** | `src/cloudos/engine.py` | Up to 8 concurrent active CPU execution lanes |
| **Virtual Memory Paging** | `src/cloudos/memory.py` | 8-frame physical memory, LRU & FIFO page replacement, hit/fault telemetry |
| **Scheduler Comparison** | `src/cloudos/engine.py` | Head-to-head isolated benchmark of all 6 algorithms with winner ranking |
| **Workload Presets & I/O** | `src/cloudos/engine.py` | 7 curated OS scenarios (Convoy, Deadlock, Starvation), random workload generator, I/O burst states |
| **Data Export** | `src/main.py` | Downloadable CSV reports for process metrics and Gantt execution log |

## Quick Start

```bash
cd os_project
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python src/main.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

- **Playback controls**: Step (+1 tick), Step Back (Undo), Play/Pause with adjustable speed.
- **Compare Schedulers**: Click **"⚡ Compare Schedulers"** to run side-by-side benchmark across all algorithms.
- **Safe Sequence Audit**: Click **"🔍 Safe Sequence Audit"** to view Banker's mathematical deduction proof.
- **Deadlock Trap**: Select "Deadlock Trap" scenario, toggle Banker's avoidance OFF, step to trigger circular deadlock alert!

## Run Unit Tests

```bash
python -m unittest discover -s tests -v
```

All 13 unit tests cover scheduler algorithms, Banker's safety, memory paging (FIFO/LRU), multi-core dispatch, and deadlock detection.

## Project Structure

```
src/
  cloudos/
    banker.py        Banker's algorithm safety audit and deadlock detection
    config.py        Configuration store and validation
    engine.py        Simulation engine, multi-core execution, metrics, undo
    memory.py        Virtual memory paging manager (FIFO & LRU)
    models.py        Process, ResourceVector, SimulationSnapshot dataclasses
    scheduler.py     CPU scheduler (FCFS, RR, Priority, SJF, SRTF)
  main.py            Flask web server & comprehensive REST API
templates/
  index.html         Cyber-dark dashboard UI with modals and timeline
static/
  app.js             Client-side state, Gantt chart, metrics, audio/visual cues
  style.css          Modern glassmorphic styling, animations, responsive grid
tests/
  test_banker.py     Unit tests for Banker's algorithm
  test_config.py     Unit tests for configuration persistence
  test_scheduler.py  Unit tests for classic schedulers
  test_extensions.py Unit tests for SJF, SRTF, Preemptive Priority, Paging, Multi-Core
docs/
  USER_MANUAL.md     Comprehensive manual and examiner presentation script
```
