# NFU Canonical Source Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `nfu-scholarships` from the university-wide activity listing to the official Office of Student Affairs scholarship listing without adding a new parser and without reducing live scholarship recall.

**Architecture:** Keep the existing `GENERIC_ANCHOR_LIST` adapter and shared paginator. Change only the NFU source contract (`entry_url` and explicit allowed host), then prove the migration with a catalog regression test plus exact-head Quality, Scholarship Source Contract, 38-program Live Source Contract, and source-health comparison.

**Tech Stack:** Python 3.11/3.13, pytest, Ruff, Pyright, BeautifulSoup-based existing collector stack, GitHub Actions live contracts.

## Global Constraints

- NFU canonical entry URL is exactly `https://osa.nfu.edu.tw/zh_tw/4/sclink/scholarship`.
- `adapter_id` remains `AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST`.
- `max_pages` remains `10`.
- `allowed_hosts` must explicitly contain `osa.nfu.edu.tw` while retaining existing NFU hosts.
- No new collector/parser class.
- No eligibility, Gemini, LINE, persistence, dependency, workflow, or paid-runtime changes.
- Live acceptance requires `collected_count >= 45`, `rejected_rows <= 895`, and all requested NFU pages to succeed.
- If NFU live acceptance fails, revert only the NFU source contract.

---

### Task 1: Lock the NFU canonical source contract with a RED test

**Files:**
- Modify: `tests/test_additional_scholarship_source_collector.py`

**Interfaces:**
- Consumes: `ADDITIONAL_SCHOLARSHIP_SOURCES`, `AdditionalSourceAdapterId`
- Produces: regression contract for the existing `nfu-scholarships` catalog entry

- [ ] **Step 1: Add the failing catalog test**

```python
def test_nfu_source_uses_osa_canonical_scholarship_listing() -> None:
    source = next(
        item
        for item in ADDITIONAL_SCHOLARSHIP_SOURCES
        if item.source_id == "nfu-scholarships"
    )

    assert source.entry_url == "https://osa.nfu.edu.tw/zh_tw/4/sclink/scholarship"
    assert "osa.nfu.edu.tw" in source.allowed_hosts
    assert source.adapter_id is AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST
    assert source.max_pages == 10
```

- [ ] **Step 2: Run the test through the branch Quality workflow and verify RED**

Expected failure: the current NFU `entry_url` is still `https://www.nfu.edu.tw/zh_tw/ann/art` and/or the explicit `osa.nfu.edu.tw` host is absent. Ruff and Pyright should remain clean.

- [ ] **Step 3: Commit the RED test only**

Commit message: `test: require NFU canonical scholarship listing`

### Task 2: Apply the minimal NFU catalog migration

**Files:**
- Modify: `src/catalogs/additional_source_catalog.py`

**Interfaces:**
- Consumes: existing `AdditionalScholarshipSource`
- Produces: updated `nfu-scholarships` source contract; no new adapter or parser API

- [ ] **Step 1: Change only the NFU catalog entry**

```python
AdditionalScholarshipSource(
    source_id="nfu-scholarships",
    display_name="國立虎尾科技大學獎助學金公告",
    entry_url="https://osa.nfu.edu.tw/zh_tw/4/sclink/scholarship",
    allowed_hosts=("nfu.edu.tw", "www.nfu.edu.tw", "osa.nfu.edu.tw"),
    review_reason="2026年持續更新，正文通常包含資格、金額與期限，能補足科技企業方案。",
    adapter_id=AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST,
    max_pages=10,
),
```

- [ ] **Step 2: Commit the minimal GREEN change**

Commit message: `refactor: route NFU to canonical scholarship listing`

- [ ] **Step 3: Run exact-head Quality checks**

Required terminal result on Python 3.11 and 3.13: Ruff success, Pyright 0 errors, pytest success, coverage >= 85%.

### Task 3: Prove live source quality and decide keep/rollback

**Files:**
- No production file changes unless rollback is required.

**Interfaces:**
- Consumes: exact-head GitHub Actions source-health artifact
- Produces: keep/rollback decision for only `nfu-scholarships`

- [ ] **Step 1: Wait for exact-head Scholarship Source Contract terminal result**

Required workflow conclusion: `success` before evaluating metrics.

- [ ] **Step 2: Read the exact-head NFU source-health record**

Compare against baseline:

```text
collected_count = 45
raw_rows = 1835
parsed_rows = 45
rejected_rows = 1790
pages_detected = 11
pages_requested = 10
pages_succeeded = 10
```

Accept only if:

```text
collected_count >= 45
rejected_rows <= 895
pages_succeeded == pages_requested
```

- [ ] **Step 3: Verify the exact-head 38-program Live Source Contract reaches `success`**

- [ ] **Step 4: Inspect Production Acceptance separately**

If it fails only because `耀登優秀人才` is fail-closed due missing nationality/enrollment fields in private `profile.json`, record it as the existing profile-data blocker. Do not change eligibility logic or fabricate profile values.

- [ ] **Step 5A: Keep the migration when all NFU acceptance conditions pass**

Record the baseline → candidate metrics in PR #126 and leave the branch Draft/unmerged.

- [ ] **Step 5B: Selectively rollback if an NFU acceptance condition fails**

Restore only:

```python
entry_url="https://www.nfu.edu.tw/zh_tw/ann/art"
allowed_hosts=("nfu.edu.tw", "www.nfu.edu.tw")
```

Keep `GENERIC_ANCHOR_LIST`, all other adapters, and all unrelated source mappings unchanged. Re-run exact-head Quality and live contracts after rollback.
