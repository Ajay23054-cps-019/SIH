import psutil
import threading
import time
import database

database.init_db()

_prev_network = None
_latest_cpu = 0.0
_latest_network = {"bytes_sent": 0, "bytes_received": 0}
_lock = threading.Lock()


def _collect():
    global _prev_network, _latest_cpu, _latest_network
    while True:
        try:
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            network = psutil.net_io_counters()
            current_network = {
                "bytes_sent": network.bytes_sent,
                "bytes_received": network.bytes_recv,
            }

            with _lock:
                if _prev_network is None:
                    _prev_network = current_network.copy()

                _latest_cpu = cpu
                _latest_network = {
                    "bytes_sent": max(0, current_network["bytes_sent"] - _prev_network["bytes_sent"]),
                    "bytes_received": max(0, current_network["bytes_received"] - _prev_network["bytes_received"]),
                }
                _prev_network = current_network

            database.insert_metrics(
                cpu,
                memory.used,
                memory.total,
                memory.percent,
                _latest_network["bytes_sent"],
                _latest_network["bytes_received"],
            )
        except Exception:
            pass


threading.Thread(target=_collect, daemon=True).start()


def information(target_processes):
    global _prev_network

    targets = {name.lower() for name in target_processes}

    memory = psutil.virtual_memory()

    with _lock:
        cpu = _latest_cpu
        network_data = _latest_network.copy()

    processes = []

    for process in psutil.process_iter(
        ["pid", "name", "cpu_percent", "memory_percent"]
    ):
        try:
            name = process.info["name"]

            if name and name.lower() in targets:
                processes.append(process.info)

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

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