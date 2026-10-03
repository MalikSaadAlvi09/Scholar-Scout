"""
Per-Job AI Request and Token Budget Tracker.
Enforces limits on AI API calls and total tokens consumed per research job
to prevent runaway loops, infinite retries, or excessive provider costs.
"""

import threading
from typing import Dict, Any, Optional
from backend.config import config
from backend.llm.schemas import UsageMetrics
from backend.llm.exceptions import BudgetExceededError
from backend.logging_utils import logger

class JobBudgetTracker:
    def __init__(self):
        self._lock = threading.Lock()
        # Maps job_id -> { "requests": int, "prompt_tokens": int, "completion_tokens": int, "total_tokens": int }
        self._job_stats: Dict[int, Dict[str, int]] = {}

    def get_job_usage(self, job_id: int) -> Dict[str, int]:
        """Returns current token and request usage for the given job."""
        with self._lock:
            if job_id not in self._job_stats:
                return {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            return dict(self._job_stats[job_id])

    def check_budget(self, job_id: Optional[int], estimated_tokens: int = 100):
        """
        Verifies whether the job has remaining request and token budget.
        Raises BudgetExceededError if budget is exhausted.
        """
        if job_id is None:
            return  # Standalone requests not associated with a batch job

        max_requests = config.job_max_llm_requests
        max_tokens = config.job_max_llm_tokens

        with self._lock:
            stats = self._job_stats.setdefault(job_id, {
                "requests": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            })

            if stats["requests"] >= max_requests:
                err_msg = (
                    f"Job #{job_id} exceeded request budget: "
                    f"{stats['requests']}/{max_requests} requests made."
                )
                logger.warning(f"[Job Budget] {err_msg}")
                raise BudgetExceededError(err_msg, job_id=job_id, current_usage=stats)

            if stats["total_tokens"] + estimated_tokens > max_tokens:
                err_msg = (
                    f"Job #{job_id} exceeded token budget: "
                    f"{stats['total_tokens']}/{max_tokens} tokens consumed."
                )
                logger.warning(f"[Job Budget] {err_msg}")
                raise BudgetExceededError(err_msg, job_id=job_id, current_usage=stats)

    def record_usage(self, job_id: Optional[int], usage: UsageMetrics):
        """Records token counts and request increment for the job."""
        if job_id is None:
            return

        with self._lock:
            stats = self._job_stats.setdefault(job_id, {
                "requests": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            })
            stats["requests"] += 1
            stats["prompt_tokens"] += usage.prompt_tokens
            stats["completion_tokens"] += usage.completion_tokens
            stats["total_tokens"] += usage.total_tokens

            logger.info(
                f"[Job Budget] Job #{job_id} recorded AI call: "
                f"+{usage.total_tokens} tokens (Job Total: {stats['total_tokens']} tokens, "
                f"{stats['requests']}/{config.job_max_llm_requests} requests)"
            )

    def reset_job(self, job_id: int):
        """Clears in-memory tracker for a finished or restarted job."""
        with self._lock:
            self._job_stats.pop(job_id, None)

job_budget_tracker = JobBudgetTracker()
