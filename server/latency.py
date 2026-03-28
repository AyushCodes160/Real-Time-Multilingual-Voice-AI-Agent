import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice_latency")

class LatencyTracker:
    def __init__(self):
        self.metrics = {}
        self._marks = {}

    def start(self, stage: str):
        self._marks[stage] = time.perf_counter()

    def stop(self, stage: str):
        if stage in self._marks:
            elapsed = (time.perf_counter() - self._marks[stage]) * 1000
            self.metrics[stage] = round(elapsed, 2)
            
    def log_pipeline(self):
        total = sum(self.metrics.values())
        self.metrics["Total"] = round(total, 2)
        logger.info(f"[LATENCY] {self.metrics}")
        return self.metrics
