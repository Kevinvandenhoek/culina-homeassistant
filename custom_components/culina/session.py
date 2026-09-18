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
KIND_STEP_STARTED = "step_started"
KIND_STEP_DONE = "step_done"
KIND_STEP_DONE_NEXT = "step_done_next"
KIND_ALL_DONE = "all_done"

# Only for households whose API does not send a template; the words normally
# come from Culina in the household's language.
FALLBACK_TEMPLATES = {
    KIND_ENDING_SOON: "{{count}} minute left for: {{step}}",
    "step_ending_soon_plural": "{{count}} minutes left for: {{step}}",
    KIND_STEP_STARTED: "Now: {{step}}. {{description}}",
    KIND_STEP_DONE: "Done with: {{step}}.",
    KIND_STEP_DONE_NEXT: "Done with: {{step}}. Now: {{next}}. {{description}}",
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
    description: str = ""

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
            description=str(data.get("description") or "").strip(),
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

    @property
    def description(self) -> str:
        """The description that belongs in the sentence: of the step that starts."""
        if self.kind == KIND_STEP_STARTED and self.step is not None:
            return self.step.description
        if self.kind == KIND_STEP_DONE_NEXT and self.next_step is not None:
            return self.next_step.description
        return ""


def started_announcements(steps: tuple[Step, ...] | list[Step], elapsed: float) -> list[Announcement]:
    """`step_started` for every step active at `elapsed`, for a session start."""
    return [Announcement(at=elapsed, kind=KIND_STEP_STARTED, step=step) for step in active_steps(steps, elapsed)]


def plan_announcements(
    steps: tuple[Step, ...] | list[Step],
    *,
    ending_soon_seconds: float = 60,
    ending_soon_min_duration: float = 120,
    tolerance: float = 1.0,
) -> list[Announcement]:
    """All announcements for a schedule, sorted by time (Culina issue #609 rules).

    At every boundary the steps that end are paired with the steps that start:
    - a pair gives `step_done_next`, with the description of the new step
    - a step that starts with nothing ending gives `step_started`
    - a step that ends with nothing starting gives `step_done`
    - the steps that end at the very end give one `all_done`
    - `step_ending_soon` before a step's end, only for steps longer than
      `ending_soon_min_duration`
    So every description is heard once and no step is named twice.
    """
    timed = sorted((step for step in steps if step.duration > 0), key=lambda step: (step.start, step.order))
    if not timed:
        return []
    total_end = max(step.end for step in timed)
    boundaries: list[float] = []
    for step in timed:
        for moment in (step.start, step.end):
            if not any(abs(moment - known) <= tolerance for known in boundaries):
                boundaries.append(moment)
    result: list[Announcement] = []
    for moment in sorted(boundaries):
        ending = [step for step in timed if abs(step.end - moment) <= tolerance]
        starting = [step for step in timed if abs(step.start - moment) <= tolerance]
        if abs(moment - total_end) <= tolerance:
            result.append(Announcement(at=total_end, kind=KIND_ALL_DONE))
            continue
        for done, new in zip(ending, starting):
            result.append(Announcement(at=moment, kind=KIND_STEP_DONE_NEXT, step=done, next_step=new))
        for done in ending[len(starting):]:
            result.append(Announcement(at=moment, kind=KIND_STEP_DONE, step=done))
        for new in starting[len(ending):]:
            result.append(Announcement(at=moment, kind=KIND_STEP_STARTED, step=new))
    for step in timed:
        if step.duration > ending_soon_min_duration:
            result.append(
                Announcement(
                    at=step.end - ending_soon_seconds,
                    kind=KIND_ENDING_SOON,
                    step=step,
                    count=max(1, round(ending_soon_seconds / 60)),
                )
            )
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
    text = (
        text.replace("{{step}}", step)
        .replace("{{next}}", next_name)
        .replace("{{count}}", str(announcement.count))
        .replace("{{description}}", announcement.description)
    )
    return re.sub(r"\s+", " ", text).strip()
