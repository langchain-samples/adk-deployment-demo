# adk-demo

A minimal demo of deploying a [Google Agent Development Kit (ADK)](https://github.com/google/adk-python) agent to [LangSmith Agent Server](https://docs.langchain.com/langsmith/agent-server), following the [Deploy Google ADK agents](https://docs.langchain.com/langsmith/deploy-google-adk) guide.

The agent is a **personal task manager**: a single ADK `LlmAgent` whose tools read and write a per-session to-do list via `tool_context.state`. Because state is persisted through `saf_sdk.adk.wrap` and `LangsmithSessionService`, tasks survive across turns (and restarts) on the same thread.

## How it works

[`agent.py`](./agent.py) defines:

- **Tools** that mutate a task list stored in session state:
  - `add_task(title, priority)` — add a task (`low` / `medium` / `high`)
  - `list_tasks(include_done)` — list open (or all) tasks, sorted by priority
  - `complete_task(task_ref)` — mark a task done by id or exact title
  - `delete_task(task_ref)` — remove a task by id or exact title
  - `summarize()` — counts by status and priority
- An `Agent` (`task_manager`) using `gemini-2.5-flash` that drives those tools.
- A module-level `agent` produced by `wrap(Runner(...))`, which Agent Server imports and serves.

Two things make this deployable:

1. The runner uses `LangsmithSessionService()` so session state is stored in the deployment's checkpoint store.
2. The wrapped graph is exported as the module-level `agent` symbol, which [`langgraph.json`](./langgraph.json) registers under the graph id `adk_echo`.

## Project layout

```
adk-demo/
├── agent.py          # exports the wrapped ADK agent
├── langgraph.json    # Agent Server config (graph id: adk_echo)
├── pyproject.toml    # Python dependencies
├── uv.lock           # pinned dependency lockfile
├── .python-version   # pinned Python version (3.12)
├── .env.example      # environment variable template
└── README.md
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (package manager; installs Python 3.12 for you via `.python-version`)
- A [LangSmith API key](https://docs.langchain.com/langsmith/create-account-api-key)
- A [Gemini API key](https://aistudio.google.com/api-keys) (the agent uses a Gemini model)

The [LangGraph CLI](https://docs.langchain.com/langsmith/cli) is pulled in as a project dependency (`langgraph-cli[inmem]`), so syncing the project gives you the `langgraph` command.

## Setup

Install dependencies (creates a virtualenv and installs from the lockfile):

```bash
uv sync
```

Copy the environment template and fill in your credentials:

```bash
cp .env.example .env
```

```bash
GEMINI_API_KEY=your-gemini-api-key
LANGSMITH_API_KEY=your-langsmith-api-key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT_NAME=adk-demo
```

## Run locally

```bash
uv run langgraph dev
```

This serves the agent at `http://127.0.0.1:2024` and opens [LangSmith Studio](https://docs.langchain.com/langsmith/studio). Try messages like:

- "Add 'write the demo readme' as a high priority task"
- "What's on my list?"
- "Mark the readme task done"
- "How am I doing?"

Or call it over HTTP:

```bash
# Create a thread
THREAD=$(curl -s -X POST http://127.0.0.1:2024/threads \
  -H "Content-Type: application/json" -d '{}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['thread_id'])")

# Run the agent and wait for the final response
curl -s -X POST "http://127.0.0.1:2024/threads/$THREAD/runs/wait" \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "adk_echo",
    "input": {"messages": [{"type": "human", "content": "Add buy milk as a low priority task"}]}
  }'
```

Reusing the same `THREAD` across requests demonstrates that the task list persists in session state.

## Deploy to LangSmith

```bash
uv run langgraph deploy --name adk-demo
```

See [Deploy to cloud](https://docs.langchain.com/langsmith/deploy-to-cloud) for environment configuration, deployment types, and revision management.
