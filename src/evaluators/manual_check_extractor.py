# -*- coding: utf-8 -*-

import re

_MANUAL_REASON_MARKERS = (
    "學業平均",
    "平均成績",
    "學業成績",
    "操行成績",
    "操行",
    "班級排名",
    "班排名",
    "系排名",
    "學業排名",
    "排名",
    "GPA",
    "不及格",
    "需準備：",
)

_SCORE_LABELS = (
    "學業平均",
    "平均成績",
    "學業成績",
    "操行成績",
    "操行",
)

_PREPARATION_ACTION = (
    r"(?:提出|撰寫|繳交|檢附|提交|上傳|填寫|製作|準備|參加|接受|完成)"
)
_PREPARATION_OBJECT = (
    r"(?:自學計畫(?:書)?|研究計畫(?:書)?|提案(?:書)?|"
    r"(?:學習|生涯|服務|執行|專題|築夢)?計畫書|"
    r"申請書|申請表|推薦函|推薦書|作品集|簡報|面試|口試)"
)


def extract_manual_checks(text: str) -> tuple[str, ...]:
    """抽取人工核對門檻與申請後續準備事項。"""

    normalized = " ".join(text.split())
    checks: list[str] = []
    checks.extend(_score_checks(normalized))
    checks.extend(_gpa_checks(normalized))
    checks.extend(_rank_checks(normalized))
    checks.extend(_failed_course_checks(normalized))
    checks.extend(_preparation_checks(normalized))
    return tuple(dict.fromkeys(checks))


def is_manual_reason(reason: str) -> bool:
    """判斷理由是否只屬人工核對或可於申請後準備的文件／程序。"""

    normalized = " ".join(reason.split())
    return any(marker in normalized for marker in _MANUAL_REASON_MARKERS) or bool(
        _preparation_checks(normalized)
    )


def _score_checks(text: str) -> list[str]:
    label_pattern = "|".join(re.escape(label) for label in _SCORE_LABELS)
    score = r"(?P<score>\d{1,3}(?:\.\d+)?)"
    patterns = (
        rf"(?P<label>{label_pattern}).{{0,16}}?{score}\s*分?\s*(?:以上|或以上)",
        rf"(?P<label>{label_pattern}).{{0,16}}?(?:不得低於|至少|須達|需達|達)\s*{score}\s*分?",
    )
    checks: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            label = _display_score_label(match.group("label"))
            value = match.group("score")
            checks.append(f"請自行確認：{label}須達 {value} 分門檻。")
    return checks


def _display_score_label(label: str) -> str:
    if label in {"學業平均", "平均成績", "學業成績"}:
        return "學業平均成績"
    if label == "操行":
        return "操行成績"
    return label


def _gpa_checks(text: str) -> list[str]:
    checks: list[str] = []
    patterns = (
        r"GPA.{0,16}?(\d(?:\.\d+)?)\s*(?:以上|或以上)",
        r"GPA.{0,16}?(?:不得低於|至少|須達|需達|達)\s*(\d(?:\.\d+)?)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            checks.append(f"請自行確認：GPA 須達 {match.group(1)} 門檻。")
    return checks


def _rank_checks(text: str) -> list[str]:
    label = r"(?:班級排名|班排名|系排名|學業排名|成績排名)"
    checks: list[str] = []
    for match in re.finditer(
        rf"(?P<label>{label}).{{0,16}}?前\s*(?P<value>\d+(?:\.\d+)?)\s*%",
        text,
    ):
        checks.append(
            f"請自行確認：{match.group('label')}須為前 {match.group('value')}%。"
        )
    for match in re.finditer(
        rf"(?P<label>{label}).{{0,16}}?前\s*(?P<value>\d+)\s*名",
        text,
    ):
        checks.append(
            f"請自行確認：{match.group('label')}須為前 {match.group('value')} 名。"
        )
    return checks


def _failed_course_checks(text: str) -> list[str]:
    patterns = (
        r"(?:不得|不可|無|未曾).{0,8}(?:不及格科目|學科不及格|科目不及格)",
        r"(?:各科|所有科目).{0,8}(?:均須及格|不得不及格)",
    )
    if any(re.search(pattern, text) for pattern in patterns):
        return ["請自行確認：是否符合公告的無不及格科目條件。"]
    return []


def _preparation_checks(text: str) -> list[str]:
    """辨識可在申請階段完成的文件或程序，不把它當既有身分門檻。"""

    checks: list[str] = []
    patterns = (
        rf"{_PREPARATION_ACTION}.{{0,24}}?(?P<object>{_PREPARATION_OBJECT})",
        rf"(?P<object>{_PREPARATION_OBJECT}).{{0,16}}?(?:須|需|必須).{{0,8}}?{_PREPARATION_ACTION}",
    )
    for sentence in re.split(r"[。；;\n]", text):
        normalized = sentence.strip()
        if not normalized:
            continue
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match is None:
                continue
            item = match.group("object")
            checks.append(f"需準備：{item}（屬申請準備，不影響硬性資格判定）。")
            break
    return checks
