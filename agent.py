"""Personal task manager ADK agent backed by session state.

A single LlmAgent with tools that read/write a per-session task list via
``tool_context.state``. Tasks persist across turns on the same thread,
which makes this a useful end-to-end demo of session-state plumbing
through ``saf_sdk.adk.wrap``.
"""

import uuid
from datetime import datetime, timezone

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.tools import ToolContext
from saf_sdk.adk import LangsmithSessionService, wrap


PRIORITIES = ("low", "medium", "high")


def _load(tool_context: ToolContext) -> list[dict]:
    return list(tool_context.state.get("tasks", []))


def _save(tool_context: ToolContext, tasks: list[dict]) -> None:
    # Reassign so ADK records a state_delta on the tool event.
    tool_context.state["tasks"] = tasks


def _find(tasks: list[dict], task_ref: str) -> dict | None:
    needle = task_ref.strip().lower()
    for t in tasks:
        if t["id"] == needle or t["title"].lower() == needle:
            return t
    return None


def add_task(title: str, priority: str, tool_context: ToolContext) -> dict:
    """Adds a new task to the user's list.

    Args:
        title (str): A short description of the task.
        priority (str): One of "low", "medium", or "high".

    Returns:
        dict: status, the created task (with id), and the new total count.
    """
    if priority.lower() not in PRIORITIES:
        return {
            "status": "error",
            "error_message": (
                f"priority must be one of {list(PRIORITIES)}; got '{priority}'."
            ),
        }
    tasks = _load(tool_context)
    task = {
        "id": uuid.uuid4().hex[:8],
        "title": title.strip(),
        "priority": priority.lower(),
        "done": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    tasks.append(task)
    _save(tool_context, tasks)
    return {"status": "success", "task": task, "total": len(tasks)}


def list_tasks(include_done: bool, tool_context: ToolContext) -> dict:
    """Lists tasks from the user's session.

    Args:
        include_done (bool): If True, include completed tasks; otherwise
            return only open tasks.

    Returns:
        dict: status, the matching tasks, and a count.
    """
    tasks = _load(tool_context)
    if not include_done:
        tasks = [t for t in tasks if not t["done"]]
    # Sort: high > medium > low, then by created_at ascending.
    order = {"high": 0, "medium": 1, "low": 2}
    tasks.sort(key=lambda t: (order.get(t["priority"], 99), t["created_at"]))
    return {"status": "success", "tasks": tasks, "count": len(tasks)}


def complete_task(task_ref: str, tool_context: ToolContext) -> dict:
    """Marks a task as done.

    Args:
        task_ref (str): The task id (preferred) or exact title.

    Returns:
        dict: status and the updated task, or an error.
    """
    tasks = _load(tool_context)
    target = _find(tasks, task_ref)
    if target is None:
        return {
            "status": "error",
            "error_message": f"No task found matching '{task_ref}'.",
        }
    if target["done"]:
        return {
            "status": "noop",
            "message": f"Task '{target['title']}' is already done.",
            "task": target,
        }
    target["done"] = True
    target["completed_at"] = datetime.now(timezone.utc).isoformat()
    _save(tool_context, tasks)
    return {"status": "success", "task": target}


def delete_task(task_ref: str, tool_context: ToolContext) -> dict:
    """Removes a task from the list entirely.

    Args:
        task_ref (str): The task id (preferred) or exact title.

    Returns:
        dict: status and the remaining task count, or an error.
    """
    tasks = _load(tool_context)
    target = _find(tasks, task_ref)
    if target is None:
        return {
            "status": "error",
            "error_message": f"No task found matching '{task_ref}'.",
        }
    tasks = [t for t in tasks if t["id"] != target["id"]]
    _save(tool_context, tasks)
    return {"status": "success", "removed": target, "remaining": len(tasks)}


def summarize(tool_context: ToolContext) -> dict:
    """Summarizes the user's task list: counts by status and priority.

    Returns:
        dict: status, totals, and a per-priority breakdown of open tasks.
    """
    tasks = _load(tool_context)
    open_tasks = [t for t in tasks if not t["done"]]
    by_priority = {p: sum(1 for t in open_tasks if t["priority"] == p) for p in PRIORITIES}
    return {
        "status": "success",
        "total": len(tasks),
        "open": len(open_tasks),
        "done": len(tasks) - len(open_tasks),
        "open_by_priority": by_priority,
    }


task_manager = Agent(
    name="task_manager",
    model="gemini-3-flash-preview",
    description=(
        "Personal task manager that remembers the user's to-do list across "
        "turns using session state."
    ),
    instruction=(
        "You are a concise personal task assistant. The user's task list "
        "lives in session state and is mutated only through your tools.\n\n"
        "Guidelines:\n"
        "- To add a task, call add_task with a clean title and a priority "
        "(low/medium/high). If the user does not specify a priority, "
        "default to 'medium'.\n"
        "- To show pending work, call list_tasks with include_done=false. "
        "If the user explicitly asks for completed items too, pass "
        "include_done=true.\n"
        "- To finish an item, call complete_task with the id when you know "
        "it; otherwise pass the exact title.\n"
        "- To remove an item entirely, call delete_task.\n"
        "- For 'how am I doing' / overview questions, call summarize.\n\n"
        "Always include the task id in your reply when confirming an add or "
        "completion so the user can refer back to it. Never invent task ids "
        "or pretend an action succeeded — rely on the tool response."
    ),
    tools=[add_task, list_tasks, complete_task, delete_task, summarize],
)


agent = wrap(
    Runner(
        agent=task_manager,
        app_name="task_manager_agent",
        session_service=LangsmithSessionService(),
    )
)