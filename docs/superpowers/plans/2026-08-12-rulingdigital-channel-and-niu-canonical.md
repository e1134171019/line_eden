# RulingDigital Channel and NIU Canonical Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a verified `/p/405` RulingDigital channel adapter for UTAIPEI/KNU and move NIU from its `/p/412` summary page to the existing canonical `/p/403 -> /p/406` adapter path.

**Architecture:** Keep `RULINGDIGITAL_LIST` unchanged for canonical `/p/403 -> /p/406` sources. Add `RULINGDIGITAL_CHANNEL_LIST` as a separate adapter that only accepts same-host `/p/405-...php` notice URLs and uses the existing listing paginator. NCUE remains generic because its `/p/412` page delegates to a different cross-host APS system.

**Tech Stack:** Python 3.11/3.13, dataclasses, StrEnum, BeautifulSoup, existing `crawl_listing_pages`, pytest, Ruff, Pyright, GitHub Actions.

## Global Constraints

- No paid runtime service or new AI dependency.
- No new package dependency.
- Do not change eligibility, Gemini, LINE, persistence, TUN, or entity-resolution behavior.
- Do not widen `RULINGDIGITAL_LIST`; keep `/p/405` and `/p/406` structural contracts separate.
- Only UTAIPEI and KNU may map to `RULINGDIGITAL_CHANNEL_LIST` in this phase.
- NIU must use `https://niuosa.niu.edu.tw/p/403-1004-1440-1.php` with `RULINGDIGITAL_LIST`.
- NCUE remains `GENERIC_ANCHOR_LIST`.
- Unknown adapters continue to fail closed.
- Production mappings are retained only if live source evidence meets the design acceptance criteria.

---

### Task 1: Add the `/p/405` parser contract

**Files:**
- Create: `src/collectors/rulingdigital_channel_scholarship_collector.py`
- Test: `tests/test_rulingdigital_channel_scholarship_collector.py`

**Interfaces:**
- Consumes: `AdditionalScholarshipSourceCollector`, `_normalize_text`, `Scholarship.from_raw`, `AdditionalScholarshipSource`.
- Produces: `RulingDigitalChannelScholarshipCollector._parse_html(html: str, page_url: str) -> tuple[list[Scholarship], int]`.

- [ ] **Step 1: Write RED tests**

Create tests proving that the parser:

```python
def test_channel_keeps_only_same_host_p405_notice_links() -> None:
    collector = _collector()
    html = """
    <ul>
      <li><span>2026-08-10</span><a href="/p/405-1000-456%2Cc63.php?Lang=zh-tw">115年測試獎學金</a></li>
      <li><a href="/p/406-1000-457%2Cr63.php">錯誤 family</a></li>
      <li><a href="https://outside.example/p/405-1000-999%2Cc63.php">外站獎學金</a></li>
    </ul>
    """
    records, raw_rows = collector._parse_html(html, collector.config.entry_url)
    assert raw_rows == 1
    assert [item.title for item in records] == ["115年測試獎學金"]
    assert records[0].published_date == "2026-08-10"
```

and that a deadline embedded in the title does not become `published_date` when no independent row date exists:

```python
def test_channel_does_not_treat_title_deadline_as_published_date() -> None:
    collector = _collector()
    records, raw_rows = collector._parse_html(
        '<a href="/p/405-1000-456%2Cc63.php">台灣電力獎學金〖自行申請至115年8月15日止〗</a>',
        collector.config.entry_url,
    )
    assert raw_rows == 1
    assert len(records) == 1
    assert records[0].published_date == ""
```

- [ ] **Step 2: Verify RED**

Run through CI by committing only the new test file. Expected failure: module `src.collectors.rulingdigital_channel_scholarship_collector` does not exist.

- [ ] **Step 3: Implement minimal parser**

Create a collector subclass that:

```python
class RulingDigitalChannelScholarshipCollector(AdditionalScholarshipSourceCollector):
    def _parse_html(self, html: str, page_url: str) -> tuple[list[Scholarship], int]:
        ...

    def _is_channel_detail(self, url: str) -> bool:
        path = urlparse(url).path.lower()
        return self._host_allowed(url) and path.startswith("/p/405-") and path.endswith(".php")
```

Count `raw_rows` only for accepted same-host `/p/405` URLs. Use anchor text as title. For publication date, inspect only ancestor/sibling context that excludes the anchor title text before calling `_extract_date`; if no independent date exists, use `""`.

- [ ] **Step 4: Verify GREEN**

Run the focused test and then full Quality workflow. Expected: focused tests PASS; no existing regression.

- [ ] **Step 5: Commit**

Commit message: `feat: add rulingdigital channel adapter parser`.

### Task 2: Register the channel adapter

**Files:**
- Modify: `src/catalogs/additional_source_catalog.py`
- Modify: `src/collectors/additional_source_adapter_registry.py`
- Modify: `tests/test_additional_source_adapter_registry.py`

**Interfaces:**
- Produces: `AdditionalSourceAdapterId.RULINGDIGITAL_CHANNEL_LIST = "rulingdigital_channel_list"`.
- Registry maps that ID to `RulingDigitalChannelScholarshipCollector`.

- [ ] **Step 1: Write RED registry test**

Add a test replacing a test config adapter ID with `RULINGDIGITAL_CHANNEL_LIST` and asserting the registry builds `RulingDigitalChannelScholarshipCollector`.

- [ ] **Step 2: Verify RED**

Expected failure: missing enum member and/or unsupported adapter.

- [ ] **Step 3: Add enum and factory mapping**

Add exactly one enum member and one registry branch. Do not change existing adapter behavior.

- [ ] **Step 4: Verify GREEN**

Run registry tests and full Quality workflow.

- [ ] **Step 5: Commit**

Commit message: `feat: register rulingdigital channel adapter`.

### Task 3: Apply exact source mappings and NIU canonical entry

**Files:**
- Modify: `src/catalogs/additional_source_catalog.py`
- Modify: `tests/test_additional_scholarship_source_collector.py`

**Interfaces:**
- UTAIPEI and KNU map to `RULINGDIGITAL_CHANNEL_LIST`.
- NIU entry URL becomes `https://niuosa.niu.edu.tw/p/403-1004-1440-1.php` and adapter becomes `RULINGDIGITAL_LIST`.
- NCUE remains `GENERIC_ANCHOR_LIST`.

- [ ] **Step 1: Write RED mapping assertions**

Assert exact specialized sets:

```python
channel_ids = {
    "utaipei-external-scholarships",
    "knu-external-scholarships",
}
```

and assert:

```python
sources_by_id["niu-scholarships"].adapter_id is AdditionalSourceAdapterId.RULINGDIGITAL_LIST
sources_by_id["niu-scholarships"].entry_url == "https://niuosa.niu.edu.tw/p/403-1004-1440-1.php"
sources_by_id["ncue-external-scholarships"].adapter_id is AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST
```

Update the existing `RULINGDIGITAL_LIST` expected IDs to include `niu-scholarships`.

- [ ] **Step 2: Verify RED**

Expected: UTAIPEI/KNU still generic and NIU still uses `/p/412` generic path.

- [ ] **Step 3: Apply only the three catalog changes**

Do not alter any other source contract.

- [ ] **Step 4: Verify GREEN**

Run catalog tests and full Quality workflow.

- [ ] **Step 5: Commit**

Commit message: `refactor: route verified rulingdigital sources`.

### Task 4: Live acceptance and selective rollback

**Files:**
- No production file change unless a mapping fails acceptance; rollback only the failed mapping.
- Add a PR conversation comment with evidence after terminal runs.

**Interfaces:**
- Baselines: UTAIPEI 53 (210/53/157), KNU 19 (100/19/81), NIU 9 (72/9/63).

- [ ] **Step 1: Wait for terminal current-head Quality workflow**

Require Python 3.11/3.13, Ruff, Pyright, pytest, and coverage PASS.

- [ ] **Step 2: Read terminal Scholarship source contract evidence**

Record `collected_count`, `raw_rows`, `parsed_rows`, `rejected_rows`, pages, completeness, and health for UTAIPEI, KNU, NIU.

- [ ] **Step 3: Read terminal 38-program live source contract**

Require success with no new severe program regression attributable to the change.

- [ ] **Step 4: Evaluate mappings independently**

Keep a mapping only if its live output meets the design acceptance criteria. If one source regresses, revert only that source's adapter/URL mapping and rerun gates. Do not remove a valid unassigned adapter implementation solely because one source does not fit it.

- [ ] **Step 5: Record evidence in PR #126**

Comment with old → new counts and raw/parsed/rejected metrics, explicitly state any HOLD or rollback, and keep the PR Draft/unmerged.
