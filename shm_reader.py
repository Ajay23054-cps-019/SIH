import mmap
import os
import struct
import time
import math
import threading
import database

database.init_db()

SHM_PATH = "/dev/shm/sysmon_shm"
SHM_SIZE = 1048608
SHM_MAGIC = 0x534D4F4E4E4F4D53
SLOT_SIZE = 4096
MAX_PROCESSES = 24
MAX_NAME_LEN = 64

HEADER_FMT = "<QQQQQ"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

SLOT_FMT = "<QdQQdQQII"
SLOT_HEADER_SIZE = struct.calcsize(SLOT_FMT)

PROCESS_FMT = "<i64sffI"
PROCESS_SIZE = struct.calcsize(PROCESS_FMT)


def _open_shm():
    fd = os.open(SHM_PATH, os.O_RDONLY)
    mm = mmap.mmap(fd, SHM_SIZE, access=mmap.ACCESS_READ)
    os.close(fd)
    return mm


def _parse_header(mm):
    data = mm[:HEADER_SIZE]
    fields = struct.unpack(HEADER_FMT, data)
    return {
        "magic": fields[0],
        "version": fields[1],
        "write_index": fields[2],
        "slot_size": fields[3],
        "slot_count": fields[4],
    }


def _read_slot(mm, header, index):
    slot_count = header["slot_count"]
    slot_size = header["slot_size"]
    offset = (index % slot_count) * slot_size + HEADER_SIZE
    data = mm[offset:offset + slot_size]
    if len(data) < SLOT_HEADER_SIZE:
        return None
    fields = struct.unpack(SLOT_FMT, data[:SLOT_HEADER_SIZE])
    ts_ns, cpu, ram_used, ram_total, ram_pct, sent, recv, pcount, _ = fields
    processes = []
    for i in range(min(pcount, MAX_PROCESSES)):
        start = SLOT_HEADER_SIZE + i * PROCESS_SIZE
        if start + PROCESS_SIZE > len(data):
            break
        pid, name_bytes, cpu_p, mem_p, _ = struct.unpack(PROCESS_FMT, data[start:start + PROCESS_SIZE])
        name = name_bytes.split(b"\x00")[0].decode("utf-8", errors="replace")
        processes.append({
            "pid": pid,
            "name": name,
            "cpu_percent": round(cpu_p, 1),
            "memory_percent": round(mem_p, 1),
        })
    return {
        "timestamp_ns": ts_ns,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts_ns / 1_000_000_000)),
        "cpu_percentage": round(cpu, 1),
        "ram": {
            "used": ram_used,
            "total": ram_total,
            "available": ram_total - ram_used,
            "percentage": round(ram_pct, 1),
        },
        "network": {
            "bytes_sent": sent,
            "bytes_received": recv,
        },
        "processes": processes,
    }


def _db_writer_loop():
    last_index = -1
    while True:
        try:
            mm = _open_shm()
            header = _parse_header(mm)
            idx = header["write_index"]
            if idx > 0 and idx != last_index:
                slot = _read_slot(mm, header, idx - 1)
                if slot:
                    database.insert_metrics(
                        slot["cpu_percentage"],
                        slot["ram"]["used"],
                        slot["ram"]["total"],
                        slot["ram"]["percentage"],
                        slot["network"]["bytes_sent"],
                        slot["network"]["bytes_received"],
                    )
                    last_index = idx
            mm.close()
        except (FileNotFoundError, OSError):
            last_index = -1
        time.sleep(1)


_db_thread = threading.Thread(target=_db_writer_loop, daemon=True)
_db_thread.start()


def information(target_processes=None):
    try:
        mm = _open_shm()
        header = _parse_header(mm)
        if header["write_index"] == 0:
            mm.close()
            return {
                "cpu_percentage": 0.0,
                "ram": {"total": 0, "used": 0, "available": 0, "percentage": 0.0},
                "network": {"bytes_sent": 0, "bytes_received": 0},
                "processes": [],
            }
        idx = header["write_index"] - 1
        slot = _read_slot(mm, header, idx)
        mm.close()
        if slot:
            return slot
        return {
            "cpu_percentage": 0.0,
            "ram": {"total": 0, "used": 0, "available": 0, "percentage": 0.0},
            "network": {"bytes_sent": 0, "bytes_received": 0},
            "processes": [],
        }
    except (FileNotFoundError, OSError):
        return {
            "cpu_percentage": 0.0,
            "ram": {"total": 0, "used": 0, "available": 0, "percentage": 0.0},
            "network": {"bytes_sent": 0, "bytes_received": 0},
            "processes": [],
        }


def get_latest_slot(limit=30):
    return database.get_latest(limit)
