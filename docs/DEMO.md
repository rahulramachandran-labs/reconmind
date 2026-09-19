# 60-second demo

For showing ReconMind live, on [reconmind-labs.vercel.app](https://reconmind-labs.vercel.app) or locally after `make bootstrap && make db seed && make dev`. The free-tier API sleeps; open the dashboard a minute early so the first request has warmed it up.

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00 | Dashboard | Point at the chart | "Twenty-one days of a synthetic retail feed. One day came in light: POSFEED on the 18th, 40% under its own average." |
| 0:08 | Dashboard | Sign in as the demo reviewer, click **Run a scan** | "A scan sends the Planner, then the Reconciliation and Data-Quality agents in parallel. They read the pipeline through two read-only MCP servers." |
| 0:15 | Dashboard | Wait for the tiles to update | "Four findings, one S1, with no model at all: the checks are deterministic, and a model only writes the explanation. Locally a scan takes about four seconds; on the free tier, about fifteen." |
| 0:22 | Incident feed | Open the key-drift finding | "Each one is a write-up, not a chat transcript: problem, record counts, root-cause hypothesis, fix steps, confidence, open questions, and the evidence and runbooks behind it." |
| 0:32 | Review queue | Add a note, click **Approve with note** | "S1s and anything the agents aren't sure about stop here. The decision resumes the LangGraph run and lands in an append-only ledger under my name." |
| 0:40 | Ask ReconMind | Ask *Did the MOBILE file have a schema problem on 2026-06-16?* | "Questions stream. The Planner decided this needs Data-Quality only, and the answer is a real investigation, not a guess from the docs." |
| 0:50 | Traces | Open the run | "Every node, tool call, retrieval and model call is recorded, with latency and cost. With LangFuse keys set, the same trace is there too." |
| 0:57 | Docs & runbooks | Search *basket_ref ContractViolation*, toggle BM25 / dense | "And the retrieval layer is inspectable on its own. Hybrid finds the exact identifier where dense-only doesn't." |

On the public demo the review queue can already be empty: anyone signed in as the demo reviewer can sign the S1 off, and later scans count it as seen again instead of queueing it twice ([ADR 0011](adr/0011-scheduled-scans-and-finding-fingerprints.md)). Open the schema-drift finding in the incident feed instead; its status shows the decision, with the reviewer's note underneath.

If there is time for one more thing: `app/domain/example_support_triage` runs the same graph on support tickets, and CI proves it on every push.
