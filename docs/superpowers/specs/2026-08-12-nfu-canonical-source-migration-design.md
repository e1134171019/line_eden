# NFU canonical source migration design

## Context

`nfu-scholarships` currently points to the university-wide `https://www.nfu.edu.tw/zh_tw/ann/art` activity listing and uses `GENERIC_ANCHOR_LIST`. The latest validated source-health artifact reports 45 collected records from 1,835 raw anchors, 1,790 rejected anchors, 11 detected pages, 10 requested pages, and 10 successful pages. This is a high-noise source.

The official Office of Student Affairs scholarship site exposes a dedicated scholarship listing at `https://osa.nfu.edu.tw/zh_tw/4/sclink/scholarship`. The live page is scholarship-specific and its pagination uses `page_no`, which the existing shared paginator already supports.

## Decision

Perform a canonical URL migration only. Do not add a new NFU adapter in this batch.

Production contract for `nfu-scholarships`:

- `entry_url`: `https://osa.nfu.edu.tw/zh_tw/4/sclink/scholarship`
- `allowed_hosts`: retain `nfu.edu.tw` and `www.nfu.edu.tw`, and add `osa.nfu.edu.tw` explicitly
- `adapter_id`: remain `AdditionalSourceAdapterId.GENERIC_ANCHOR_LIST`
- `max_pages`: remain `10`
- no eligibility, Gemini, LINE, persistence, dependency, or workflow behavior changes

## Alternatives rejected

### Scholarship landing dashboard

`https://osa.nfu.edu.tw/zh_tw/life/scholarship/scholarship_news` is a useful human navigation page, but it is composed of several category summaries and “more” links. The production crawler follows listing pagination, not arbitrary category expansion, so using the dashboard as the sole entry risks reduced recall.

### New NFU-specific adapter

A dedicated adapter could constrain detail URLs further, but a new parser is unnecessary until the canonical listing has been tested with the existing generic parser. YAGNI: migrate the source contract first and specialize only if live diagnostics still show material noise.

## Data flow

`AdditionalSourceRegistry` → `nfu-scholarships` canonical config → `AdditionalSourceAdapterRegistry` → existing `GENERIC_ANCHOR_LIST` → shared `crawl_listing_pages()` with `page_no` pagination → existing scholarship marker filtering → source-health/live contract.

## Acceptance gates

Baseline from the latest validated head:

- collected: 45
- raw rows: 1,835
- parsed rows: 45
- rejected rows: 1,790
- pages detected: 11
- pages requested/succeeded: 10/10

Candidate head must satisfy all of the following:

1. Quality checks pass on Python 3.11 and 3.13, including Ruff, Pyright, pytest, and coverage >= 85%.
2. Scholarship Source Contract reaches terminal success.
3. `nfu-scholarships.collected_count >= 45`.
4. `nfu-scholarships.rejected_rows <= 895` (at least 50% lower than the 1,790 baseline).
5. `nfu-scholarships.pages_succeeded == nfu-scholarships.pages_requested` for the requested batch.
6. 38-program Live Source Contract reaches terminal success.
7. Production Acceptance is inspected separately. A known fail-closed profile-data blocker must not be “fixed” by weakening eligibility logic or fabricating private profile fields.

If gates 3, 4, or 5 fail, revert only the NFU source contract to its prior entry URL/host set. Do not remove unrelated adapters or modify downstream eligibility logic.

## Test strategy

Add a catalog regression test that requires the exact NFU canonical `entry_url`, explicit `osa.nfu.edu.tw` host allowance, unchanged `GENERIC_ANCHOR_LIST`, and unchanged `max_pages=10`. Run it first against the old catalog to obtain RED. Then make only the catalog change and verify GREEN through the full quality workflow and live source contracts.

## Scope boundary

This batch does not change TP2E, HKU, Pan Wen-Yuan, UCH, NYCU, UTAIPEI, NCUE, or any other source. It does not introduce a new parser class.