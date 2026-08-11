# Free Core Adapter Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a deterministic, no-cost source/adapter composition layer without changing existing collection output semantics.

**Architecture:** Existing additional-source contracts gain an explicit `adapter_id`. A focused adapter registry resolves that ID to a collector factory. `ExpandedScholarshipCollector` delegates additional-source collector construction to the registry, while dedicated collectors and `MultiSourceCollector` remain unchanged.

**Tech Stack:** Python, dataclasses, pytest, existing collector classes, GitHub Actions.

## Global Constraints

- No paid runtime service or new AI dependency.
- No new package dependency.
- Preserve existing source IDs, URLs, eligibility behavior, Gemini behavior, LINE behavior, and `MultiSourceCollector` semantics.
- Fail closed for unknown adapter IDs.
- Follow repository `AGENTS.md` and run the full existing test suite before completion.

---

### Task 1: Contract and adapter registry

**Files:**
- Modify: `src/catalogs/additional_source_catalog.py`
- Create: `src/collectors/additional_source_adapter_registry.py`
- Test: `tests/test_additional_source_adapter_registry.py`

**Interfaces:**
- Produces: `AdditionalScholarshipSource.adapter_id: str`
- Produces: `AdditionalSourceAdapterRegistry.build(config, timeout_seconds, user_agent, collection_mode, max_pages) -> BaseCollector`

- [ ] Write a failing test asserting the default contract adapter ID is `generic_anchor_list`, the registry returns `AdditionalScholarshipSourceCollector`, and an unknown adapter ID raises `ValueError`.
- [ ] Run the focused test and verify failure is caused by the missing field/registry.
- [ ] Add `adapter_id` to the contract and implement the minimal registry with the `generic_anchor_list` factory.
- [ ] Run the focused test and verify it passes.

### Task 2: Route expanded collection through the registry

**Files:**
- Modify: `src/collectors/expanded_scholarship_collector.py`
- Test: `tests/test_expanded_scholarship_collector_registry.py`

**Interfaces:**
- Consumes: `AdditionalSourceAdapterRegistry.build(...)`
- Produces: unchanged `ExpandedScholarshipCollector.collect() -> list[Scholarship]`

- [ ] Write a failing test that injects or substitutes the registry and proves additional official/broad source collectors are requested through it.
- [ ] Run the focused test and verify it fails against the current direct construction path.
- [ ] Add a registry dependency with a default production registry and replace `_additional_collector` direct construction with registry resolution.
- [ ] Run the focused test and verify it passes.

### Task 3: Regression verification

**Files:**
- Modify only if required by legitimate regressions discovered by tests.

- [ ] Run `pytest tests/` in CI for the feature branch.
- [ ] Confirm no existing collection/eligibility/notification tests regress.
- [ ] Review the diff for accidental paid-service or AI coupling.
- [ ] Keep the change on the feature branch and open a pull request for review; do not merge to `main` automatically.
