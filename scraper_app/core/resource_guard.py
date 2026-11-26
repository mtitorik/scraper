import os
import sys
import time
import asyncio
from typing import Dict, Any, Optional

try:
    import psutil
except ImportError:
    psutil = None


class ResourceGuard:
    """Monitors CPU and RAM usage of Scraper and its child processes (Playwright/Browser).
    Applies core affinity, CPU throttling, and triggers RAM context recycling.
    """

    def __init__(self, max_cores: int = 2, max_cpu_percent: int = 40, max_ram_gb: float = 2.0):
        self.max_cores = max_cores
        self.max_cpu_percent = max_cpu_percent
        self.max_ram_gb = max_ram_gb
        self.process = psutil.Process() if psutil else None
        self._child_cache: Dict[int, Any] = {}
        if self.process:
            try:
                self.process.cpu_percent(interval=None)  # Prime baseline delta
            except Exception:
                pass
        self._apply_core_affinity()

    def update_limits(self, max_cores: Optional[int] = None, max_cpu_percent: Optional[int] = None, max_ram_gb: Optional[float] = None):
        if max_cores is not None and max_cores != self.max_cores:
            self.max_cores = max_cores
            self._apply_core_affinity()
        if max_cpu_percent is not None:
            self.max_cpu_percent = max_cpu_percent
        if max_ram_gb is not None:
            self.max_ram_gb = max_ram_gb

    def _apply_core_affinity(self):
        if not self.process:
            return
        if hasattr(self.process, "cpu_affinity") and sys.platform != "darwin":
            try:
                available_cores = list(range(min(self.max_cores, os.cpu_count() or 1)))
                self.process.cpu_affinity(available_cores)
            except Exception as e:
                print(f"[ResourceGuard] Warning: could not set CPU affinity: {e}")

    def get_process_tree_memory_bytes(self) -> int:
        """Calculates total RSS memory used by this process and all child processes."""
        if not self.process:
            return 0
        total_rss = 0
        try:
            total_rss += self.process.memory_info().rss
            for child in self.process.children(recursive=True):
                try:
                    total_rss += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return total_rss

    def get_process_tree_cpu_percent(self) -> float:
        """Estimates live CPU usage percentage (0-100% system scale) across Python + all Chromium child processes."""
        if not self.process:
            return 0.0
        total_cpu = 0.0
        try:
            total_cpu += self.process.cpu_percent(interval=None)
            live_pids = set()
            for child in self.process.children(recursive=True):
                pid = child.pid
                live_pids.add(pid)
                cached = self._child_cache.get(pid)
                if cached is None:
                    try:
                        child.cpu_percent(interval=None)  # Prime new child process
                        self._child_cache[pid] = child
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                else:
                    try:
                        total_cpu += cached.cpu_percent(interval=None)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        self._child_cache.pop(pid, None)
            # Prune exited child PIDs
            for stale_pid in list(self._child_cache.keys()):
                if stale_pid not in live_pids:
                    self._child_cache.pop(stale_pid, None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        num_cores = max(1, os.cpu_count() or 1)
        normalized = min(100.0, total_cpu / num_cores)
        return round(normalized, 1)

    def should_recycle_browser(self) -> bool:
        """Returns True if RAM usage approaches or exceeds 85% of the configured limit."""
        if self.max_ram_gb <= 0:
            return False
        total_bytes = self.get_process_tree_memory_bytes()
        cap_bytes = self.max_ram_gb * 1024 * 1024 * 1024
        # 85% threshold
        return total_bytes >= (cap_bytes * 0.85)

    def get_adaptive_pause(self) -> float:
        """Returns adaptive micro-pause delay in seconds if CPU exceeds limit."""
        if self.max_cpu_percent <= 0:
            return 0.0
        cpu = self.get_process_tree_cpu_percent()
        if cpu > self.max_cpu_percent:
            # Over the limit: calculate proportional pause between 0.1s and 1.5s
            excess_ratio = min((cpu - self.max_cpu_percent) / 50.0, 1.0)
            return round(0.1 + (1.4 * excess_ratio), 2)
        return 0.0

    async def throttle_if_needed(self):
        """Asynchronously injects micro-pause if CPU usage exceeds the user cap."""
        pause_sec = self.get_adaptive_pause()
        if pause_sec > 0:
            await asyncio.sleep(pause_sec)

    def get_live_metrics(self) -> Dict[str, Any]:
        """Returns live resource metrics for the UI."""
        mem_bytes = self.get_process_tree_memory_bytes()
        mem_mb = round(mem_bytes / (1024 * 1024), 1)
        mem_gb = round(mem_bytes / (1024 * 1024 * 1024), 2)
        cpu_percent = self.get_process_tree_cpu_percent()
        
        cap_gb = self.max_ram_gb if self.max_ram_gb > 0 else 1.0
        mem_percent_of_cap = min(round((mem_gb / cap_gb) * 100, 1), 100.0)

        sys_free_gb = 0.0
        sys_total_gb = 0.0
        if psutil:
            try:
                vm = psutil.virtual_memory()
                sys_free_gb = round(vm.available / (1024 * 1024 * 1024), 1)
                sys_total_gb = round(vm.total / (1024 * 1024 * 1024), 1)
            except Exception:
                pass

        return {
            "cpu_percent": cpu_percent,
            "max_cpu_percent": self.max_cpu_percent,
            "memory_mb": mem_mb,
            "memory_gb": mem_gb,
            "max_ram_gb": self.max_ram_gb,
            "memory_percent_of_cap": mem_percent_of_cap,
            "system_ram_free_gb": sys_free_gb,
            "system_ram_total_gb": sys_total_gb,
            "should_recycle": self.should_recycle_browser(),
        }
