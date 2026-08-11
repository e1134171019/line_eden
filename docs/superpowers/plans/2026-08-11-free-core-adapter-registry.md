# Free Core Adapter Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a deterministic, no-cost source/adapter composition layer without changing existing collection output semantics.

**Architecture:** Additional-source contracts require an explicit `adapter_id`. `AdditionalSourceRegistry` exposes approved source groups, `AdditionalSourceAdapterRegistry` resolves each source contract to a collector implementation, and the existing `MultiSourceCollector` remains the runner. No redundant runner wrapper is added.

**Tech Stack:** Python, dataclasses, Protocol, pytest, existing collector classes, GitHub Actions.

## Global Constraints

- No paid runtime service or new AI dependency.
- No new package dependency.
- Preserve existing source IDs, URLs, eligibility behavior, Gemini behavior, LINE behavior, and `MultiSourceCollector` semantics.
- Fail closed for missing or unknown adapter IDs.
- Follow repository `AGENTS.md` and run the full existing test suite before completion.

---

### Task 1: Explicit adapter contract and registry

**Files:**
- Modify: `src/catalogs/additional_source_catalog.py`
- Create: `src/collectors/additional_source_adapter_registry.py`
- Test: `tests/test_additional_source_adapter_registry.py`
- Test: `tests/test_additional_scholarship_source_collector.py`

- [x] Write RED tests for the adapter registry and unsupported adapter behavior.
- [x] Add `adapter_id` to `AdditionalScholarshipSource`.
- [x] Remove the implicit adapter default so every additional source must declare its strategy.
- [x] Explicitly map the 19 existing sources to `generic_anchor_list` to preserve current behavior.
- [x] Implement `AdditionalSourceAdapterRegistry` and fail closed for unknown adapter IDs.
- [x] Verify the focused behavior through CI.

### Task 2: Route additional collector creation through adapter registry

**Files:**
- Modify: `src/collectors/expanded_scholarship_collector.py`
- Test: `tests/test_expanded_scholarship_collector_registry.py`

- [x] Write a RED test proving the current constructor cannot inject an adapter registry.
- [x] Add an adapter-registry Protocol dependency with a default production implementation.
- [x] Route `_additional_collector` through the adapter registry.
- [x] Verify the behavior through CI.

### Task 3: Introduce source registry and remove catalog coupling

**Files:**
- Create: `src/catalogs/additional_source_registry.py`
- Modify: `src/collectors/expanded_scholarship_collector.py`
- Test: `tests/test_additional_source_registry.py`
- Test: `tests/test_expanded_scholarship_collector_registry.py`

- [x] Write a RED test for the missing source registry.
- [x] Implement `AdditionalSourceRegistry` for approved official/additional and broad source groups.
- [x] Write a RED integration test proving `ExpandedScholarshipCollector` still depends directly on catalog groups.
- [x] Inject the source registry and load additional-source groups through it.
- [x] Keep the existing `MultiSourceCollector` as the runner instead of adding a redundant wrapper.
- [x] Verify the behavior through CI.

### Task 4: Regression and governance verification

**Files:**
- Modify only documentation if required to keep the design consistent with the implemented architecture.

- [ ] Run the final full quality workflow on Python 3.11 and 3.13.
- [ ] Confirm Ruff and Pyright are clean.
- [ ] Confirm the coverage threshold remains satisfied.
- [ ] Check source-contract and production-acceptance workflows for regressions.
- [ ] Review the final PR diff for accidental paid-service or AI coupling.
- [ ] Keep the change on the feature branch and draft PR; do not merge to `main` automatically.
