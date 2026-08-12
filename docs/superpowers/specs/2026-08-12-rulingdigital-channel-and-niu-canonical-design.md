# RulingDigital Channel and NIU Canonical Source Design

## Goal

Reduce false candidates and preserve or improve live scholarship coverage for the remaining RulingDigital/DYNA-style additional sources without introducing a universal `/p/412` parser.

## Verified source structure

The four `/p/412` candidates do not share one detail protocol.

- UTAIPEI (`utaipei-external-scholarships`): the `/p/412-1034-63.php` surface exposes scholarship items as same-host `/p/405-1034-...php` content pages. Search and direct link resolution confirm `/p/405` pages contain full scholarship notice content and attachments.
- KNU (`knu-external-scholarships`): the `/p/412-1005-2921.php` surface exposes scholarship items as same-host `/p/405-1005-...php` content pages. Indexed `/p/405` pages contain the notice body.
- NIU (`niu-scholarships`): the `/p/412-1004-559.php` page is only a summary widget. Its "更多" link points to canonical `/p/403-1004-1440-1.php`; that list is paginated and uses same-host `/p/406-...php` detail pages. This already matches the existing `RULINGDIGITAL_LIST` contract.
- NCUE (`ncue-external-scholarships`): the `/p/412-1000-1513.php` surface links notices to the separate `aps.ncue.edu.tw` announcement system. It is not a `/p/405` or `/p/406` family and remains outside this change.

## Architecture decision

Do not add a generic `/p/412` adapter. `/p/412` is a container/page type, not a stable notice-detail protocol.

Introduce one new structural family:

`RULINGDIGITAL_CHANNEL_LIST`

Its parser accepts only same-host URLs whose path starts with `/p/405-` and ends with `.php`. It reuses the existing paginator so DYNA widget pagination remains available where the page exposes it. It does not accept `/p/403`, `/p/404`, `/p/406`, external hosts, navigation links, or arbitrary anchors.

Map only UTAIPEI and KNU to this family.

For NIU, replace the summary `/p/412` entry URL with the verified canonical `/p/403-1004-1440-1.php` list and map it to the existing `RULINGDIGITAL_LIST` adapter. This avoids creating a second parser for an already-supported `/p/403 -> /p/406` contract.

NCUE remains on `GENERIC_ANCHOR_LIST` in this phase because its cross-host APS system requires separate structural verification.

## Date semantics

`published_date` must represent a publication date, not an application deadline.

The `/p/405` channel cards often include application deadlines in their title text but may not expose a publication date beside the item. `RULINGDIGITAL_CHANNEL_LIST` therefore extracts a date only from near-row context when that context provides an explicit date independent of the title; otherwise it leaves `published_date` blank. It must not infer a publication date from deadline text embedded in a scholarship title.

## Scope

In scope:

- add `RULINGDIGITAL_CHANNEL_LIST` adapter ID;
- add one focused parser for same-host `/p/405` items;
- map UTAIPEI and KNU to the new adapter;
- change NIU to canonical `/p/403` and existing `RULINGDIGITAL_LIST`;
- add tests for URL filtering, date safety, registry creation, and exact source mappings;
- run quality and live source contracts and compare live output with the current generic baseline.

Out of scope:

- NCUE APS parsing;
- changes to eligibility rules, Gemini, LINE, persistence, entity resolution, or TUN collection;
- new packages or paid services;
- widening `RULINGDIGITAL_LIST` to accept `/p/405`.

## Live acceptance criteria

Baseline from the last successful source-contract run before this change:

- UTAIPEI: collected 53; raw/parsed/rejected 210/53/157.
- KNU: collected 19; raw/parsed/rejected 100/19/81.
- NIU: collected 9; raw/parsed/rejected 72/9/63.

Acceptance rules:

1. Quality workflow passes on Python 3.11 and 3.13 with Ruff, Pyright, pytest, and coverage gate.
2. Scholarship source contract and 38-program live source contract do not regress.
3. UTAIPEI and KNU specialized adapters must not reduce `collected_count` below their baseline unless the live site itself demonstrably changed during verification.
4. UTAIPEI and KNU should materially reduce rejected raw candidates because only `/p/405` notice links are counted as raw rows.
5. NIU canonical `/p/403` path must produce at least the previous 9 collected notices and should expose real pagination rather than only the `/p/412` summary widget.
6. Any regression triggers rollback of only the affected production mapping; adapter capability may remain unassigned if its unit contract is valid.

## Cost and safety boundary

The entire change remains deterministic Python code using the repository's existing HTTP, BeautifulSoup, paginator, diagnostics, and GitHub Actions stack. No new AI runtime dependency, paid adapter service, secret, or package is introduced. Unknown adapter IDs continue to fail closed.
