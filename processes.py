import psutil
import database

database.init_db()

_targets = {"code"}
_cached_pids = set()
_cached_time = 0.0


def information(target_processes):
    global _cached_pids, _cached_time
    now = psutil.boot_time() + psutil.time.time()
    if not _cached_pids or now - _cached_time > 5:
        _cached_pids = set()
        _cached_time = now
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if p.info["name"] and p.info["name"].lower() in target_processes:
                    _cached_pids.add(p.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    cpu = psutil.cpu_percent(interval=0.2)
    memory = psutil.virtual_memory()
    network = psutil.net_io_counters()
    current_network = {
        "bytes_sent": network.bytes_sent,
        "bytes_received": network.bytes_recv,
    }

    prev = getattr(information, "_prev_network", None)
    if prev is None:
        prev = current_network.copy()
    network_data = {
        "bytes_sent": max(0, current_network["bytes_sent"] - prev["bytes_sent"]),
        "bytes_received": max(0, current_network["bytes_received"] - prev["bytes_received"]),
    }
    information._prev_network = current_network

    processes = []
    if _cached_pids:
        for pid in _cached_pids:
            try:
                p = psutil.Process(pid)
                processes.append({
                    "pid": pid,
                    "name": p.name(),
                    "cpu_percent": p.cpu_percent(),
                    "memory_percent": p.memory_percent(),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                _cached_pids.discard(pid)

    database.insert_metrics(
        cpu,
        memory.used,
        memory.total,
        memory.percent,
        network_data["bytes_sent"],
        network_data["bytes_received"],
    )

    return {
        "cpu_percentage": cpu,
        "ram": {
            "total": memory.total,
            "used": memory.used,
            "available": memory.available,
            "percentage": memory.percent,
        },
        "network": network_data,
        "processes": processes,
    }