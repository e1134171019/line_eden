# Free Core Adapter Registry Design

## Goal

Refactor the scholarship collection entry path so adding an additional source does not require the orchestration layer to know its concrete collector implementation, while keeping the production core deterministic and free of paid AI dependencies.

## Scope

This is a staged collection-composition refactor. It does not redesign eligibility rules, Gemini document extraction, LINE notification delivery, persistence, cross-source entity resolution, or AI-assisted source discovery.

Dedicated legacy collectors such as LHU, HelpDreams and TUN remain in the existing composition root for this phase. The new registry path applies to the `AdditionalScholarshipSource` catalog first so the architecture can be introduced without changing production collection semantics.

## Architecture

The additional-source production path is:

`AdditionalSourceRegistry -> AdditionalSourceAdapterRegistry -> existing MultiSourceCollector`

- `AdditionalSourceRegistry` exposes the approved official/additional and broad-portal source contract groups.
- `AdditionalSourceAdapterRegistry` maps each contract's explicit `adapter_id` to a collector implementation.
- `ExpandedScholarshipCollector` composes those resolved collectors with the existing dedicated collectors.
- `MultiSourceCollector` remains the runner responsible for source isolation, diagnostics and current cross-source deduplication. A second `CollectorRunner` wrapper is intentionally not introduced.

## Adapter policy

`AdditionalScholarshipSourceCollector` is retained as the implementation behind `generic_anchor_list`. A generic adapter is not a universal fallback.

Every `AdditionalScholarshipSource` must explicitly declare `adapter_id`; there is no default. An unknown adapter ID fails closed. This prevents future sources from silently inheriting a parser whose DOM assumptions were never validated.

The 19 existing additional sources explicitly declare `generic_anchor_list` only to preserve current behavior in this first refactor. Moving heterogeneous sites to structure-family or dedicated adapters is a separate follow-up task and requires site-level verification.

Candidate future adapter families include:

- `generic_anchor_list`
- `simple_table`
- `wordpress_rss`
- `json_api`
- `javascript_api`
- dedicated site adapters when a structure cannot safely share a parser

These are design directions, not automatically registered production adapters.

## Cost boundary

The production collection path remains pure program logic:

- no paid adapter service;
- no new AI dependency;
- no new package dependency in this refactor;
- no requirement for an LLM to select selectors or parse routine daily listings.

Existing Gemini integration remains optional and limited to the repository's difficult-document review path.

## Compatibility

- Existing source IDs and URLs remain unchanged.
- Existing dedicated collectors remain unchanged.
- Existing `MultiSourceCollector` behavior remains unchanged.
- Eligibility, LINE notification and Gemini behavior are outside this refactor.
- Unknown adapter strategies fail closed rather than guessing.

## Verification

Tests must prove that:

1. an additional-source contract cannot be created without an explicit `adapter_id`;
2. the adapter registry builds the expected collector for a supported adapter ID;
3. unknown adapter IDs fail closed;
4. the source registry exposes the approved source groups;
5. `ExpandedScholarshipCollector` obtains additional-source groups from the source registry;
6. `ExpandedScholarshipCollector` resolves each additional source through the adapter registry;
7. the full existing test suite remains green on supported Python versions.
