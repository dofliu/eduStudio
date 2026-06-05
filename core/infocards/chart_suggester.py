"""圖表類型偵測／建議（從 infoCard services/chartTypeSuggester.ts 收編，Phase C presentation）。

純函式、可離線、零 API：從文字／表格自動偵測數列，建議 bar/line/pie，讓 chart_focus 版型
不必依賴 AI 猜測。chart_focus renderer 僅支援 bar/pie，line 收斂回 bar。

公開接點（presentation_service 用）：is_renderable_chart_data、build_chart_data_for_slide。
其餘 detect/suggest/to_chart_data 一併移植以維持保真與可測。
"""
from __future__ import annotations

import re

_NUM = r"-?\d[\d,]*(?:\.\d+)?"
# 整格皆為數值（表格儲存格用）
_NUM_CELL_RE = re.compile(rf"^{_NUM}\s*[%％]?$")
_LEADING_NUM_RE = re.compile(rf"^({_NUM})\s*([%％]?)")

# 時間序列標籤樣式（命中一半以上即視為時間軸）
_TIME_LABEL_RES = [
    re.compile(r"^(?:19|20)\d{2}\s*年?$"),          # 2020 / 2020年
    re.compile(r"^第?\s*[1-4一二三四]\s*季$"),       # 第1季 / 一季
    re.compile(r"^Q[1-4]$", re.IGNORECASE),          # Q1
    re.compile(r"^(?:0?[1-9]|1[0-2])\s*月$"),        # 3月 / 12月
    re.compile(r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", re.IGNORECASE),
    re.compile(r"^第\s*\d+\s*(?:週|周|天|日|期|年|月|季)$"),  # 第3週
    re.compile(r"^\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?$"),       # 2020-01 / 2020/1/5
]

_PERCENT_KEYWORD_RE = re.compile(r"佔比|占比|比例|百分比|構成|組成|比重|分布占|份額")
_LINE_KEYWORD_RE = re.compile(r"趨勢|成長|逐年|逐月|變化|走勢|歷年|年度|時間")
_BAR_KEYWORD_RE = re.compile(r"比較|排名|各|分布|分佈|數量|統計|數據|對比")

_SEP_RE = re.compile(r"^(.+?)\s*[:：=]\s*(.+)$")
_PCT_RE = re.compile(rf"^(.+?)\s+({_NUM})\s*[%％]")
_TIGHT_RE = re.compile(rf"^(.+?)\s+({_NUM})$")
_SPLIT_RE = re.compile(r"[、；;，]|,(?!\d)")  # 逗號只在「非數字前」才當分隔（保護千分位 1,234）
_TABLE_DIVIDER_RE = re.compile(r"^:?-{2,}:?$")

MAX_PIE_SLICES = 8


def _strip_commas(s: str) -> float:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return float("nan")


def _clean_label(raw: str) -> str:
    s = re.sub(r"^[\s|]+", "", raw)
    s = re.sub(r"[\s:：=\-–—~|]+$", "", s)
    s = re.sub(r"^[-*•・]\s+", "", s)
    return s.strip()


def _parse_leading_number(s: str):
    m = _LEADING_NUM_RE.match(s.strip())
    if not m:
        return None
    value = _strip_commas(m.group(1))
    if value != value or value in (float("inf"), float("-inf")):  # NaN/inf
        return None
    return {"value": value, "is_percent": m.group(2) in ("%", "％")}


def _parse_table(text: str) -> list[dict]:
    rows = [l for l in text.split("\n") if "|" in l]
    if len(rows) < 2:
        return []
    points: list[dict] = []
    for row in rows:
        cells = [c.strip() for c in row.split("|") if c.strip()]
        if cells and all(_TABLE_DIVIDER_RE.match(c) for c in cells):
            continue
        if len(cells) < 2:
            continue
        label = cells[0]
        value = None
        for c in cells[1:]:
            if _NUM_CELL_RE.match(c):
                value = _parse_leading_number(c)
                break
        if label and value:
            points.append({"label": label, "value": value["value"], "is_percent": value["is_percent"]})
    return points


def _parse_segment(seg: str):
    s = seg.strip()
    if not s:
        return None
    m = _SEP_RE.match(s)
    if m:
        label = _clean_label(m.group(1))
        n = _parse_leading_number(m.group(2))
        if label and n:
            return {"label": label, "value": n["value"], "is_percent": n["is_percent"]}
    m = _PCT_RE.match(s)
    if m:
        label = _clean_label(m.group(1))
        if label:
            return {"label": label, "value": _strip_commas(m.group(2)), "is_percent": True}
    m = _TIGHT_RE.match(s)
    if m:
        label = _clean_label(m.group(1))
        if label:
            return {"label": label, "value": _strip_commas(m.group(2)), "is_percent": False}
    return None


def _parse_lines(text: str) -> tuple[list[dict], str]:
    points: list[dict] = []
    inline = False
    for line in text.split("\n"):
        segs = _SPLIT_RE.split(line)
        line_hits = 0
        for seg in segs:
            p = _parse_segment(seg)
            if p:
                points.append(p)
                line_hits += 1
        if line_hits >= 2:
            inline = True
    return points, ("inline" if inline else "list")


def _is_time_label(label: str) -> bool:
    l = label.strip()
    return any(re.match(l) for re in _TIME_LABEL_RES)


def detect_data_series(text: str) -> dict | None:
    """偵測第一個有效數列（≥2 點）；偵測不到回 None。"""
    if not text or not text.strip():
        return None
    points = _parse_table(text)
    source = "table"
    if len(points) < 2:
        points, source = _parse_lines(text)
    if len(points) < 2:
        return None
    labels = [p["label"] for p in points]
    values = [p["value"] for p in points]
    time_count = sum(1 for l in labels if _is_time_label(l))
    is_time_series = time_count >= -(-len(labels) // 2)  # ceil(n/2)
    total = sum(values)
    sum_near_100 = len(values) >= 2 and 95 <= total <= 105
    is_percentage = any(p["is_percent"] for p in points) or sum_near_100 or bool(_PERCENT_KEYWORD_RE.search(text))
    return {"labels": labels, "values": values, "is_percentage": is_percentage,
            "is_time_series": is_time_series, "source": source}


def _keyword_fallback(text: str) -> dict:
    if _LINE_KEYWORD_RE.search(text):
        return {"type": "line", "series": None}
    if _PERCENT_KEYWORD_RE.search(text):
        return {"type": "pie", "series": None}
    return {"type": "bar", "series": None}


def suggest_chart_type(text: str) -> dict:
    """偵測數列並建議圖表類型；偵測不到也回弱建議（series=None）。"""
    series = detect_data_series(text)
    if not series:
        return _keyword_fallback(text)
    n = len(series["labels"])
    if series["is_time_series"]:
        return {"type": "line", "series": series}
    if series["is_percentage"] and 2 <= n <= MAX_PIE_SLICES:
        return {"type": "pie", "series": series}
    return {"type": "bar", "series": series}


def to_chart_data(suggestion: dict) -> dict | None:
    """建議 → Slide.chartData 形狀。line 收斂為 bar（renderer 限制）。無有效數列回 None。"""
    s = suggestion.get("series")
    if not s or len(s["values"]) < 2:
        return None
    ctype = "pie" if suggestion["type"] == "pie" else "bar"
    return {"labels": s["labels"], "values": s["values"], "type": ctype}


def is_renderable_chart_data(data) -> bool:
    """既有 chartData 是否已可被 chart_focus renderer 正確渲染（labels/values 等長且 ≥2）。"""
    if not data or not isinstance(data, dict):
        return False
    labels, values = data.get("labels"), data.get("values")
    if not isinstance(labels, list) or not isinstance(values, list):
        return False
    return len(labels) >= 2 and len(labels) == len(values)


def build_chart_data_for_slide(layout: str, text: str) -> dict | None:
    """為 chart_focus 投影片從文字偵測數列產出 chartData；非 chart_focus 或偵測不到回 None。"""
    if layout != "chart_focus":
        return None
    if not text or not text.strip():
        return None
    return to_chart_data(suggest_chart_type(text))
