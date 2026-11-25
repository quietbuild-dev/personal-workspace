"""Task-level precedence over existing study steps; reservations are not progress."""

from workspace.advanced_planner import PlannerSnapshot


def dependency_context(snapshot: PlannerSnapshot):
    """Validate references and DAG, then return topological ranks and prerequisites."""
    ids = {s.id for s in snapshot.task_states} | {s.task_id for s in snapshot.steps}
    parents = {i: set() for i in ids}
    for edge in snapshot.dependencies:
        if edge.task_id not in ids or edge.prerequisite_id not in ids:
            raise ValueError("A dependency references a missing task.")
        if edge.task_id == edge.prerequisite_id:
            raise ValueError("A task cannot depend on itself.")
        parents[edge.task_id].add(edge.prerequisite_id)
    ranks = {}
    remaining = set(ids)
    # Iterative traversal avoids recursion limits on long imported chains.
    while remaining:
        ready = {i for i in remaining if parents[i] <= ranks.keys()}
        if not ready:
            raise ValueError("Circular task dependencies are not allowed.")
        for i in ready:
            ranks[i] = max((ranks[p] + 1 for p in parents[i]), default=0)
        remaining -= ready
    return ranks, parents


def prerequisite_ready(snapshot: PlannerSnapshot, task_id: int) -> bool:
    """Actual completion: closed parent or all represented steps really finished.

    A pending task without timed steps needs explicit completion. Checking a
    checklist alone must not discard a legacy parent's unrepresented estimate.
    """
    if any(t.id == task_id and t.completed for t in snapshot.task_states):
        return True
    steps = [s for s in snapshot.steps if s.task_id == task_id]
    if any(s.parent_completed for s in steps):
        return True
    return any(s.kind == "timed" for s in steps) and all(
        s.remaining_minutes == 0 if s.kind == "timed" else s.checked for s in steps
    )


def validate_dependencies(snapshot, slots):
    """Independent precedence check, also used inside the approval transaction."""
    _, parents = dependency_context(snapshot)
    by_task = {i: [] for i in parents}
    steps = {s.id: s for s in snapshot.steps}
    allocated = {}
    for slot in slots:
        by_task[steps[slot.step_id].task_id].append(slot)
        allocated[slot.step_id] = allocated.get(slot.step_id, 0) + slot.minutes
    for task_id, blocks in by_task.items():
        if not blocks:
            continue
        first = min((s.day, s.start) for s in blocks)
        for parent in parents[task_id]:
            if prerequisite_ready(snapshot, parent):
                continue
            required = [s for s in snapshot.steps if s.task_id == parent]
            if (
                not any(s.kind == "timed" for s in required)
                or any(s.kind == "checklist" and not s.checked for s in required)
                or any(
                    allocated.get(s.id, 0) != s.remaining_minutes
                    for s in required
                    if s.kind == "timed"
                )
            ):
                raise ValueError(
                    "A prerequisite has unfinished work without a complete earlier plan."
                )
            last = max(((s.day, s.end) for s in by_task[parent]), default=first)
            if first < last:
                raise ValueError("A dependent task starts before its prerequisite plan finishes.")
