"""Common validation for quick-add checklists."""


def parse_subtasks(text: str, *, required: bool = False) -> tuple[str, ...]:
    if not isinstance(text, str):
        raise ValueError("Subtasks must be text.")
    names = tuple(line.strip() for line in text.splitlines() if line.strip())
    if required and not names:
        raise ValueError("Enter at least one subtask.")
    if len(names) > 20 or any(len(line) > 120 for line in names):
        raise ValueError("Use at most 20 subtasks, each under 120 characters.")
    return names
