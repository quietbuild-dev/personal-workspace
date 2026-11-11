"""Task data and validation, independent of the UI and database."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class TaskDraft:
    title: str
    category: str = "Personal"
    deadline: date | None = None
    priority: int = 2
    estimate_minutes: int = 60

    def __post_init__(self) -> None:
        for field, limit in (("title", 120), ("category", 40)):
            value = getattr(self, field)
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
                raise ValueError(f"{field.capitalize()} must contain 1–{limit} characters.")
            object.__setattr__(self, field, value.strip())
        if type(self.priority) is not int or self.priority not in (1, 2, 3):
            raise ValueError("Priority must be Low, Medium, or High.")
        if type(self.estimate_minutes) is not int or self.estimate_minutes <= 0:
            raise ValueError("Estimated time must be a positive whole number of minutes.")
        if self.estimate_minutes > 2**63 - 1:
            raise ValueError("Estimated time is too large to store.")
        if self.deadline is not None and type(self.deadline) is not date:
            raise ValueError("Deadline must be a calendar date or empty.")


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    category: str
    deadline: date | None
    priority: int
    estimate_minutes: int
    remaining_minutes: int
    status: str
    created_at: datetime
    completed_at: datetime | None
