# Free Core Adapter Registry Design

## Goal

Refactor the scholarship collection entry path so adding sources does not require the orchestration layer to know every concrete collector, while keeping the production core deterministic and free of paid AI dependencies.

## Scope

This change is intentionally limited to collection composition. It does not redesign eligibility rules, Gemini document extraction, LINE notification delivery, persistence, or source-discovery AI.

## Architecture

The production path becomes:

`SourceRegistry -> AdapterRegistry -> CollectorRunner -> existing MultiSourceCollector`

`SourceRegistry` owns enabled source contracts. `AdapterRegistry` maps an `adapter_id` to a factory that can build the correct collector for a source contract. The orchestration layer asks the registries for collectors instead of directly constructing every additional-source collector.

Existing dedicated collectors remain valid. `AdditionalScholarshipSourceCollector` is retained as one adapter implementation for sources that genuinely share that parsing structure; it is no longer treated as the universal mechanism for every future source.

## Data model

Extend the existing additional-source contract with `adapter_id`. The default for currently supported additional sources is `generic_anchor_list`, preserving behavior while making the parsing strategy explicit.

## Compatibility

- No paid service is introduced.
- No new runtime dependency is introduced.
- Existing source IDs and URLs remain unchanged.
- Existing `MultiSourceCollector` behavior remains unchanged in this first refactor.
- Existing Gemini integration remains optional and outside the collection composition path.

## Verification

Tests must prove that:

1. a source contract exposes an explicit adapter ID;
2. the adapter registry builds the expected collector from that ID;
3. unknown adapter IDs fail closed;
4. the expanded collector obtains additional-source collectors through the registry path rather than directly constructing them;
5. the existing test suite remains green.
