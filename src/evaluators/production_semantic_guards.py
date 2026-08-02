# -*- coding: utf-8 -*-

from collections.abc import Callable

from src.evaluators import eligibility_rules

TermRequirement = Callable[[str, str, tuple[str, ...]], bool]


# 安裝一次全域安全規則；所有 EligibilityEvaluator 共用同一語意。
def install_semantic_guards() -> None:
    if getattr(eligibility_rules, "_production_semantic_guard_installed", False):
        return
    eligibility_rules._term_is_required = _term_is_required_without_exclusions
    eligibility_rules._production_semantic_guard_installed = True


# 「不含學士班一年級新生」是排除子群，不得解讀為限定新生。
def _term_is_required_without_exclusions(
    text: str,
    title: str,
    terms: tuple[str, ...],
) -> bool:
    if (
        any(term in title for term in terms)
        and not eligibility_rules._contains_preference(title)
        and not eligibility_rules._explicitly_excludes(title, terms)
    ):
        return True
    for sentence in eligibility_rules._sentences(text):
        if not any(term in sentence for term in terms):
            continue
        if eligibility_rules._explicitly_excludes(sentence, terms):
            continue
        if eligibility_rules._sentence_requires_group(sentence, terms):
            return True
    return False
