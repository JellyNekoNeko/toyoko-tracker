from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from typing import Any, Callable, Dict, Mapping, Optional, Union


class PacerCancelled(RuntimeError):
    """Raised when a provider slot wait is cancelled."""


class ProviderPermit:
    """One acquired provider request slot.

    Permits are idempotent context managers, so callers may either use
    ``with pacer.acquire(...)`` or release the returned permit explicitly.
    """

    def __init__(self, pacer: "ProviderPacer", provider: str, task_id: str = "") -> None:
        self._pacer = pacer
        self.provider = provider
        self.task_id = task_id
        self._released = False
        self._lock = threading.Lock()

    @property
    def released(self) -> bool:
        with self._lock:
            return self._released

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
        self._pacer._release_provider(self.provider)

    def __enter__(self) -> "ProviderPermit":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.release()


class ProviderPacer:
    """Process-wide provider concurrency, spacing and cooldown coordinator.

    The injected clock must be monotonic. The injected wait function receives
    a non-negative duration in seconds, making pacing deterministic in tests.
    """

    def __init__(
        self,
        *,
        total_limit: int = 4,
        per_provider_limit: int = 2,
        provider_limits: Optional[Mapping[str, int]] = None,
        min_start_interval: float = 0.0,
        provider_min_start_intervals: Optional[Mapping[str, float]] = None,
        base_cooldown: float = 5.0,
        max_cooldown: float = 300.0,
        cancellation_poll_interval: float = 0.1,
        clock: Callable[[], float] = time.monotonic,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        if int(total_limit) < 1:
            raise ValueError("total_limit must be at least 1")
        if int(per_provider_limit) < 1:
            raise ValueError("per_provider_limit must be at least 1")
        if float(min_start_interval) < 0:
            raise ValueError("min_start_interval must be non-negative")
        if float(base_cooldown) <= 0:
            raise ValueError("base_cooldown must be positive")
        if float(max_cooldown) < float(base_cooldown):
            raise ValueError("max_cooldown must be at least base_cooldown")
        if float(cancellation_poll_interval) <= 0:
            raise ValueError("cancellation_poll_interval must be positive")

        self.total_limit = int(total_limit)
        self.per_provider_limit = int(per_provider_limit)
        self.provider_limits = self._positive_int_mapping(provider_limits or {})
        self.min_start_interval = float(min_start_interval)
        self.provider_min_start_intervals = self._non_negative_float_mapping(
            provider_min_start_intervals or {}
        )
        self.base_cooldown = float(base_cooldown)
        self.max_cooldown = float(max_cooldown)
        self.cancellation_poll_interval = float(cancellation_poll_interval)
        self._clock = clock
        self._wait = wait
        self._lock = threading.RLock()
        self._active_total = 0
        self._active_by_provider: Dict[str, int] = defaultdict(int)
        self._waiting_total = 0
        self._waiting_by_provider: Dict[str, int] = defaultdict(int)
        self._last_started_at: Dict[str, float] = {}
        self._next_start_at: Dict[str, float] = {}
        self._cooldown_until: Dict[str, float] = {}
        self._failure_streak: Dict[str, int] = defaultdict(int)
        self._acquired_total = 0
        self._released_total = 0
        self._cancelled_total = 0

    @staticmethod
    def _provider_name(provider: str) -> str:
        value = str(provider or "").strip().lower()
        if not value:
            raise ValueError("provider must be non-empty")
        return value

    @classmethod
    def _positive_int_mapping(cls, values: Mapping[str, int]) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for provider, value in values.items():
            name = cls._provider_name(provider)
            if int(value) < 1:
                raise ValueError(f"provider limit must be at least 1: {name}")
            result[name] = int(value)
        return result

    @classmethod
    def _non_negative_float_mapping(
        cls, values: Mapping[str, float]
    ) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for provider, value in values.items():
            name = cls._provider_name(provider)
            if float(value) < 0:
                raise ValueError(f"provider interval must be non-negative: {name}")
            result[name] = float(value)
        return result

    @staticmethod
    def _is_cancelled(cancel_event: Optional[Any]) -> bool:
        return bool(cancel_event is not None and cancel_event.is_set())

    def _provider_limit(self, provider: str) -> int:
        return self.provider_limits.get(provider, self.per_provider_limit)

    def _provider_interval(self, provider: str) -> float:
        return self.provider_min_start_intervals.get(
            provider, self.min_start_interval
        )

    def _wait_once(self, duration: float, cancel_event: Optional[Any]) -> None:
        duration = max(0.0, float(duration))
        if cancel_event is not None:
            duration = min(duration, self.cancellation_poll_interval)
        self._wait(duration)

    def acquire(
        self,
        provider: str,
        *,
        task_id: str = "",
        cancel_event: Optional[Any] = None,
        min_start_interval: Optional[float] = None,
    ) -> ProviderPermit:
        """Wait for and reserve one request slot.

        A cancelled waiter raises :class:`PacerCancelled` before reserving any
        global or provider token.
        """

        name = self._provider_name(provider)
        requested_interval = (
            0.0
            if min_start_interval is None
            else float(min_start_interval)
        )
        if not math.isfinite(requested_interval) or requested_interval < 0:
            raise ValueError("min_start_interval must be non-negative")
        with self._lock:
            self._waiting_total += 1
            self._waiting_by_provider[name] += 1
        try:
            while True:
                if self._is_cancelled(cancel_event):
                    with self._lock:
                        self._cancelled_total += 1
                    raise PacerCancelled(f"provider wait cancelled: {name}")

                now = float(self._clock())
                with self._lock:
                    capacity_ready = (
                        self._active_total < self.total_limit
                        and self._active_by_provider[name] < self._provider_limit(name)
                    )
                    cooldown_remaining = max(
                        0.0, self._cooldown_until.get(name, 0.0) - now
                    )
                    interval_remaining = max(
                        0.0,
                        self._next_start_at.get(name, -math.inf) - now,
                    )
                    if (
                        capacity_ready
                        and cooldown_remaining <= 0
                        and interval_remaining <= 0
                    ):
                        self._active_total += 1
                        self._active_by_provider[name] += 1
                        self._last_started_at[name] = now
                        effective_interval = max(
                            self._provider_interval(name),
                            requested_interval,
                        )
                        self._next_start_at[name] = now + effective_interval
                        self._acquired_total += 1
                        return ProviderPermit(self, name, str(task_id or ""))

                timing_wait = max(cooldown_remaining, interval_remaining)
                wait_for = timing_wait if timing_wait > 0 else self.cancellation_poll_interval
                self._wait_once(wait_for, cancel_event)
        finally:
            with self._lock:
                self._waiting_total = max(0, self._waiting_total - 1)
                self._waiting_by_provider[name] = max(
                    0, self._waiting_by_provider[name] - 1
                )

    def _release_provider(self, provider: str) -> None:
        with self._lock:
            active = self._active_by_provider.get(provider, 0)
            if active <= 0 or self._active_total <= 0:
                raise RuntimeError(f"provider slot is not active: {provider}")
            self._active_by_provider[provider] = active - 1
            self._active_total -= 1
            self._released_total += 1

    def release(self, permit_or_provider: Union[ProviderPermit, str]) -> None:
        """Release a permit, or one active slot for a provider."""

        if isinstance(permit_or_provider, ProviderPermit):
            if permit_or_provider._pacer is not self:
                raise ValueError("permit belongs to another pacer")
            permit_or_provider.release()
            return
        self._release_provider(self._provider_name(permit_or_provider))

    @staticmethod
    def _retry_after_seconds(value: Optional[Any]) -> Optional[float]:
        if value is None or isinstance(value, bool):
            return None
        try:
            seconds = float(str(value).strip())
        except (TypeError, ValueError):
            return None
        if not math.isfinite(seconds) or seconds < 0:
            return None
        return seconds

    def report_response(
        self,
        provider: str,
        status_code: int,
        *,
        retry_after: Optional[Any] = None,
    ) -> float:
        """Update provider cooldown state and return the imposed delay.

        HTTP 429 and 503 responses use exponential cooldown. A numeric
        Retry-After value is honored when it requests a longer delay.
        Successful responses reset the exponential failure streak but do not
        shorten a cooldown already imposed by another in-flight request.
        """

        name = self._provider_name(provider)
        status = int(status_code)
        now = float(self._clock())
        with self._lock:
            if status not in {429, 503}:
                if 200 <= status < 400:
                    self._failure_streak[name] = 0
                return 0.0

            streak = self._failure_streak[name] + 1
            self._failure_streak[name] = streak
            exponent = min(streak - 1, 30)
            exponential = min(
                self.max_cooldown, self.base_cooldown * (2 ** exponent)
            )
            explicit = self._retry_after_seconds(retry_after)
            delay = exponential if explicit is None else max(exponential, explicit)
            delay = min(self.max_cooldown, delay)
            self._cooldown_until[name] = max(
                self._cooldown_until.get(name, 0.0), now + delay
            )
            return delay

    def clear_cooldown(self, provider: str) -> None:
        """Clear one provider's cooldown and exponential failure streak."""

        name = self._provider_name(provider)
        with self._lock:
            self._cooldown_until.pop(name, None)
            self._failure_streak[name] = 0

    def snapshot(self) -> Dict[str, Any]:
        now = float(self._clock())
        with self._lock:
            providers = set(self.provider_limits)
            providers.update(self.provider_min_start_intervals)
            providers.update(self._active_by_provider)
            providers.update(self._waiting_by_provider)
            providers.update(self._last_started_at)
            providers.update(self._next_start_at)
            providers.update(self._cooldown_until)
            providers.update(self._failure_streak)
            provider_state = {}
            for provider in sorted(providers):
                cooldown_until = self._cooldown_until.get(provider, 0.0)
                provider_state[provider] = {
                    "active": self._active_by_provider.get(provider, 0),
                    "waiting": self._waiting_by_provider.get(provider, 0),
                    "concurrency_limit": self._provider_limit(provider),
                    "min_start_interval": self._provider_interval(provider),
                    "last_started_at": self._last_started_at.get(provider),
                    "next_start_at": self._next_start_at.get(provider),
                    "spacing_remaining": max(
                        0.0,
                        self._next_start_at.get(provider, 0.0) - now,
                    ),
                    "cooldown_until": (
                        cooldown_until if cooldown_until > now else None
                    ),
                    "cooldown_remaining": max(0.0, cooldown_until - now),
                    "failure_streak": self._failure_streak.get(provider, 0),
                }
            return {
                "total_limit": self.total_limit,
                "per_provider_limit": self.per_provider_limit,
                "active_total": self._active_total,
                "waiting_total": self._waiting_total,
                "acquired_total": self._acquired_total,
                "released_total": self._released_total,
                "cancelled_total": self._cancelled_total,
                "providers": provider_state,
            }


provider_pacer = ProviderPacer()
