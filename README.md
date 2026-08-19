# System Monitor (SIH)

Lightweight real-time system resource monitor with a browser dashboard.

## Architecture

Uses **Option B — POSIX Shared Memory** for the fastest possible metrics pipeline:

- **C++ writer** (`shm_writer.cpp`): Standalone binary that samples CPU, RAM, network, and per-process stats from `/proc` and writes them into a 1 MB POSIX shared memory ring buffer (`/dev/shm/sysmon_shm`) at 100 Hz.
- **Python reader** (`shm_reader.py`): Maps the same shared memory segment via `mmap` and exposes metrics to FastAPI with zero-copy reads.
- **FastAPI server** (`main.py`): Serves live data at `/` and history at `/history`.
- **Frontend** (`frontend/index.html`): Single-page dashboard with CPU, RAM, network sparklines and a process table.

Why shared memory wins:
- Zero serialization — C++ writes raw structs, Python reads them via `mmap`.
- No context switching — single shared memory segment, no subprocess, no sockets.
- Minimal footprint — C++ binary is ~100–500 KB; Python just maps a ~1 KB ring buffer slot per read.

## Building

Requires `g++` with C++17 support.

```bash
make
```

This produces `shm_writer`.

## Running

```bash
./run.sh
```

Or manually:

```bash
make && ./shm_writer &
cd /home/ajay/Desktop/SIH
/home/ajay/Desktop/SIH/env/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000`.

## API Endpoints

| Method | Path               | Description                          |
|--------|--------------------|--------------------------------------|
| GET    | `/`                | Latest system metrics snapshot       |
| GET    | `/history?limit=N` | Last N history rows (default 30)     |

## Data Format

**`GET /`**
```json
{
  "cpu_percentage": 57.1,
  "ram": { "used": 5740240896, "total": 8055336960, "available": 2315096064, "percentage": 71.3 },
  "network": { "bytes_sent": 0, "bytes_received": 0 },
  "processes": [
    { "pid": 3425, "name": "code", "cpu_percent": 0.0, "memory_percent": 1.7 }
  ]
}
```

**`GET /history?limit=3`**
```json
[
  { "timestamp": "2026-08-19T11:59:02", "cpu": 95.0, "ram_percent": 71.5, "bytes_sent": 0, "bytes_received": 0 },
  { "timestamp": "2026-08-19T11:59:01", "cpu": 96.2, "ram_percent": 71.5, "bytes_sent": 0, "bytes_received": 0 }
]
```

## Project Structure

```
SIH/
├── shm_writer.cpp      # C++ shared memory metrics writer
├── shm_reader.py       # Python mmap-based shared memory reader
├── main.py             # FastAPI entry point
├── Makefile            # Builds shm_writer
├── run.sh              # One-click build + run script
├── frontend/
│   └── index.html      # Dashboard UI
├── processes.py        # Legacy psutil-based collector (replaced)
├── database.py         # Legacy SQLite storage (replaced)
└── system_metrics.db   # SQLite database (legacy)
```

## Notes

- The C++ writer targets VS Code (`code`), Chrome (`chrome`), and Firefox (`firefox`) processes by default. Edit `g_targets` in `shm_writer.cpp:57` to change which processes are tracked.
- Shared memory is recreated on each writer start (`shm_unlink` in `main()`).
- Network deltas are cumulative per-sample; the frontend displays the most recent sample values.
