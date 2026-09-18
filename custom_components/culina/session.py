"""Cooking session model: elapsed time, active steps and announcement planning.

Pure Python, no Home Assistant imports, so it can be unit tested on its own.
Mirrors the web client's `activeStepIndicesAt` (Culina spec 01 FR-22): steps
are scheduled as a DAG, so several can be active at the same time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_DURATION_RE = re.compile(
    r"^P(?:(?P<d>\d+)D)?"
    r"(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+(?:\.\d+)?)S)?)?$"
)

KIND_ENDING_SOON = "step_ending_soon"
KIND_STEP_DONE = "step_done"
KIND_STEP_DONE_NEXT = "step_done_next"
KIND_ALL_DONE = "all_done"

FALLBACK_TEMPLATES = {
    KIND_ENDING_SOON: "{{step}} is done in {{count}} minute",
    "step_ending_soon_plural": "{{step}} is done in {{count}} minutes",
    KIND_STEP_DONE: "{{step}} is done",
    KIND_STEP_DONE_NEXT: "{{step}} is done, next up {{next}}",
    KIND_ALL_DONE: "All steps are done, enjoy your meal",
}


def parse_duration(value: str | None) -> float:
    """Convert an ISO 8601 duration such as PT1H30M to seconds."""
    if not value:
        return 0.0
    match = _DURATION_RE.match(value)
    if match is None:
        raise ValueError(f"Unsupported duration: {value!r}")
    parts = match.groupdict()
    return (
        int(parts["d"] or 0) * 86400
        + int(parts["h"] or 0) * 3600
        + int(parts["m"] or 0) * 60
        + float(parts["s"] or 0)
    )


@dataclass(frozen=True)
class Step:
    """One recipe step on the schedule, times in seconds from recipe start."""

    order: int
    key: str
    name: str
    start: float
    duration: float
    hands_off: bool = False
    optional: bool = False

    @property
    def end(self) -> float:
        return self.start + self.duration

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Step:
        return cls(
            order=int(data.get("order", 0)),
            key=str(data.get("key", "")),
            name=str(data.get("name") or data.get("key") or ""),
            start=parse_duration(data.get("durationOffset")),
            duration=parse_duration(data.get("duration")),
            hands_off=bool(data.get("handsOff", False)),
            optional=bool(data.get("optional", False)),
        )


@dataclass(frozen=True)
class Recipe:
    """The parts of a Culina recipe the bridge needs."""

    id: str
    title: str
    cuisine_id: str | None
    cuisine_name: str | None
    steps: tuple[Step, ...]
    translation_pending: bool = False

    @property
    def total_duration(self) -> float:
        return max((step.end for step in self.steps), default=0.0)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Recipe:
        cuisine = data.get("cuisine") or {}
        steps = tuple(
            sorted(
                (Step.from_api(step) for step in data.get("steps") or []),
                key=lambda step: (step.start, step.order),
            )
        )
        return cls(
            id=str(data["id"]),
            title=str(data.get("title") or ""),
            cuisine_id=cuisine.get("id"),
            cuisine_name=cuisine.get("name"),
            steps=steps,
            translation_pending=bool(data.get("translationPending", False)),
        )


@dataclass(frozen=True)
class Session:
    """A household's cooking session as the API sends it."""

    recipe_id: str
    started_at: float | None  # server clock, milliseconds; None means paused
    elapsed_offset: float  # seconds
    updated_at: float | None = None

    @property
    def paused(self) -> bool:
        return self.started_at is None

    def elapsed_at(self, server_now_ms: float) -> float:
        """Seconds into the recipe at the given server time."""
        if self.started_at is None:
            return self.elapsed_offset
        return self.elapsed_offset + (server_now_ms - self.started_at) / 1000

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Session:
        started = data.get("startedAt")
        return cls(
            recipe_id=str(data["recipeId"]),
            started_at=float(started) if started is not None else None,
            elapsed_offset=float(data.get("elapsedOffset") or 0),
            updated_at=data.get("updatedAt"),
        )


def active_steps(steps: tuple[Step, ...] | list[Step], elapsed: float) -> list[Step]:
    """Every step whose window contains the elapsed time, in schedule order."""
    return [step for step in steps if step.start <= elapsed < step.end]


@dataclass(frozen=True)
class Announcement:
    """Something to say at a point in the recipe, in seconds from the start."""

    at: float
    kind: str
    step: Step | None = None
    next_step: Step | None = None
    count: int = 0


def plan_announcements(
    steps: tuple[Step, ...] | list[Step],
    *,
    ending_soon_seconds: float = 60,
    ending_soon_min_duration: float = 120,
    tolerance: float = 1.0,
) -> list[Announcement]:
    """All announcements for a schedule, sorted by time.

    - ending soon: `ending_soon_seconds` before a step's end, only for steps
      longer than `ending_soon_min_duration`
    - done: at a step's end; "done, next up X" when another step starts at
      that moment, plain "done" otherwise
    - all done: when the last step ends, instead of "done" for the steps
      that end at that moment
    """
    timed = [step for step in steps if step.duration > 0]
    if not timed:
        return []
    total_end = max(step.end for step in timed)
    ordered = sorted(timed, key=lambda step: (step.start, step.order))
    result: list[Announcement] = []
    for step in ordered:
        if step.duration > ending_soon_min_duration:
            result.append(
                Announcement(
                    at=step.end - ending_soon_seconds,
                    kind=KIND_ENDING_SOON,
                    step=step,
                    count=max(1, round(ending_soon_seconds / 60)),
                )
            )
        if abs(step.end - total_end) <= tolerance:
            continue
        next_step = next(
            (
                candidate
                for candidate in ordered
                if candidate is not step and abs(candidate.start - step.end) <= tolerance
            ),
            None,
        )
        if next_step is not None:
            result.append(
                Announcement(at=step.end, kind=KIND_STEP_DONE_NEXT, step=step, next_step=next_step)
            )
        else:
            result.append(Announcement(at=step.end, kind=KIND_STEP_DONE, step=step))
    result.append(Announcement(at=total_end, kind=KIND_ALL_DONE))
    return sorted(result, key=lambda item: item.at)


def group_announcements(
    announcements: list[Announcement], *, tolerance: float = 1.0
) -> list[list[Announcement]]:
    """Cluster announcements that fall within `tolerance` seconds of each other."""
    groups: list[list[Announcement]] = []
    for item in announcements:
        if groups and item.at - groups[-1][0].at <= tolerance:
            groups[-1].append(item)
        else:
            groups.append([item])
    return groups


def render(templates: dict[str, str] | None, announcement: Announcement) -> str:
    """Fill a Culina announcement template. The words come from Culina, not from here."""
    source = {**FALLBACK_TEMPLATES, **(templates or {})}
    key = announcement.kind
    if key == KIND_ENDING_SOON and announcement.count != 1 and source.get("step_ending_soon_plural"):
        key = "step_ending_soon_plural"
    text = source.get(key) or FALLBACK_TEMPLATES[announcement.kind]
    step = announcement.step.name if announcement.step else ""
    next_name = announcement.next_step.name if announcement.next_step else ""
    return (
        text.replace("{{step}}", step)
        .replace("{{next}}", next_name)
        .replace("{{count}}", str(announcement.count))
        .strip()
    )
