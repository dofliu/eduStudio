#!/usr/bin/env python3
"""measure_narration_truncation.py — N1 真實 baseline 測量 (offline-first).

掃 jobs/*/deck.json (+ OUTPUT_DIR 既有 deck.json), 對每個
(length_mode, narration_style) 組合算兩層統計:

  1. slide-level over-budget ratio — narration 字數超出 length_mode preset
     上限 (`narration_chars_range` 高值) 的 slide 比例. 復用
     `core.narration_validator`.
  2. per-cue 過長句統計 — narration 按 `core.srt.narration_to_cues` 切成 cue
     (跟 build_srt 同一條) 後, 單一 cue 超出字幕帶可容字數的比例.

純離線, 不打 Gemini / GCP TTS, 只讀既有 deck.json.

為什麼分兩層:
  真實「截斷」發生在字幕帶視覺層, 不是 slide narration 本身. `build_srt`
  (core/srt.py) 按標點把 narration 切成 cue, 各 cue 按字數比例分時長. N3
  治本上線後, build_srt 用 `narration_to_cues` 在 per-cue 上限
  (SUBTITLE_CUE_CHAR_BUDGET) 把過長句再切, 避免在 ffmpeg subtitles filter
  (FontSize=22, 1080p, MarginV=40, 見 pipeline._build_hardsub_cmd) wrap 成多行
  頂出 180px 字幕帶 (core.visuals.SUBTITLE_BAND_HEIGHT). 這支工具 (N3-verify
  起) 復用同一條 `narration_to_cues`, 量到的 over-cue = 修後仍超出上限的殘留
  (理想 0).

per-cue 字數上限 (DEFAULT_CUE_CHAR_BUDGET) 直接綁 core.srt.SUBTITLE_CUE_CHAR_BUDGET
(N3 定案值), 兩邊同一常數不漂移. 仍同時輸出多 threshold 的 cue 長度分布看切分後
散布. `--cue-budget 0` 可關閉過長句切分, 量「修前」對照.

使用:
    python tools/measure_narration_truncation.py
    python tools/measure_narration_truncation.py --out docs/narration-truncation-report.md
    python tools/measure_narration_truncation.py --cue-budget 40 --jobs-dir jobs --quiet
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 本檔在 tools/ 底下, 加 parent 到 sys.path 才能 import 上層模組
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.length_mode import preset  # noqa: E402
from core.narration_validator import (  # noqa: E402
    _parse_range_high,
    validate_slide_narration,
)
from core.srt import SUBTITLE_CUE_CHAR_BUDGET, narration_to_cues  # noqa: E402


# per-cue 字數上限 — 直接綁 core.srt.SUBTITLE_CUE_CHAR_BUDGET (N3 治本上線後
# build_srt 真的會在此上限切 cue). 兩邊同一個常數, 改一處兩邊一起動不漂移.
DEFAULT_CUE_CHAR_BUDGET = SUBTITLE_CUE_CHAR_BUDGET

# cue 長度分布 threshold — 讓 N3 / 用戶有資料挑 per-cue 上限
CUE_DISTRIBUTION_THRESHOLDS = (20, 30, 40, 50, 60, 80)

# N2 eval fixture 預設路徑 (匿名化的代表性 deck, CI 可重現截斷率測量)
DEFAULT_FIXTURES_PATH = "tests/fixtures/narration/decks.json"

# 沒在 state.json 標 length_mode / narration_style 時的預設 (對齊 preset() 與
# JobOptions schema 的隱含預設, 否則 group 標籤跟實際渲染行為對不上)
DEFAULT_LENGTH_MODE = "quick"
DEFAULT_NARRATION_STYLE = "storyteller"

# worst-cue 報告擷取上限 (避免把整段 narration 灌進 markdown)
_CUE_EXCERPT_CHARS = 50


# --------------------------------------------------------------------------- #
# 純函式 (無 IO) — 可單元測試
# --------------------------------------------------------------------------- #

def split_cues(
    narration: str | None,
    *,
    max_cue_chars: int = DEFAULT_CUE_CHAR_BUDGET,
) -> list[str]:
    """把 narration 切成 SRT cue, 直接走 core.srt.narration_to_cues.

    N3 治本上線後 build_srt 用 narration_to_cues 做字幕帶切分 (終止標點切句 →
    過長句次級標點再切). 本工具復用同一條 function 確保「截斷率測量」跟「字幕
    實際呈現」逐字對齊 — 量到的就是修後真實 cue.

    max_cue_chars <= 0 關閉過長句切分 (回退成只按終止標點切句 = 修前行為),
    方便對照「修前 vs 修後」.
    """
    return narration_to_cues(narration, max_cue_chars=max_cue_chars)


def resolve_length_mode(options: dict | None) -> str:
    """從 job options 取 length_mode, 空 / None → 預設 (對齊 preset() 行為)."""
    return ((options or {}).get("length_mode")) or DEFAULT_LENGTH_MODE


def resolve_narration_style(options: dict | None) -> str:
    """從 job options 取 narration_style, 空 / None → 預設 (對齊 schema 行為)."""
    return ((options or {}).get("narration_style")) or DEFAULT_NARRATION_STYLE


def measure_deck(
    deck: dict,
    *,
    length_mode: str | None,
    cue_budget: int = DEFAULT_CUE_CHAR_BUDGET,
) -> dict:
    """單一 deck 的 narration 統計 (slide-level + per-cue). 純函式, 無 IO.

    支援兩種 schema (sections/slides 與 v1 problems/steps), 跟
    narration_validator 一致. 跳過 `_` 開頭的 cover/outro section (narration
    是模板, 不受 length_mode 限制).

    回 dict:
        max_chars: int            slide narration preset 上限
        cue_budget: int           per-cue 上限 (本次測量用)
        total_slides / over_slide_count
        total_cues / over_cue_count
        worst_slide / worst_cue   (None 若空)
        slides / cues             逐筆明細 (供 aggregate 用)
    """
    max_chars = _parse_range_high(preset(length_mode).get("narration_chars_range"))

    slides_out: list[dict] = []
    cues_out: list[dict] = []
    sections = deck.get("sections") or deck.get("problems") or []
    for sec_idx, sec in enumerate(sections):
        sec_id = str(sec.get("id") or f"sec{sec_idx + 1}")
        if sec_id.startswith("_"):  # cover / outro, narration 是模板
            continue
        items = sec.get("slides") or sec.get("steps") or []
        for slide_idx, sl in enumerate(items):
            slide_id = str(sl.get("id") or f"{sec_id}_{slide_idx + 1}")
            narration = sl.get("narration")

            stat = validate_slide_narration(narration, max_chars)
            stat["slide_id"] = slide_id
            stat["section_id"] = sec_id
            slides_out.append(stat)

            for cue_idx, cue in enumerate(split_cues(narration, max_cue_chars=cue_budget)):
                cues_out.append({
                    "section_id": sec_id,
                    "slide_id": slide_id,
                    "cue_index": cue_idx,
                    "length": len(cue),
                    "over": len(cue) > cue_budget,
                    "text": cue,
                })

    over_slides = [s for s in slides_out if s["over"]]
    over_cues = [c for c in cues_out if c["over"]]
    return {
        "max_chars": max_chars,
        "cue_budget": cue_budget,
        "total_slides": len(slides_out),
        "over_slide_count": len(over_slides),
        "total_cues": len(cues_out),
        "over_cue_count": len(over_cues),
        "worst_slide": max(over_slides, key=lambda s: s["excess"], default=None),
        "worst_cue": max(cues_out, key=lambda c: c["length"], default=None),
        "slides": slides_out,
        "cues": cues_out,
    }


def cue_length_distribution(
    lengths: list[int],
    thresholds: tuple[int, ...] = CUE_DISTRIBUTION_THRESHOLDS,
) -> list[dict]:
    """算 cue 長度分布: 每個 threshold 有幾個 cue 超過 + 佔比.

    回 list (跟 thresholds 同序), 每筆 {threshold, count, ratio}.
    """
    total = len(lengths)
    out = []
    for th in thresholds:
        cnt = sum(1 for n in lengths if n > th)
        out.append({
            "threshold": th,
            "count": cnt,
            "ratio": round(cnt / total, 4) if total else 0.0,
        })
    return out


def aggregate(records: list[dict]) -> dict:
    """把多個 deck record 依 (length_mode, narration_style) 分組彙整.

    record = {length_mode, narration_style, source, measure}, measure 是
    measure_deck() 回傳值.

    回 dict:
        groups: list[dict]    每組統計 (依 key 排序)
        overall: dict         全部加總
    """
    groups: dict[tuple[str, str], dict] = {}
    for rec in records:
        key = (rec["length_mode"], rec["narration_style"])
        g = groups.get(key)
        if g is None:
            g = {
                "length_mode": rec["length_mode"],
                "narration_style": rec["narration_style"],
                "deck_count": 0,
                "total_slides": 0,
                "over_slide_count": 0,
                "total_cues": 0,
                "over_cue_count": 0,
                "max_chars": rec["measure"]["max_chars"],
                "cue_lengths": [],
                "worst_cue": None,
            }
            groups[key] = g
        m = rec["measure"]
        g["deck_count"] += 1
        g["total_slides"] += m["total_slides"]
        g["over_slide_count"] += m["over_slide_count"]
        g["total_cues"] += m["total_cues"]
        g["over_cue_count"] += m["over_cue_count"]
        g["cue_lengths"].extend(c["length"] for c in m["cues"])
        wc = m["worst_cue"]
        if wc and (g["worst_cue"] is None or wc["length"] > g["worst_cue"]["length"]):
            g["worst_cue"] = {**wc, "_source": rec["source"]}

    group_list = []
    overall_lengths: list[int] = []
    o_slides = o_over_slides = o_cues = o_over_cues = o_decks = 0
    o_worst_cue = None
    for key in sorted(groups):
        g = groups[key]
        lengths = g["cue_lengths"]
        group_list.append({
            "length_mode": g["length_mode"],
            "narration_style": g["narration_style"],
            "max_chars": g["max_chars"],
            "deck_count": g["deck_count"],
            "total_slides": g["total_slides"],
            "over_slide_count": g["over_slide_count"],
            "over_slide_ratio": round(g["over_slide_count"] / g["total_slides"], 4)
                                if g["total_slides"] else 0.0,
            "total_cues": g["total_cues"],
            "over_cue_count": g["over_cue_count"],
            "over_cue_ratio": round(g["over_cue_count"] / g["total_cues"], 4)
                              if g["total_cues"] else 0.0,
            "max_cue_len": max(lengths) if lengths else 0,
            "avg_cue_len": round(sum(lengths) / len(lengths), 1) if lengths else 0.0,
            "distribution": cue_length_distribution(lengths),
            "worst_cue": g["worst_cue"],
        })
        overall_lengths.extend(lengths)
        o_decks += g["deck_count"]
        o_slides += g["total_slides"]
        o_over_slides += g["over_slide_count"]
        o_cues += g["total_cues"]
        o_over_cues += g["over_cue_count"]
        wc = g["worst_cue"]
        if wc and (o_worst_cue is None or wc["length"] > o_worst_cue["length"]):
            o_worst_cue = wc

    overall = {
        "deck_count": o_decks,
        "total_slides": o_slides,
        "over_slide_count": o_over_slides,
        "over_slide_ratio": round(o_over_slides / o_slides, 4) if o_slides else 0.0,
        "total_cues": o_cues,
        "over_cue_count": o_over_cues,
        "over_cue_ratio": round(o_over_cues / o_cues, 4) if o_cues else 0.0,
        "max_cue_len": max(overall_lengths) if overall_lengths else 0,
        "avg_cue_len": round(sum(overall_lengths) / len(overall_lengths), 1)
                       if overall_lengths else 0.0,
        "distribution": cue_length_distribution(overall_lengths),
        "worst_cue": o_worst_cue,
    }
    return {"groups": group_list, "overall": overall}


def _excerpt(text: str, limit: int = _CUE_EXCERPT_CHARS) -> str:
    """把 cue 文字壓成單行 markdown-safe 擷取 (truncate + 去管線符)."""
    one_line = " ".join((text or "").split()).replace("|", "/")
    return one_line if len(one_line) <= limit else one_line[:limit] + "…"


def format_markdown_report(
    agg: dict,
    *,
    cue_budget: int,
    generated_at: str = "",
    deck_count: int = 0,
) -> str:
    """把 aggregate() 結果轉成 markdown 報告字串."""
    o = agg["overall"]
    thresholds = [d["threshold"] for d in o["distribution"]]
    lines: list[str] = []

    lines.append("# Narration 截斷 baseline 測量報告 (N3 修後)")
    lines.append("")
    if generated_at:
        lines.append(f"> 產出時間: {generated_at}")
    lines.append(f"> 工具: `tools/measure_narration_truncation.py` (offline, 純讀 deck.json)")
    lines.append(f"> 掃描 deck 數: {deck_count}  |  per-cue 上限: {cue_budget} 字")
    lines.append("")
    lines.append(
        "本報告量 N3 治本「修後」: cue 切分走 `core.srt.narration_to_cues` (跟 "
        "build_srt 同一條), **over-cue ratio** = 單一 cue 經 per-cue 上限切分後仍 "
        "超出字幕帶可容字數的殘留比例 (理想 0); **over-slide ratio** = narration "
        "整段超出 length_mode preset 上限 (不受 cue 切分影響). N1 修前在 19 個真實 "
        "deck 量到 over-cue 44.9% (見 git 歷史), 治本目標就是把它壓到 ~0."
    )
    lines.append("")

    # 全域摘要
    lines.append("## 全域摘要")
    lines.append("")
    lines.append(f"- deck 數: **{o['deck_count']}**, slide 數: {o['total_slides']}, "
                 f"cue 數: {o['total_cues']}")
    lines.append(f"- **over-cue ratio (> {cue_budget} 字): "
                 f"{o['over_cue_ratio']:.1%}** ({o['over_cue_count']}/{o['total_cues']})")
    lines.append(f"- over-slide ratio: {o['over_slide_ratio']:.1%} "
                 f"({o['over_slide_count']}/{o['total_slides']})")
    lines.append(f"- cue 長度: 平均 {o['avg_cue_len']} 字, 最長 {o['max_cue_len']} 字")
    if o["worst_cue"]:
        wc = o["worst_cue"]
        src = wc.get("_source", "")
        lines.append(f"- 最長 cue: {wc['length']} 字 @ `{src}` "
                     f"{wc['section_id']}/{wc['slide_id']} — 「{_excerpt(wc['text'])}」")
    lines.append("")

    # cue 長度分布 (全域)
    lines.append("## Cue 長度分布 (全域)")
    lines.append("")
    lines.append("> 不同 per-cue 上限下會有多少 cue 過長 — 看切分後的長度散布.")
    lines.append("")
    lines.append("| 上限 (字) | 超過的 cue 數 | 佔比 |")
    lines.append("|---|---|---|")
    for d in o["distribution"]:
        lines.append(f"| > {d['threshold']} | {d['count']} | {d['ratio']:.1%} |")
    lines.append("")

    # 分組
    lines.append("## 依 (length_mode × narration_style) 分組")
    lines.append("")
    if not agg["groups"]:
        lines.append("_(沒有掃到任何 deck)_")
        lines.append("")
    else:
        header_th = " | ".join(f">{t}" for t in thresholds)
        lines.append(
            "| length_mode | narration_style | decks | slides | over-slide | "
            f"cues | over-cue ({cue_budget}) | 最長 | 平均 | " + header_th + " |"
        )
        sep = "|---" * (10 + len(thresholds)) + "|"
        lines.append(sep)
        for g in agg["groups"]:
            dist = " | ".join(str(d["count"]) for d in g["distribution"])
            lines.append(
                f"| {g['length_mode']} | {g['narration_style']} | {g['deck_count']} | "
                f"{g['total_slides']} | {g['over_slide_ratio']:.0%} | "
                f"{g['total_cues']} | {g['over_cue_ratio']:.0%} | "
                f"{g['max_cue_len']} | {g['avg_cue_len']} | {dist} |"
            )
        lines.append("")

        # 各組最長 cue 範例
        lines.append("### 各組最長 cue 範例")
        lines.append("")
        for g in agg["groups"]:
            wc = g["worst_cue"]
            if not wc:
                continue
            src = wc.get("_source", "")
            lines.append(
                f"- **{g['length_mode']} / {g['narration_style']}**: "
                f"{wc['length']} 字 @ `{src}` {wc['section_id']}/{wc['slide_id']} — "
                f"「{_excerpt(wc['text'])}」"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# IO 層 — 掃描磁碟, 薄包裝
# --------------------------------------------------------------------------- #

def load_options_for_deck(deck_path: Path) -> dict:
    """讀 deck.json 旁的 state.json options (取 length_mode / narration_style).

    沒 state.json (例如 OUTPUT_DIR 直接放的 deck) → 回空 dict, 走預設.
    """
    state_path = deck_path.parent / "state.json"
    if not state_path.is_file():
        return {}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    opts = state.get("options")
    return opts if isinstance(opts, dict) else {}


def make_record(deck: dict, options: dict | None, source: str, *, cue_budget: int) -> dict:
    """從 deck dict + options 組一筆 record (磁碟掃描與 fixture 模式共用).

    把 length_mode / narration_style 解析 + measure_deck 串起來, 讓
    build_record (讀 state.json) 與 load_fixture_records (內嵌 options) 走同一條
    路徑, 不各自重算 — 否則兩邊預設值 drift 會讓 CI fixture 數字跟實機掃描對不上.
    """
    length_mode = resolve_length_mode(options)
    return {
        "length_mode": length_mode,
        "narration_style": resolve_narration_style(options),
        "source": source.replace("\\", "/"),
        "measure": measure_deck(deck, length_mode=length_mode, cue_budget=cue_budget),
    }


def build_record(deck_path: Path, *, root: Path, cue_budget: int) -> dict | None:
    """讀一個 deck.json + 旁邊 options, 回 record. 壞檔回 None."""
    try:
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(deck, dict):
        return None
    try:
        source = str(deck_path.relative_to(root))
    except ValueError:
        source = str(deck_path)
    return make_record(
        deck, load_options_for_deck(deck_path), source, cue_budget=cue_budget,
    )


def load_fixture_records(path: Path, *, cue_budget: int) -> list[dict]:
    """讀 N2 eval fixture (匿名化的代表性 deck), 回 record list (依 source 排序).

    fixture 檔格式: ``{"fixtures": [{"name", "options", "deck"}, ...]}``. options
    內嵌 (不讀旁邊 state.json), 讓 CI 在無 jobs 資料 / 無 Gemini 下也能逐字重現
    截斷率測量. fixture 的 narration 經 length-preserving 匿名化, cue 切分與字數
    跟原 deck 相同, 故數字具代表性. 壞檔 / 格式不符 → 回空 list (跟 collect_records
    對壞檔的容忍一致, 不讓 CI 因 fixture 格式炸掉整個測量).
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    records: list[dict] = []
    for entry in data.get("fixtures") or []:
        if not isinstance(entry, dict):
            continue
        deck = entry.get("deck")
        if not isinstance(deck, dict):
            continue
        source = str(entry.get("name") or entry.get("source") or "fixture")
        opts = entry.get("options")
        records.append(make_record(
            deck, opts if isinstance(opts, dict) else {}, source, cue_budget=cue_budget,
        ))
    records.sort(key=lambda r: r["source"])
    return records


def collect_records(
    dirs: list[Path], *, root: Path, cue_budget: int,
) -> list[dict]:
    """掃多個目錄底下所有 deck.json, 回 record list (依 source 排序穩定)."""
    seen: set[Path] = set()
    records: list[dict] = []
    for d in dirs:
        if not d.exists():
            continue
        for deck_path in sorted(d.rglob("deck.json")):
            rp = deck_path.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            rec = build_record(deck_path, root=root, cue_budget=cue_budget)
            if rec is not None:
                records.append(rec)
    records.sort(key=lambda r: r["source"])
    return records


def main(argv: list[str] | None = None) -> int:
    from core.config import JOBS_DIR, OUTPUT_DIR  # noqa: E402 (避免 import 副作用)

    ap = argparse.ArgumentParser(description="N1 narration 截斷 baseline 測量 (offline)")
    ap.add_argument("--jobs-dir", default=str(JOBS_DIR), help="jobs 目錄 (預設 core.config.JOBS_DIR)")
    ap.add_argument("--output-dir", default=str(OUTPUT_DIR), help="OUTPUT 目錄 (預設 core.config.OUTPUT_DIR)")
    ap.add_argument("--out", default="docs/narration-truncation-report.md",
                    help="markdown 報告輸出路徑 ('-' = stdout)")
    ap.add_argument("--cue-budget", type=int, default=DEFAULT_CUE_CHAR_BUDGET,
                    help=f"per-cue 字數上限 (provisional, 預設 {DEFAULT_CUE_CHAR_BUDGET})")
    ap.add_argument("--fixtures", nargs="?", const=DEFAULT_FIXTURES_PATH, default=None,
                    help=f"改讀 N2 eval fixture (CI 可重現, 無 Gemini / 無 jobs 資料); "
                         f"不帶值用預設 {DEFAULT_FIXTURES_PATH}")
    ap.add_argument("--date", default="", help="報告產出日期字串 (預設留空)")
    ap.add_argument("--quiet", action="store_true", help="不印 stderr 摘要")
    args = ap.parse_args(argv)

    if args.fixtures:
        fixtures_path = Path(args.fixtures)
        if not fixtures_path.is_absolute():
            fixtures_path = ROOT / fixtures_path
        records = load_fixture_records(fixtures_path, cue_budget=args.cue_budget)
    else:
        dirs = [Path(args.jobs_dir), Path(args.output_dir)]
        records = collect_records(dirs, root=ROOT, cue_budget=args.cue_budget)
    agg = aggregate(records)
    report = format_markdown_report(
        agg, cue_budget=args.cue_budget, generated_at=args.date,
        deck_count=len(records),
    )

    if args.out == "-":
        sys.stdout.write(report)
    else:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        if not args.quiet:
            o = agg["overall"]
            print(f"掃 {len(records)} 個 deck, over-cue ratio (> {args.cue_budget} 字) "
                  f"= {o['over_cue_ratio']:.1%} ({o['over_cue_count']}/{o['total_cues']})",
                  file=sys.stderr)
            print(f"報告寫到 {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
