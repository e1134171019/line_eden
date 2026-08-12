# NPU + Tadnews Adapter Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace high-noise generic-anchor parsing for NPU and NCHU with two verified URL-contract adapters while preserving or improving live collected counts.

**Architecture:** Keep `AdditionalSourceRegistry` and `MultiSourceCollector` unchanged. Add one narrow NPU LatestEvent adapter and one narrow Tadnews category adapter, register both through `AdditionalSourceAdapterRegistry`, and extend the existing safe pagination recognizer with the Tadnews `g2p` page-query key. Production mappings are switched only after RED tests and are rolled back independently if live acceptance fails.

**Tech Stack:** Python 3.11/3.13, dataclasses, StrEnum, BeautifulSoup, urllib.parse, pytest, Ruff, Pyright, GitHub Actions.

## Global Constraints

- No paid runtime service or new AI dependency.
- No new package dependency.
- Do not change eligibility, Gemini, LINE, persistence, entity resolution, SSL verification, or `MultiSourceCollector` semantics.
- Unknown adapter IDs continue to fail closed.
- NPU live acceptance: collected count `>= 98`, rejected rows `<= 813`, and no adapter-attributable parser/fetch errors.
- NCHU live acceptance: collected count `>= 30`, rejected rows `<= 226`, and no adapter-attributable parser/fetch errors; if the live Tadnews page still exposes more than 2 pages, `pages_detected > 2` is required.
- A lower rejection count never compensates for a collected-count regression.
- Roll back only the source mapping that fails live acceptance.
- Keep PR #126 Draft and do not merge `main` automatically.
- Production Acceptance #85 is a known private-profile-data blocker, not evidence of collector regression; do not modify `STUDENT_PROFILE_B64` or eligibility fail-closed behavior in this batch.

---

### Task 1: Add the NPU LatestEvent URL-contract parser

**Files:**
- Create: `tests/test_npu_latestevent_scholarship_collector.py`
- Create: `src/collectors/npu_latestevent_scholarship_collector.py`

**Interfaces:**
- Consumes: `AdditionalScholarshipSourceCollector`, `_extract_date`, `_normalize_text`, `Scholarship.from_raw`, `AdditionalScholarshipSource`, `CollectionMode`.
- Produces: `NpuLatestEventScholarshipCollector._parse_html(html: str, page_url: str) -> tuple[list[Scholarship], int]`.
- URL contract: same allowed host; path ends with `/sub/latestevent/details.aspx` case-insensitively; query contains a non-empty `Parser` value case-insensitively.

- [ ] **Step 1: Write the failing parser tests**

Create `tests/test_npu_latestevent_scholarship_collector.py` with a local `_collector()` fixture and these cases:

```python
# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import (
    AdditionalScholarshipSource,
    AdditionalSourceAdapterId,
)
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.npu_latestevent_scholarship_collector import (
    NpuLatestEventScholarshipCollector,
)


def _collector() -> NpuLatestEventScholarshipCollector:
    config = AdditionalScholarshipSource(
        source_id="npu-latestevent-test",
        display_name="NPU LatestEvent 測試來源",
        entry_url=(
            "https://www.npu.edu.tw/sub/latestevent/index.aspx?"
            "Parser=9%2C22%2C501%2C486"
        ),
        allowed_hosts=("npu.edu.tw", "www.npu.edu.tw"),
        review_reason="測試 NPU LatestEvent URL contract。",
        adapter_id=AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST,
        max_pages=10,
    )
    return NpuLatestEventScholarshipCollector(
        config,
        10.0,
        "test-agent",
        CollectionMode.INCREMENTAL,
        10,
    )


def test_npu_keeps_only_same_host_latestevent_detail_links() -> None:
    collector = _collector()
    html = """
    <table>
      <tr>
        <td>2026-08-10</td>
        <td><a href="/sub/latestevent/Details.aspx?Parser=9%2C22%2C501%2C486%2C1234">
          115年度測試學生獎
        </a></td>
      </tr>
      <tr><td><a href="/sub/latestevent/index.aspx?Parser=9">列表</a></td></tr>
      <tr><td><a href="/sub/latestevent/Details.aspx?id=88">缺 Parser</a></td></tr>
      <tr><td><a href="https://outside.example/sub/latestevent/Details.aspx?Parser=1">外站</a></td></tr>
    </table>
    """

    records, raw_rows = collector._parse_html(html, collector.config.entry_url)

    assert raw_rows == 1
    assert [item.title for item in records] == ["115年度測試學生獎"]
    assert records[0].published_date == "2026-08-10"
    assert records[0].detail_url.endswith("Parser=9%2C22%2C501%2C486%2C1234")


def test_npu_parser_query_key_is_case_insensitive() -> None:
    collector = _collector()
    records, raw_rows = collector._parse_html(
        '<a href="/SUB/LATESTEVENT/DETAILS.ASPX?parser=abc">企業人才獎勵方案</a>',
        collector.config.entry_url,
    )

    assert raw_rows == 1
    assert [item.title for item in records] == ["企業人才獎勵方案"]


def test_npu_does_not_treat_title_deadline_as_published_date() -> None:
    collector = _collector()
    records, raw_rows = collector._parse_html(
        '<div><a href="/sub/latestevent/Details.aspx?Parser=abc">某基金會獎學金 115年9月30日截止</a></div>',
        collector.config.entry_url,
    )

    assert raw_rows == 1
    assert len(records) == 1
    assert records[0].published_date == ""
```

- [ ] **Step 2: Commit only the RED test and verify the expected failure in CI**

Commit message:

```text
test: define NPU LatestEvent adapter contract
```

Expected Quality failure: import/module error for `src.collectors.npu_latestevent_scholarship_collector`; Ruff/Pyright should reveal no unrelated regression once collection reaches that phase.

- [ ] **Step 3: Implement the minimal NPU collector**

Create `src/collectors/npu_latestevent_scholarship_collector.py`:

```python
# -*- coding: utf-8 -*-

from urllib.parse import parse_qsl, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from src.collectors.additional_scholarship_source_collector import (
    AdditionalScholarshipSourceCollector,
    _extract_date,
    _normalize_text,
)
from src.models.scholarship import Scholarship


class NpuLatestEventScholarshipCollector(AdditionalScholarshipSourceCollector):
    """解析 NPU LatestEvent 獎助學金列表中的正式 Details.aspx 公告。"""

    def _parse_html(self, html: str, page_url: str) -> tuple[list[Scholarship], int]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        raw_rows = 0
        for anchor in soup.find_all("a", href=True):
            if not isinstance(anchor, Tag):
                continue
            detail_url = urljoin(page_url, str(anchor.get("href", "")).strip())
            if not self._is_latestevent_detail(detail_url):
                continue
            raw_rows += 1
            title = _normalize_text(anchor.get_text(" ", strip=True))
            if not title:
                continue
            records.append(
                Scholarship.from_raw(
                    self.config.source_id,
                    title,
                    _extract_date(_independent_date_context(anchor), ""),
                    detail_url,
                    entry_url=self.config.entry_url,
                    detail_url=detail_url,
                )
            )
        return records, raw_rows

    def _is_latestevent_detail(self, url: str) -> bool:
        if not self._host_allowed(url):
            return False
        parsed = urlparse(url)
        if not parsed.path.casefold().endswith("/sub/latestevent/details.aspx"):
            return False
        return any(
            key.casefold() == "parser" and value.strip()
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        )


def _independent_date_context(anchor: Tag) -> str:
    parent: Tag | None = anchor
    for _ in range(4):
        candidate = parent.parent
        if not isinstance(candidate, Tag):
            break
        parent = candidate
        parts: list[str] = []
        for node in parent.find_all(string=True):
            if any(node_parent is anchor for node_parent in node.parents):
                continue
            text = _normalize_text(str(node))
            if text:
                parts.append(text)
        context = " ".join(parts)
        if _extract_date(context, ""):
            return context
        if parent.name in {"li", "tr", "article"}:
            break
    return ""
```

- [ ] **Step 4: Verify GREEN**

Run through the Quality workflow. Expected: the three NPU tests pass; no production mapping has changed yet.

- [ ] **Step 5: Commit the implementation**

Commit message:

```text
feat: add NPU LatestEvent adapter parser
```

---

### Task 2: Add Tadnews parser and safe `g2p` pagination recognition

**Files:**
- Create: `tests/test_tadnews_category_scholarship_collector.py`
- Modify: `tests/test_listing_utils.py`
- Create: `src/collectors/tadnews_category_scholarship_collector.py`
- Modify: `src/collectors/listing_utils.py`

**Interfaces:**
- Produces: `TadnewsCategoryScholarshipCollector._parse_html(html: str, page_url: str) -> tuple[list[Scholarship], int]`.
- Detail contract: same allowed host; path ends with `/modules/tadnews/index.php`; numeric `nsn`; when entry URL has `ncsn`, detail URL must contain the same `ncsn` value.
- Pagination contract: `numbered_page_urls()` recognizes a numeric link whose same-path query contains `g2p` as a page URL; existing same-host/path guards remain unchanged.

- [ ] **Step 1: Write the failing Tadnews parser tests**

Create `tests/test_tadnews_category_scholarship_collector.py`:

```python
# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import (
    AdditionalScholarshipSource,
    AdditionalSourceAdapterId,
)
from src.collectors.collection_diagnostics import CollectionMode
from src.collectors.tadnews_category_scholarship_collector import (
    TadnewsCategoryScholarshipCollector,
)


def _collector() -> TadnewsCategoryScholarshipCollector:
    config = AdditionalScholarshipSource(
        source_id="tadnews-test",
        display_name="Tadnews 測試來源",
        entry_url=(
            "https://example.edu.tw/osa/laa/sys/modules/tadnews/"
            "index.php?ncsn=4"
        ),
        allowed_hosts=("example.edu.tw",),
        review_reason="測試 Tadnews category contract。",
        adapter_id=AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST,
        max_pages=10,
    )
    return TadnewsCategoryScholarshipCollector(
        config,
        10.0,
        "test-agent",
        CollectionMode.INCREMENTAL,
        10,
    )


def test_tadnews_keeps_numeric_nsn_in_same_category() -> None:
    collector = _collector()
    html = """
    <article>
      <span>2026-08-11</span>
      <a href="index.php?ncsn=4&nsn=123">企業優秀學生獎</a>
    </article>
    <a href="index.php?ncsn=4&g2p=2">2</a>
    <a href="index.php?ncsn=5&nsn=124">其他分類公告</a>
    <a href="index.php?ncsn=4&nsn=abc">非數字 nsn</a>
    """

    records, raw_rows = collector._parse_html(html, collector.config.entry_url)

    assert raw_rows == 1
    assert [item.title for item in records] == ["企業優秀學生獎"]
    assert records[0].published_date == "2026-08-11"


def test_tadnews_requires_configured_category_when_present() -> None:
    collector = _collector()
    records, raw_rows = collector._parse_html(
        '<a href="index.php?nsn=123">缺少 ncsn</a>',
        collector.config.entry_url,
    )

    assert raw_rows == 0
    assert records == []


def test_tadnews_does_not_use_deadline_in_title_as_publication_date() -> None:
    collector = _collector()
    records, raw_rows = collector._parse_html(
        '<a href="index.php?ncsn=4&nsn=123">某獎學金 115年10月1日截止</a>',
        collector.config.entry_url,
    )

    assert raw_rows == 1
    assert len(records) == 1
    assert records[0].published_date == ""
```

- [ ] **Step 2: Add a failing `g2p` pagination test**

Append to `tests/test_listing_utils.py`:

```python
# Tadnews 的 g2p 必須被辨識成同一 category list 的數字分頁。
def test_tadnews_g2p_query_is_numbered_pagination() -> None:
    base_url = (
        "https://example.edu.tw/osa/laa/sys/modules/tadnews/"
        "index.php?ncsn=4"
    )
    html = """
    <nav>
      <a href="index.php?g2p=2&ncsn=4">2</a>
      <a href="index.php?g2p=3&ncsn=4">3</a>
      <a href="https://outside.example/index.php?g2p=4&ncsn=4">4</a>
    </nav>
    """

    assert numbered_page_urls(html, base_url) == [
        (2, "https://example.edu.tw/osa/laa/sys/modules/tadnews/index.php?g2p=2&ncsn=4"),
        (3, "https://example.edu.tw/osa/laa/sys/modules/tadnews/index.php?g2p=3&ncsn=4"),
    ]
    assert detect_total_pages(html, base_url) == 3
```

- [ ] **Step 3: Commit only the tests and verify RED**

Commit message:

```text
test: define Tadnews adapter and pagination contract
```

Expected failures:
- missing `src.collectors.tadnews_category_scholarship_collector` module;
- after module import is satisfiable, `g2p` is not yet recognized by `numbered_page_urls`.

- [ ] **Step 4: Implement the minimal Tadnews collector**

Create `src/collectors/tadnews_category_scholarship_collector.py` using the same independent-date pattern as Task 1 and these exact guards:

```python
from urllib.parse import parse_qs, urljoin, urlparse

...

class TadnewsCategoryScholarshipCollector(AdditionalScholarshipSourceCollector):
    def _parse_html(self, html: str, page_url: str) -> tuple[list[Scholarship], int]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[Scholarship] = []
        raw_rows = 0
        for anchor in soup.find_all("a", href=True):
            if not isinstance(anchor, Tag):
                continue
            detail_url = urljoin(page_url, str(anchor.get("href", "")).strip())
            if not self._is_tadnews_detail(detail_url):
                continue
            raw_rows += 1
            title = _normalize_text(anchor.get_text(" ", strip=True))
            if not title:
                continue
            records.append(
                Scholarship.from_raw(
                    self.config.source_id,
                    title,
                    _extract_date(_independent_date_context(anchor), ""),
                    detail_url,
                    entry_url=self.config.entry_url,
                    detail_url=detail_url,
                )
            )
        return records, raw_rows

    def _is_tadnews_detail(self, url: str) -> bool:
        if not self._host_allowed(url):
            return False
        parsed = urlparse(url)
        if not parsed.path.casefold().endswith("/modules/tadnews/index.php"):
            return False
        query = parse_qs(parsed.query, keep_blank_values=True)
        nsn = _first_query_value(query, "nsn")
        if not nsn.isdigit():
            return False
        expected_category = _query_value(self.config.entry_url, "ncsn")
        if not expected_category:
            return True
        return _first_query_value(query, "ncsn") == expected_category
```

Define `_first_query_value`, `_query_value`, and `_independent_date_context` in the same file. Query-key matching must be case-insensitive; category values must compare exactly after stripping whitespace.

- [ ] **Step 5: Add only `g2p` to the shared safe page-query key set**

Modify `src/collectors/listing_utils.py`:

```python
_PAGE_QUERY_KEYS = frozenset(
    {"page", "pageno", "page_no", "pageindex", "page_index", "g2p"}
)
```

Do not widen path/host rules and do not add other undocumented query keys.

- [ ] **Step 6: Verify GREEN**

Run the focused tests through CI and then the full Quality workflow. Expected: Tadnews parser tests and `test_tadnews_g2p_query_is_numbered_pagination` pass, with existing pagination tests unchanged.

- [ ] **Step 7: Commit the implementation**

Commit message:

```text
feat: add Tadnews category adapter parser
```

---

### Task 3: Register both adapter capabilities

**Files:**
- Modify: `tests/test_additional_source_adapter_registry.py`
- Modify: `src/catalogs/additional_source_catalog.py`
- Modify: `src/collectors/additional_source_adapter_registry.py`

**Interfaces:**
- Produces enum members:
  - `AdditionalSourceAdapterId.NPU_LATESTEVENT_LIST = "npu_latestevent_list"`
  - `AdditionalSourceAdapterId.TADNEWS_CATEGORY_LIST = "tadnews_category_list"`
- Registry maps them to `NpuLatestEventScholarshipCollector` and `TadnewsCategoryScholarshipCollector` respectively.

- [ ] **Step 1: Write RED registry tests**

Add imports for the two new collector classes and append:

```python
def test_registry_builds_npu_latestevent_collector() -> None:
    registry = AdditionalSourceAdapterRegistry()
    config = replace(
        _config(),
        adapter_id=AdditionalSourceAdapterId.NPU_LATESTEVENT_LIST,
    )

    collector = registry.build(
        config, 10.0, "test-agent", CollectionMode.INCREMENTAL, 20
    )

    assert isinstance(collector, NpuLatestEventScholarshipCollector)


def test_registry_builds_tadnews_category_collector() -> None:
    registry = AdditionalSourceAdapterRegistry()
    config = replace(
        _config(),
        adapter_id=AdditionalSourceAdapterId.TADNEWS_CATEGORY_LIST,
    )

    collector = registry.build(
        config, 10.0, "test-agent", CollectionMode.INCREMENTAL, 20
    )

    assert isinstance(collector, TadnewsCategoryScholarshipCollector)
```

- [ ] **Step 2: Commit tests and verify RED**

Commit message:

```text
test: require NPU and Tadnews adapter registry entries
```

Expected failure: missing enum members and therefore unsupported registry paths.

- [ ] **Step 3: Add enum members**

In `src/catalogs/additional_source_catalog.py`, extend only the enum:

```python
NPU_LATESTEVENT_LIST = "npu_latestevent_list"
TADNEWS_CATEGORY_LIST = "tadnews_category_list"
```

Do not change production source mappings in this task.

- [ ] **Step 4: Add registry imports and factory branches**

In `src/collectors/additional_source_adapter_registry.py`, import both new collectors and add two branches matching the existing registry style. Unknown IDs must still reach the existing `ValueError`.

- [ ] **Step 5: Verify GREEN and commit**

Run the registry tests and full Quality workflow. Commit message:

```text
feat: register NPU and Tadnews adapters
```

---

### Task 4: Apply exact production mappings

**Files:**
- Create: `tests/test_npu_tadnews_source_mappings.py`
- Modify: `tests/test_additional_scholarship_source_collector.py`
- Modify: `src/catalogs/additional_source_catalog.py`

**Interfaces:**
- `npu-scholarship-portal` → `AdditionalSourceAdapterId.NPU_LATESTEVENT_LIST`.
- `nchu-external-scholarships` → `AdditionalSourceAdapterId.TADNEWS_CATEGORY_LIST`.
- All source URLs, `allowed_hosts`, `max_pages`, and other source contracts remain unchanged.

- [ ] **Step 1: Add exact RED mapping assertions**

Create `tests/test_npu_tadnews_source_mappings.py`:

```python
# -*- coding: utf-8 -*-

from src.catalogs.additional_source_catalog import (
    ADDITIONAL_SCHOLARSHIP_SOURCES,
    AdditionalSourceAdapterId,
)


def test_npu_and_nchu_use_only_their_verified_adapters() -> None:
    sources = {item.source_id: item for item in ADDITIONAL_SCHOLARSHIP_SOURCES}

    assert {
        source_id
        for source_id, item in sources.items()
        if item.adapter_id is AdditionalSourceAdapterId.NPU_LATESTEVENT_LIST
    } == {"npu-scholarship-portal"}
    assert {
        source_id
        for source_id, item in sources.items()
        if item.adapter_id is AdditionalSourceAdapterId.TADNEWS_CATEGORY_LIST
    } == {"nchu-external-scholarships"}
```

Also update `test_additional_source_catalog_has_nineteen_reviewed_unique_sources` so `specialized_ids` includes NPU and NCHU and the generic-only assertion remains exact.

- [ ] **Step 2: Commit tests and verify RED**

Commit message:

```text
test: require exact NPU and NCHU adapter mappings
```

Expected failure: NPU and NCHU are still `GENERIC_ANCHOR_LIST`.

- [ ] **Step 3: Switch only the two production adapter IDs**

In `src/catalogs/additional_source_catalog.py`:

```python
# npu-scholarship-portal
adapter_id=AdditionalSourceAdapterId.NPU_LATESTEVENT_LIST,

# nchu-external-scholarships
adapter_id=AdditionalSourceAdapterId.TADNEWS_CATEGORY_LIST,
```

Do not change entry URLs or any other source.

- [ ] **Step 4: Verify GREEN and commit**

Run catalog/mapping tests and the full Quality workflow. Commit message:

```text
refactor: route NPU and NCHU through verified adapters
```

---

### Task 5: Final live acceptance, selective rollback, and governance evidence

**Files:**
- Modify production files only if a source-specific rollback is required.
- Add one PR #126 conversation comment after terminal evidence is available.

**Interfaces:**
- NPU baseline: collected 98; raw/parsed/rejected `1725/98/1627`.
- NCHU baseline: collected 30; raw/parsed/rejected `482/30/452`; prior pages detected 2.

- [ ] **Step 1: Require terminal current-head Quality success**

Verify:

- Python 3.11 job success.
- Python 3.13 job success.
- Ruff success.
- Pyright 0 errors/warnings.
- Full pytest success.
- Coverage `>= 85%`.

Do not infer success from an in-progress run.

- [ ] **Step 2: Read terminal Scholarship Source Contract evidence**

Download `source-health` artifact for the exact final head and record for NPU/NCHU:

- `collected_count`
- `raw_rows`
- `parsed_rows`
- `rejected_rows`
- `pages_detected`
- `pages_requested`
- `pages_succeeded`
- `completeness`
- `error`

- [ ] **Step 3: Evaluate NPU independently**

Keep NPU mapping only when all are true:

```text
collected_count >= 98
rejected_rows <= 813
error is empty / no adapter-attributable fetch or parse failure
```

Otherwise write a RED mapping test expecting `GENERIC_ANCHOR_LIST`, rollback only NPU, rerun Quality + Scholarship Source Contract.

- [ ] **Step 4: Evaluate NCHU independently**

Keep NCHU mapping only when all are true:

```text
collected_count >= 30
rejected_rows <= 226
error is empty / no adapter-attributable fetch or parse failure
pages_detected > 2 when the live page still exposes >2 pages
```

Otherwise write a RED mapping test expecting `GENERIC_ANCHOR_LIST`, rollback only NCHU, rerun Quality + Scholarship Source Contract.

- [ ] **Step 5: Require terminal 38-program Live Source Contract success**

Verify the exact final head's 38-program run is terminal `success`. If it fails, inspect logs before attributing the failure to this change.

- [ ] **Step 6: Inspect Production Acceptance only as a separate gate**

If Production Acceptance runs, distinguish collector failures from the known private-profile blocker. The known failure signature is the `耀登優秀人才` expectation receiving `review` because `profile.json` lacks nationality and enrollment status. Do not alter private profile secrets or eligibility behavior in this batch.

- [ ] **Step 7: Add governance evidence to PR #126**

Post one comment containing:

- exact final head SHA;
- Quality result and test count/coverage;
- old → new NPU metrics;
- old → new NCHU metrics;
- pagination improvement for NCHU;
- any selective rollback performed;
- 38-program Live Source Contract result;
- Production Acceptance status/root-cause classification;
- explicit statement that PR remains Draft/unmerged and no paid/AI runtime dependency was added.

- [ ] **Step 8: Final PR state check**

Confirm PR #126 is still `open`, `draft=true`, `merged=false`. Do not merge or mark ready automatically.
