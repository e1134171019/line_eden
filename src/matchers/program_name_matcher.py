# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re
import unicodedata

from src.catalogs.tun_2025_program_catalog import ScholarshipProgramWatch

MATCHED = "matched"
AMBIGUOUS = "ambiguous"
NO_MATCH = "no_match"
_MATCH_THRESHOLD = 80
_MINIMUM_MARGIN = 15
_EXACT_ALIAS_SCORE = 100
_EQUIVALENT_ALIAS_SCORE = 95
_REQUIRED_SCORE = 60
_OPTIONAL_SCORE = 10
_ORGANIZER_SCOPE_SCORE = 15
_FORBIDDEN_PENALTY = 80

_EQUIVALENT_TERMS = (
    ("大專院校", "大專校院"),
    ("臺北", "台北"),
    ("獎助金", "獎助學金"),
    ("獎勵學金", "獎學金"),
)
_YEAR_PATTERNS = (
    re.compile(r"(?:19|20)\d{2}\s*年?"),
    re.compile(r"(?:民國\s*)?1\d{2}\s*年"),
    re.compile(r"第\s*[一二三四五六七八九十百零〇兩\d]+\s*屆"),
)
_GENERIC_PREFIXES = (
    "轉知",
    "公告",
    "申請公告",
    "開始受理",
    "開放申請",
    "獎學金公告",
)


@dataclass(frozen=True)
class ProgramRule:
    """方案名稱變動時仍應保持穩定的必要、加分與排除詞。"""

    required_terms: tuple[str, ...]
    optional_terms: tuple[str, ...] = tuple()
    forbidden_terms: tuple[str, ...] = tuple()


@dataclass(frozen=True)
class ProgramMatchResult:
    """方案競爭匹配結果，保留第一、第二名與命中證據。"""

    matched: bool
    method: str = "none"
    matched_alias: str = ""
    required_hits: tuple[str, ...] = tuple()
    optional_hits: tuple[str, ...] = tuple()
    score: int = 0
    status: str = NO_MATCH
    program_id: str = ""
    second_best_score: int = 0
    competing_program_id: str = ""
    forbidden_hits: tuple[str, ...] = tuple()


@dataclass(frozen=True)
class _ProgramScore:
    program_id: str
    method: str
    matched_alias: str
    required_hits: tuple[str, ...]
    optional_hits: tuple[str, ...]
    forbidden_hits: tuple[str, ...]
    score: int


# 38 項方案皆有受控 fallback；同主辦單位方案以 forbidden_terms 避免互相誤抓。
_PROGRAM_RULES: dict[str, ProgramRule] = {
    "tf4dr-aid": ProgramRule(("賑災", "助學"), ("基金會", "獎助學金")),
    "foxconn-scholarship-whale": ProgramRule(("獎學鯨",), ("鴻海", "教育基金會")),
    "avc-talented-student": ProgramRule(("資優學生",), ("奇鋐", "獎學金")),
    "cfh-graduate": ProgramRule(
        ("研究所",),
        ("鄭豐喜", "獎學金"),
        ("大學獎學金", "肢障", "家庭子女"),
    ),
    "cfh-university": ProgramRule(
        ("大學",),
        ("鄭豐喜", "獎學金"),
        ("研究所", "肢障", "家庭子女"),
    ),
    "kumota-flying": ProgramRule(("乘風飛揚",), ("雲田", "獎助學金")),
    "lijin-taoyuan": ProgramRule(("利晉", "清寒"), ("桃園", "助學金")),
    "tcb-foundation": ProgramRule(("台中商",), ("銀行", "文教基金會", "獎學金")),
    "tainan-kaiji": ProgramRule(("臺疆祖廟",), ("清寒", "優秀", "獎學金")),
    "songliang-aid": ProgramRule(("松樑",), ("助學金", "教育公益")),
    "wang-yun-wu-self-study": ProgramRule(("自學獎學金",), ("王雲五", "基金會")),
    "rehe-association": ProgramRule(("熱河同鄉會",), ("台北", "獎助學金")),
    "wisdomshare-service-learning": ProgramRule(
        ("青力親為",),
        ("千萬祝福", "服務學習", "獎勵計畫"),
    ),
    "hsinrong-emergency-aid": ProgramRule(("欣榮", "急難救助"), ("助學金",)),
    "it-social-care": ProgramRule(("資訊人", "社會關懷"), ("獎學金",)),
    "you-care-hand-in-hand": ProgramRule(("大手拉小手",), ("助學計畫", "普仁")),
    "chiu-filial-piety": ProgramRule(("清寒", "孝親"), ("績優", "獎助學金")),
    "buddha-charity-progress": ProgramRule(
        ("清寒學生", "進步"),
        ("誌善", "獎學金"),
    ),
    "yonglin-hope": ProgramRule(("銘日希望",), ("永齡", "獎助學金")),
    "cdf-vocational": ProgramRule(("技藝職能",), ("中華開發", "獎學金")),
    "ht-emergency": ProgramRule(
        ("急難濟助",),
        ("行天宮",),
        ("資優學生", "長期獎助學金", "行天宮助學金"),
    ),
    "ht-talented-long-term": ProgramRule(
        ("資優學生",),
        ("行天宮", "長期", "獎助學金"),
        ("急難濟助",),
    ),
    "ht-student-aid": ProgramRule(
        ("助學金",),
        ("行天宮",),
        ("資優學生", "急難濟助"),
    ),
    "cht-fang-hsien-chi": ProgramRule(("方賢齊",), ("中華電信", "獎學金")),
    "heart-child": ProgramRule(("心臟病童",), ("獎勵學金", "獎學金")),
    "sunshine-scholarship": ProgramRule(
        ("陽光", "獎學金"),
        ("獎助學金",),
        ("萬足",),
    ),
    "sunshine-wanzu": ProgramRule(
        ("萬足",),
        ("燒傷", "勞工子女", "大專生", "獎助學金"),
        ("陽光獎學金",),
    ),
    "cfh-disabled-family": ProgramRule(
        ("肢障", "家庭子女"),
        ("鄭豐喜", "獎學金"),
        ("研究所獎學金", "大學獎學金"),
    ),
    "lovepeace-disadvantaged": ProgramRule(
        ("祥和", "清寒"),
        ("優秀", "獎學金"),
    ),
    "dapeng-aid": ProgramRule(("大鵬",), ("科技慈善", "獎助學金")),
    "hndasset-wenxiang": ProgramRule(("文向獎學金",), ("教育基金會",)),
    "cy-arch-aid": ProgramRule(("昌益",), ("慈善基金會", "獎助學金")),
    "lihpao-fullon": ProgramRule(("麗寶", "福容"), ("獎助學金",)),
    "gfc-scholarship": ProgramRule(("崇友",), ("實業", "獎學金")),
    "auden-innovation-research": ProgramRule(
        ("創新", "研究"),
        ("耀登", "炳南", "研究獎"),
        ("大專校院優秀人才", "優秀人才獎學金"),
    ),
    "auden-university-talent": ProgramRule(
        ("大專", "優秀人才"),
        ("耀登", "炳南", "獎學金"),
        ("創新研究", "研究獎"),
    ),
    "harmony-stability": ProgramRule(("和諧安定",), ("獎學金",)),
    "taishin-youth-volunteer": ProgramRule(
        ("青少年志工", "菁英獎"),
        ("台新", "獎助學金"),
    ),
}


# 保留單一方案既有介面；不使用 organizer 直接增加分數。
def match_program(text: str, program: ScholarshipProgramWatch) -> ProgramMatchResult:
    scored = _score_program(text, program, organizer_confirmed=False)
    status = MATCHED if scored.score >= _MATCH_THRESHOLD else NO_MATCH
    return _result_from_score(scored, status, 0, "")


# 同一來源中的所有方案一起評分，避免主辦單位多方案互相誤抓。
def match_programs(
    text: str,
    programs: tuple[ScholarshipProgramWatch, ...],
) -> ProgramMatchResult:
    if not programs:
        return ProgramMatchResult(False)
    organizer_confirmed = _single_organizer_scope(programs)
    scores = sorted(
        (_score_program(text, item, organizer_confirmed) for item in programs),
        key=lambda item: (-item.score, item.program_id),
    )
    top = scores[0]
    second = scores[1] if len(scores) > 1 else None
    second_score = second.score if second else 0
    competing_id = second.program_id if second else ""
    if top.score < _MATCH_THRESHOLD:
        return _result_from_score(top, NO_MATCH, second_score, competing_id)
    if second and top.score - second.score < _MINIMUM_MARGIN:
        return _result_from_score(top, AMBIGUOUS, second_score, competing_id)
    return _result_from_score(top, MATCHED, second_score, competing_id)


# 將內部分數轉成公開結果。
def _result_from_score(
    scored: _ProgramScore,
    status: str,
    second_score: int,
    competing_id: str,
) -> ProgramMatchResult:
    return ProgramMatchResult(
        status == MATCHED,
        scored.method if status == MATCHED else status,
        scored.matched_alias,
        scored.required_hits,
        scored.optional_hits,
        scored.score,
        status,
        scored.program_id,
        second_score,
        competing_id,
        scored.forbidden_hits,
    )


# 計算單一方案的 alias、核心詞、來源範圍與排除詞分數。
def _score_program(
    text: str,
    program: ScholarshipProgramWatch,
    organizer_confirmed: bool,
) -> _ProgramScore:
    compact = _compact(text)
    normalized = _normalize_for_match(text)
    method, alias, base_score = _alias_score(compact, normalized, program.aliases)
    rule = _PROGRAM_RULES.get(program.program_id, ProgramRule(tuple()))
    required_hits = _hits(normalized, rule.required_terms)
    optional_hits = _hits(normalized, rule.optional_terms)
    forbidden_hits = _hits(normalized, rule.forbidden_terms)
    if not base_score and rule.required_terms and len(required_hits) == len(rule.required_terms):
        method = "core_terms"
        base_score = _REQUIRED_SCORE
    score = _weighted_score(
        base_score,
        optional_hits,
        forbidden_hits,
        organizer_confirmed,
    )
    return _ProgramScore(
        program.program_id,
        method,
        alias,
        required_hits,
        optional_hits,
        forbidden_hits,
        score,
    )


# exact alias 優先，其次使用受控等價詞 alias。
def _alias_score(
    compact: str,
    normalized: str,
    aliases: tuple[str, ...],
) -> tuple[str, str, int]:
    for alias in aliases:
        raw_alias = _compact(alias)
        if len(raw_alias) >= 4 and raw_alias in compact:
            return "exact_alias", alias, _EXACT_ALIAS_SCORE
    for alias in aliases:
        normalized_alias = _normalize_for_match(alias)
        if len(normalized_alias) >= 4 and normalized_alias in normalized:
            return "equivalent_alias", alias, _EQUIVALENT_ALIAS_SCORE
    return "none", "", 0


# 只有 alias 或所有 required terms 命中時才允許 organizer 與 optional 加分。
def _weighted_score(
    base_score: int,
    optional_hits: tuple[str, ...],
    forbidden_hits: tuple[str, ...],
    organizer_confirmed: bool,
) -> int:
    if not base_score:
        return 0
    score = base_score + len(optional_hits) * _OPTIONAL_SCORE
    if organizer_confirmed:
        score += _ORGANIZER_SCOPE_SCORE
    score -= len(forbidden_hits) * _FORBIDDEN_PENALTY
    return max(score, 0)


# 來源群組只有一個 organizer_id 時，視為已確認主辦單位範圍。
def _single_organizer_scope(programs: tuple[ScholarshipProgramWatch, ...]) -> bool:
    organizer_ids = {_organizer_id(item) for item in programs}
    return len(organizer_ids) == 1 and bool(next(iter(organizer_ids), ""))


# 新來源契約優先使用 organizer_id，舊測試資料退回主辦單位文字。
def _organizer_id(program: ScholarshipProgramWatch) -> str:
    value = getattr(program, "organizer_id", "")
    return str(value).strip() or _compact(program.organizer)


# 回傳正規化文字中實際命中的規則詞。
def _hits(normalized: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(term for term in terms if _normalize_for_match(term) in normalized)


# 只做 Unicode 與標點壓縮，供 exact alias 使用。
def _compact(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"[\W_]+", "", value)


# 移除年度、屆次與通用公告前綴，再套用受控等價詞。
def _normalize_for_match(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    for pattern in _YEAR_PATTERNS:
        value = pattern.sub("", value)
    for prefix in _GENERIC_PREFIXES:
        value = value.replace(prefix, "")
    for source, target in _EQUIVALENT_TERMS:
        value = value.replace(source, target)
    return re.sub(r"[\W_]+", "", value)
