# CloudOS User Manual & Feature Guide

## Overview

CloudOS is an interactive **Operating System Lab & Simulation Platform** designed for demonstrations, coursework, and evaluations. It models multi-resource allocation (CPU, RAM, GPU, Storage), CPU scheduling algorithms, deadlock avoidance (Banker's Algorithm), multi-core processing, virtual memory paging, and quantitative performance benchmarking.

---

## Quick Start

1. Activate your virtual environment and run the application:
   ```bash
   .venv\Scripts\activate
   pip install -r requirements.txt
   python src/main.py
   ```
2. Open **[http://127.0.0.1:5000](http://127.0.0.1:5000)** in your browser.
3. Run tests at any time:
   ```bash
   python -m unittest discover -s tests -v
   ```

---

## Implemented OS Features & Labs

### 1. Performance Metrics Dashboard (Evaluation & Comparison)
Tracks precise per-process metrics and real-time system averages:
- **Arrival Tick ($t_{arr}$)**: when the process entered the system.
- **Start Tick ($t_{start}$)**: first tick the process ran on a CPU core.
- **Finish Tick ($t_{fin}$)**: tick when execution completed ($remaining = 0$).
- **Response Time**: $t_{start} - t_{arr}$ (latency to first CPU dispatch).
- **Turnaround Time**: $t_{fin} - t_{arr}$ (total lifecycle duration).
- **Waiting Time**: accumulated ticks waiting in `READY` queue.
- **CPU Utilization (%)**: $\frac{\text{Total Busy Core Ticks}}{\text{Total Ticks} \times \text{Active Cores}} \times 100\%$.
- **Throughput**: completed processes per simulation tick.

### 2. Interactive Execution Timeline (Gantt Chart)
- Real-time horizontal timeline recording which process (or `IDLE`) executed on each CPU core at every clock tick.
- Color-coded per process with interactive hover tooltips showing start/end ticks, duration, and process name.
- Synchronized **Gantt Axis & Tick Ruler** beneath the execution lanes displays clock ticks (aligned to time slice boundaries), making Round Robin quantum intervals instantly clear.
- Supports single-core and multi-core lane views.

### 3. Banker's Algorithm Lab & Step-by-Step Safe Sequence Audit
- **Dynamic Resource Requests**: Test incremental resource allocation step-by-step (+CPU, +RAM, +GPU, +Storage).
- **Safe State Enforcement**: If Banker's avoidance is active, unsafe requests are refused with a clear mathematical rationale.
- **Mathematical Proof Modal**: Click **"Safe Sequence Audit"** to view the full deduction table showing initial Available vector, Work vector progression, Need $\le$ Work test, and process completion sequence.

### 4. Deadlock Demo Mode (Avoidance On vs. Off)
- **Deadlock Avoidance Toggle**: Switch Banker's Avoidance **ON (Safe)** or **OFF (Greedy/Deadlock Mode)**.
- **Circular Wait Demonstration**: Load the **"Deadlock Trap"** scenario. Turn avoidance OFF and step forward:
  - System immediately detects mutual circular wait: P1 holds CPU and needs GPU; P2 holds GPU and needs CPU.
  - A pulsing red **CRITICAL DEADLOCK DETECTED** banner alerts the examiner with exact details.
  - Toggle avoidance back ON to demonstrate how Banker's prevents the deadlock and finishes the workload safely!

### 5. Extended Scheduling Algorithms
CloudOS includes 6 scheduling algorithms accessible via dropdown:
1. **FCFS (First-Come, First-Served)**: non-preemptive queue based on arrival order.
2. **Round Robin**: cyclic scheduling with configurable time slice ($q$, adjustable from 1 to 20 ticks).
   - Time quantum is strictly enforced: active processes retain CPU execution across consecutive ticks until their time slice reaches $q$, at which point they are preempted if other ready tasks exist.
   - Adjust quantum directly via the **Time Quantum (q)** input in the CPU Settings card or inside the System Resource Editor modal.
   - The active quantum is prominently displayed in the top header badge (e.g. `Round Robin (q=2)`).
3. **Priority (Non-Preemptive)**: lowest priority number runs to completion.
4. **Priority (Preemptive)**: incoming higher-priority task preempts current execution.
5. **SJF (Shortest Job First - Non-Preemptive)**: selects shortest job upon CPU availability.
6. **SRTF (Shortest Remaining Time First - Preemptive)**: dynamically preempts if a process with shorter remaining burst arrives.

### 6. Starvation Prevention (Aging)
- Enable the **Aging** toggle in the CPU settings.
- For every $N$ ticks (configurable, default 5) a process waits in `READY`, its priority number decreases (priority increases).
- Prevents lower-priority batch tasks from starving under high-priority workloads.

### 7. Multi-Core Execution
- Set CPU cores to **1, 2, 4, or 8 active cores**.
- Schedulers dispatch up to $k$ processes simultaneously across cores.
- Gantt chart timeline automatically adds separate lanes for Core 0, Core 1, Core 2, etc.

### 8. Curated Educational Scenarios & Workload Generator
Quickly load preset scenarios from the control bar:
- **Default Balanced**: standard mix (Web Server, ML Training, Database, Analytics).
- **Deadlock Trap**: circular contention for CPU and GPU with Banker's demo.
- **Overloaded System**: high RAM & GPU contention exceeding safe capacity.
- **GPU Contention**: 3 deep learning workloads competing for finite GPUs.
- **Convoy Effect**: 30-tick monolith followed by 2-tick tasks under FCFS vs SJF.
- **Priority Starvation**: low-priority task starved by continuous VIP jobs.
- **Priority Inversion**: guided demo showing low-priority holding resource needed by high-priority.
- **🎲 Random Workload**: generates 4 randomized realistic cloud workloads.

### 9. Export Results (CSV)
Download reports directly from the **"Export CSV"** dropdown:
- **Process Metrics CSV**: table of PID, Name, Priority, Burst, Arrival, Start, Finish, Turnaround, Waiting, and Response.
- **Gantt Timeline CSV**: tick-by-tick log of which process executed on each core.

### 10. Scheduler Comparison Studio (Side-by-Side Benchmark)
- Click **"⚡ Compare Schedulers"** to clone the current workload and run it across all 6 algorithms simultaneously in background sandboxes.
- Displays a comparative scorecard ranking the best performing algorithm, along with side-by-side turnaround time bar charts.

### 11. Memory Management & Paging Visualizer
- Physical memory is partitioned into 8 hardware frames.
- Supports **LRU (Least Recently Used)** and **FIFO (First-In, First-Out)** page replacement policies.
- Live telemetry tracks: Page Hits, Page Faults, Hit Ratio %, and Fault Ratio %.
- Visual 8-frame memory map shows active processes, page numbers, and eviction notices.

### 12. Playback Controls (Auto-Run, Speed, Undo)
- **▶ Play / ⏸ Pause**: continuous auto-simulation.
- **Speed Slider**: control clock speed from 0.5x to 5.0x.
- **Step (+1) / +5 / +20**: manual forward advancement.
- **⏮ Step Back (Undo)**: rewind simulation state tick-by-tick using history snapshots.

### 13. I/O Wait State Simulation
- Click the **⚡** button next to any running process to block it for I/O (3 ticks).
- Process releases CPU core while retaining allocated RAM/GPU, entering `WAITING (I/O)`.
- When I/O finishes, process automatically transitions back to `READY`.

### 14. System Resource & Node Capacity Management
CloudOS allows editing the simulated server hardware resources both dynamically at runtime and persistently:
- **Opening the Editor**: Click **`⚙️ Edit Resources`** in the top navigation bar or **`⚙️ Edit Capacity`** on the System Resources card header.
- **Configurable Hardware Parameters**:
  - **CPU Cores**: Total processing cores (1–32).
  - **RAM (GB)**: System memory pool (1–256 GB).
  - **GPU Units**: Accelerators for machine learning / compute workloads (0–16 units).
  - **Storage (GB)**: Node storage pool (10–2048 GB).
  - **Alert Thresholds**: High-pressure warning (default 80%) and critical-pressure alert (default 90%) thresholds.
  - **Default Algorithm & Quantum**: Boot-up scheduler configuration.
- **Two Update Modes**:
  1. **"⚡ Apply Live Update"**: Instantly reconfigures the live node capacity without resetting the simulation or terminating running processes. (Guarded: capacity cannot be lowered below currently allocated resources to prevent inconsistent states).
  2. **"💾 Save to Config & Reset"**: Permanently saves the updated hardware values to `config.json` and resets the simulation with the new baseline hardware profile.

---

## Suggested Examiner Presentation Script

1. **Scheduling & Gantt Chart**:
   - Start with default demo under **Round Robin**. Click **+5 Ticks**.
   - Show the interactive **Gantt Chart** timeline rotating across processes.
   - Point out the real-time **Performance Metrics** (Avg Turnaround, Waiting, Response).
2. **Scheduler Comparison Studio**:
   - Click **"⚡ Compare Schedulers"**. Show side-by-side comparison of FCFS vs Round Robin vs SJF vs SRTF vs Priority.
   - Point out the winning algorithm and the turnaround comparison bar chart.
3. **Deadlock Avoidance vs. Deadlock Occurrence**:
   - Select the **"Deadlock Trap"** scenario and click **Load**.
   - Show that Banker's Avoidance reports a safe order or refuses unsafe allocation.
   - Switch Banker's Avoidance **OFF**. Step forward 1 tick.
   - Show the pulsing red **DEADLOCK DETECTED** banner: circular dependency between Worker A and Worker B!
   - Click **"Enable Banker's & Reset"** to show how avoidance prevents the circular wait.
4. **Mathematical Safe Sequence Proof**:
   - Click **"Safe Sequence Audit"** to reveal the step-by-step Work vector and Need $\le$ Work matrix proof.
5. **Virtual Memory Paging**:
   - Show the 8 memory frames updating as processes execute, tracking Page Hits, Faults, and LRU/FIFO evictions.
6. **Multi-Core & Export**:
   - Change Cores to **2 Cores** and watch the Gantt chart show parallel execution lanes.
   - Click **"Export CSV"** to demonstrate downloadable reports for lab deliverables.
