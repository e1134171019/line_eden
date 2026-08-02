# -*- coding: utf-8 -*-

APPLY_CANDIDATE = "apply_candidate"
VERIFY_SOURCE = "verify_source"
MANUAL_REVIEW = "manual_review"
REJECT = "reject"
NOT_ACTIONABLE = "not_actionable"

_VALID_APPLICATION_DETAIL = "valid_application_detail"
_NON_ACTIONABLE_PERIODS = {"expired", "stale_unknown", "not_applicable"}


# 由硬性資格、來源證據、公告類型與申請期間推導下一步行動。
def derive_action_status(
    hard_eligibility_status: str,
    source_evidence_status: str,
    notice_kind: str,
    application_status: str,
) -> str:
    if notice_kind != "application" or application_status in _NON_ACTIONABLE_PERIODS:
        return NOT_ACTIONABLE
    if hard_eligibility_status == "ineligible":
        return REJECT
    source_complete = source_evidence_status == _VALID_APPLICATION_DETAIL
    if hard_eligibility_status == "eligible":
        return APPLY_CANDIDATE if source_complete else VERIFY_SOURCE
    if hard_eligibility_status == "review":
        return MANUAL_REVIEW if source_complete else VERIFY_SOURCE
    return MANUAL_REVIEW
