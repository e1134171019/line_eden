# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re
import unicodedata

from src.catalogs.tun_2025_program_catalog import ScholarshipProgramWatch

_EQUIVALENT_TERMS = (
    ("大專院校", "大專校院"),
    ("臺北", "台北"),
    ("獎助金", "獎助學金"),
    ("獎勵學金", "獎學金"),
)

# 只有已確認不會跨方案混淆的核心詞才允許 fallback。
_PROGRAM_CORE_TERMS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "auden-university-talent": (("耀登", "炳南"), ("大專", "優秀人才", "獎學金")),
    "foxconn-scholarship-whale": (("鴻海", "獎學鯨"), ("教育基金會",)),
    "cfh-graduate": (("鄭豐喜", "研究所"), ("獎學金",)),
    "cfh-university": (("鄭豐喜", "大學"), ("獎學金",)),
    "cfh-disabled-family": (("鄭豐喜", "肢障"), ("家庭子女", "獎學金")),
    "ht-emergency": (("行天宮", "急難濟助"), tuple()),
    "ht-talented-long-term": (("行天宮", "資優學生"), ("長期", "獎助學金")),
    "ht-student-aid": (("行天宮", "助學金"), tuple()),
    "cht-fang-hsien-chi": (("方賢齊",), ("中華電信", "獎學金")),
    "heart-child": (("心臟病童",), ("獎勵學金", "獎學金")),
}


@dataclass(frozen=True)
class ProgramMatchResult:
    """方案匹配結果，保留命中方法、詞彙與分數供 audit。"""

    matched: bool
    method: str = "none"
    matched_alias: str = ""
    required_hits: tuple[str, ...] = tuple()
    optional_hits: tuple[str, ...] = tuple()
    score: int = 0


def match_program(text: str, program: ScholarshipProgramWatch) -> ProgramMatchResult:
    """依原始 alias、等價詞 alias、受控核心詞順序比對方案。"""

    compact = _compact(text)
    for alias in program.aliases:
        raw_alias = _compact(alias)
        if len(raw_alias) >= 4 and raw_alias in compact:
            return ProgramMatchResult(True, "exact_alias", alias, score=100)

    normalized = _normalize(text)
    for alias in program.aliases:
        normalized_alias = _normalize(alias)
        if len(normalized_alias) >= 4 and normalized_alias in normalized:
            return ProgramMatchResult(True, "equivalent_alias", alias, score=95)

    terms = _PROGRAM_CORE_TERMS.get(program.program_id)
    if terms is None:
        return ProgramMatchResult(False)
    required, optional = terms
    required_hits = tuple(term for term in required if _normalize(term) in normalized)
    optional_hits = tuple(term for term in optional if _normalize(term) in normalized)
    optional_minimum = 0 if not optional else min(2, len(optional))
    matched = len(required_hits) == len(required) and len(optional_hits) >= optional_minimum
    return ProgramMatchResult(
        matched,
        "core_terms" if matched else "none",
        required_hits=required_hits,
        optional_hits=optional_hits,
        score=80 if matched else 0,
    )


def _compact(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"[\W_]+", "", value)


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    for source, target in _EQUIVALENT_TERMS:
        value = value.replace(source, target)
    return re.sub(r"[\W_]+", "", value)
