# -*- coding: utf-8 -*-

from src.evaluators import eligibility_rules


# 帶有明確「不含／不包括」的子群，不能被外層申請對象標題反向視為必要條件。
def _term_is_required_with_exclusion_scope(
    text: str,
    title: str,
    terms: tuple[str, ...],
) -> bool:
    if any(term in title for term in terms):
        if eligibility_rules._explicitly_excludes(title, terms):
            return False
        if not eligibility_rules._contains_preference(title):
            return True
    for sentence in eligibility_rules._sentences(text):
        if not any(term in sentence for term in terms):
            continue
        if eligibility_rules._explicitly_excludes(sentence, terms):
            continue
        if eligibility_rules._sentence_requires_group(sentence, terms):
            return True
    return False


# 於 evaluators package 初始化時安裝，讓所有既有 evaluator 共用相同作用域規則。
def install_production_rule_scope_guard() -> None:
    setattr(
        eligibility_rules,
        "_term_is_required",
        _term_is_required_with_exclusion_scope,
    )
