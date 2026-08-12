# Private Profile Completion + Formal LINE Delivery Design

## Goal
Complete the three missing production profile facts without committing them in plaintext, rerun the exact production acceptance logic, and send LINE only when that same audit passes.

## Isolation
- Work only on `ops/line-delivery-20260812`, created from validated head `8e91e191c256669f82afc57b847865f5fead39c5`.
- Do not modify or merge `main`.
- Do not modify PR #126.
- Profile plaintext must not be committed, logged, or uploaded as an artifact.

## Runtime Profile Overlay
The existing `STUDENT_PROFILE_B64` remains the source of all private profile data. The one-time operation overlays only these approved facts at runtime:
- `nationality = 中華民國`
- `enrollment_status = 在學`
- `academic_year_average = 82.6`

## Encryption Transport
1. A key-generation workflow creates an RSA-3072 key pair.
2. The private key is immediately encrypted with existing `STATE_PASSPHRASE`; only encrypted private key + public key are uploaded.
3. The approved profile overlay JSON is encrypted locally with RSA-OAEP/SHA-256.
4. Only base64 ciphertext is committed to `ops/profile-overlay.b64`.
5. The delivery workflow decrypts the private key, decrypts the overlay, merges exactly the three allowed keys into decoded `STUDENT_PROFILE_B64`, and writes temporary `profile.json`.
6. Plaintext temporary files are deleted with an `always()` cleanup step.

## Acceptance Gate
The delivery workflow executes the same production collection, semantic audit, and `evaluate_release_acceptance(...)` logic used by `src.automation.production_acceptance_audit`.

LINE delivery is forbidden unless production acceptance passes.

## Formal LINE Candidate Rule
Do not call `send_confirmed_line_links.py` and do not merge `USER_CONFIRMED_ELIGIBLE_LINKS` into this one-time formal send.

Send only records from the same audit result whose runtime state is:
- final hard status = `eligible`;
- `action_status = apply_candidate`;
- non-empty title and detail/source URL.

Deduplicate by URL. Reuse `build_line_message` and `line_notifier.send_text_message`.

This prevents a previously confirmed tracking item from overriding a current hard `ineligible` result, including 2026 Auden.

## Failure Handling
- Missing Secrets, key artifact, decryption error, invalid overlay, or disallowed overlay key: fail closed before LINE.
- Production acceptance failure: retain diagnostics but do not send LINE.
- Empty eligible set after a passing acceptance: send the normal zero-eligible completion message; do not substitute static links.
- LINE API failure: fail the workflow; do not auto-retry and risk duplicate delivery.

## Verification
Required evidence:
- unit tests for dynamic `apply_candidate` link selection;
- synthetic regression proving an ineligible Auden record is excluded;
- Quality checks pass;
- production acceptance passes with runtime overlay;
- LINE transport succeeds in the same delivery workflow;
- final logs state the number of links sent without printing profile plaintext.
