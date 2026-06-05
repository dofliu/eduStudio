"""infoCard 生成資料模型（從 types.ts 收編，Phase C-1）。

pydantic 模型，**欄位名維持 camelCase** 對齊前端 JSON 契約（mainTitle/speakerNotes…）。
列舉用 Literal（對齊 TS union）。涵蓋三模式輸出：簡報(PresentationData)、海報(InfographicData)、
漫畫(ComicData)，加兩階段大綱(PresentationOutline)。PPTX 專用的 SlideMaster 系列待 C-3 補。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ── 列舉（對齊 types.ts union）──
InfographicStyle = Literal[
    "professional", "comic", "digital", "watercolor", "minimalist", "custom",
    "vibrant", "nature", "academic", "pastel", "ocean", "sunset", "lavender",
    "cyberpunk", "earth", "forest", "navy", "frieren", "naruto",
]
InfographicLayout = Literal["grid", "timeline", "process", "comparison"]
InfographicAspectRatio = Literal["vertical", "horizontal", "square"]
TypographyType = Literal["modern", "classic", "mono", "handwriting"]
AnimationType = Literal["fade", "slide", "zoom", "none"]
DensityType = Literal["minimal", "balanced", "detailed"]
SlideLayout = Literal[
    "title_cover", "section_header", "text_and_image", "bullet_list", "big_number",
    "quote", "diagram_image", "conclusion", "two_column", "process_steps", "timeline",
    "chart_focus", "full_image", "worked_example", "exercise", "code_block",
    "swot_analysis", "pyramid_diagram", "comparison_table",
]


# ── 成本 ──
class CostBreakdown(BaseModel):
    textInput: float
    textOutput: float
    imageGeneration: float
    imageCount: int
    imageModel: str


class AICost(BaseModel):
    totalCost: float
    currency: str = "USD"
    breakdown: CostBreakdown


# ── 海報（Infographic）──
class InfographicStat(BaseModel):
    id: str
    value: str
    label: str


class InfographicSection(BaseModel):
    id: str
    title: str
    content: str
    iconType: Literal["bulb", "chart", "list", "target", "warning", "info", "calendar", "check", "time"]
    imagePrompt: str | None = None
    imageUrl: str | None = None


class ChartItem(BaseModel):
    label: str
    value: float
    color: str | None = None


class InfographicChart(BaseModel):
    id: str
    title: str
    type: Literal["bar", "pie"]
    data: list[ChartItem]
    description: str | None = None


class InfographicData(BaseModel):
    mainTitle: str
    subtitle: str
    layout: InfographicLayout
    aspectRatio: InfographicAspectRatio | None = None
    comparisonLabels: list[str] | None = None
    sections: list[InfographicSection] = Field(default_factory=list)
    statistics: list[InfographicStat] = Field(default_factory=list)
    charts: list[InfographicChart] | None = None
    conclusion: str = ""
    themeColor: str
    style: InfographicStyle
    costEstimate: AICost | None = None
    promptUsed: str | None = None


# ── 簡報（Presentation）──
class ChartData(BaseModel):
    labels: list[str]
    values: list[float]
    type: Literal["bar", "pie"]


class SlideContentSection(BaseModel):
    id: str
    type: Literal["text", "image", "chart", "list", "quote", "placeholder"]
    content: str | None = None
    bulletPoints: list[str] | None = None
    chartData: ChartData | None = None
    quoteAttribution: str | None = None
    imagePrompt: str | None = None
    imageUrl: str | None = None
    imageIndex: int | None = None
    imagePositionId: str | None = None


class Quadrants(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    threats: list[str] = Field(default_factory=list)


class ComparisonData(BaseModel):
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class Slide(BaseModel):
    id: str
    layout: SlideLayout
    title: str
    sections: list[SlideContentSection] | None = None
    # legacy 向後相容欄位
    content: str | None = None
    bulletPoints: list[str] | None = None
    imagePrompt: str | None = None
    imageIndex: int | None = None
    imageUrl: str | None = None
    speakerNotes: str = ""
    statValue: str | None = None
    columnLeft: list[str] | None = None
    columnRight: list[str] | None = None
    chartData: ChartData | None = None
    codeLanguage: str | None = None
    quadrants: Quadrants | None = None
    pyramidLayers: list[str] | None = None
    comparisonData: ComparisonData | None = None


class PresentationData(BaseModel):
    mainTitle: str
    subtitle: str
    slides: list[Slide] = Field(default_factory=list)
    themeColor: str
    style: InfographicStyle
    typography: TypographyType | None = None
    animation: AnimationType | None = None
    density: DensityType | None = None
    costEstimate: AICost | None = None
    promptUsed: str | None = None
    presentationTheme: str | None = None


# ── 兩階段大綱（Stage 1 低成本預覽）──
class SlideOutline(BaseModel):
    layout: SlideLayout
    title: str
    summary: str


class PresentationOutline(BaseModel):
    id: str
    label: str
    approach: str
    recommendedAudience: str | None = None
    suggestedTheme: str
    suggestedTypography: TypographyType
    mainTitle: str
    subtitle: str
    slides: list[SlideOutline] = Field(default_factory=list)
    estimatedImageCount: int = 0


# ── 漫畫（Comic）──
class ComicPanel(BaseModel):
    id: str
    panelNumber: int
    description: str
    dialogue: str
    cameraDetail: str
    imagePrompt: str
    imageUrl: str | None = None


class ComicData(BaseModel):
    title: str
    storySummary: str
    characterVisualBible: str
    panels: list[ComicPanel] = Field(default_factory=list)
    style: InfographicStyle
    costEstimate: AICost | None = None
    promptUsed: str | None = None
