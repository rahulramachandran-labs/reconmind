# 0013. The model may choose tools, but only for open questions and only three

- Status: accepted
- Date: 2026-09-19

## Context

The specialists run fixed checks through the MCP tools. That is deliberate (ADR 0010): the numbers in an incident report are measured, so a model can't invent them. But it meant a model never chose a tool, and questions about the data that aren't one of the four failure types had nowhere good to go. "Which submitter sent the fewest rows on the 18th, and when did its file land?" went to every specialist, which ran their checks and replied with a scan summary that didn't answer it.

## Decision

- A new intent, `explore`, and an Explorer node. The Planner sends a question there when it asks for a fact about the data or runs rather than whether something is wrong. The keyword router does the same for data questions no specialist's keywords match.
- The Explorer offers the model every tool on both MCP servers, named `server__tool`, through the providers' OpenAI-compatible tool calling. The model may make **at most three calls in total**. After that the tools are withdrawn and it has to answer.
- Each call goes through the same `MCPToolBox` as the checks, so it is a traced tool step with its arguments and result. Results are cut at 3,000 characters and treated as data: the system prompt says to ignore instructions in them.
- A bad tool name or bad arguments comes back to the model as an error message rather than failing the run.
- With no model, or none that can call tools (the Anthropic provider here doesn't), the question is answered from the runbooks instead.
- Scans are unchanged: specialists and fixed checks only.

## Consequences

- The model now demonstrably decides what to look at, and the trace shows each decision: an `explore` model step listing the tool calls it asked for, the tool steps, then the answer.
- Its answers are not held to the grounding check the specialists' write-ups get (a tool result isn't a fixed set of facts to check against), so they are chat answers, never incident reports.
- Three calls fit within a free tier's per-minute token limit alongside the planner call; a question that needs more gets a partial answer that says what it looked at.
