# Private Profile LINE Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Securely overlay the three approved private-profile facts at runtime, require production acceptance to pass, then send only current dynamic `apply_candidate` scholarships to LINE.

**Architecture:** Use isolated branch `fix/ops-line-delivery-20260812` and a two-run RSA handoff so no profile plaintext is committed. A keygen workflow creates a public key and a `STATE_PASSPHRASE`-encrypted private key artifact. A delivery workflow decrypts a ciphertext overlay, runs the existing production audit once, selects dynamic eligible/apply-candidate records from that same result, and sends LINE only after acceptance passes.

**Tech Stack:** Python 3.13, GitHub Actions, OpenSSL RSA-OAEP/SHA-256, GPG AES256, existing scholarship service/evaluators/LINE notifier.

## Global Constraints
- Branch: `fix/ops-line-delivery-20260812` only.
- Base validated head: `8e91e191c256669f82afc57b847865f5fead39c5`.
- Never modify or merge `main` or PR #126.
- Never commit/log/upload profile plaintext.
- Overlay may contain exactly `nationality`, `enrollment_status`, `academic_year_average`.
- LINE send occurs only after `evaluate_release_acceptance(...)` passes in the same process/run.
- Do not use `USER_CONFIRMED_ELIGIBLE_LINKS` for the formal send.

---

### Task 1: Dynamic formal LINE selection

**Files:**
- Create: `src/automation/accepted_line_delivery.py`
- Create: `tests/test_accepted_line_delivery.py`

**Interfaces:**
- Produces: `links_from_accepted_records(records: list[AuditRecord]) -> tuple[EligibleLink, ...]`
- Produces: one orchestration entry point that performs full source collection, semantic audit, acceptance, then LINE send.

- [ ] Write a failing test with synthetic audit records showing only `eligible + apply_candidate` is selected.
- [ ] Add a regression where Auden is `ineligible` while a static confirmed Auden link exists; assert it is absent from formal selected links.
- [ ] Run targeted tests and confirm RED because module/function does not yet exist.
- [ ] Implement URL-deduplicated dynamic selection using final hard status and `APPLY_CANDIDATE`.
- [ ] Implement orchestration by reusing existing collector/audit/release acceptance and LINE formatter/notifier; do not merge static confirmed links.
- [ ] Run targeted tests and full Quality suite.

### Task 2: One-time encrypted profile transport

**Files:**
- Create: `.github/workflows/ops-profile-keygen.yml`
- Create after encryption: `ops/profile-overlay.b64`

**Interfaces:**
- Keygen artifact name: `profile-overlay-key`.
- Artifact files: `public.pem`, `private.pem.gpg` only.

- [ ] Add a push-triggered keygen workflow scoped to `fix/ops-line-delivery-20260812` and path `.github/workflows/ops-profile-keygen.yml`.
- [ ] Require non-empty `STATE_PASSPHRASE`.
- [ ] Generate RSA-3072 key pair, encrypt private key with GPG AES256, securely delete plaintext private key, upload public key + encrypted private key.
- [ ] Trigger by committing workflow and verify artifact exists.
- [ ] Download artifact, encrypt the approved three-field JSON locally with RSA-OAEP/SHA-256, base64 it, and commit only ciphertext to `ops/profile-overlay.b64`.

### Task 3: Gated production LINE workflow

**Files:**
- Create: `.github/workflows/ops-formal-line-delivery.yml`

**Interfaces:**
- Consumes: `ops/profile-overlay.b64`, latest keygen artifact, `STUDENT_PROFILE_B64`, `STATE_PASSPHRASE`, `GEMINI_API_KEY`, `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_USER_ID`.
- Executes: `python -m src.automation.accepted_line_delivery` after runtime profile creation.

- [ ] Validate required Secrets before decryption or collection.
- [ ] Resolve/download the exact keygen artifact for this ops branch.
- [ ] Decrypt private key with `STATE_PASSPHRASE`; decrypt overlay ciphertext with RSA-OAEP/SHA-256.
- [ ] Validate overlay JSON key set exactly matches the three approved keys and types.
- [ ] Decode existing `STUDENT_PROFILE_B64`, merge only overlay values, write temporary `profile.json` without printing it.
- [ ] Run `accepted_line_delivery`; acceptance failure must prevent LINE transport.
- [ ] Upload production diagnostic artifacts, excluding `profile.json`, decrypted overlay, private key, and other plaintext private files.
- [ ] Always delete plaintext profile/key/overlay files.
- [ ] Verify workflow terminal result and LINE step log.

### Task 4: Final verification and handoff

- [ ] Verify current ops head Quality: Python 3.11/3.13, Ruff, Pyright, pytest, coverage.
- [ ] Verify production acceptance PASS in the same formal LINE run.
- [ ] Verify LINE API transport success and exact count of links sent.
- [ ] Verify PR #126 head/state unchanged and `main` unchanged.
- [ ] Record tool-route result and evidence in a short ops audit comment/document without private values.
