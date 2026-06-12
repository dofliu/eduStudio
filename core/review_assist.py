"""review 數值二次校驗 — 確定性一致性檢查（F9-1a，offline）。

為什麼存在
==========
eduStudio 最大的差異化是 **review gate（硬規則 #1，AI 答錯不流出）**。但 reviewer 是
「肉眼逐題看」——一份期中考十幾題、每題好幾個計算步驟,很容易漏看一個「50000 / 500 算成
1000」的低級錯誤。這支把**可疑點自動標出來**輔助 reviewer 的注意力,等於把核心賣點做深。

設計見 [docs/REVIEW_ASSIST_RFC.md](../docs/REVIEW_ASSIST_RFC.md)。本檔做三個確定性形式校驗:

1. **算術校驗**（`arithmetic`，F9-1a）: 把 `display` 裡形如 `... = <expr> = <number> <unit>`
   的等式鏈抽出來,用 **`ast` 白名單安全求值**（不是 `eval`,只允許 `+ - * / ** ()` 與數字）
   算各段,等號兩側對不上 → 標 `arithmetic`（severity=warn）。
2. **結果數字 ↔ narration 對齊**（`narration_mismatch`，F9-1a）: 把 `display` 的**結果數字**
   （最右側的數值）與 `narration` 唸出來的數字比對,結果沒在旁白出現 → 標
   `narration_mismatch`（severity=info,較軟的提示）。對應 RFC 問題 #4「答案與步驟對不上」。
3. **單位/量綱換算校驗**（`unit`，F9-1b）: 等式鏈裡兩段以上帶**可辨識單位**時,用**零依賴
   的白名單換算表**（RFC 開放問題 #2 建議的「先白名單」,不引入 `pint`）比對兩側的物理量值
   ——同量綱但換算對不上（`50 kN = 50 N`,算術校驗剝單位後看不出來）或等號兩側量綱根本不同
   → 標 `unit`（severity=warn）。對應 RFC 問題 #2。**只認白名單內的單位**（力/應力/長度/面積/
   體積/質量/能量/功率/時間/頻率的常見 SI 前綴）,不認得的單位一律跳過（高精度、不亂猜）。

**不可妥協紀律（呼應 RFC）**:
- **只標記、不自動改**: 產出是 `ReviewFlag` annotation,不碰 deck 內容本身（硬規則 #1）。
- **不阻擋 review**: 任何 step 校驗丟例外 → fail-open 當作「該 step 沒可疑點」,不讓校驗器
  壞掉就卡住整個 review(設計目標 #4)。
- **高精度、低誤報**: 寧可漏報也別狼來了(設計目標 #1)——只在**確定性**對不上時才標,
  混入符號/函式/逗號分隔等不能安全求值的段一律跳過(不亂猜)。
- **offline-first**: 純函式,零 API、零 IO、可重現、好測(fixture deck in → flags out)。

**不在這刀**(後續 slice / GATE,見 RFC 拆解表):
- **符號一致性檢查**(F9-1b 其餘):「同一量用兩種符號 / 只出現一次的疑似錯字」誤報率高、
  與設計目標 #1「高精度低誤報」相衝,留作後續 offline slice 另評估,本刀只做可確定性算的
  單位換算。接 pipeline(F9-1c)/前端 ⚠ 標記(F9-1d)已落地。
- 二次模型 pass(`model_disagree`)= F9-1e 骨架 / F9-1f 實測(GATE,需開額度)。
"""
from __future__ import annotations

import ast
import operator
import re

from pydantic import BaseModel, field_validator

# 校驗種類 / 嚴重度 / 來源的合法值(type guard：寫入當下擋拼錯)。
# 含後續 slice 才產的 kind(unit/symbol/model_disagree)與 source(second_model),
# 先收進合法集合,避免 F9-1b/e 落地時再回頭改 schema。
FLAG_KINDS = frozenset(
    {"arithmetic", "unit", "symbol", "narration_mismatch", "model_disagree"}
)
FLAG_SEVERITIES = frozenset({"info", "warn"})
FLAG_SOURCES = frozenset({"deterministic", "second_model"})

# 算術比對的預設相對容差(RFC 開放問題 #5)。AI 的低級錯通常差一個數量級(100→1000),
# 真正要躲的是「四捨五入」造成的假陽性:取到 2 位有效數字約差 0.5%,故 1% 容差足以放過
# 合理捨入、又能抓出 10x 級的真錯。可由 caller 覆寫,日後依 reviewer 回饋調。
DEFAULT_REL_TOL = 0.01

__all__ = [
    "ReviewFlag",
    "FLAG_KINDS",
    "FLAG_SEVERITIES",
    "FLAG_SOURCES",
    "DEFAULT_REL_TOL",
    "check_deck",
]


class ReviewFlag(BaseModel):
    """一個 reviewer 該注意的可疑點(只提醒、不阻擋、不自動改)。"""

    problem_id: str  # 對應 problems[].id
    step_index: int  # steps[] 索引(-1 = 題級)
    kind: str  # FLAG_KINDS 之一
    severity: str  # info | warn(不做 error——不阻擋,只提醒)
    message: str  # 給 reviewer 看的人話
    source: str = "deterministic"  # deterministic | second_model

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v: str) -> str:
        if v not in FLAG_KINDS:
            raise ValueError(f"未知 ReviewFlag kind: {v!r}")
        return v

    @field_validator("severity")
    @classmethod
    def _known_severity(cls, v: str) -> str:
        if v not in FLAG_SEVERITIES:
            raise ValueError(f"未知 ReviewFlag severity: {v!r}")
        return v

    @field_validator("source")
    @classmethod
    def _known_source(cls, v: str) -> str:
        if v not in FLAG_SOURCES:
            raise ValueError(f"未知 ReviewFlag source: {v!r}")
        return v


# ---------- 安全數值求值(ast 白名單,非 eval) ----------
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node: ast.AST) -> float:
    """遞迴求值單一 ast 節點,只放行數字與四則 / 次方,其餘一律拒。"""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("非數值常數")
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        if isinstance(node.op, ast.Pow):
            # 擋 2**99999 這類炸 CPU/記憶體的次方(這裡只是考卷算式,指數很小)。
            exp = _eval_node(node.right)
            if abs(exp) > 100:
                raise ValueError("指數過大")
            return _BIN_OPS[ast.Pow](_eval_node(node.left), exp)
        return _BIN_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError("不允許的運算節點")


def _safe_eval(expr: str) -> float | None:
    """安全求一個純數值算式;不是可安全求值的數值算式 → None(交給 caller 跳過)。"""
    expr = expr.strip()
    if not expr or not any(ch.isdigit() for ch in expr):
        return None
    try:
        tree = ast.parse(expr, mode="eval")
        return _eval_node(tree.body)
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None


# Unicode 數學符號 → Python 算符,讓 ast 看得懂黑板寫法(× ÷ ^ 與真減號)。
_OP_NORMALIZE = str.maketrans({"×": "*", "·": "*", "÷": "/", "^": "*", "−": "-"})
# `^` 其實是次方,單一字元 translate 無法產 `**`,故先單獨處理。
def _normalize_math(text: str) -> str:
    return text.replace("^", "**").translate(_OP_NORMALIZE)


# 抽段尾單位:結尾一串以(ASCII/希臘 µΩ)字母起頭的單位 token(MPa / GPa / mm² / N / rad/s …)。
# 不吃數字,故 e-notation(1.5e3)與純數字結尾不會被誤砍。
_TRAILING_UNIT_RE = re.compile(
    r"\s*[°%‰]?\s*[A-Za-zµΩ][A-Za-zµΩ²³·/°%‰]*\s*$"
)


def _segment_value(seg: str) -> float | None:
    """把等式鏈的一段(例 " 50000 / 500 " 或 " 100 MPa ")求成數值;不能安全求值 → None。"""
    s = _normalize_math(seg).strip().strip(",，;；").strip()
    if not s:
        return None
    # 砍掉段尾單位後再求值;符號(σ)、函式(cos)、變數(F1)、逗號分隔等留在式子裡會
    # 讓 _safe_eval 解析失敗回 None ＝ 自動跳過(高精度:不確定就不標)。
    m = _TRAILING_UNIT_RE.search(s)
    expr = s[: m.start()] if m else s
    return _safe_eval(expr)


# ---------- 單位/量綱白名單換算表(零依賴,F9-1b) ----------
# RFC 開放問題 #2 拍板:先用白名單常見換算表(覆蓋材力/自控常見單位),不引入 pint。
# 每個量綱 → (人讀名, 基準單位顯示, {單位: 對基準的換算倍率})。
# 只放**無歧義**的單位:溫度(°C/K 有偏移、非純倍率)、角度(rad/° 走 π)刻意不收。
_DIMENSIONS: dict[str, tuple[str, str, dict[str, float]]] = {
    "length": ("長度", "m", {"km": 1e3, "m": 1.0, "cm": 1e-2, "mm": 1e-3, "um": 1e-6, "nm": 1e-9}),
    "area": ("面積", "m2", {"km2": 1e6, "m2": 1.0, "cm2": 1e-4, "mm2": 1e-6}),
    "volume": ("體積", "m3", {"m3": 1.0, "cm3": 1e-6, "mm3": 1e-9, "L": 1e-3, "mL": 1e-6}),
    "mass": ("質量", "kg", {"t": 1e3, "kg": 1.0, "g": 1e-3, "mg": 1e-6}),
    "force": ("力", "N", {"MN": 1e6, "kN": 1e3, "N": 1.0, "mN": 1e-3}),
    "pressure": ("應力/壓力", "Pa", {"GPa": 1e9, "MPa": 1e6, "kPa": 1e3, "Pa": 1.0}),
    "energy": ("能量", "J", {"MJ": 1e6, "kJ": 1e3, "J": 1.0, "mJ": 1e-3}),
    "power": ("功率", "W", {"MW": 1e6, "kW": 1e3, "W": 1.0, "mW": 1e-3}),
    "time": ("時間", "s", {"h": 3600.0, "min": 60.0, "s": 1.0, "ms": 1e-3, "us": 1e-6}),
    "frequency": ("頻率", "Hz", {"GHz": 1e9, "MHz": 1e6, "kHz": 1e3, "Hz": 1.0}),
}
_DIM_LABEL = {k: v[0] for k, v in _DIMENSIONS.items()}
_DIM_BASE = {k: v[1] for k, v in _DIMENSIONS.items()}


def _normalize_unit(u: str) -> str:
    """單位字串正規化:µ/μ → u、上標 ²³ → 2/3,去頭尾標點空白,以便查白名單。"""
    u = u.strip().strip(",，;；").strip()
    u = u.replace("µ", "u").replace("μ", "u")
    return u.replace("²", "2").replace("³", "3")


# 白名單:正規化單位 → (量綱, 對基準倍率)。同名跨量綱不存在(已人工確認無碰撞)。
_UNIT_TABLE: dict[str, tuple[str, float]] = {
    _normalize_unit(u): (dim, factor)
    for dim, (_label, _base, units) in _DIMENSIONS.items()
    for u, factor in units.items()
}


def _trailing_unit(seg: str) -> str | None:
    """抽一段(等式鏈的一格)結尾的單位 token;沒有 → None。用原字串(不過 math 正規化)。"""
    s = seg.strip().strip(",，;；").strip()
    m = _TRAILING_UNIT_RE.search(s)
    if not m:
        return None
    return _normalize_unit(s[m.start():])


def _check_arithmetic(
    problem_id: str, step_index: int, display: str, rel_tol: float
) -> list[ReviewFlag]:
    """等號鏈各段數值要一致;對不上 → 一個 arithmetic flag(每 step 至多一個,免洗版)。"""
    if "=" not in display:
        return []
    evaluable: list[tuple[str, float]] = []
    seen_units: set[str] = set()
    for seg in display.split("="):
        val = _segment_value(seg)
        if val is not None:
            evaluable.append((seg.strip(), val))
            u = _trailing_unit(seg)
            if u:
                seen_units.add(u)
    if len(evaluable) < 2:
        return []  # 沒有可比對的兩段數值(例 "σ = P / A" 或逗號分隔賦值)→ 不標
    if len(seen_units) > 1:
        # 跨不同單位的等式鏈(如 "1 m = 100 cm"):剝單位後的純數值比對不成立,不是算術錯。
        # 交給 _check_units 做量綱/換算校驗,這裡不亂標(高精度、避免假陽性)。
        return []
    base_raw, base_val = evaluable[0]
    for raw, val in evaluable[1:]:
        scale = max(abs(base_val), abs(val), 1e-9)
        if abs(base_val - val) > rel_tol * scale:
            return [
                ReviewFlag(
                    problem_id=problem_id,
                    step_index=step_index,
                    kind="arithmetic",
                    severity="warn",
                    message=(
                        f"等號兩側數值對不上:「{base_raw}」≈ {_fmt(base_val)},"
                        f"但「{raw}」≈ {_fmt(val)}。"
                    ),
                )
            ]
    return []


def _check_units(
    problem_id: str, step_index: int, display: str, rel_tol: float
) -> list[ReviewFlag]:
    """等式鏈兩段以上帶可辨識單位時,比對物理量值;換算/量綱對不上 → 一個 unit flag。

    只看**白名單內**的單位;不認得的單位(km/h、N·m…)一律跳過(高精度、不亂猜)。要求至少
    兩段帶**不同**單位字串才檢查——同一單位的純數值差異是 `_check_arithmetic` 的事,這裡專管
    「換算」(50 kN vs 50 N、1 m vs 100 cm)。
    """
    if "=" not in display:
        return []
    measured: list[tuple[str, str, float, str]] = []  # (raw, dim, magnitude, unit)
    for seg in display.split("="):
        val = _segment_value(seg)
        if val is None:
            continue
        unit = _trailing_unit(seg)
        if not unit:
            continue
        entry = _UNIT_TABLE.get(unit)
        if entry is None:
            continue  # 不認得的單位 → 跳過
        dim, factor = entry
        measured.append((seg.strip(), dim, val * factor, unit))
    if len(measured) < 2:
        return []
    if len({u for *_, u in measured}) < 2:
        return []  # 同一單位 → 換算無從錯,純數值由 _check_arithmetic 管
    base_raw, base_dim, base_mag, _ = measured[0]
    for raw, dim, mag, _ in measured[1:]:
        if dim != base_dim:
            return [
                ReviewFlag(
                    problem_id=problem_id,
                    step_index=step_index,
                    kind="unit",
                    severity="warn",
                    message=(
                        f"等號兩側單位量綱不一致:「{base_raw}」是{_DIM_LABEL[base_dim]},"
                        f"「{raw}」是{_DIM_LABEL[dim]}。"
                    ),
                )
            ]
        scale = max(abs(base_mag), abs(mag), 1e-9)
        if abs(base_mag - mag) > rel_tol * scale:
            base = _DIM_BASE[base_dim]
            return [
                ReviewFlag(
                    problem_id=problem_id,
                    step_index=step_index,
                    kind="unit",
                    severity="warn",
                    message=(
                        f"等號兩側單位換算對不上:「{base_raw}」≈ {_fmt(base_mag)} {base},"
                        f"但「{raw}」≈ {_fmt(mag)} {base}。"
                    ),
                )
            ]
    return []


# 抽阿拉伯數字(含千分逗號與小數)。希臘字母/中文數字不在此(narration 多用阿拉伯數字唸數值,
# prompt 也要求 display 結果數字在 narration 重述)。
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> list[float]:
    out: list[float] = []
    for tok in _NUMBER_RE.findall(text):
        try:
            out.append(float(tok.replace(",", "")))
        except ValueError:
            continue
    return out


def _check_narration_numbers(
    problem_id: str, step_index: int, display: str, narration: str, rel_tol: float
) -> list[ReviewFlag]:
    """display 的**結果數字**(最右側數值)要在 narration 唸到;沒唸到 → narration_mismatch。"""
    if not narration.strip():
        return []
    disp_nums = _numbers(display)
    if not disp_nums:
        return []
    result = disp_nums[-1]  # 最右側 = 該步的結論值(RFC 問題 #4:答案與步驟對不上)
    narr_nums = _numbers(narration)
    scale = max(abs(result), 1e-9)
    if any(abs(result - n) <= rel_tol * scale for n in narr_nums):
        return []
    return [
        ReviewFlag(
            problem_id=problem_id,
            step_index=step_index,
            kind="narration_mismatch",
            severity="info",
            message=(
                f"display 結果 {_fmt(result)} 未在 narration 中唸出,"
                f"請確認旁白與算式一致。"
            ),
        )
    ]


def _fmt(v: float) -> str:
    """數值轉人話:整數去掉 .0,其餘保留(避免訊息出現 100.0)。"""
    if v == int(v):
        return str(int(v))
    return f"{v:g}"


def check_deck(deck: dict, *, rel_tol: float = DEFAULT_REL_TOL) -> list[ReviewFlag]:
    """掃 exam deck(`problems[].steps[]`),回每個可疑點的 ReviewFlag(只標記、不阻擋)。

    每個 step 的兩項檢查各自 try/except ＝ **fail-open**:某一 step 的算式怪到讓校驗器
    丟例外,只是該 step 不出 flag,不會中斷整份掃描(設計目標 #4,不讓校驗器壞掉卡 review)。
    非 dict / 沒 problems 的輸入回空 list。
    """
    if not isinstance(deck, dict):
        return []
    flags: list[ReviewFlag] = []
    problems = deck.get("problems") or []
    if not isinstance(problems, list):
        return []
    for p_idx, prob in enumerate(problems):
        if not isinstance(prob, dict):
            continue
        pid = str(prob.get("id") or f"q{p_idx + 1}")
        steps = prob.get("steps") or []
        if not isinstance(steps, list):
            continue
        for s_idx, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            display = str(step.get("display") or "")
            narration = str(step.get("narration") or "")
            try:
                flags.extend(_check_arithmetic(pid, s_idx, display, rel_tol))
            except Exception:  # noqa: BLE001 — fail-open，校驗器壞掉不可卡 review
                pass
            try:
                flags.extend(_check_units(pid, s_idx, display, rel_tol))
            except Exception:  # noqa: BLE001 — fail-open
                pass
            try:
                flags.extend(
                    _check_narration_numbers(pid, s_idx, display, narration, rel_tol)
                )
            except Exception:  # noqa: BLE001 — fail-open
                pass
    return flags
