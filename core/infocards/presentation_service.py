"""教學簡報生成（從 infoCard services/presentationService.ts:generatePresentation 收編）。

本批移植**核心單階段生成主流程**：內容 → 結構化 PresentationData（多頁 Slide，含
speakerNotes/layout/bulletPoints…）→ 對允許版型逐頁生圖（16:9）。走核心 Gemini helper。

範圍說明（刻意分批，避免單一巨 PR）：
- 已含：完整 PRESENTATION_GENERATION_PROMPT（版型規則 + 內容預算 + 生圖政策）、主題色解析
  （presentation_themes）、imagePrompt 政策過濾（native/icon/chart 版型即使 AI 雞婆填了也丟棄）、
  Literal 越界 coerce、逐頁生圖。
- 未含（後續 PR）：兩階段大綱(generatePresentationOutlines)、單頁 refine、character sheet 角色
  一致性、chart_focus 數據回填、teaching budget 裁切、上傳圖片 imageIndex 引用、PPTX 匯出。
這些是精修/延伸路徑，不影響「給主題即產出完整簡報」的主幹。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from core.infocards.chart_suggester import (
    build_chart_data_for_slide,
    is_renderable_chart_data,
)
from core.infocards.gemini import generate_image_b64, generate_json
from core.infocards.layout_rules import analyze_outline_slide, reconcile_layout
from core.infocards.outline_normalizer import normalize_outlines
from core.infocards.presentation_themes import get_theme_by_style
from core.infocards.schemas import PresentationData, PresentationOutline
from core.infocards.slide_budget import enforce_teaching_layout_budget_dict

# 允許 AI 生圖的版型（對齊 layouts.ts needsAIImage：imagePolicy required/optional）。
# 其餘版型由前端 SVG/CSS/icon 原生繪製，即使 AI 填了 imagePrompt 也丟棄（省成本 + 視覺一致）。
_AI_IMAGE_LAYOUTS = {"title_cover", "text_and_image", "diagram_image", "full_image"}
# 合法版型集合（對齊 schemas.SlideLayout）；Gemini 越界值 coerce 成 bullet_list。
_LAYOUTS = {
    "title_cover", "section_header", "text_and_image", "bullet_list", "big_number",
    "quote", "diagram_image", "conclusion", "two_column", "process_steps", "timeline",
    "chart_focus", "full_image", "worked_example", "exercise", "code_block",
    "swot_analysis", "pyramid_diagram", "comparison_table",
}
_CHART_TYPES = {"bar", "pie"}


def needs_ai_image(layout: str) -> bool:
    return layout in _AI_IMAGE_LAYOUTS


# ── 生成用 schema（約束 Gemini 輸出；對齊 presentationService.ts presentationSchema）──
class _ChartGen(BaseModel):
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    type: str = "bar"


class _QuadGen(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    threats: list[str] = Field(default_factory=list)


class _CompGen(BaseModel):
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class _SlideGen(BaseModel):
    id: str
    layout: str = "bullet_list"
    title: str
    content: str = ""
    speakerNotes: str = ""
    imagePrompt: str | None = None
    imageIndex: int | None = None
    statValue: str | None = None
    bulletPoints: list[str] | None = None
    columnLeft: list[str] | None = None
    columnRight: list[str] | None = None
    chartData: _ChartGen | None = None
    codeLanguage: str | None = None
    quadrants: _QuadGen | None = None
    pyramidLayers: list[str] | None = None
    comparisonData: _CompGen | None = None


class _PresentationGen(BaseModel):
    mainTitle: str
    subtitle: str
    themeColor: str
    style: str
    slides: list[_SlideGen]


# 完整生成 prompt（忠實移植 presentationService.ts PRESENTATION_GENERATION_PROMPT 的版型規則、
# 內容預算與生圖政策；繁中台灣）。為控制長度只保留規則主體，逐字對齊原版語意。
_PRESENTATION_PROMPT = """
【ROLE】你是一位資深簡報設計師兼內容策略師，擅長將複雜內容轉化為視覺化、結構化的專業簡報。尤其擅長理工科教學簡報，能將理論、公式、計算過程、程式碼轉化為清晰的教學投影片。

【SLIDE LAYOUT SELECTION RULES - 嚴格遵守】
- title_cover: 僅用於第 1 頁封面。需要有震撼力的標題與精煉副標題。
- section_header: 主題轉換的過渡頁。每 3-4 頁內容頁後插入一次。
- bullet_list: 列舉 3-5 個精煉重點，每點不超過 20 個中文字。
- text_and_image: 左文右圖，文字精簡（不超過 80 字），imagePrompt 必填。
- big_number: 突出關鍵數據/統計值/公式。statValue 必填，content 為 1-2 句解釋。
- quote: 引用名言、重要結論或核心觀點。
- diagram_image: 流程圖/架構圖/比較表等全幅圖片內容。imagePrompt 必填。
- conclusion: 僅用於最後一頁。總結核心要點並提供行動呼籲。
- two_column: 比較型/優缺點/兩方案對比。content 為「左標題|右標題」，columnLeft/columnRight 為左右要點陣列。
- process_steps: 步驟流程展示。bulletPoints 存各步驟說明。
- timeline: 歷史沿革/里程碑。bulletPoints 每項格式「年份: 事件描述」。
- chart_focus: 數據視覺化。chartData 必填 {labels:string[], values:number[], type:"bar"|"pie"}。
- full_image: 強烈視覺衝擊。imagePrompt 必填，title 為圖片底部覆蓋文字。
- swot_analysis: 優勢/劣勢/機會/威脅四象限。quadrants 必填。
- pyramid_diagram: 階層金字塔。pyramidLayers 必填（底層到頂層，3-5 層）。
- comparison_table: 多維度對比。comparisonData 必填（headers + rows）。
- worked_example: 計算範例/解題示範。content 為題目，bulletPoints 為逐步計算，statValue 為最終答案。
- exercise: 練習題/隨堂測驗。content 為題目，bulletPoints 為提示，statValue 為參考答案。
- code_block: 程式碼範例。content 為程式碼（保留縮排），bulletPoints 為說明，codeLanguage 為語言名稱。

【智慧版型選擇規則】
- 含「步驟/流程/操作/如何/依序」→ process_steps
- 含「比較/優缺/vs/對比」且精簡 → two_column
- 含「優勢/劣勢/機會/威脅/SWOT」→ swot_analysis
- 含「階層/等級/金字塔/架構層次」→ pyramid_diagram
- 含「方案對比/規格差異/多物件詳細對比」→ comparison_table
- 含年份(1800-2100)且描述歷史脈絡 → timeline
- 有 3 個以上具體數字需對比 → chart_focus
- 含數學推導/公式代入/計算/解題 → worked_example
- 含「練習/習題/試求/Exercise/Problem」→ exercise
- 含程式碼/演算法/MATLAB/Python 範例 → code_block
- 教學內容每 4-5 頁理論頁後至少插入 1 頁 worked_example 或 exercise

【CONTENT STRUCTURE RULES】
- 前 20% 封面+概述；中間 60% 核心內容（混用版型）；後 20% 總結+行動呼籲
- 絕不連續使用相同 layout 超過 2 次；每 3-4 頁內容頁後插入 section_header
- 教學內容必須包含「理論→範例→練習」完整學習循環

【IMAGE PROMPT POLICY】
僅 text_and_image / diagram_image / full_image 必填 imagePrompt，title_cover 可選；
其餘版型嚴禁填 imagePrompt（由前端原生繪製）。imagePrompt 必須用英文、描述具體場景、含風格指令。

【CONTENT BUDGET（嚴格遵守避免文字溢出）】
- bullet_list 最多 5 點每點 ≤25 字；text_and_image 文字 ≤80 字；big_number statValue ≤30 字元
- two_column 每欄 ≤5 點每點 ≤20 字；process_steps ≤5 步每步 ≤40 字；timeline ≤5 事件每項 ≤50 字
- worked_example 題目 ≤80 字 / 步驟 ≤6 步每步 ≤50 字 / 答案 ≤30 字；exercise 題目 ≤100 字
- code_block 程式碼 ≤20 行；quote ≤120 字；swot 每象限 ≤3 點；pyramid ≤5 層；comparison ≤4 欄 5 列
- speakerNotes: 每頁 3-5 句完整講稿（開場引導 + 重點提示 + 互動問題建議）
"""

_DENSITY = {
    "minimal": "極簡模式：每頁最多 3 個要點，每點不超過 15 字，大量留白",
    "balanced": "均衡模式：每頁 3-5 個要點，每點 15-25 字",
    "detailed": "詳細模式：每頁 4-6 個要點，可包含完整說明句",
}
_TYPOGRAPHY = {
    "modern": "簡潔現代的排版風格，無襯線字體感",
    "classic": "傳統學術的排版風格，正式穩重",
    "mono": "等寬字體風格，適合包含程式碼或技術內容",
    "handwriting": "手寫風格，親切自然，適合教學場景",
}


def _build_outline_instruction(outline: dict | None) -> str:
    """已選大綱 → 注入「嚴格遵守此架構」指令（對齊 presentationService.ts outlineInstruction）。"""
    if not outline:
        return ""
    slides = outline.get("slides") or []
    lines = "\n".join(
        f"  第 {i + 1} 頁: [{s.get('layout')}] {s.get('title')} — {s.get('summary')}"
        for i, s in enumerate(slides)
    )
    return f"""
【使用者已選定的簡報大綱 - 必須嚴格遵守此架構】
方案名稱：{outline.get('label', '')}
設計思路：{outline.get('approach', '')}
主標題：{outline.get('mainTitle', '')}
副標題：{outline.get('subtitle', '')}
投影片結構（請依此順序與版型生成完整內容）：
{lines}

重要：請嚴格按照上述大綱的版型(layout)、標題和主題順序生成完整內容。每頁的具體文字內容
和 imagePrompt 需要你根據大綱方向展開撰寫。
"""


def _build_prompt(text: str, style: str, custom: str, slide_count: int,
                  density: str, typography: str, theme: dict,
                  outline: dict | None = None) -> str:
    if style == "custom":
        style_header = f"THEME: {custom}"
    else:
        bg = "暗色主題 (Dark Mode)" if theme["bgBase"] == "#0f172a" else "亮色主題 (Light Mode)"
        style_header = (
            f"STYLE: {style}\n【主題視覺指令 - 嚴格遵守】\n"
            f"- 主色調：{theme['accent']}，搭配次強調色 {theme['accentSecondary']}\n"
            f"- 背景風格：{bg}\n"
            f"- imagePrompt 生成時必須匹配此風格：使用與 {theme['description']} 相符的視覺風格\n"
            f"- 所有視覺元素需保持一致的配色與氛圍"
        )
    return f"""{_PRESENTATION_PROMPT}
【本次設定】
- 視覺風格：{style_header}
- 內容密度：{_DENSITY.get(density, _DENSITY['balanced'])}
- 排版風格：{_TYPOGRAPHY.get(typography, _TYPOGRAPHY['modern'])}
- 目標頁數：精確生成 {slide_count} 頁（含封面和總結頁）
- 語言：繁體中文（台灣）
{_build_outline_instruction(outline)}
【待處理內容】
{text or '請分析內容，生成完整的專業簡報。'}"""


def _coerce(data: dict) -> dict:
    """Gemini 輸出的純函式校正（對齊 presentationService.ts 的零 API 後處理）：

    1. layout/chart.type Literal 越界值退安全預設。
    2. 依生圖政策丟棄 native/icon/chart 版型多填的 imagePrompt（對齊 needsAIImage 過濾）。
    3. chart_focus 版型若無可渲染 chartData，從投影片文字偵測數列回填（不覆蓋有效數據）。
    4. 教學版型 bulletPoints 套用 budget 裁切（只裁數量不裁文字）。
    """
    for sl in data.get("slides") or []:
        if sl.get("layout") not in _LAYOUTS:
            sl["layout"] = "bullet_list"
        layout = sl["layout"]
        if sl.get("imagePrompt") and not needs_ai_image(layout):
            sl["imagePrompt"] = None
        ch = sl.get("chartData")
        if isinstance(ch, dict) and ch.get("type") not in _CHART_TYPES:
            ch["type"] = "bar"
        # chart_focus 數據回填：AI 未給可渲染 chartData 時，從標題+內容+要點偵測數列。
        if layout == "chart_focus" and not is_renderable_chart_data(sl.get("chartData")):
            slide_text = "\n".join(
                str(x) for x in [sl.get("title"), sl.get("content"), *(sl.get("bulletPoints") or [])] if x
            )
            inferred = build_chart_data_for_slide(layout, slide_text)
            if inferred:
                sl["chartData"] = inferred
        # 教學版型條列數量預算（worked_example/exercise/code_block）。
        enforce_teaching_layout_budget_dict(sl)
    return data


def generate_presentation_data(
    text: str,
    style: str,
    *,
    custom: str = "",
    slide_count: int = 10,
    density: str = "balanced",
    typography: str = "modern",
    animation: str = "fade",
    selected_outline: dict | None = None,
    model: str | None = None,
    files=None,
) -> PresentationData:
    """內容 → 簡報結構 PresentationData（不含圖；imageUrl 之後由 images 步驟填）。

    selected_outline（兩階段流程 Stage 2）：傳入已選大綱時，沿用其 suggestedTheme/
    suggestedTypography，並把大綱結構注入 prompt 嚴格遵守（對齊 presentationService.ts）。
    """
    effective_style = style
    if selected_outline:
        effective_style = selected_outline.get("suggestedTheme") or style
        typography = selected_outline.get("suggestedTypography") or typography
    theme = get_theme_by_style("professional" if effective_style == "custom" else effective_style)
    prompt = _build_prompt(text, effective_style, custom, slide_count, density, typography,
                           theme, selected_outline)
    data = generate_json(prompt, model=model, response_schema=_PresentationGen, files=files)
    data = _coerce(data)
    # 後端補（非模型輸出，對齊 presentationService.ts）。
    data["typography"] = typography
    data["density"] = density
    data["animation"] = animation
    data["promptUsed"] = prompt
    if not data.get("themeColor") or data.get("themeColor") == "#000000":
        data["themeColor"] = theme["accent"]
    data["presentationTheme"] = theme["id"]
    data.setdefault("style", effective_style)
    return PresentationData.model_validate(data)


def generate_presentation_images(
    data: PresentationData,
    *,
    style: str = "professional",
    custom: str = "",
    image_model: str | None = None,
) -> PresentationData:
    """對允許生圖且有 imagePrompt 的版型逐頁生圖，填回 slide.imageUrl（16:9 概念，base64）。"""
    for slide in data.slides:
        if slide.imageUrl:
            continue
        if slide.imagePrompt and needs_ai_image(slide.layout):
            slide.imageUrl = generate_image_b64(slide.imagePrompt, model=image_model)
    return data


# ── 兩階段大綱（Stage 1：低成本預覽 3 個方案）──
_OUTLINE_PROMPT = """
【ROLE】你是一位資深簡報策略顧問，擅長根據內容規劃不同風格的簡報架構。
【TASK】根據內容產生 3 個不同風格的簡報大綱方案，讓使用者預覽後選擇再完整生成。
【3 個方案（同一視覺主題下的不同敘事/版型方案，差異在敘事結構與 layout 分配，非配色）】
- 方案 A「敘事型」：以故事線串連，有起承轉合，適合演講與報告
- 方案 B「分析型」：以數據和邏輯為主，善用圖表、比較、流程，適合專業提案
- 方案 C「視覺型」：大量圖片與視覺衝擊，文字極簡，適合產品發表或行銷
【每個方案需含】label / approach（1-2 句設計思路）/ recommendedAudience（1-5 字受眾標籤）/
suggestedTheme（主題 ID）/ suggestedTypography（modern/classic/mono/handwriting）/
mainTitle / subtitle / slides（每頁 layout+title+summary 一句話）/ estimatedImageCount。
【SLIDE LAYOUT OPTIONS】title_cover / section_header / bullet_list / text_and_image / big_number /
quote / diagram_image / conclusion / two_column / process_steps / timeline / chart_focus /
full_image / worked_example / exercise / code_block / swot_analysis / pyramid_diagram / comparison_table
【RULES】每方案頁數符合指定頁數；3 方案沿用同一主題；差異體現在 layout 分配與敘事結構；
summary 用繁中（台灣）每項 ≤30 字；絕不連續使用相同 layout 超過 2 次。
"""


class _SlideOutlineGen(BaseModel):
    layout: str = "bullet_list"
    title: str
    summary: str = ""


class _OutlineGen(BaseModel):
    label: str
    approach: str = ""
    recommendedAudience: str | None = None
    suggestedTheme: str = "professional"
    suggestedTypography: str = "modern"
    mainTitle: str
    subtitle: str = ""
    estimatedImageCount: int = 0
    slides: list[_SlideOutlineGen]


class _OutlinesGen(BaseModel):
    outlines: list[_OutlineGen]


def generate_presentation_outlines(
    text: str,
    style: str,
    *,
    custom: str = "",
    slide_count: int = 10,
    model: str | None = None,
    files=None,
) -> list[PresentationOutline]:
    """Stage 1：產 3 個大綱方案（低成本，不生圖）。

    每頁版型經規則引擎校正（analyze_outline_slide + reconcile_layout），整批再
    normalize_outlines（typography/estimatedImageCount 合法化 + 主題統一為使用者選定風格）。
    """
    style_hint = (
        f"使用者偏好風格：{custom}（三個方案仍需有差異）" if style == "custom" and custom
        else f"使用者初始選擇風格：{style}（三個方案仍需有差異）"
    )
    prompt = f"""{_OUTLINE_PROMPT}
【本次設定】
- {style_hint}
- 目標頁數：每個方案精確 {slide_count} 頁（含封面和總結頁）
- 語言：繁體中文（台灣）
【待處理內容】
{text or '請根據內容規劃簡報大綱。'}"""

    data = generate_json(prompt, model=model, response_schema=_OutlinesGen, files=files)
    outlines = data.get("outlines") or []

    for i, o in enumerate(outlines):
        o.setdefault("id", f"outline_{i}")
        total = len(o.get("slides") or [])
        for idx, s in enumerate(o.get("slides") or []):
            signals = analyze_outline_slide(s.get("title", ""), s.get("summary", ""))
            s["layout"] = reconcile_layout(
                slide_index=idx + 1, total_slides=total,
                title=s.get("title"), content=s.get("summary"),
                ai_hint=s.get("layout"), **signals)

    normalize_outlines(outlines, style)
    return [PresentationOutline.model_validate(o) for o in outlines]
