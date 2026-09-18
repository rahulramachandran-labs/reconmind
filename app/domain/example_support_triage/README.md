# Pointing ReconMind at another domain

This folder is a working example of a second domain: support ticket triage. It is small on purpose. The graph, the prompts, retrieval, tracing, human review and the UI all run on it unchanged, and `tests/integration/test_domain_agnostic.py` proves it on every CI run.

An adapter implements `app.domain.protocol.DomainAdapter`:

| Member | What it decides |
|---|---|
| `specialists` | Which specialist agents exist, what they look for, and the words that route a question to them. The graph creates one node per specialist. |
| `scan_keywords` | Phrases that mean "check everything". |
| `resolve_scope(question, tools)` | The window an investigation covers. |
| `run_checks(role, tools, scope)` | The deterministic checks that produce facts. This is the only place that touches data, and it does so through the MCP tool box. |
| `severity(finding)` | The rubric. Models never set severity. |
| `problem_statement(finding)` | The opening paragraph of the write-up. |
| `retrieval_query(finding)` | What to search the runbooks for. |
| `fallback_analysis(finding, sources)` | Root cause, fix and confidence when no model is available or a model's answer fails validation. |

To make this one real:

1. Replace `TICKETS` with an MCP server over the ticketing system (open tickets, SLA policy, customer account state), read-only like the two retail servers.
2. Put the support runbooks and past postmortems in a corpus folder and point `CORPUS_DIR` at it.
3. Set `DOMAIN_ADAPTER=example_support_triage`.

The same pattern covers the other domains in the deck:

- **Claims (healthcare).** Dedup key: claim id + line + service date. The drift pair is the provider's NPI vs the billing TIN. Anomalies are EOB volume and denial-rate swings.
- **Signal review (trading).** Dedup on venue + order id + fill id. The drift pair is internal instrument id vs venue symbol. Anomalies are tick-rate gaps and position drift between the ledger and the venues.
