"""review 數值二次校驗 — 確定性一致性檢查（F9-1a，offline）。

為什麼存在
==========
eduStudio 最大的差異化是 **review gate（硬規則 #1，AI 答錯不流出）**。但 reviewer 是
「肉眼逐題看」——一份期中考十幾題、每題好幾個計算步驟,很容易漏看一個「50000 / 500 算成
1000」的低級錯誤。這支把**可疑點自動標出來**輔助 reviewer 的注意力,等於把核心賣點做深。

設計見 [docs/REVIEW_ASSIST_RFC.md](../docs/REVIEW_ASSIST_RFC.md)。本檔是 **F9-1a：純函式
確定性檢查**,只做兩個最高價值的形式校驗:

1. **算術校驗**（`arithmetic`）: 把 `display` 裡形如 `... = <expr> = <number> <unit>` 的
   等式鏈抽出來,用 **`ast` 白名單安全求值**（不是 `eval`,只允許 `+ - * / ** ()` 與數字）
   算各段,等號兩側對不上 → 標 `arithmetic`（severity=warn）。
2. **結果數字 ↔ narration 對齊**（`narration_mismatch`）: 把 `display` 的**結果數字**
   （最右側的數值）與 `narration` 唸出來的數字比對,結果沒在旁白出現 → 標
   `narration_mismatch`（severity=info,較軟的提示）。對應 RFC 問題 #4「答案與步驟對不上」。

**不可妥協紀律（呼應 RFC）**:
- **只標記、不自動改**: 產出是 `ReviewFlag` annotation,不碰 deck 內容本身（硬規則 #1）。
- **不阻擋 review**: 任何 step 校驗丟例外 → fail-open 當作「該 step 沒可疑點」,不讓校驗器
  壞掉就卡住整個 review(設計目標 #4)。
- **高精度、低誤報**: 寧可漏報也別狼來了(設計目標 #1)——只在**確定性**對不上時才標,
  混入符號/函式/逗號分隔等不能安全求值的段一律跳過(不亂猜)。
- **offline-first**: 純函式,零 API、零 IO、可重現、好測(fixture deck in → flags out)。

**不在這刀**(後續 slice / GATE,見 RFC 拆解表):
- 單位/量綱 + 符號一致性檢查 = F9-1b(offline,待依賴抉擇)。
- 接進 pipeline 落 `review_flags.json` + 端點 = F9-1c(offline)。
- 前端 ⚠ 標記 = F9-1d(offline)。
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


def _check_arithmetic(
    problem_id: str, step_index: int, display: str, rel_tol: float
) -> list[ReviewFlag]:
    """等號鏈各段數值要一致;對不上 → 一個 arithmetic flag(每 step 至多一個,免洗版)。"""
    if "=" not in display:
        return []
    evaluable: list[tuple[str, float]] = []
    for seg in display.split("="):
        val = _segment_value(seg)
        if val is not None:
            evaluable.append((seg.strip(), val))
    if len(evaluable) < 2:
        return []  # 沒有可比對的兩段數值(例 "σ = P / A" 或逗號分隔賦值)→ 不標
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
                flags.extend(
                    _check_narration_numbers(pid, s_idx, display, narration, rel_tol)
                )
            except Exception:  # noqa: BLE001 — fail-open
                pass
    return flags
