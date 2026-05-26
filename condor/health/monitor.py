"""
Monitor de recursos do sistema: CPU, RAM, VRAM, disco, temperatura.
"""

from __future__ import annotations

import logging
import time

import psutil

log = logging.getLogger("condor.health.monitor")


class SystemMonitor:
    def snapshot(self) -> dict:
        mem  = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        snap = {
            "ts":       time.time(),
            "cpu_pct":  psutil.cpu_percent(interval=0.2),
            "ram_used": mem.used,
            "ram_total": mem.total,
            "ram_pct":  mem.percent,
            "disk_used": disk.used,
            "disk_total": disk.total,
            "disk_pct": disk.percent,
            "temps":    {},
            "vram_used": 0,
            "vram_total": 0,
        }

        # Temperatura (disponível no Linux e alguns Windows)
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for key, entries in temps.items():
                    if entries:
                        snap["temps"][key] = entries[0].current
        except AttributeError:
            pass  # Windows sem drivers de temp

        # VRAM via pynvml (opcional)
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info   = pynvml.nvmlDeviceGetMemoryInfo(handle)
            snap["vram_used"]  = info.used
            snap["vram_total"] = info.total
        except Exception:
            pass

        return snap

    def get_process_list(self, limit: int = 10) -> list[dict]:
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except psutil.NoSuchProcess:
                pass
        procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
        return procs[:limit]
