# 0007. LangGraph over CrewAI for orchestration

- Status: accepted
- Date: 2026-09-18

## Context

The investigation has a fixed shape: route, investigate in parallel, write up, and sometimes stop for a person. It has to survive a restart between "paused for review" and "approved", and every step has to be traceable and testable on its own.

Three options were considered:

- **CrewAI.** Role-based agents that talk to each other. Quick to prototype, but control flow emerges from the conversation between agents, which is the opposite of what an auditable incident process needs.
- **A hand-written asyncio pipeline.** Full control, but pause/resume, checkpointing and fan-out would all be reinvented.
- **LangGraph.** An explicit `StateGraph`: nodes, conditional edges, reducers for merging parallel results, `interrupt()` for human input, and checkpointers that persist state between the pause and the resume.

## Decision

LangGraph. The graph is built from the domain adapter: one node per specialist, so the same code runs the retail and support-triage domains. The specialists run in the same superstep, so they execute concurrently. Human review uses `interrupt()` with a Postgres checkpointer (`AsyncPostgresSaver`), and the API resumes a run with `Command(resume=...)`.

## Consequences

- The control flow is readable in one file (`app/agents/graph.py`) and testable with an in-memory checkpointer.
- A paused run survives an API restart: the checkpoint is in Postgres, keyed by run id.
- No free-form agent-to-agent chat. That is deliberate. When a new behaviour is needed, it becomes a new node or edge, not a new prompt.
