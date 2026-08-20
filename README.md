# System Monitor (SIH)

Lightweight real-time system resource monitor with a browser dashboard and token-based authentication.

## Architecture

Uses **Option B — POSIX Shared Memory** for the fastest possible metrics pipeline:

- **C++ writer** (`backend/shm_writer.cpp`): Standalone binary that samples CPU, RAM, network, and per-process stats from `/proc` and writes them into a 1 MB POSIX shared memory ring buffer (`/dev/shm/sysmon_shm`) at 100 Hz.
- **Python reader** (`backend/shm_reader.py`): Maps the same shared memory segment via `mmap` and exposes metrics to FastAPI with zero-copy reads.
- **FastAPI server** (`backend/main.py`): Serves live data at `/api/live` and history at `/api/history` with token-based authentication.
- **Frontend** (`frontend/index.html`): Single-page dashboard with Chart.js graphs, login page, and process table.

Why shared memory wins:
- Zero serialization — C++ writes raw structs, Python reads them via `mmap`.
- No context switching — single shared memory segment, no subprocess, no sockets.
- Minimal footprint — C++ binary is ~100–500 KB; Python just maps a ~1 KB ring buffer slot per read.

## Authentication

- On first startup, the backend creates a default admin user and prints credentials to the console.
- Credentials are stored in the system database at `/home/ajay/.local/share/sysmon/auth.db` (not in the project folder).
- Session tokens expire after 24 hours.
- The frontend shows a login page before granting access to the dashboard.

## Building

Requires `g++` with C++17 support and `python-multipart` for form-based login.

```bash
cd backend
make
```

This produces `shm_writer`.

## Running

```bash
cd backend
./run.sh
```

Or manually:

```bash
cd backend
make && ./shm_writer &
uvicorn --app-dir /home/ajay/Desktop/SIH/backend main:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000`.

## API Endpoints

| Method | Path               | Description                          |
|--------|--------------------|--------------------------------------|
| POST   | `/login`           | Authenticate and receive bearer token |
| POST   | `/signup`          | Create a new user account            |
| GET    | `/api/live`        | Latest system metrics snapshot       |
| GET    | `/api/history?limit=N` | Last N history rows (default 30)     |

## Data Format

**`GET /api/live`**
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

**`GET /api/history?limit=3`**
```json
[
  { "timestamp": "2026-08-19T11:59:02", "cpu": 95.0, "ram_percent": 71.5, "bytes_sent": 0, "bytes_received": 0 },
  { "timestamp": "2026-08-19T11:59:01", "cpu": 96.2, "ram_percent": 71.5, "bytes_sent": 0, "bytes_received": 0 }
]
```

## Project Structure

```
SIH/
├── backend/
│   ├── main.py             # FastAPI entry point with auth middleware
│   ├── shm_reader.py       # Python mmap-based shared memory reader
│   ├── shm_writer.cpp      # C++ shared memory metrics writer
│   ├── auth.py             # Token-based authentication (system DB)
│   ├── database.py         # SQLite persistence for history
│   ├── processes.py        # Legacy psutil-based collector
│   ├── Makefile            # Builds shm_writer
│   └── run.sh              # One-click build + run script
├── frontend/
│   └── index.html          # Chart.js dashboard with login page
├── env/                    # Python virtual environment
└── README.md
```

## System Database Locations

- **Metrics DB**: `backend/system_metrics.db` (SQLite, persistent history)
- **Auth DB**: `/home/ajay/.local/share/sysmon/auth.db` (users and tokens)

## Notes

- The C++ writer targets VS Code (`code`), Chrome (`chrome`), and Firefox (`firefox`) processes by default. Edit `g_targets` in `backend/shm_writer.cpp:57` to change which processes are tracked.
- Shared memory is recreated on each writer start (`shm_unlink` in `main()`).
- Network deltas are cumulative per-sample; the frontend displays the most recent sample values.
- History is persisted in SQLite and survives restarts.
