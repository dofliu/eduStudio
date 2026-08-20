/* eduStudio 統一 app — 由設計 handoff 原型串接落地（infoCard React19 + Vite）。
   原型各檔共享全域 scope，此處串成單一 module 等同同 scope；僅加 React/ReactDOM import
   與 CSS imports。tokens.css + themes.css 在 data-theme=lumen 下即為定稿 Lumen 設計。 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import './tokens.css';
import './themes.css';
import './components.css';
import './layout.css';
import './screens.css';
import './creator.css';
import { WORKFLOWS, createTaskBrief, inferWorkflowIntent } from './workflows.js';
import ComicStudio from './comic-studio.jsx';

/* eduStudio — mock data (Traditional-Chinese, STEM teaching context) */

const LANGS = [
  { code: "zh-TW", label: "繁體中文", native: "繁體中文", source: true },
  { code: "en",    label: "英文",     native: "English" },
  { code: "ja",    label: "日文",     native: "日本語" },
  { code: "ko",    label: "韓文",     native: "한국어" },
  { code: "zh-CN", label: "簡體中文", native: "简体中文" },
  { code: "vi",    label: "越南文",   native: "Tiếng Việt" },
];

const PROJECTS = [
  { id: "p1", name: "普通物理（一）", term: "2026 春 · 力學", hue: "var(--es-ws-video)", sources: 6, outputs: 11 },
  { id: "p2", name: "單變數微積分",   term: "2026 春",        hue: "var(--es-ws-material)", sources: 4, outputs: 7 },
  { id: "p3", name: "工程數學",       term: "2025 秋",        hue: "var(--es-ws-visual)", sources: 9, outputs: 18 },
];

const SOURCE_TYPES = {
  pdf:   { icon: "file-text", label: "PDF", hue: "var(--es-error)" },
  video: { icon: "film",      label: "影片", hue: "var(--es-ws-video)" },
  url:   { icon: "link",      label: "連結", hue: "var(--es-info)" },
  repo:  { icon: "github",    label: "Repo", hue: "var(--es-fg-2)" },
  image: { icon: "image",     label: "圖片", hue: "var(--es-ws-visual)" },
  audio: { icon: "mic",       label: "音訊", hue: "var(--es-accent)" },
};

const SOURCES = [
  { id: "s1", type: "pdf",   name: "期中考卷 2026 春.pdf", meta: "6 頁 · 已解析", added: "2 天前" },
  { id: "s2", type: "pdf",   name: "第 7 章 講義 — 動量守恆.pdf", meta: "18 頁", added: "5 天前" },
  { id: "s3", type: "url",   name: "MIT 8.01 Lecture 12 — Momentum", meta: "youtube.com · 49:51", added: "1 週前" },
  { id: "s4", type: "audio", name: "教學討論會錄音 0530.m4a", meta: "32:14", added: "6 天前" },
  { id: "s5", type: "video", name: "自由落體實驗.mp4", meta: "01:48 · 1080p", added: "1 週前" },
  { id: "s6", type: "image", name: "受力分析示意圖.png", meta: "PNG · 2.1 MB", added: "1 週前" },
];

const TASK_TYPES = {
  solve:    { label: "解題影片",  icon: "sigma",    desc: "由考卷／講義生成逐步旁白教學影片", hue: "var(--es-ws-video)" },
  dub:      { label: "影片配音",  icon: "volume",   desc: "外部影片的多語配音與翻譯字幕",     hue: "var(--es-info)" },
  summary:  { label: "會議摘要",  icon: "message-square", desc: "會議／演講錄音的重點摘要影片", hue: "var(--es-accent)" },
  subtitle: { label: "字幕",      icon: "captions", desc: "為既有影片生成多語字幕",           hue: "var(--es-warning)" },
};

const VIDEO_TASKS = [
  { id: "v1", title: "期中考 第 3 題 — 斜向拋體解題", type: "solve", status: "review",
    source: "期中考卷 2026 春.pdf", duration: "04:32", segments: 6, approved: 1, lang: "zh-TW",
    updated: "12 分鐘前", cost: 0.42, model: "Gemini 2.5 Pro" },
  { id: "v2", title: "MIT Lecture 12 — 配音翻譯", type: "dub", status: "running",
    source: "MIT 8.01 Lecture 12", progress: 62, lang: "en", target: "zh-TW",
    updated: "進行中", cost: 1.18, model: "Gemini 2.5 Pro" },
  { id: "v3", title: "教學討論會 0530 — 重點摘要", type: "summary", status: "approved",
    source: "教學討論會錄音 0530.m4a", duration: "06:10", lang: "zh-TW",
    updated: "昨天", cost: 0.31, model: "Gemini 2.5 Flash" },
  { id: "v4", title: "自由落體實驗講解", type: "solve", status: "queued",
    source: "自由落體實驗.mp4", lang: "zh-TW", updated: "排隊中 · 第 2 位", cost: 0, model: "Gemini 2.5 Pro" },
  { id: "v5", title: "第 6 章 動量 — 字幕生成", type: "subtitle", status: "failed",
    source: "第 6 章 動量.mp4", lang: "zh-TW", updated: "1 小時前", cost: 0.05, model: "Gemini 2.5 Flash",
    error: "來源影片無音軌，無法生成字幕" },
];

/* Review-gate segments for task v1 — narration + formulas + numbers to verify */
const f = (s) => s; // formula HTML passthrough
const REVIEW_SEGMENTS = [
  {
    id: "seg1", t: "00:00 – 00:18", status: "approved", confidence: 0.97,
    narration: "本題為斜向拋體運動。物體以初速度 v₀ = 20 m/s、仰角 θ = 30° 拋出，忽略空氣阻力，重力加速度取 g = 9.8 m/s²。",
    formula: null,
    values: [ { k: "v₀", v: "20 m/s" }, { k: "θ", v: "30°" }, { k: "g", v: "9.8 m/s²" } ],
  },
  {
    id: "seg2", t: "00:18 – 00:52", status: "review", confidence: 0.74, flag: "數值可能需修正",
    narration: "首先將初速度分解為水平與垂直分量。水平分量為 v₀ cos θ，垂直分量為 v₀ sin θ。",
    formula: f("<span class='es-eq'>v<sub>0x</sub> = v<sub>0</sub>cos θ = 20 × cos 30° = <mark class='es-flag'>17.3</mark> m/s</span><span class='es-eq'>v<sub>0y</sub> = v<sub>0</sub>sin θ = 20 × sin 30° = 10.0 m/s</span>"),
    values: [ { k: "v₀ₓ", v: "17.3 m/s", flag: true, suggest: "17.32 m/s" }, { k: "v₀ᵧ", v: "10.0 m/s" } ],
  },
  {
    id: "seg3", t: "00:52 – 01:40", status: "review", confidence: 0.91,
    narration: "在最高點，垂直速度為零。利用運動學公式可求得最大高度 H。",
    formula: f("<span class='es-eq'>H = <span class='es-frac'><span class='es-fnum'>v<sub>0y</sub>²</span><span class='es-fden'>2g</span></span> = <span class='es-frac'><span class='es-fnum'>10²</span><span class='es-fden'>2 × 9.8</span></span> = 5.10 m</span>"),
    values: [ { k: "H", v: "5.10 m" } ],
  },
  {
    id: "seg4", t: "01:40 – 02:30", status: "pending", confidence: 0.88,
    narration: "整體飛行時間為上升與下降時間之和，可由垂直分量除以重力加速度的兩倍求得。",
    formula: f("<span class='es-eq'>t = <span class='es-frac'><span class='es-fnum'>2 v<sub>0y</sub></span><span class='es-fden'>g</span></span> = <span class='es-frac'><span class='es-fnum'>2 × 10</span><span class='es-fden'>9.8</span></span> = 2.04 s</span>"),
    values: [ { k: "t", v: "2.04 s" } ],
  },
  {
    id: "seg5", t: "02:30 – 03:20", status: "pending", confidence: 0.85,
    narration: "水平方向為等速運動，射程等於水平速度乘以飛行時間。",
    formula: f("<span class='es-eq'>R = v<sub>0x</sub> · t = 17.3 × 2.04 = <mark class='es-flag'>35.3</mark> m</span>"),
    values: [ { k: "R", v: "35.3 m", flag: true, suggest: "35.32 m" } ],
  },
  {
    id: "seg6", t: "03:20 – 04:32", status: "pending", confidence: 0.93,
    narration: "綜上所述，此斜向拋體的最大高度約為 5.1 公尺，水平射程約為 35.3 公尺，總飛行時間約 2.04 秒。建議學生注意三角函數值的有效位數。",
    formula: null,
    values: [],
  },
];

const VISUAL_MODES = {
  slides: { label: "教學簡報", icon: "presentation", desc: "成套投影片 · 16:9", hue: "var(--es-ws-video)" },
  // 圖卡與海報合併為單一視覺成品（單張大圖），用版式(直式海報/方形圖卡/橫式)區分用途。
  poster: { label: "圖卡 · 海報", icon: "image",      desc: "單張視覺 · 印刷級", hue: "var(--es-ws-visual)" },
  // 資訊圖卡：多區塊結構化版面，支援逐區（區域選擇）refine。
  infographic: { label: "資訊圖卡", icon: "layout-grid", desc: "多區塊 · 可逐區微調", hue: "var(--es-ws-material)" },
};

const VISUAL_OUTPUTS = [
  { id: "g1", mode: "slides", title: "第 7 章 動量守恆 — 教學簡報", meta: "12 張", status: "approved", localized: ["en", "ja"] },
  { id: "g2", mode: "poster", title: "牛頓三大運動定律 — 資訊圖卡", meta: "1 張 · 方形", status: "review", localized: [] },
  { id: "g3", mode: "poster", title: "期末專題成果發表 — 海報", meta: "A1 直式", status: "draft", localized: [] },
];

/* Unified cross-type output library for a project */
const LIBRARY = [
  { id: "v1", kind: "video",  title: "期中考 第 3 題 — 斜向拋體解題", meta: "影片 · 04:32", status: "review",    localized: ["en"] },
  { id: "v3", kind: "video",  title: "教學討論會 0530 — 重點摘要",     meta: "影片 · 06:10", status: "approved",  localized: ["en", "ja", "ko"] },
  { id: "g1", kind: "slides", title: "第 7 章 動量守恆 — 教學簡報",     meta: "簡報 · 12 張", status: "approved",  localized: ["en", "ja"] },
  { id: "g2", kind: "card",   title: "牛頓三大運動定律 — 資訊圖卡",     meta: "圖卡 · 1 張",  status: "review",    localized: [] },
  { id: "v5", kind: "subtitle", title: "第 6 章 動量 — 多語字幕",       meta: "字幕 · SRT",   status: "approved",  localized: ["en", "ja", "ko", "vi"] },
];

const PUBLISH_ITEMS = [
  { id: "pub1", title: "期中考 第 3 題 — 斜向拋體解題", channel: "youtube", status: "published",
    meta: "公開 · 3 種語言", views: "1,204", date: "2 天前", langs: ["zh-TW", "en", "ja"] },
  { id: "pub2", title: "教學討論會 0530 — 重點摘要", channel: "youtube", status: "published",
    meta: "不公開連結", views: "37", date: "昨天", langs: ["zh-TW"] },
  { id: "pub3", title: "第 7 章 動量守恆 — 教學簡報", channel: "pptx", status: "approved",
    meta: "可匯出 PPTX / PDF", langs: ["zh-TW", "en", "ja"] },
  { id: "pub4", title: "牛頓三大運動定律 — 資訊圖卡", channel: "image", status: "review",
    meta: "PNG / 分享連結", langs: ["zh-TW"] },
];

/* 成本面板用量由後端 /api/usage 即時提供（真實統計，無 mock 示意數字）。 */

const TOOLBOX = [
  { id: "flashcard", label: "單字卡", icon: "layout-grid", desc: "由教材生成記憶卡" },
  { id: "writing",   label: "寫作糾錯", icon: "pencil",    desc: "英文教材文法校對" },
  { id: "convo",     label: "會話練習", icon: "message-square", desc: "情境口說對練" },
];

Object.assign(window, {
  LANGS, PROJECTS, SOURCE_TYPES, SOURCES, TASK_TYPES, VIDEO_TASKS,
  REVIEW_SEGMENTS, VISUAL_MODES, VISUAL_OUTPUTS, LIBRARY, PUBLISH_ITEMS,
  TOOLBOX,
});
/* eduStudio — shared UI primitives (Icon set, Button, Badge, Card, Field…) */
const { useState, useRef, useEffect, useLayoutEffect, createContext, useContext } = React;

/* ───────────────────────── Icons (lucide-style) ───────────────────────── */
const ICONS = {
  home:'<path d="m3 11 9-8 9 8"/><path d="M5 10v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V10"/><path d="M9 21v-7h6v7"/>',
  video:'<path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5"/><rect x="2" y="6" width="14" height="12" rx="2"/>',
  palette:'<circle cx="13.5" cy="6.5" r=".6" fill="currentColor" stroke="none"/><circle cx="17.5" cy="10.5" r=".6" fill="currentColor" stroke="none"/><circle cx="8.5" cy="7.5" r=".6" fill="currentColor" stroke="none"/><circle cx="6.5" cy="12.5" r=".6" fill="currentColor" stroke="none"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.555C21.965 6.012 17.461 2 12 2z"/>',
  inbox:'<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
  upload:'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
  send:'<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/><path d="m21.854 2.147-10.94 10.939"/>',
  play:'<polygon points="6 3 20 12 6 21 6 3"/>',
  plus:'<path d="M5 12h14"/><path d="M12 5v14"/>',
  check:'<path d="M20 6 9 17l-5-5"/>',
  x:'<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  'chevron-right':'<path d="m9 18 6-6-6-6"/>',
  'chevron-left':'<path d="m15 18-6-6 6-6"/>',
  'chevron-down':'<path d="m6 9 6 6 6-6"/>',
  settings:'<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
  search:'<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  languages:'<path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="m22 22-5-10-5 10"/><path d="M14 18h6"/>',
  sparkles:'<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .962 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.962 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/>',
  coins:'<circle cx="8" cy="8" r="6"/><path d="M18.09 10.37A6 6 0 1 1 10.34 18"/><path d="M7 6h1v4"/><path d="m16.71 13.88.7.71-2.82 2.82"/>',
  'file-text':'<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
  image:'<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
  presentation:'<path d="M2 3h20"/><path d="M21 3v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V3"/><path d="m7 21 5-5 5 5"/>',
  'layout-grid':'<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
  folder:'<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  link:'<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  mic:'<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/>',
  captions:'<rect width="18" height="14" x="3" y="5" rx="2" ry="2"/><path d="M7 15h4M15 15h2M7 11h2M13 11h4"/>',
  'refresh-cw':'<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
  pencil:'<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>',
  'check-circle':'<path d="M21.801 10A10 10 0 1 1 17 3.335"/><path d="m9 11 3 3L22 4"/>',
  'alert-triangle':'<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  info:'<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  'shield-alert':'<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
  clock:'<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  loader:'<path d="M12 2v4"/><path d="m16.2 7.8 2.9-2.9"/><path d="M18 12h4"/><path d="m16.2 16.2 2.9 2.9"/><path d="M12 18v4"/><path d="m4.9 19.1 2.9-2.9"/><path d="M2 12h4"/><path d="m4.9 4.9 2.9 2.9"/>',
  sigma:'<path d="M18 7V5a1 1 0 0 0-1-1H6.5a.5.5 0 0 0-.4.8l4.5 6a2 2 0 0 1 0 2.4l-4.5 6a.5.5 0 0 0 .4.8H17a1 1 0 0 0 1-1v-2"/>',
  eye:'<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
  'more-horizontal':'<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
  youtube:'<path d="M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17"/><path d="m10 15 5-3-5-3z"/>',
  download:'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
  share:'<path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" x2="12" y1="2" y2="15"/>',
  file:'<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>',
  github:'<path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/><path d="M9 18c-4.51 2-5-2-7-2"/>',
  'panel-left':'<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/>',
  'graduation-cap':'<path d="M21.42 10.922a1 1 0 0 0-.019-1.838L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.832l8.57 3.908a2 2 0 0 0 1.66 0z"/><path d="M22 10v6"/><path d="M6 12.5V16a6 3 0 0 0 12 0v-3.5"/>',
  'book-open':'<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>',
  activity:'<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  wand:'<path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72"/><path d="m14 7 3 3"/><path d="M5 6v4"/><path d="M19 14v4"/><path d="M10 2v2"/><path d="M7 8H3"/><path d="M21 16h-4"/><path d="M11 3H9"/>',
  'arrow-right':'<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  trash:'<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  copy:'<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  volume:'<polygon points="11 4.7 6.5 8.5 3 8.5 3 15.5 6.5 15.5 11 19.3"/><path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.4 18.4a9 9 0 0 0 0-12.8"/>',
  type:'<path d="M12 4v16"/><path d="M4 7V5a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v2"/><path d="M9 20h6"/>',
  list:'<path d="M3 12h.01"/><path d="M3 18h.01"/><path d="M3 6h.01"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M8 6h13"/>',
  zap:'<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
  dollar:'<line x1="12" x2="12" y1="2" y2="22"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
  film:'<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18"/><path d="M3 7.5h4"/><path d="M3 12h18"/><path d="M3 16.5h4"/><path d="M17 3v18"/><path d="M17 7.5h4"/><path d="M17 16.5h4"/>',
  bell:'<path d="M10.268 21a2 2 0 0 0 3.464 0"/><path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326"/>',
  globe:'<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
  'message-square':'<path d="M22 17a2 2 0 0 1-2 2H6l-4 4V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2z"/>',
  'pen-tool':'<path d="M15.707 21.293a1 1 0 0 1-1.414 0l-1.586-1.586a1 1 0 0 1 0-1.414l5.586-5.586a1 1 0 0 1 1.414 0l1.586 1.586a1 1 0 0 1 0 1.414z"/><path d="m18 13-1.375-6.874a1 1 0 0 0-.746-.776L3.235 2.028a1 1 0 0 0-1.207 1.207L5.35 15.879a1 1 0 0 0 .776.746L13 18"/><path d="m2.3 2.3 7.286 7.286"/><circle cx="11" cy="11" r="2"/>',
};

function Icon({ name, size = 18, strokeWidth = 1.9, className = "", style = {} }) {
  const inner = ICONS[name] || ICONS['file'];
  return React.createElement('svg', {
    className: 'es-icon ' + className, width: size, height: size, viewBox: '0 0 24 24',
    fill: 'none', stroke: 'currentColor', strokeWidth, strokeLinecap: 'round',
    strokeLinejoin: 'round', style, 'aria-hidden': true,
    dangerouslySetInnerHTML: { __html: inner },
  });
}

function Spinner({ size = 16, className = "" }) {
  return <Icon name="loader" size={size} className={"es-spin " + className} />;
}

/* ───────────────────────── Button ───────────────────────── */
function Button({ variant = "default", size = "md", icon, iconRight, children, className = "", ...rest }) {
  return (
    <button className={`es-btn es-btn-${variant} es-btn-${size} ${className}`} {...rest}>
      {icon && <Icon name={icon} size={size === "sm" ? 15 : 17} />}
      {children && <span>{children}</span>}
      {iconRight && <Icon name={iconRight} size={size === "sm" ? 15 : 17} />}
    </button>
  );
}

function IconButton({ icon, size = 18, className = "", title, ...rest }) {
  return (
    <button className={`es-iconbtn ${className}`} title={title} {...rest}>
      <Icon name={icon} size={size} />
    </button>
  );
}

/* ───────────────────────── Badge / StatusPill ───────────────────────── */
const STATUS_META = {
  draft:    { label: "草稿",   tone: "neutral", icon: "file" },
  queued:   { label: "排隊中", tone: "info",    icon: "clock" },
  running:  { label: "生成中", tone: "running", icon: "loader" },
  review:   { label: "待審查", tone: "warning", icon: "eye" },
  approved: { label: "已核准", tone: "success", icon: "check-circle" },
  published:{ label: "已發布", tone: "success", icon: "youtube" },
  failed:   { label: "失敗",   tone: "error",   icon: "alert-triangle" },
};

function StatusPill({ status, size = "md" }) {
  const m = STATUS_META[status] || STATUS_META.draft;
  return (
    <span className={`es-pill es-pill-${m.tone} es-pill-${size}`}>
      {m.icon === "loader"
        ? <Spinner size={size === "sm" ? 12 : 13} />
        : <Icon name={m.icon} size={size === "sm" ? 12 : 13} />}
      {m.label}
    </span>
  );
}

function Badge({ children, tone = "neutral", icon, className = "" }) {
  return (
    <span className={`es-badge es-badge-${tone} ${className}`}>
      {icon && <Icon name={icon} size={12} />}
      {children}
    </span>
  );
}

/* ───────────────────────── Card ───────────────────────── */
function Card({ children, className = "", state, interactive, ...rest }) {
  return (
    <div className={`es-card ${state ? "es-card-" + state : ""} ${interactive ? "es-card-int" : ""} ${className}`} {...rest}>
      {children}
    </div>
  );
}

/* ───────────────────────── Fields ───────────────────────── */
function Field({ label, hint, children, className = "" }) {
  return (
    <label className={`es-field ${className}`}>
      {label && <span className="es-field-label">{label}</span>}
      {children}
      {hint && <span className="es-field-hint">{hint}</span>}
    </label>
  );
}

function Segmented({ options, value, onChange, size = "md" }) {
  return (
    <div className={`es-seg es-seg-${size}`} role="tablist">
      {options.map(o => (
        <button key={o.value}
          className={"es-seg-item" + (value === o.value ? " is-active" : "")}
          onClick={() => onChange(o.value)} role="tab" aria-selected={value === o.value}>
          {o.icon && <Icon name={o.icon} size={15} />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

function ProgressBar({ value, tone = "primary", height = 6 }) {
  return (
    <div className="es-prog" style={{ height }}>
      <div className={`es-prog-fill es-prog-${tone}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

function Avatar({ name = "陳", color = "var(--es-primary)" }) {
  return <div className="es-avatar" style={{ background: color }}>{name}</div>;
}

/* Popover anchored under a trigger ref */
function Popover({ open, onClose, anchorRef, children, align = "right", width = 280 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target) &&
          anchorRef.current && !anchorRef.current.contains(e.target)) onClose();
    };
    const onEsc = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onEsc); };
  }, [open]);
  if (!open) return null;
  return (
    <div ref={ref} className="es-popover" style={{ width, [align]: 0 }}>
      {children}
    </div>
  );
}

Object.assign(window, {
  Icon, Spinner, Button, IconButton, StatusPill, Badge, Card, Field,
  Segmented, ProgressBar, Avatar, Popover, STATUS_META, ICONS,
});
/* eduStudio — 一鍵在地化 (one-click localization). Reusable across workstations.
   Button → choose target languages → generate (simulated) → result chips. */

function LangChip({ code, removable, onRemove }) {
  const l = LANGS.find(x => x.code === code);
  if (!l) return null;
  return (
    <span className={"es-langchip" + (l.source ? " is-source" : "")}>
      <span className="es-langchip-code">{code}</span>
      {l.native}
      {removable && !l.source && <button className="es-langchip-x" onClick={onRemove}><Icon name="x" size={12} /></button>}
    </span>
  );
}

// 前端短碼 → 後端 canonical 連字號碼（/localization 邊界再轉底線）。
const ES_LANG_API = { "en": "en-US", "ja": "ja-JP", "ko": "ko-KR", "zh-CN": "zh-CN", "vi": "vi-VN", "zh-TW": "zh-TW" };

function LocalizeMenu({ localized = [], onChange, size = "sm", label = "一鍵在地化", text = "", projectId = "" }) {
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState([]);
  const [phase, setPhase] = useState("idle"); // idle | running | done
  const [doneLangs, setDoneLangs] = useState([]);
  const [results, setResults] = useState({}); // code → 真實譯文
  const ref = useRef(null);
  const targets = LANGS.filter(l => !l.source && !localized.includes(l.code));

  const toggle = (code) =>
    setPicked(p => p.includes(code) ? p.filter(c => c !== code) : [...p, code]);

  // 接 /localization/translate：對每個選的語言真的翻譯（傳成品標題作示範）。
  // F9-2j：有作用中課程（projectId）→ 帶 project_id，讓後端套該課 glossary 固定譯名
  //（route 欄位選填、fail-soft；沒給/查無沿用現行行為）。
  const run = async () => {
    if (!picked.length) return;
    setPhase("running");
    const src = text || label;
    const out = {};
    for (const code of picked) {
      try {
        const r = await fetch("/localization/translate", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: src, target_lang: ES_LANG_API[code] || code, source_lang: "zh-TW",
            ...(projectId ? { project_id: projectId } : {}),
          }),
        });
        const d = await r.json();
        out[code] = d.translated_text || "";
      } catch (e) { out[code] = "（翻譯失敗）"; }
    }
    setResults(out);
    setPhase("done");
    setDoneLangs(picked);
    onChange && onChange([...localized, ...picked]);
  };

  const reset = () => { setOpen(false); setTimeout(() => { setPicked([]); setPhase("idle"); setDoneLangs([]); setResults({}); }, 200); };

  return (
    <div className="es-localize" ref={ref}>
      <Button variant="accent" size={size} icon="languages" onClick={() => setOpen(o => !o)}>
        {label}{localized.length ? ` · ${localized.length}` : ""}
      </Button>
      <Popover open={open} onClose={reset} anchorRef={ref} align="right" width={300}>
        {phase === "idle" && (
          <div className="es-loc-pop">
            <div className="es-pop-label"><Icon name="globe" size={13} /> 選擇要產生的語言</div>
            {localized.length > 0 && (
              <div className="es-loc-existing">
                <span className="es-cap es-mut">已在地化：</span>
                <div className="es-row es-gap-xs" style={{ flexWrap: "wrap" }}>
                  {localized.map(c => <LangChip key={c} code={c} />)}
                </div>
              </div>
            )}
            <div className="es-loc-list">
              {targets.length === 0 && <div className="es-cap es-mut" style={{ padding: "8px 4px" }}>所有支援語言皆已產生 🎉</div>}
              {targets.map(l => (
                <button key={l.code} className={"es-loc-opt" + (picked.includes(l.code) ? " is-on" : "")} onClick={() => toggle(l.code)}>
                  <span className="es-checkbox">{picked.includes(l.code) && <Icon name="check" size={13} />}</span>
                  <span className="es-langchip-code">{l.code}</span>
                  <span className="es-grow" style={{ textAlign: "left" }}>{l.native}</span>
                  <span className="es-cap es-mut">{l.label}</span>
                </button>
              ))}
            </div>
            <div className="es-loc-foot">
              <span className="es-cap es-mut">翻譯字幕 · 旁白 · 文字</span>
              <Button variant="accent" size="sm" icon="sparkles" disabled={!picked.length} onClick={run}>
                生成 {picked.length || ""} 種語言
              </Button>
            </div>
          </div>
        )}
        {phase === "running" && (
          <div className="es-loc-running">
            <Spinner size={26} />
            <div className="es-h3" style={{ marginTop: 10 }}>正在生成多語版本…</div>
            <div className="es-row es-gap-xs" style={{ flexWrap: "wrap", justifyContent: "center", marginTop: 8 }}>
              {picked.map(c => <LangChip key={c} code={c} />)}
            </div>
            <div className="es-loc-steps">
              <span><Icon name="check" size={12} /> 翻譯文字</span>
              <span><Spinner size={11} /> 合成旁白</span>
              <span className="es-mut"><Icon name="captions" size={12} /> 對齊字幕</span>
            </div>
          </div>
        )}
        {phase === "done" && (
          <div className="es-loc-done">
            <div className="es-loc-done-ico"><Icon name="check-circle" size={28} /></div>
            <div className="es-h3">已完成 {doneLangs.length} 種語言</div>
            <div className="es-row es-gap-xs" style={{ flexWrap: "wrap", justifyContent: "center", margin: "10px 0 4px" }}>
              {doneLangs.map(c => <LangChip key={c} code={c} />)}
            </div>
            {Object.keys(results).length > 0 && (
              <div className="es-col" style={{ gap: 6, margin: "6px 0 10px" }}>
                {doneLangs.map(c => (
                  <div key={c} className="es-col" style={{ gap: 2, padding: "6px 8px", background: "var(--es-surface-3)", borderRadius: 6 }}>
                    <span className="es-mono es-cap" style={{ color: "var(--es-accent)" }}>{c}</span>
                    <span className="es-body-2 es-clip">{results[c] || "—"}</span>
                  </div>
                ))}
              </div>
            )}
            <p className="es-cap es-mut" style={{ textAlign: "center", marginBottom: 10 }}>標題已由 Gemini 翻譯（示範）；完整成品在地化（字幕/旁白）為後續。</p>
            <div className="es-row es-gap-sm" style={{ justifyContent: "center" }}>
              <Button variant="ghost" size="sm" onClick={reset}>完成</Button>
              <Button variant="accent" size="sm" icon="plus" onClick={() => setPhase("idle")}>再加語言</Button>
            </div>
          </div>
        )}
      </Popover>
    </div>
  );
}

Object.assign(window, { LocalizeMenu, LangChip });
/* eduStudio — App shell: Sidebar, Topbar, ProjectMenu, CostPanel */

// 固定導覽只保留跨工作流程的核心區域。影片／簡報／圖卡／漫畫只在被選中時出現，
// 避免一進站就把所有產製功能攤給使用者。
const WORKSTATIONS = [
  { key: "home",     label: "開始製作", icon: "home",     hue: "var(--es-primary)",     sub: "描述需求 · 選擇成品" },
  { key: "material", label: "Project",  icon: "folder",   hue: "var(--es-ws-material)", sub: "來源 · 素材 · 成品庫" },
  { key: "status",   label: "我的任務", icon: "activity", hue: "var(--es-info)",        sub: "進度 · 審核 · 完成" },
  { key: "publish",  label: "發布",     icon: "upload",   hue: "var(--es-ws-publish)", sub: "YouTube · 匯出 · 分享" },
];

function Brand({ collapsed }) {
  return (
    <div className="es-brand">
      <div className="es-brand-mark"><Icon name="graduation-cap" size={20} /></div>
      {!collapsed && (
        <div className="es-brand-text">
          <span className="es-brand-name">eduStudio</span>
          <span className="es-brand-tag">教學內容工作站</span>
        </div>
      )}
    </div>
  );
}

function Sidebar({ active, currentWorkflow, onNav, collapsed, onToggle, onOpenToolbox }) {
  const workflowItem = currentWorkflow
    ? {
        key: currentWorkflow.route,
        label: currentWorkflow.label,
        icon: currentWorkflow.icon,
        hue: currentWorkflow.hue,
        sub: "目前開啟的製作流程",
      }
    : null;
  const navItems = workflowItem
    ? [WORKSTATIONS[0], workflowItem, ...WORKSTATIONS.slice(1)]
    : WORKSTATIONS;
  return (
    <aside className={"es-sidebar" + (collapsed ? " is-collapsed" : "")}>
      <Brand collapsed={collapsed} />

      <nav className="es-nav">
        {!collapsed && <div className="es-nav-label">工作站</div>}
        {navItems.map(w => (
          <button key={w.key}
            className={"es-nav-item" + (active === w.key ? " is-active" : "")}
            style={{ "--ws-hue": w.hue }}
            onClick={() => onNav(w.key)} title={collapsed ? w.label : undefined}>
            <span className="es-nav-rail" />
            <span className="es-nav-ico"><Icon name={w.icon} size={20} /></span>
            {!collapsed && (
              <span className="es-nav-body">
                <span className="es-nav-name">{w.label}</span>
                <span className="es-nav-sub">{w.sub}</span>
              </span>
            )}
          </button>
        ))}
      </nav>

      <div className="es-sidebar-foot">
        <button className="es-nav-item es-nav-tool" onClick={onOpenToolbox} title={collapsed ? "工具箱" : undefined}>
          <span className="es-nav-ico"><Icon name="book-open" size={20} /></span>
          {!collapsed && <span className="es-nav-body"><span className="es-nav-name">學習工具箱</span></span>}
          {!collapsed && <Badge tone="neutral">3</Badge>}
        </button>
        <button className="es-collapse" onClick={onToggle} title={collapsed ? "展開" : "收合"}>
          <Icon name={collapsed ? "chevron-right" : "panel-left"} size={18} />
        </button>
      </div>
    </aside>
  );
}

// 一門課一個顏色（依 project_id hash 穩定取色）。
const ES_PROJ_HUES = ["var(--es-ws-video)", "var(--es-ws-material)", "var(--es-ws-visual)", "var(--es-accent)", "var(--es-info)", "var(--es-warning)"];
function esProjHue(pid) { let h = 0; for (const c of String(pid || "")) h = (h * 31 + c.charCodeAt(0)) >>> 0; return ES_PROJ_HUES[h % ES_PROJ_HUES.length]; }

function ProjectMenu({ projects, activePid, activeProject, onPick, onCreate }) {
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [nid, setNid] = useState("");
  const [ntitle, setNtitle] = useState("");
  const [err, setErr] = useState("");
  const ref = useRef(null);
  const doCreate = async () => {
    setErr("");
    const res = await onCreate(nid, ntitle);
    if (res && res.ok) { setCreating(false); setNid(""); setNtitle(""); setOpen(false); }
    else setErr((res && res.err) || "建立失敗");
  };
  return (
    <div className="es-projsel" ref={ref}>
      <button className="es-projsel-btn" onClick={() => setOpen(o => !o)}>
        <span className="es-proj-dot" style={{ background: activeProject ? esProjHue(activeProject.project_id) : "var(--es-border-2)" }} />
        <span className="es-projsel-text">
          <span className="es-projsel-name">{activeProject ? activeProject.title : "全部課程"}</span>
          <span className="es-projsel-term">{activeProject
            ? `${(activeProject.sources || []).length} 來源 · ${(activeProject.artifacts || []).length} 成品`
            : "不限課程 · 成品進全域素材庫"}</span>
        </span>
        <Icon name="chevron-down" size={16} className="es-mut" />
      </button>
      <Popover open={open} onClose={() => { setOpen(false); setCreating(false); }} anchorRef={ref} align="left" width={320}>
        <div className="es-pop-label">作用中的課程（一門課＝一工作空間）</div>
        <button className={"es-pop-item" + (!activePid ? " is-active" : "")} onClick={() => { onPick(""); setOpen(false); }}>
          <span className="es-proj-dot" style={{ background: "var(--es-border-2)" }} />
          <span className="es-col" style={{ gap: 1, alignItems: "flex-start" }}>
            <span style={{ fontWeight: 500 }}>全部課程（不限）</span>
            <span className="es-cap es-mut">建立的任務/成品不歸屬特定課程</span>
          </span>
          {!activePid && <Icon name="check" size={16} style={{ marginLeft: "auto", color: "var(--es-primary-soft)" }} />}
        </button>
        {projects.map(p => (
          <button key={p.project_id} className={"es-pop-item" + (p.project_id === activePid ? " is-active" : "")}
            onClick={() => { onPick(p.project_id); setOpen(false); }}>
            <span className="es-proj-dot" style={{ background: esProjHue(p.project_id) }} />
            <span className="es-col" style={{ gap: 1, alignItems: "flex-start" }}>
              <span style={{ fontWeight: 500 }}>{p.title || p.project_id}</span>
              <span className="es-cap es-mut">{(p.sources || []).length} 來源 · {(p.artifacts || []).length} 成品 · {(p.jobs || []).length} 任務</span>
            </span>
            {p.project_id === activePid && <Icon name="check" size={16} style={{ marginLeft: "auto", color: "var(--es-primary-soft)" }} />}
          </button>
        ))}
        <div className="es-pop-sep" />
        {!creating ? (
          <button className="es-pop-item es-pop-item-cta" onClick={() => setCreating(true)}><Icon name="plus" size={16} /> 建立新課程</button>
        ) : (
          <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 6 }}>
            <input className="es-input" style={{ padding: "6px 8px", fontSize: 13 }} placeholder="課程 ID（英數底線，如 statics_2026）" value={nid} onChange={e => setNid(e.target.value)} />
            <input className="es-input" style={{ padding: "6px 8px", fontSize: 13 }} placeholder="課程名稱（如 靜力學 2026）" value={ntitle} onChange={e => setNtitle(e.target.value)} />
            {err && <span className="es-cap" style={{ color: "var(--es-error)" }}>{err}</span>}
            <div className="es-row es-gap-xs">
              <Button variant="primary" size="sm" icon="check" onClick={doCreate}>建立</Button>
              <Button variant="ghost" size="sm" onClick={() => { setCreating(false); setErr(""); }}>取消</Button>
            </div>
          </div>
        )}
      </Popover>
    </div>
  );
}

function Topbar({ projects, activePid, activeProject, onPickProject, onCreateProject, avatarName, wsTitle, usage, onOpenCost, onOpenSettings, theme, onTheme }) {
  const used = usage ? usage.used : 0;
  const budget = usage ? usage.budget : 0;
  const pct = budget ? Math.round((used / budget) * 100) : 0;
  return (
    <header className="es-topbar">
      <div className="es-row es-gap-md">
        <ProjectMenu projects={projects} activePid={activePid} activeProject={activeProject} onPick={onPickProject} onCreate={onCreateProject} />
        <span className="es-topbar-div" />
        <div className="es-ws-crumb">{wsTitle}</div>
      </div>

      <div className="es-search">
        <Icon name="search" size={16} className="es-mut" />
        <input placeholder="搜尋來源、任務、成品…" />
        <kbd>⌘K</kbd>
      </div>

      <div className="es-row es-gap-sm">
        <button className="es-cost-pill" onClick={onOpenCost} title="AI 用量與花費">
          <Icon name="coins" size={15} />
          <span className="es-mono">${used.toFixed(2)}</span>
          <span className="es-cost-track"><span className="es-cost-track-fill" style={{ width: pct + "%" }} /></span>
        </button>
        <ThemeSwitcher theme={theme} onTheme={onTheme} />
        <IconButton icon="settings" title="設定" onClick={onOpenSettings} />
        <Avatar name={avatarName || "師"} />
      </div>
    </header>
  );
}

const ES_STATION_HUE = { video: "var(--es-ws-video)", visual: "var(--es-ws-visual)", language: "var(--es-accent)", material: "var(--es-ws-material)" };

function CostPanel({ open, onClose, usage }) {
  // 全部走後端 /api/usage 真實統計：有呼叫紀錄才有數字，否則顯示空狀態（不再有 mock 示意）。
  const live = usage && usage.count > 0 ? usage : null;
  const used = usage ? usage.used : 0;
  const budget = usage ? usage.budget : 0;
  const byStation = live
    ? live.byStation.map(s => ({ ...s, hue: ES_STATION_HUE[s.key] || "var(--es-fg-2)" }))
    : [];
  const recent = live
    ? live.recent.map(r => ({ label: r.label || (r.kind === "image" ? "圖片生成" : "文字生成"),
        model: r.model || "Gemini", tok: r.station, time: r.time ? new Date(r.time).toLocaleString("zh-TW") : "", amount: r.amount }))
    : [];
  const pct = budget ? Math.round((used / budget) * 100) : 0;
  return (
    <>
      <div className={"es-drawer-scrim" + (open ? " is-open" : "")} onClick={onClose} />
      <aside className={"es-drawer" + (open ? " is-open" : "")} aria-hidden={!open}>
        <div className="es-drawer-head">
          <div className="es-row es-gap-sm"><Icon name="coins" size={18} style={{ color: "var(--es-accent)" }} /><h2 className="es-h2">AI 用量與花費</h2></div>
          <IconButton icon="x" onClick={onClose} />
        </div>
        <div className="es-drawer-body">
          <div className="es-cost-hero">
            <div className="es-row" style={{ justifyContent: "space-between", alignItems: "flex-end" }}>
              <div className="es-col" style={{ gap: 2 }}>
                <span className="es-cap es-mut">本月累計</span>
                <span className="es-cost-big es-mono">${used.toFixed(2)}</span>
              </div>
              <span className="es-cap es-mut">預算 ${budget.toFixed(0)}</span>
            </div>
            <ProgressBar value={pct} tone="accent" height={8} />
            <div className="es-row" style={{ justifyContent: "space-between" }}>
              <span className="es-cap es-mut">已使用 {pct}%</span>
              <Badge tone="accent" icon="zap">{live ? live.count : 0} 次 Gemini 呼叫</Badge>
            </div>
          </div>

          {live ? (
            <>
              <div className="es-cost-sec">
                <div className="es-cost-sec-title">各工作站花費</div>
                {byStation.map(s => {
                  const w = used ? Math.round((s.amount / used) * 100) : 0;
                  return (
                    <div key={s.key} className="es-cost-row">
                      <span className="es-proj-dot" style={{ background: s.hue }} />
                      <span className="es-grow">{s.label}</span>
                      <div className="es-cost-bar"><span style={{ width: w + "%", background: s.hue }} /></div>
                      <span className="es-mono es-cost-amt">${s.amount.toFixed(2)}</span>
                    </div>
                  );
                })}
              </div>

              <div className="es-cost-sec">
                <div className="es-cost-sec-title">近期呼叫</div>
                {recent.map((r, i) => (
                  <div key={i} className="es-cost-call">
                    <div className="es-col" style={{ gap: 2, minWidth: 0 }}>
                      <span className="es-clip" style={{ fontWeight: 500 }}>{r.label}</span>
                      <span className="es-cap es-mut">{r.model} · {r.tok} · {r.time}</span>
                    </div>
                    <span className="es-mono es-cost-amt">${r.amount.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="es-cost-sec">
              <div className="es-cap es-mut" style={{ padding: "8px 0" }}>
                目前還沒有任何 Gemini 呼叫紀錄。產生內容後，這裡會顯示真實的用量與花費。
              </div>
            </div>
          )}

          <div className="es-cost-note">
            <Icon name="alert-triangle" size={14} />
            成本為依用量估算（以 Google 官方定價為準）。預算 ${budget.toFixed(0)} 僅供參考，系統不會自動扣費或擋下呼叫。
          </div>
        </div>
      </aside>
    </>
  );
}

// 學習工具 → 後端 /localization/learning/* 接線設定。
const ES_LEARN_TOOLS = {
  flashcard: {
    endpoint: "/localization/learning/flashcards",
    fields: [{ k: "text", label: "教材內容 / 單字清單", area: true, ph: "貼上要做成單字卡的內容…" }],
    build: (s) => ({ text: s.text || "", target_lang: "zh-TW", source_lang: "auto", count: 5 }),
  },
  writing: {
    endpoint: "/localization/learning/writing-correction",
    fields: [{ k: "text", label: "你的英文寫作", area: true, ph: "貼上要糾錯的英文段落…" }],
    build: (s) => ({ text: s.text || "", lang: "en-US", native_lang: "zh-TW" }),
  },
  convo: {
    endpoint: "/localization/learning/conversation",
    fields: [
      { k: "scenario", label: "情境", ph: "例如：在咖啡廳點餐" },
      { k: "user_message", label: "你的一句話", ph: "用練習語言說一句…" },
    ],
    build: (s) => ({ scenario: s.scenario || "", user_message: s.user_message || "", practice_lang: "en-US", native_lang: "zh-TW", history: "" }),
  },
};

function Toolbox({ open, onClose }) {
  const [active, setActive] = useState(null);
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState("");
  const [err, setErr] = useState("");

  const select = (id) => { setActive(id); setForm({}); setResult(""); setErr(""); };
  const run = async () => {
    const cfg = ES_LEARN_TOOLS[active];
    if (!cfg) return;
    setBusy(true); setErr(""); setResult("");
    try {
      const r = await fetch(cfg.endpoint, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cfg.build(form)),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "執行失敗");
      setResult(data.result || "（無內容）");
    } catch (e) { setErr(String((e && e.message) || e)); }
    finally { setBusy(false); }
  };

  const cfg = active ? ES_LEARN_TOOLS[active] : null;
  return (
    <>
      <div className={"es-drawer-scrim" + (open ? " is-open" : "")} onClick={onClose} />
      <aside className={"es-drawer es-drawer-left" + (open ? " is-open" : "")} aria-hidden={!open}>
        <div className="es-drawer-head">
          <div className="es-row es-gap-sm"><Icon name="book-open" size={18} style={{ color: "var(--es-primary-soft)" }} /><h2 className="es-h2">學習工具箱</h2></div>
          <IconButton icon="x" onClick={onClose} />
        </div>
        <div className="es-drawer-body">
          <p className="es-body-2 es-mut" style={{ marginBottom: 4 }}>由本 Project 的教材延伸的輔助學習工具。</p>
          {TOOLBOX.map(t => (
            <button key={t.id} className={"es-tool-card" + (active === t.id ? " is-active" : "")} onClick={() => select(t.id)}>
              <span className="es-tool-ico"><Icon name={t.icon} size={20} /></span>
              <span className="es-col" style={{ gap: 2, alignItems: "flex-start" }}>
                <span style={{ fontWeight: 600 }}>{t.label}</span>
                <span className="es-cap es-mut">{t.desc}</span>
              </span>
              <Icon name={active === t.id ? "chevron-down" : "chevron-right"} size={18} className="es-mut" style={{ marginLeft: "auto" }} />
            </button>
          ))}

          {cfg && (
            <div style={{ marginTop: 10, padding: 12, border: "1px solid var(--es-border)", borderRadius: 10, display: "flex", flexDirection: "column", gap: 10 }}>
              {cfg.fields.map(f => (
                <Field key={f.k} label={f.label}>
                  {f.area
                    ? <textarea className="es-input" rows={4} placeholder={f.ph} value={form[f.k] || ""} onChange={(e) => setForm(s => ({ ...s, [f.k]: e.target.value }))} style={{ resize: "vertical", width: "100%", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--es-border)", background: "var(--es-bg-1)", color: "var(--es-fg-1)" }} />
                    : <input className="es-input" placeholder={f.ph} value={form[f.k] || ""} onChange={(e) => setForm(s => ({ ...s, [f.k]: e.target.value }))} />}
                </Field>
              ))}
              <Button variant="primary" icon="wand" disabled={busy} onClick={run}>{busy ? <><Spinner size={14} /> 執行中…</> : <>產生</>}</Button>
              {err && <div className="es-cap" style={{ color: "var(--es-error)" }}><Icon name="alert-triangle" size={12} /> {err}</div>}
              {result && <div className="es-cap" style={{ whiteSpace: "pre-wrap", lineHeight: 1.6, padding: 10, background: "var(--es-bg-2)", borderRadius: 8 }}>{result}</div>}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

const THEMES = [
  { key: "aurora", name: "Aurora 極光", desc: "深色 · 紫羅蘭科技 · 圓潤", sw: ["#7C5CFF", "#2DD4BF", "#0B0E14"] },
  { key: "lumen",  name: "Lumen 學刊",  desc: "淺色紙感 · 靛藍襯線編輯感", sw: ["#4F46E5", "#0D9488", "#F3F0E9"] },
  { key: "carbon", name: "Carbon 工坊", desc: "純黑 · 暖橘薄荷 · 方正", sw: ["#FF6A3D", "#2DE1B6", "#0A0A0B"] },
  { key: "soft",   name: "溫潤 Garden", desc: "淺色綠調 · 大圓角 · 柔和陰影 · 親切教育", sw: ["#3F8F6B", "#DB8A3C", "#EFF3EC"] },
];

function ThemeSwitcher({ theme, onTheme }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  return (
    <div className="es-themesel" ref={ref}>
      <button className="es-iconbtn" title="切換風格" onClick={() => setOpen(o => !o)}>
        <Icon name="palette" size={18} />
      </button>
      <Popover open={open} onClose={() => setOpen(false)} anchorRef={ref} align="right" width={272}>
        <div className="es-pop-label"><Icon name="palette" size={13} /> 介面風格（即時切換比較）</div>
        {THEMES.map(t => (
          <button key={t.key} className={"es-theme-opt" + (theme === t.key ? " is-active" : "")}
            onClick={() => { onTheme(t.key); setOpen(false); }}>
            <span className="es-theme-chip">
              {t.sw.map((c, i) => <span key={i} style={{ background: c }} />)}
            </span>
            <span className="es-col" style={{ gap: 2, alignItems: "flex-start" }}>
              <span className="es-theme-name">{t.name}</span>
              <span className="es-theme-desc">{t.desc}</span>
            </span>
            {theme === t.key && <Icon name="check" size={16} style={{ marginLeft: "auto", color: "var(--es-primary-soft)" }} />}
          </button>
        ))}
      </Popover>
    </div>
  );
}

Object.assign(window, { Sidebar, Topbar, CostPanel, Toolbox, ThemeSwitcher, THEMES, WORKSTATIONS });
/* eduStudio — 影片工作站: 建立任務 (選來源/選類型) + 任務列表/狀態 */

function CreateTaskPanel({ onCreate }) {
  const [type, setType] = useState("exam_pdf");
  const [open, setOpen] = useState(true);
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState("");
  const [path, setPath] = useState("");
  const [theme, setTheme] = useState("forest");
  const [busy, setBusy] = useState(false);
  const [voices, setVoices] = useState([]);
  const [voice, setVoice] = useState("");
  // 審查 + 進階選項
  const [reviewOn, setReviewOn] = useState(true);
  const [adv, setAdv] = useState(false);
  const [lengthMode, setLengthMode] = useState("quick");
  const [hardsub, setHardsub] = useState(false);
  const [prependIntro, setPrependIntro] = useState(false);
  const [prependCover, setPrependCover] = useState(false);
  const [appendOutro, setAppendOutro] = useState(false);
  const [aiDiagrams, setAiDiagrams] = useState(false);
  const fileRef = useRef(null);
  const cfg = ES_VIDEO_SOURCES[type];

  // 旁白聲音（全域 tts_config，影響後續生成的影片）。
  useEffect(() => {
    fetch("/voices").then(r => r.json()).then(d => { setVoices(d.voices || []); setVoice(d.current || ""); }).catch(() => {});
  }, []);
  const changeVoice = async (vid) => {
    setVoice(vid);
    try { await fetch("/voices", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ voice_id: vid }) }); } catch {}
  };

  // 切換類型時清掉不適用的輸入。
  const pickType = (k) => { setType(k); setFile(null); setUrl(""); setPath(""); if (fileRef.current) fileRef.current.value = ""; };

  const ready = cfg.mode === "file" ? !!file
    : cfg.mode === "url" ? /^https?:\/\//.test(url.trim())
    : !!path.trim();
  const reviewForced = !!cfg.review;   // exam_pdf 硬規則 #1 強制審查
  const submit = async () => {
    setBusy(true);
    const options = {
      require_review: reviewForced || reviewOn,
      ...(cfg.theme ? { theme } : {}),
      hardsub, prepend_intro: prependIntro, prepend_cover: prependCover,
      append_outro: appendOutro, ai_generate_diagrams: aiDiagrams,
      ...(cfg.theme ? { length_mode: lengthMode } : {}),   // length_mode 只對 repo/document/url
    };
    await onCreate({ type, file, url, path, options });
    setBusy(false);
    setFile(null); setUrl(""); setPath(""); if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <Card className="es-create">
      <button className="es-create-head" onClick={() => setOpen(o => !o)}>
        <span className="es-create-ico"><Icon name="plus" size={18} /></span>
        <span className="es-grow" style={{ textAlign: "left" }}>
          <span className="es-h3">{cfg.tool ? "建立影片 · 影音工具" : "建立教學影片"}</span>
          <span className="es-cap es-mut" style={{ display: "block" }}>{cfg.tool ? "影音工具（配音／會議摘要／歌詞抽取）即時處理，回文字或檔案" : "選來源 → 同一條 AI pipeline 產旁白講解影片（考卷停人工審查）"}</span>
        </span>
        <Icon name={open ? "chevron-down" : "chevron-right"} size={18} className="es-mut" />
      </button>

      {open && (
        <div className="es-create-body">
          <div className="es-create-step">
            <div className="es-step-no">1</div>
            <div className="es-grow">
              <div className="es-field-label" style={{ marginBottom: 10 }}>選擇來源類型</div>
              <div className="es-type-grid">
                {Object.entries(ES_VIDEO_SOURCES).map(([k, t]) => (
                  <button key={k} className={"es-type-card" + (type === k ? " is-active" : "")}
                    style={{ "--ws-hue": t.hue }} onClick={() => pickType(k)}>
                    <span className="es-type-ico"><Icon name={t.icon} size={20} /></span>
                    <span className="es-type-name">{t.label}</span>
                    <span className="es-type-desc">{t.hint}</span>
                    {type === k && <span className="es-type-check"><Icon name="check" size={13} /></span>}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {cfg.tool && (
            <div className="es-create-step">
              <div className="es-step-no">2</div>
              <div className="es-grow">
                <div className="es-field-label" style={{ marginBottom: 6 }}>{cfg.label}<span className="es-cap es-mut" style={{ marginLeft: 8 }}>{cfg.hint}</span></div>
                <MediaToolForm tool={cfg.tool} />
              </div>
            </div>
          )}

          {!cfg.tool && (<>
          <div className="es-create-step">
            <div className="es-step-no">2</div>
            <div className="es-grow">
              <div className="es-field-label" style={{ marginBottom: 10 }}>
                {cfg.mode === "file" ? "上傳來源檔案" : cfg.mode === "url" ? "來源網址" : "來源路徑"}
              </div>
              {cfg.mode === "file" ? (
                <div className="es-src-pick">
                  <input ref={fileRef} type="file" accept={cfg.accept} style={{ display: "none" }}
                    onChange={e => setFile(e.target.files && e.target.files[0] ? e.target.files[0] : null)} />
                  <button className="es-src-opt" onClick={() => fileRef.current && fileRef.current.click()}>
                    <span className="es-src-ico" style={{ color: cfg.hue }}><Icon name="upload" size={16} /></span>
                    <span className="es-grow es-clip" style={{ textAlign: "left" }}>{file ? file.name : "選擇檔案…"}</span>
                    {file && <span className="es-cap es-mut">{(file.size / 1048576).toFixed(1)} MB</span>}
                  </button>
                </div>
              ) : cfg.mode === "url" ? (
                <input type="url" className="es-input" placeholder="https://example.com/article"
                  value={url} onChange={e => setUrl(e.target.value)}
                  style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1px solid var(--es-border)", background: "var(--es-bg-1)", color: "var(--es-fg-1)" }} />
              ) : (
                <input className="es-input" placeholder={type === "song" ? "D:\\path\\to\\song.json" : "D:\\path\\to\\repo"}
                  value={path} onChange={e => setPath(e.target.value)}
                  style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1px solid var(--es-border)", background: "var(--es-bg-1)", color: "var(--es-fg-1)" }} />
              )}
              <div className="es-cap es-mut" style={{ marginTop: 8 }}><Icon name="info" size={12} /> {cfg.hint}</div>
              <div className="es-row es-gap-sm" style={{ marginTop: 10, alignItems: "center", flexWrap: "wrap" }}>
                {voices.length > 0 && (
                  <>
                    <span className="es-cap es-mut"><Icon name="mic" size={12} /> 旁白聲音</span>
                    <select style={{ ...esSelectStyle, width: "auto", maxWidth: 260 }} value={voice} onChange={e => changeVoice(e.target.value)}>
                      {voices.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
                    </select>
                  </>
                )}
                {cfg.theme && (
                  <>
                    <span className="es-cap es-mut" style={{ marginLeft: 8 }}>投影片主題</span>
                    <select style={{ ...esSelectStyle, width: "auto" }} value={theme} onChange={e => setTheme(e.target.value)}>
                      <option value="forest">Forest（教學）</option>
                      <option value="navy">Navy（科技）</option>
                    </select>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="es-create-step">
            <div className="es-step-no">3</div>
            <div className="es-grow">
              <div className="es-field-label" style={{ marginBottom: 10 }}>審查與進階選項</div>
              <label className="es-row es-gap-sm" style={{ cursor: reviewForced ? "not-allowed" : "pointer", alignItems: "flex-start" }}>
                <input type="checkbox" checked={reviewForced || reviewOn} disabled={reviewForced} onChange={e => setReviewOn(e.target.checked)} style={{ marginTop: 3 }} />
                <span>
                  <span style={{ fontWeight: 500 }}>解析完成後先人工審查，再渲染影片</span>
                  <span className="es-cap es-mut" style={{ display: "block" }}>
                    {reviewForced ? "考卷一律需審查（學術誠信，不可關）" : "勾選＝停在審查頁讓你檢查/修改逐段內容；取消＝解析完直接出影片"}
                  </span>
                </span>
              </label>

              <button className="es-row es-gap-xs" style={{ background: "none", border: "none", cursor: "pointer", padding: "10px 0 4px", color: "var(--es-fg-2)" }} onClick={() => setAdv(a => !a)}>
                <Icon name={adv ? "chevron-down" : "chevron-right"} size={15} /> <span className="es-cap">進階選項（封面 / 結尾 / 字幕 / 長度 / 配圖）</span>
              </button>
              {adv && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, paddingLeft: 4 }}>
                  {cfg.theme && (
                    <div className="es-row es-gap-sm" style={{ alignItems: "center" }}>
                      <span className="es-cap es-mut" style={{ width: 84 }}>影片長度</span>
                      <select style={{ ...esSelectStyle, width: "auto" }} value={lengthMode} onChange={e => setLengthMode(e.target.value)}>
                        <option value="ultra_quick">極速（最短）</option>
                        <option value="quick">快速講解（8–15 分）</option>
                        <option value="lecture">完整授課（60–180 分）</option>
                      </select>
                    </div>
                  )}
                  <label className="es-row es-gap-sm es-cap" style={{ cursor: "pointer" }}><input type="checkbox" checked={prependCover} onChange={e => setPrependCover(e.target.checked)} /> 插入封面頁（標題＋設定頁的講者/單位/日期）</label>
                  <label className="es-row es-gap-sm es-cap" style={{ cursor: "pointer" }}><input type="checkbox" checked={appendOutro} onChange={e => setAppendOutro(e.target.checked)} /> 插入結尾頁（謝謝聆聽＋連結）</label>
                  <label className="es-row es-gap-sm es-cap" style={{ cursor: "pointer" }}><input type="checkbox" checked={prependIntro} onChange={e => setPrependIntro(e.target.checked)} /> 串接個人 intro 影片（需先設定 intro 路徑）</label>
                  <label className="es-row es-gap-sm es-cap" style={{ cursor: "pointer" }}><input type="checkbox" checked={hardsub} onChange={e => setHardsub(e.target.checked)} /> 燒錄字幕進影片（離線播放用；YouTube 建議關）</label>
                  <label className="es-row es-gap-sm es-cap" style={{ cursor: "pointer" }}><input type="checkbox" checked={aiDiagrams} onChange={e => setAiDiagrams(e.target.checked)} /> AI 生成架構圖配圖（耗 Gemini 額度）</label>
                </div>
              )}
            </div>
          </div>

          <div className="es-create-foot">
            <div className="es-row es-gap-sm es-mut es-cap">
              <Icon name="sparkles" size={14} style={{ color: "var(--es-primary-soft)" }} />
              {(reviewForced || reviewOn) ? "完成後停在人工審查" : "完成後直接出影片"}
            </div>
            <Button variant="primary" icon="wand" disabled={!ready || busy} onClick={submit}>
              {busy ? "建立中…" : "開始生成"}
            </Button>
          </div>
          </>)}
        </div>
      )}
    </Card>
  );
}

function TaskCard({ task, onReview, onLocalize, onRetry, onCancel, onPublish, onRerender, onDelete }) {
  const tt = esTaskMeta(task.type);
  const isRun = task.status === "running";
  const isReview = task.status === "review";
  const isApproved = task.status === "approved";
  const isFailed = task.status === "failed";
  const canRerender = task.rawState === "done" || task.rawState === "failed";
  const [open, setOpen] = useState(false);
  const [log, setLog] = useState(null);
  const [sections, setSections] = useState(null);
  const [rerendering, setRerendering] = useState("");
  const [versions, setVersions] = useState(null);   // F9-4：重 render 前歸檔的歷史舊版

  // 展開時抓 log tail；running 任務每 4 秒刷新 log。
  useEffect(() => {
    if (!open || !task._job) return;
    let alive = true;
    const fetchLog = () => fetch(`/jobs/${task.id}/log?tail=40`).then(r => r.json())
      .then(d => { if (alive) setLog((d.entries || []).slice(-14)); }).catch(() => {});
    fetchLog();
    if (isRun || task.status === "queued") { const id = setInterval(fetchLog, 4000); return () => { alive = false; clearInterval(id); }; }
    return () => { alive = false; };
  }, [open, task.id, task.status]);

  // 展開且 done/failed → 抓 deck 章節供逐章重渲染。
  useEffect(() => {
    if (!open || !task._job || !canRerender) return;
    let alive = true;
    fetch(`/jobs/${task.id}/draft`).then(r => r.ok ? r.json() : Promise.reject())
      .then(d => { if (alive) setSections(esDeckSections(d.deck || d)); }).catch(() => { if (alive) setSections([]); });
    return () => { alive = false; };
  }, [open, task.id, canRerender]);

  // 展開且 done/failed → 抓歷史版本（F9-4：重 render 前自動歸檔的舊版，可下載比對/回滾）。
  useEffect(() => {
    if (!open || !task._job || !canRerender) return;
    let alive = true;
    fetch(`/jobs/${task.id}/versions`).then(r => r.ok ? r.json() : Promise.reject())
      .then(d => { if (alive) setVersions(d.versions || []); }).catch(() => { if (alive) setVersions([]); });
    return () => { alive = false; };
  }, [open, task.id, canRerender]);

  const rerender = async (sid) => {
    setRerendering(sid);
    try {
      const r = await fetch(`/jobs/${task.id}/sections/${sid}/render`, { method: "POST" });
      if (!r.ok) { let d = r.status; try { d = (await r.json()).detail || d; } catch {} alert("重渲染失敗：" + d); setRerendering(""); return; }
      onRerender && onRerender(task);
    } catch (e) { alert("重渲染錯誤：" + e.message); }
    finally { setRerendering(""); }
  };

  return (
    <Card state={task.status === "queued" ? null : task.status} className="es-task" style={{ display: "block" }}>
      <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
        <div className="es-task-ico" style={{ background: `color-mix(in srgb, ${tt.hue} 16%, transparent)`, color: tt.hue, flexShrink: 0 }}>
          <Icon name={tt.icon} size={20} />
        </div>
        <div className="es-task-main" style={{ flex: 1, minWidth: 0 }}>
          <div className="es-row es-gap-sm" style={{ flexWrap: "wrap" }}>
            <span className="es-task-title">{task.title}</span>
            <Badge tone="neutral">{tt.label}</Badge>
          </div>
          <div className="es-task-meta">
            <span><Icon name="file" size={13} /> {task.source}</span>
            <span className="es-mut">更新於 {task.updated}</span>
          </div>
          {(isRun || task.status === "queued") && (
            <div className="es-task-prog">
              <ProgressBar value={task.progress} tone="primary" />
              <span className="es-mono es-cap">{task.progress}%</span>
              {task.progLabel && <span className="es-cap es-mut"><Spinner size={11} /> {task.progLabel}</span>}
            </div>
          )}
          {isFailed && <div className="es-task-err"><Icon name="alert-triangle" size={14} /> {task.error}</div>}
        </div>
        <div className="es-task-side">
          <StatusPill status={task.status} />
          <div className="es-task-actions">
            {isReview && <Button variant="primary" size="sm" icon="eye" onClick={() => onReview(task)}>開始審查</Button>}
            {isApproved && <>
              <LocalizeMenu localized={task.localized || []} onChange={(l) => onLocalize(task.id, l)} text={task.title} projectId={task.project_id} />
              <Button variant="default" size="sm" icon="upload" onClick={() => onPublish && onPublish(task)}>發布</Button>
            </>}
            {isFailed && <Button variant="default" size="sm" icon="refresh-cw" onClick={() => onRetry && onRetry(task)}>重試</Button>}
            {task.status === "queued" && <Button variant="ghost" size="sm" icon="x" onClick={() => onCancel && onCancel(task)}>取消</Button>}
            {task._job && <Button variant="ghost" size="sm" icon={open ? "chevron-up" : "list"} onClick={() => setOpen(o => !o)}>{open ? "收合" : "詳情"}</Button>}
            {onDelete && task.status !== "queued" && <Button variant="ghost" size="sm" icon="trash-2" onClick={() => onDelete(task)}>刪除</Button>}
          </div>
        </div>
      </div>

      {open && task._job && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--es-border)" }}>
          {task._stages && task._stages.length > 0 && (
            <div className="es-row es-gap-xs" style={{ flexWrap: "wrap", marginBottom: 10 }}>
              {task._stages.map((s, i) => (
                <Badge key={i} tone={s.state === "done" ? "success" : s.state === "running" ? "primary" : s.state === "failed" ? "error" : "neutral"}>
                  {(ES_STAGE_LABEL[s.name] || s.name)}{s.state === "running" ? "…" : s.state === "done" ? " ✓" : ""}
                </Badge>
              ))}
            </div>
          )}
          <div className="es-cap es-mut" style={{ marginBottom: 4 }}>執行紀錄</div>
          <div style={{ fontFamily: "var(--es-font-mono, monospace)", fontSize: 11, lineHeight: 1.6, background: "var(--es-bg-2)", borderRadius: 8, padding: 10, maxHeight: 200, overflow: "auto" }}>
            {log === null ? <span className="es-mut">載入紀錄…</span>
              : log.length === 0 ? <span className="es-mut">尚無紀錄</span>
              : log.map((e, i) => <div key={i} className="es-clip" style={{ color: e.level === "ERROR" ? "var(--es-error)" : "var(--es-fg-2)" }}>{(e.stage ? "[" + (ES_STAGE_LABEL[e.stage] || e.stage) + "] " : "")}{e.msg}</div>)}
          </div>
          {canRerender && sections && sections.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div className="es-cap es-mut" style={{ marginBottom: 6 }}>逐章重渲染（改某章 deck 後只重跑該章，不必整支重來）</div>
              <div className="es-row es-gap-xs" style={{ flexWrap: "wrap" }}>
                {sections.map(s => (
                  <Button key={s.id} variant="ghost" size="sm" icon="refresh-cw" disabled={!!rerendering}
                    onClick={() => rerender(s.id)}>{rerendering === s.id ? "排程中…" : s.title}</Button>
                ))}
              </div>
            </div>
          )}
          {canRerender && versions && versions.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div className="es-cap es-mut" style={{ marginBottom: 6 }}>歷史版本（重 render 前自動歸檔的舊版，可下載比對 / 回滾）</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {versions.map(v => (
                  <div key={v.version} style={{ background: "var(--es-bg-2)", borderRadius: 8, padding: "8px 10px" }}>
                    <div className="es-row es-gap-sm" style={{ flexWrap: "wrap", alignItems: "baseline" }}>
                      <Badge tone="neutral">v{v.version}</Badge>
                      <span className="es-cap es-mut">歸檔於 {v.archived_at ? new Date(v.archived_at).toLocaleString("zh-TW") : "—"}</span>
                      {v.note && <span className="es-cap es-mut">· {v.note}</span>}
                    </div>
                    <div className="es-row es-gap-xs" style={{ flexWrap: "wrap", marginTop: 6 }}>
                      {(v.artifacts || []).length === 0
                        ? <span className="es-cap es-mut">（此版本無可下載產物）</span>
                        : (v.artifacts || []).map(a => (
                          <a key={a.name} className="es-cap es-mut" href={a.url} download
                            style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                            <Icon name="download" size={12} /> {a.name}{a.size_bytes ? ` (${esFmtSize(a.size_bytes)})` : ""}
                          </a>
                        ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="es-row es-gap-sm" style={{ marginTop: 8 }}>
            <a className="es-cap es-mut" href={"/editor/" + task.id} target="_blank" rel="noreferrer"><Icon name="external-link" size={12} /> 在進階編輯器開啟</a>
          </div>
        </div>
      )}
    </Card>
  );
}

/* ── 影片站 / review gate 接 autoSolver 後端（/jobs）── */
const ES_STATE_MAP = { pending: "queued", ingesting: "running", awaiting_review: "review", rendering: "running", done: "approved", failed: "failed" };

function esBasename(p) { return p ? String(p).split(/[\\/]/).pop() : ""; }

// stage 名稱 → 中文標籤（顯示目前在跑哪一步）。
const ES_STAGE_LABEL = { ingest: "解析來源", solve: "AI 解題", outline: "規劃大綱", scriptor: "撰寫旁白",
  script: "撰寫旁白", render: "渲染影片", batch: "渲染影片", tts: "語音合成", upload: "上傳" };

// 從 JobRecord.stages + state 算進度（百分比 + 目前步驟標籤）。
function esJobProgress(rec) {
  const stages = rec.stages || [];
  const total = stages.length || 1;
  const done = stages.filter(s => s.state === "done").length;
  const running = stages.find(s => s.state === "running");
  const st = rec.state;
  let percent, label;
  if (st === "done") { percent = 100; label = "完成"; }
  else if (st === "awaiting_review") { percent = 100; label = "待人工審查"; }
  else if (st === "failed") { percent = Math.round((done / total) * 100); label = "失敗"; }
  else if (st === "pending") { percent = 3; label = "排隊中"; }
  else {
    // ingesting / rendering：用 stage 比例 + 正在跑的步驟名
    percent = Math.max(8, Math.round((done / Math.max(total, 1)) * 100));
    const name = running ? running.name : (st === "rendering" ? "render" : "ingest");
    label = (ES_STAGE_LABEL[name] || name) + "…";
    if (running && running.state === "running") percent = Math.min(96, percent + 8);
  }
  return { percent, label, stage: running ? (ES_STAGE_LABEL[running.name] || running.name) : "" };
}

function esJobToTask(rec) {
  const src = rec.source || {};
  const label = esBasename(src.path) || src.url || rec.source_type || rec.id;
  const prog = esJobProgress(rec);
  return {
    id: rec.id,
    title: String(label).replace(/\.[a-z0-9]+$/i, ""),
    type: rec.source_type || "document",   // 直接帶真實 source_type，TaskCard 以 esTaskMeta 顯示
    status: ES_STATE_MAP[rec.state] || "queued",
    source: esBasename(src.path) || src.url || rec.source_type || "—",
    lang: "zh-TW", updated: rec.updated_at ? new Date(rec.updated_at).toLocaleString("zh-TW") : "",
    cost: 0, model: "Gemini", error: rec.error || "來源或生成發生錯誤", _job: true,
    project_id: rec.project_id || "",   // F9-2g：job 所屬課程，在地化套該課 glossary（F9-2j）
    _stype: rec.source_type, _src: rec.source || {},   // 重試用：保留原始來源
    rawState: rec.state, progress: prog.percent, progLabel: prog.label, stage: prog.stage,
    _stages: rec.stages || [],
  };
}

/* autoSolver deck（exam problems[].steps[] 或 sections）→ review gate 分段。
   formula/values 在 exam deck 無結構化欄位 → 留空，審查頁優雅只顯示 narration。 */
// deck → 可重渲染的章節清單 [{id, title}]（exam problems / deck sections）。
function esDeckSections(deck) {
  if (deck && Array.isArray(deck.problems))
    return deck.problems.map((p, i) => ({ id: p.id || ("q" + i), title: p.number || p.title || ("第 " + (i + 1) + " 題") }));
  if (deck && Array.isArray(deck.sections))
    return deck.sections.map((s, i) => ({ id: s.id || ("s" + i), title: s.title || ("段 " + (i + 1)) }));
  return [];
}

function esDeckToSegments(deck) {
  const segs = [];
  // _path = narration 在 deck 內的容器路徑（存回時依此寫 obj.narration）；_field = 寫哪個欄位。
  if (deck && Array.isArray(deck.problems)) {
    deck.problems.forEach((p, pi) => (p.steps || []).forEach((st, si) =>
      segs.push({ id: (p.id || ("q" + pi)) + "_" + si, t: p.number || ("第 " + (pi + 1) + " 題"),
        status: "pending", confidence: 0.9, narration: st.narration || st.display || "", formula: null, values: [],
        _path: ["problems", pi, "steps", si], _field: st.narration !== undefined ? "narration" : "display",
        // F9-1d: 對應後端 review_assist.check_deck 的 (problem_id, step_index)，給確定性校驗 flag 配位。
        // fallback 與後端一致（`q{idx+1}`，1-indexed）；有 p.id 時直接用 id。
        _pid: p.id || ("q" + (pi + 1)), _sidx: si })));
  } else if (deck && Array.isArray(deck.sections)) {
    deck.sections.forEach((s, si) => {
      const items = s.slides || s.steps || null;
      const key = s.slides ? "slides" : "steps";
      (items || [s]).forEach((sl, li) =>
        segs.push({ id: "s" + si + "_" + li, t: s.title || ("段 " + (si + 1)),
          status: "pending", confidence: 0.9, narration: sl.narration || sl.content || sl.title || "", formula: null, values: [],
          _path: items ? ["sections", si, key, li] : ["sections", si],
          _field: sl.narration !== undefined ? "narration" : (sl.content !== undefined ? "content" : "narration") }));
    });
  }
  if (!segs.length) segs.push({ id: "all", t: "全文", status: "pending", confidence: 0.9,
    narration: (deck && (deck.exam_title || deck.title)) || "（此 job 尚無可審查的逐段內容）", formula: null, values: [] });
  return segs;
}

/* F9-1d: 把後端確定性 review 校驗的可疑點（GET /jobs/{id}/review-flags）配位到分段。
   每個 flag 形如 {problem_id, step_index, kind, severity, message, source}，依 _pid/_sidx 對位。
   flags 只是輔助 reviewer 注意力的提醒 — 不阻擋 approve（硬規則 #1 的權威是人不是校驗器）。 */
function esAttachReviewFlags(segs, flags) {
  if (!Array.isArray(flags) || !flags.length) return segs;
  const byKey = {};
  flags.forEach(f => {
    if (!f || f.problem_id == null) return;
    const k = f.problem_id + "::" + f.step_index;
    (byKey[k] = byKey[k] || []).push(f);
  });
  return segs.map(s => {
    if (s._pid == null) return s;
    const hit = byKey[s._pid + "::" + s._sidx];
    return hit ? { ...s, reviewFlags: hit } : s;
  });
}

// autoSolver 影片來源類型（對齊後端 SourceType）→ 建立路徑。
// file 走 POST /upload（限 exam_pdf/slides_pdf/document）；url/path 走 POST /jobs JSON。
// 這是「教學影片生成」的完整來源；translateGemma 配音/會議在獨立的「影音工具」面板。
const ES_VIDEO_SOURCES = {
  exam_pdf:   { label: "考卷 PDF", icon: "file-text", hue: "var(--es-ws-video)", mode: "file", accept: ".pdf", source_type: "exam_pdf", hint: "逐題解題影片 — 產出停在人工審查", review: true },
  slides_pdf: { label: "簡報 PDF", icon: "presentation", hue: "var(--es-ws-visual)", mode: "file", accept: ".pdf", source_type: "slides_pdf", hint: "簡報逐頁講解影片" },
  document:   { label: "文件", icon: "file", hue: "var(--es-info)", mode: "file", accept: ".pdf,.md,.txt,.markdown", source_type: "document", hint: "PDF / Markdown / TXT → AI 大綱 → 講解影片", theme: true },
  repo:       { label: "程式 Repo", icon: "github", hue: "var(--es-fg-2)", mode: "path", source_type: "repo", hint: "本機資料夾路徑 → 掃檔 → 大綱 → 影片", theme: true },
  url:        { label: "網址文章", icon: "link", hue: "var(--es-accent)", mode: "url", source_type: "url", hint: "文章網址 → 大綱 → 講解影片", theme: true },
  song:       { label: "歌曲 MV", icon: "music", hue: "var(--es-warning)", mode: "path", source_type: "song", hint: "歌曲 song.json（音檔+歌詞軸）→ AI 生圖 MV" },
  // 影音工具（translateGemma 同步端點，回文字/路徑而非 job）併入同一格九宮格，
  // 點到帶 tool 旗標的卡時，CreateTaskPanel 改顯示該工具的表單（非建 job 流程）。
  dub:        { label: "影片配音", icon: "volume", hue: "var(--es-accent)", tool: "dub", hint: "外部影片／連結 → 翻譯配音＋字幕" },
  meeting:    { label: "會議摘要", icon: "message-square", hue: "var(--es-accent)", tool: "meeting", hint: "會議／演講錄音 → 重點摘要" },
  songext:    { label: "歌詞抽取", icon: "align-left", hue: "var(--es-warning)", tool: "song", hint: "歌曲 mp3／mp4 → song.json（給歌曲 MV 用）" },
};
// 任務卡顯示 meta：先查來源類型，退回設計用 TASK_TYPES（mock）。
function esTaskMeta(type) {
  return ES_VIDEO_SOURCES[type] || TASK_TYPES[type] || ES_VIDEO_SOURCES.document;
}

// translateGemma 影音工具的目標語言（hyphen 碼，後端邊界轉 underscore）。
const ES_MEDIA_LANGS = [
  { v: "zh-TW", label: "繁體中文" }, { v: "en-US", label: "English" },
  { v: "ja-JP", label: "日本語" }, { v: "ko-KR", label: "한국어" },
  { v: "vi-VN", label: "Tiếng Việt" }, { v: "es-ES", label: "Español" }, { v: "fr-FR", label: "Français" },
];

// 後端／proxy 發生 500 時不保證 body 是 JSON。先讀文字再嘗試解析，避免真正錯誤被
// `Unexpected token 'I'` 這類二次 JSON parse error 蓋掉。
async function esReadApiResponse(response) {
  const raw = await response.text();
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    const compact = raw.replace(/\s+/g, " ").trim().slice(0, 240);
    throw new Error(`伺服器回傳非 JSON（HTTP ${response.status}）：${compact || "空白回應"}`);
  }
}

// 影音工具表單：配音 / 會議摘要 / 歌詞抽取（translateGemma 同步端點，回文字/路徑非 job）。
// tool 由上層九宮格的卡片決定（"dub" | "meeting" | "song"），不再自帶選擇器。
function MediaToolForm({ tool }) {
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState("");
  const [lang, setLang] = useState("zh-TW");
  const [burn, setBurn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [out, setOut] = useState(null);
  const fileRef = useRef(null);

  // 切換工具卡時清掉上一個工具的輸入/結果。
  useEffect(() => { setFile(null); setUrl(""); setOut(null); setErr(""); if (fileRef.current) fileRef.current.value = ""; }, [tool]);

  const run = async () => {
    setBusy(true); setErr(""); setOut(null);
    try {
      const fd = new FormData();
      let endpoint;
      if (tool === "dub") {
        endpoint = "/localization/dub";
        if (file) fd.append("file", file);
        else if (url.trim()) fd.append("url", url.trim());
        else { setErr("請上傳影片檔或貼連結"); setBusy(false); return; }
        fd.append("target_lang", lang); fd.append("source_lang", "auto"); fd.append("burn_subtitles", burn ? "true" : "false");
      } else if (tool === "meeting") {
        endpoint = "/localization/meeting/summarize";
        if (!file) { setErr("請上傳會議錄音／影片"); setBusy(false); return; }
        fd.append("file", file); fd.append("language", "auto"); fd.append("summary_types", "full_summary");
      } else {
        endpoint = "/localization/song/transcribe";
        if (!file) { setErr("請上傳歌曲 mp3／mp4"); setBusy(false); return; }
        fd.append("file", file); fd.append("language", "auto");
      }
      const r = await fetch(endpoint, { method: "POST", body: fd });
      const data = await esReadApiResponse(r);
      if (!r.ok || data.error) throw new Error(data.detail || data.error || "處理失敗");
      setOut(data);
    } catch (e) { setErr(String((e && e.message) || e)); }
    finally { setBusy(false); }
  };

  // song.json 下載
  const downloadSong = () => {
    if (!out || !out.song) return;
    const blob = new Blob([JSON.stringify(out.song, null, 2)], { type: "application/json" });
    const u = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = u; a.download = (out.song.song_title || "song") + ".json";
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(u);
  };

  return (
        <div style={{ padding: "4px 0", display: "flex", flexDirection: "column", gap: 10 }}>
          <input ref={fileRef} type="file" accept="audio/*,video/*" style={{ display: "none" }}
            onChange={(e) => setFile(e.target.files && e.target.files[0] ? e.target.files[0] : null)} />
          <div className="es-row es-gap-xs" style={{ flexWrap: "wrap" }}>
            <Button variant="default" size="sm" icon="upload" onClick={() => fileRef.current && fileRef.current.click()}>{file ? file.name : (tool === "dub" ? "選影片／音檔…" : tool === "song" ? "選歌曲 mp3／mp4…" : "選錄音／影片…")}</Button>
            {tool === "dub" && <input className="es-input" style={{ flex: 1, minWidth: 160 }} placeholder="或貼 YouTube 連結" value={url} onChange={(e) => setUrl(e.target.value)} />}
          </div>
          <div className="es-row es-gap-sm" style={{ flexWrap: "wrap", alignItems: "center" }}>
            {tool === "dub" && (
              <>
                <span className="es-cap es-mut">目標語言</span>
                <select style={{ ...esSelectStyle, width: "auto" }} value={lang} onChange={(e) => setLang(e.target.value)}>
                  {ES_MEDIA_LANGS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
                </select>
                <label className="es-cap" style={{ display: "flex", gap: 4, alignItems: "center", cursor: "pointer" }}>
                  <input type="checkbox" checked={burn} onChange={(e) => setBurn(e.target.checked)} /> 燒錄字幕
                </label>
              </>
            )}
            <Button variant="primary" size="sm" icon="wand" disabled={busy} onClick={run}>{busy ? <><Spinner size={14} /> 處理中…</> : <>開始處理</>}</Button>
            <span className="es-cap es-mut">＊長任務，可能需數分鐘</span>
          </div>
          {err && <div className="es-cap" style={{ color: "var(--es-error)" }}><Icon name="alert-triangle" size={12} /> {err}</div>}
          {out && tool === "meeting" && (
            <div className="es-cap" style={{ whiteSpace: "pre-wrap", lineHeight: 1.6, padding: 10, background: "var(--es-bg-2)", borderRadius: 8, maxHeight: 320, overflow: "auto" }}>
              <b>摘要</b>（{out.duration ? Math.round(out.duration) + "s · " : ""}{out.language}）{"\n"}{out.summary || "（無摘要）"}
            </div>
          )}
          {out && tool === "dub" && (
            <div className="es-cap" style={{ whiteSpace: "pre-wrap", lineHeight: 1.6, padding: 10, background: "var(--es-bg-2)", borderRadius: 8 }}>
              <b>配音完成</b>（{out.target_lang}）{"\n"}{Object.entries(out.results || {}).map(([k, v]) => `${k}: ${v}`).join("\n") || "（無產出）"}
            </div>
          )}
          {out && tool === "song" && out.song && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div className="es-row es-gap-sm" style={{ alignItems: "center" }}>
                <b className="es-cap">已抽取 {out.segments} 段歌詞</b>
                <Button variant="primary" size="sm" icon="download" onClick={downloadSong}>下載 song.json</Button>
              </div>
              <div className="es-cap" style={{ whiteSpace: "pre-wrap", lineHeight: 1.6, padding: 10, background: "var(--es-bg-2)", borderRadius: 8, maxHeight: 280, overflow: "auto" }}>
                {(out.song.segments || []).map(s => `[${s.start}s–${s.end}s] ${(s.lines || []).join(" / ")}`).join("\n") || "（無歌詞）"}
              </div>
              <div className="es-cap es-mut">下載後存進歌曲資料夾，再用上方「歌曲 MV」來源指向此 song.json（記得補 audio_path / 生圖後可渲染）。</div>
            </div>
          )}
        </div>
  );
}

// AI 提案片單：掃資料夾 → Gemini 建議影片 → 核准建 job（autoSolver /proposals 對等）。
function ProposalsPanel({ onJobCreated }) {
  const [open, setOpen] = useState(false);
  const [proposals, setProposals] = useState([]);
  const [folder, setFolder] = useState("");
  const [scanning, setScanning] = useState(false);
  const [msg, setMsg] = useState("");

  const load = () => fetch("/proposals?only_pending=true").then(r => r.json()).then(d => setProposals(d.proposals || [])).catch(() => {});
  useEffect(() => { if (open) load(); }, [open]);

  const scan = async () => {
    if (!folder.trim()) { setMsg("請輸入資料夾路徑"); return; }
    setScanning(true); setMsg("掃描中…（Gemini 分析每份 PDF，可能數分鐘）");
    try {
      const r = await fetch("/proposals/scan-folder/async", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ folder: folder.trim(), source_type: "auto" }) });
      const d = await r.json();
      if (!r.ok) { setMsg("掃描失敗：" + (d.detail || r.status)); setScanning(false); return; }
      const poll = async () => {
        const s = await fetch("/proposals/scan-status/" + d.scan_id).then(x => x.json()).catch(() => null);
        if (!s) { setScanning(false); return; }
        if (s.state === "done") { setMsg(`掃描完成：掃 ${s.scanned} 份、新增 ${s.new} 個提案`); setScanning(false); load(); return; }
        if (s.state === "failed") { setMsg("掃描失敗：" + (s.error || s.message)); setScanning(false); return; }
        setMsg("掃描中…" + (s.message ? " " + s.message : "")); setTimeout(poll, 3000);
      };
      setTimeout(poll, 2000);
    } catch (e) { setMsg("掃描錯誤：" + e.message); setScanning(false); }
  };
  const approve = async (p) => {
    setMsg("建立中…");
    try {
      const r = await fetch("/proposals/" + p.id + "/approve", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const d = await r.json();
      if (!r.ok) { setMsg("核准失敗：" + (d.detail || r.status)); return; }
      setMsg(`已建立影片任務「${p.suggested_title}」`); load(); onJobCreated && onJobCreated();
    } catch (e) { setMsg("核准錯誤：" + e.message); }
  };
  const ignore = async (p) => { try { await fetch("/proposals/" + p.id + "/ignore", { method: "PATCH" }); load(); } catch {} };

  return (
    <div style={{ marginTop: 18 }}>
      <div className="es-list-head">
        <button className="es-row es-gap-sm" style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }} onClick={() => setOpen(o => !o)}>
          <Icon name={open ? "chevron-down" : "chevron-right"} size={16} className="es-mut" />
          <h2 className="es-h2">AI 提案片單</h2>
          {proposals.length > 0 && <Badge tone="primary">{proposals.length}</Badge>}
        </button>
        <span className="es-cap es-mut">掃資料夾 → Gemini 建議教學影片</span>
      </div>
      {open && (
        <>
          <Card style={{ padding: 12, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
            <input className="es-input" style={{ flex: 1, minWidth: 200 }} placeholder="要掃描的資料夾路徑，例如 D:\teaching\materials"
              value={folder} onChange={e => setFolder(e.target.value)} />
            <Button variant="primary" size="sm" icon="search" disabled={scanning} onClick={scan}>{scanning ? <><Spinner size={14} /> 掃描中…</> : <>掃描</>}</Button>
          </Card>
          {msg && <div className="es-cap es-mut" style={{ marginBottom: 10 }}>{msg}</div>}
          {proposals.length === 0 ? <div className="es-mut es-cap" style={{ padding: 12 }}>尚無待決策提案。掃描資料夾後，Gemini 會在這裡列出建議影片。</div> : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {proposals.map(p => (
                <Card key={p.id} className="es-task" style={{ display: "block" }}>
                  <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                    <div className="es-grow" style={{ minWidth: 0 }}>
                      <div className="es-row es-gap-sm" style={{ flexWrap: "wrap" }}>
                        <span style={{ fontWeight: 600 }}>{p.suggested_title}</span>
                        <Badge tone="neutral">{p.source_type}</Badge>
                        <span className="es-cap es-mut">~{p.estimated_duration_min} 分鐘</span>
                      </div>
                      <div className="es-cap es-mut es-clip" style={{ marginTop: 3 }}><Icon name="file" size={12} /> {esBasename(p.source_file)}</div>
                      {p.reason && <div className="es-cap es-mut" style={{ marginTop: 3 }}>{p.reason}</div>}
                      {p.suggested_chapters && p.suggested_chapters.length > 0 && (
                        <div className="es-cap es-mut" style={{ marginTop: 3 }}>章節：{p.suggested_chapters.slice(0, 5).join("、")}{p.suggested_chapters.length > 5 ? "…" : ""}</div>
                      )}
                    </div>
                    <div className="es-col es-gap-xs" style={{ flexShrink: 0 }}>
                      <Button variant="primary" size="sm" icon="wand" onClick={() => approve(p)}>建立影片</Button>
                      <Button variant="ghost" size="sm" icon="x" onClick={() => ignore(p)}>忽略</Button>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function VideoStation({ projectId, onReview, onGoPublish, onGoStatus }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [usingMock, setUsingMock] = useState(false);
  const [toast, setToast] = useState(null);

  const refresh = () => fetch("/jobs").then(r => r.json()).then(d => {
    const list = (d.jobs || d || []).map(esJobToTask);
    if (list.length) { setTasks(list); setUsingMock(false); }
    else if (!usingMock) { setTasks([]); }
    setLoading(false);
    return list;
  }).catch(() => { setTasks(VIDEO_TASKS); setUsingMock(true); setLoading(false); return []; });

  useEffect(() => { refresh(); }, []);

  // 進度恢復：有 active job（排隊/生成中）時每 4 秒輪詢 /jobs，即時更新狀態與進度。
  const activeRef = useRef(false);
  useEffect(() => { activeRef.current = tasks.some(t => t.status === "running" || t.status === "queued"); }, [tasks]);
  useEffect(() => {
    const id = setInterval(() => { if (activeRef.current) refresh(); }, 4000);
    return () => clearInterval(id);
  }, []);

  const flash = (msg) => { setToast(msg); setTimeout(() => setToast(null), 3200); };

  // 真建 job：file→/upload(multipart)，url/path→/jobs(JSON)。建完 refetch 取真實 JobRecord。
  const create = async ({ type, file, url, path, options }) => {
    const cfg = ES_VIDEO_SOURCES[type];
    const opts = options || {};
    try {
      let res;
      // 有作用中課程 → 任務歸屬該課程：file 帶 project_id 欄位、url/path 改打 /projects/{pid}/jobs。
      const jobUrl = projectId ? "/projects/" + projectId + "/jobs" : "/jobs";
      if (cfg.mode === "file") {
        if (!file) { flash("請先選擇檔案"); return; }
        const fd = new FormData();
        fd.append("file", file);
        fd.append("source_type", cfg.source_type);
        fd.append("options_json", JSON.stringify(opts));
        if (projectId) fd.append("project_id", projectId);
        res = await fetch("/upload", { method: "POST", body: fd });
      } else if (cfg.mode === "url") {
        const u = (url || "").trim();
        if (!/^https?:\/\//.test(u)) { flash("請輸入有效的 http(s) 連結"); return; }
        res = await fetch(jobUrl, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source_type: cfg.source_type, source: { url: u }, options: opts }),
        });
      } else {
        const p = (path || "").trim();
        if (!p) { flash("請輸入來源路徑"); return; }
        res = await fetch(jobUrl, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source_type: cfg.source_type, source: { path: p }, options: opts }),
        });
      }
      if (!res.ok) {
        let detail = res.status;
        try { const e = await res.json(); detail = e.detail || detail; } catch {}
        flash(`建立失敗：${detail}`); return;
      }
      flash(`已建立「${cfg.label}」任務，開始解析…`);
      await refresh();
    } catch (e) {
      flash("建立發生錯誤：" + e.message);
    }
  };

  const localize = (id, langs) => setTasks(t => t.map(x => x.id === id ? { ...x, localized: langs } : x));

  // TaskCard 次要動作
  const goPublish = () => onGoPublish && onGoPublish();
  const cancel = async (task) => {
    if (!task._job) { setTasks(t => t.filter(x => x.id !== task.id)); return; }
    try {
      const r = await fetch("/jobs/" + task.id, { method: "DELETE" });
      if (!r.ok && r.status !== 404) { flash("取消失敗（" + r.status + "）"); return; }
      flash("已取消任務"); await refresh();
    } catch (e) { flash("取消發生錯誤：" + e.message); }
  };
  const retry = async (task) => {
    if (!task._stype || !task._src) { flash("無法重試：缺原始來源"); return; }
    try {
      const r = await fetch("/jobs", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_type: task._stype, source: task._src, options: {} }),
      });
      if (!r.ok) { let d = r.status; try { d = (await r.json()).detail || d; } catch {} flash("重試失敗：" + d); return; }
      flash("已重新建立任務"); await refresh();
    } catch (e) { flash("重試發生錯誤：" + e.message); }
  };

  const counts = tasks.reduce((a, t) => (a[t.status] = (a[t.status] || 0) + 1, a), {});
  // 影片頁下方只顯示「進行中」任務（排隊/生成中）。完整任務管理（詳情/發布/刪除）移到「發布」工作站。
  const activeTasks = tasks.filter(t => t.status === "running" || t.status === "queued");

  return (
    <div className="es-screen">
      <div className="es-screen-head">
        <div>
          <h1 className="es-h1">影片工作站</h1>
          <p className="es-screen-sub">由考卷／講義產旁白教學影片、外部影片配音翻譯、會議摘要與字幕。</p>
        </div>
        <div className="es-row es-gap-xs es-stat-chips">
          <span className="es-stat-chip"><b>{counts.review || 0}</b> 待審查</span>
          <span className="es-stat-chip"><b>{counts.running || 0}</b> 生成中</span>
          <span className="es-stat-chip"><b>{counts.approved || 0}</b> 已核准</span>
        </div>
      </div>

      <CreateTaskPanel onCreate={create} />

      <ProposalsPanel onJobCreated={refresh} />

      <div className="es-list-head">
        <h2 className="es-h2">進行中任務 <span className="es-mut">{activeTasks.length}</span></h2>
        <button className="es-cap es-link" style={{ background: "none", border: "none", cursor: "pointer", color: "var(--es-primary)" }} onClick={() => onGoStatus && onGoStatus()}>
          所有任務（審核 / 發布 / 刪除）→ 製作狀態
        </button>
      </div>

      {loading ? <div className="es-mut" style={{ padding: 24 }}>載入任務…</div> : null}
      {!loading && !activeTasks.length ? (
        <div className="es-mut" style={{ padding: 24 }}>
          目前沒有進行中的任務。{counts.review ? `有 ${counts.review} 個待審查、` : ""}已完成與待審查的任務請到「發布」工作站管理。
        </div>
      ) : null}
      <div className="es-task-list">
        {activeTasks.map(t => <TaskCard key={t.id} task={t} onReview={onReview} onLocalize={localize}
          onRetry={retry} onCancel={cancel} onPublish={goPublish}
          onRerender={() => { flash("已排程重渲染章節"); refresh(); }} />)}
      </div>

      {toast && <div className="es-toast"><Spinner size={15} /> {toast}</div>}
    </div>
  );
}

Object.assign(window, { VideoStation });
/* eduStudio — review gate 審查頁: 逐段內容（含公式/數字）、可編輯、approve/重生
   This is the product differentiator — a human review gate over AI output. */

function ConfidenceMeter({ value }) {
  const pct = Math.round(value * 100);
  const tone = value >= 0.9 ? "success" : value >= 0.8 ? "warning" : "error";
  const label = value >= 0.9 ? "高信心" : value >= 0.8 ? "中信心" : "需注意";
  return (
    <span className={"es-conf es-conf-" + tone} title={`AI 信心 ${pct}%`}>
      <span className="es-conf-dots">
        {[0,1,2,3,4].map(i => <span key={i} className={"es-conf-dot" + (i < Math.round(value*5) ? " on" : "")} />)}
      </span>
      {label} · {pct}%
    </span>
  );
}

function SegmentNav({ segs, active, onPick }) {
  return (
    <div className="es-segnav">
      <div className="es-segnav-head">分段（{segs.length}）</div>
      <div className="es-segnav-list">
        {segs.map((s, i) => (
          <button key={s.id} className={"es-segnav-item" + (i === active ? " is-active" : "") + " st-" + s.status}
            onClick={() => onPick(i)}>
            <span className="es-segnav-dot" />
            <span className="es-grow es-col" style={{ gap: 2, alignItems: "flex-start", minWidth: 0 }}>
              <span className="es-mono es-cap">{s.t}</span>
              <span className="es-segnav-text es-clip">{s.narration}</span>
            </span>
            {s.reviewFlags && s.reviewFlags.length > 0 &&
              <Icon name="alert-triangle" size={14} className="es-segnav-flag"
                title={"確定性校驗標出 " + s.reviewFlags.length + " 個可疑點"} />}
            {s.status === "approved" && <Icon name="check" size={15} className="es-segnav-ok" />}
            {s.flag && s.status !== "approved" && <Icon name="alert-triangle" size={14} className="es-segnav-flag" />}
          </button>
        ))}
      </div>
    </div>
  );
}

function ReviewGate({ task, onClose, onComplete }) {
  const [segs, setSegs] = useState([]);
  const [active, setActive] = useState(0);
  const [editing, setEditing] = useState(false);
  const [regening, setRegening] = useState(false);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const deckRef = useRef(null);   // 原始 deck.json（存回時依 seg._path 寫回 narration）

  // 真實 job → 取 deck.json（autoSolver /jobs/{id}/draft）映射成分段；非 job 或失敗 fallback mock。
  useEffect(() => {
    let alive = true;
    if (task && task._job && task.id) {
      fetch("/jobs/" + task.id + "/draft").then(r => r.ok ? r.json() : Promise.reject())
        .then(d => { if (alive) { const deck = d.deck || d; deckRef.current = deck; setSegs(esDeckToSegments(deck)); setLoading(false); } })
        .catch(() => { if (alive) { setSegs(REVIEW_SEGMENTS.map(s => ({ ...s }))); setLoading(false); } });
      // F9-1d: 取確定性 review 校驗可疑點，配位到分段顯示 ⚠（輔助提醒、不阻擋）。
      // fail-open：抓不到（舊 job / 端點錯）就不顯示，絕不卡審查。
      fetch("/jobs/" + task.id + "/review-flags").then(r => r.ok ? r.json() : { flags: [] })
        .then(d => { const fl = (d && d.flags) || []; if (alive && fl.length) setSegs(cur => esAttachReviewFlags(cur, fl)); })
        .catch(() => {});
    } else { setSegs(REVIEW_SEGMENTS.map(s => ({ ...s }))); setLoading(false); }
    return () => { alive = false; };
  }, [task]);

  // 把目前 segs 的 narration 依 _path 寫回 deck 並 PUT 存回 server（真實 job 才存）。
  const saveDeck = async () => {
    if (!task || !task._job || !deckRef.current) return true;  // mock 視為成功
    const deck = JSON.parse(JSON.stringify(deckRef.current));
    segs.forEach(s => {
      if (!s._path) return;
      let obj = deck;
      for (const k of s._path) { if (obj == null) return; obj = obj[k]; }
      if (obj && typeof obj === "object") obj[s._field || "narration"] = s.narration;
    });
    setSaving(true);
    try {
      const r = await fetch("/jobs/" + task.id + "/draft", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deck }),
      });
      if (!r.ok) return false;
      deckRef.current = deck; setDirty(false); return true;
    } catch { return false; }
    finally { setSaving(false); }
  };

  const seg = segs[active];
  const approvedCount = segs.filter(s => s.status === "approved").length;
  const pct = segs.length ? Math.round((approvedCount / segs.length) * 100) : 0;
  const allDone = segs.length > 0 && approvedCount === segs.length;

  const update = (patch) => { if ("narration" in patch) setDirty(true); setSegs(arr => arr.map((s, i) => i === active ? { ...s, ...patch } : s)); };

  const approve = () => {
    update({ status: "approved", flag: null });
    setEditing(false);
    const next = segs.findIndex((s, i) => i > active && s.status !== "approved");
    if (next !== -1) setTimeout(() => setActive(next), 220);
  };
  // 一次核准全部段（略過逐段檢查）
  const approveAll = () => { setEditing(false); setSegs(arr => arr.map(s => ({ ...s, status: "approved", flag: null }))); };
  const regen = () => {
    setRegening(true);
    setTimeout(() => { setRegening(false); update({ confidence: Math.min(0.99, seg.confidence + 0.12), flag: null, status: "review" }); }, 1500);
  };
  const applySuggest = (idx) => {
    update({
      values: seg.values.map((v, i) => i === idx ? { ...v, v: v.suggest, flag: false, fixed: true } : v),
      formula: seg.formula ? seg.formula.replace(/class='es-flag'/g, "class='es-fixed'") : seg.formula,
      flag: null,
    });
  };

  // 完成 → 先存回修改的 deck（dirty 才存），再 approve（awaiting_review → rendering）。
  const completeAndPublish = async () => {
    if (task && task._job && task.id) {
      setApproving(true);
      if (dirty) { const ok = await saveDeck(); if (!ok) { setApproving(false); alert("存回修改失敗，請重試"); return; } }
      try { await fetch("/jobs/" + task.id + "/approve", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); }
      catch (e) { /* 忽略：approve 失敗仍讓使用者看到完成流程 */ }
      setApproving(false);
    }
    onComplete();
  };

  if (loading || !seg) {
    return (
      <div className="es-gate" data-screen-label="review-gate">
        <header className="es-gate-top">
          <button className="es-gate-back" onClick={onClose}><Icon name="chevron-left" size={18} /> 返回</button>
          <div className="es-gate-titlewrap"><span className="es-gate-title">{task ? task.title : "審查"}</span></div>
        </header>
        <div className="es-gate-body" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div className="es-row es-gap-sm es-mut"><Spinner size={18} /> 載入審查內容…</div>
        </div>
      </div>
    );
  }

  return (
    <div className="es-gate" data-screen-label="review-gate">
      <header className="es-gate-top">
        <button className="es-gate-back" onClick={onClose}><Icon name="chevron-left" size={18} /> 返回</button>
        <div className="es-gate-titlewrap">
          <div className="es-row es-gap-sm">
            <Icon name="eye" size={16} style={{ color: "var(--es-warning)" }} />
            <span className="es-gate-title">{task ? task.title : "解題影片審查"}</span>
            <Badge tone="warning" icon="sigma">含公式 · 需逐段確認</Badge>
          </div>
          <span className="es-cap es-mut">人工審查確保每段公式與數值正確，再行發布 — 這是 eduStudio 的把關環節。</span>
        </div>
        <div className="es-gate-progress">
          <div className="es-col" style={{ gap: 4, alignItems: "flex-end" }}>
            <span className="es-cap es-mut"><b className="es-fg">{approvedCount}</b> / {segs.length} 段已核准</span>
            <div style={{ width: 160 }}><ProgressBar value={pct} tone="success" /></div>
          </div>
          {!allDone && <Button variant="outline" icon="check-circle" onClick={approveAll}>全部核准</Button>}
          <Button variant="success" icon="check-circle" disabled={!allDone || approving} onClick={completeAndPublish}>
            {approving ? <><Spinner size={14} /> 核准中…</> : allDone ? "完成並發布" : "全部核准後完成"}
          </Button>
        </div>
      </header>

      <div className="es-gate-body">
        <SegmentNav segs={segs} active={active} onPick={(i) => { setActive(i); setEditing(false); }} />

        <div className="es-gate-main">
          {/* preview */}
          <div className="es-gate-preview">
            <div className="es-preview-frame">
              <div className="es-preview-badge es-mono">{seg.t}</div>
              <div className="es-preview-center">
                <Icon name="play" size={26} />
                <span className="es-cap es-mut">第 {active + 1} 段預覽 · 1080p</span>
              </div>
              <div className="es-preview-timeline">
                {segs.map((s, i) => (
                  <span key={s.id} className={"es-tl-seg st-" + s.status + (i === active ? " is-active" : "")}
                    style={{ flex: 1 }} onClick={() => setActive(i)} title={s.t} />
                ))}
              </div>
            </div>
          </div>

          {/* segment editor */}
          <div className="es-seg-editor">
            <div className="es-seg-ehead">
              <div className="es-row es-gap-sm">
                <span className="es-mono es-seg-tc">{seg.t}</span>
                <ConfidenceMeter value={seg.confidence} />
              </div>
              <StatusPill status={seg.status === "pending" ? "review" : seg.status} size="sm" />
            </div>

            {seg.flag && (
              <div className="es-seg-warn">
                <Icon name="alert-triangle" size={15} />
                <span>{seg.flag}：偵測到有效位數可能不足，請確認下方標記的數值。</span>
              </div>
            )}

            {/* F9-1d: 確定性 review 校驗（算術／結果↔旁白對齊）標出的可疑點 —
                只提醒、不阻擋 approve（硬規則 #1 的權威是人）。 */}
            {seg.reviewFlags && seg.reviewFlags.length > 0 && (
              <div className="es-reviewflags">
                <div className="es-seg-blabel"><Icon name="shield-alert" size={13} /> 自動校驗提醒 · 待人工確認</div>
                {seg.reviewFlags.map((f, i) => (
                  <div key={i} className={"es-reviewflag es-rf-" + (f.severity === "warn" ? "warn" : "info")}>
                    <Icon name={f.severity === "warn" ? "alert-triangle" : "info"} size={14} className="es-rf-icon" />
                    <span className="es-rf-msg">{f.message}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="es-seg-block">
              <div className="es-seg-blabel"><Icon name="type" size={13} /> 旁白文字
                <button className="es-seg-edit" onClick={() => setEditing(e => !e)}>
                  <Icon name={editing ? "check" : "pencil"} size={13} /> {editing ? "完成" : "編輯"}
                </button>
              </div>
              {editing
                ? <textarea className="es-textarea" value={seg.narration} onChange={e => update({ narration: e.target.value })} />
                : <p className="es-seg-narr">{seg.narration}</p>}
            </div>

            {seg.formula && (
              <div className="es-seg-block">
                <div className="es-seg-blabel"><Icon name="sigma" size={13} /> 公式推導</div>
                {regening
                  ? <div className="es-formula es-formula-regen"><Spinner size={18} /> 重新生成本段…</div>
                  : <div className="es-formula" dangerouslySetInnerHTML={{ __html: seg.formula }} />}
              </div>
            )}

            {seg.values.length > 0 && (
              <div className="es-seg-block">
                <div className="es-seg-blabel"><Icon name="check-circle" size={13} /> 數值核對</div>
                <div className="es-vals">
                  {seg.values.map((v, i) => (
                    <div key={i} className={"es-val" + (v.flag ? " is-flag" : "") + (v.fixed ? " is-fixed" : "")}>
                      <span className="es-mono es-val-k">{v.k}</span>
                      <span className="es-mono es-val-v">{v.v}</span>
                      {v.flag && <>
                        <span className="es-val-sug">建議：<b className="es-mono">{v.suggest}</b></span>
                        <button className="es-val-apply" onClick={() => applySuggest(i)}><Icon name="check" size={12} /> 採用</button>
                      </>}
                      {v.fixed && <Badge tone="success" icon="check">已修正</Badge>}
                      {!v.flag && !v.fixed && <Icon name="check" size={14} className="es-val-ok" />}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="es-seg-actions">
              <Button variant="outline" icon="refresh-cw" onClick={regen} disabled={regening}>重新生成本段</Button>
              {dirty && <Button variant="default" icon="save" onClick={saveDeck} disabled={saving}>{saving ? "儲存中…" : "儲存修改"}</Button>}
              <div className="es-spacer" />
              {active > 0 && <Button variant="ghost" icon="chevron-left" onClick={() => setActive(active - 1)}>上一段</Button>}
              <Button variant="success" icon="check" onClick={approve}>
                {seg.status === "approved" ? "已核准 · 下一段" : "核准本段"}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ReviewGate });
/* eduStudio — 視覺工作站: 選模式（教學簡報／圖卡·海報）+ 輸入 + 預覽 */

function VisualPreview({ mode }) {
  if (mode === "slides") return (
    <div className="es-pv es-pv-slide">
      <div className="es-pv-slide-bar"><span /><span /><span /></div>
      <div className="es-pv-eyebrow">第 7 章 · 動量</div>
      <div className="es-pv-h">動量守恆定律</div>
      <ul className="es-pv-bullets"><li>封閉系統總動量不變</li><li>p = m·v，向量守恆</li><li>碰撞前後動量相等</li></ul>
      <div className="es-pv-foot"><span>eduStudio</span><span className="es-mono">07 / 12</span></div>
    </div>
  );
  // 圖卡 · 海報（合併）：單張視覺預覽
  return (
    <div className="es-pv es-pv-poster">
      <div className="es-pv-eyebrow">2026 期末專題</div>
      <div className="es-pv-h" style={{ fontSize: 26 }}>成果發表會</div>
      <div className="es-pv-poster-img"><Icon name="image" size={28} /></div>
      <div className="es-pv-clist" style={{ flexDirection: "column", gap: 6 }}>
        <div>6/24（三）14:00</div><div>科學館 R201</div>
      </div>
    </div>
  );
}

/* 真實後端 /api/generate 回傳的成品預覽（取代 mock VisualPreview）。
   infographic 模式下傳 selectedSection / onPickSection → 區塊可點選（區域選擇 UI）。 */
function RealPreview({ mode, result, selectedSection, onPickSection }) {
  if (mode === "poster" && result.imageUrl) {
    return <img src={result.imageUrl} alt="圖卡 · 海報" style={{ maxWidth: "100%", maxHeight: 380, borderRadius: 8, objectFit: "contain" }} />;
  }
  if (mode === "infographic" && result.data) {
    const d = result.data;
    const sections = d.sections || [];
    const theme = d.themeColor || "var(--es-ws-material)";
    return (
      <div className="es-pv es-pv-slides" style={{ textAlign: "left", padding: 12, overflow: "auto", maxHeight: 380, width: "100%" }}>
        <div style={{ fontWeight: 700, fontSize: 15, color: theme }}>{d.mainTitle}</div>
        {d.subtitle && <div className="es-cap es-mut" style={{ marginBottom: 8 }}>{d.subtitle} · {sections.length} 區{onPickSection ? "（點選區塊即可逐區微調）" : ""}</div>}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {sections.map((s, i) => (
            <div key={s.id || i} onClick={onPickSection ? () => onPickSection(i) : undefined}
              style={{ border: "1px solid " + (selectedSection === i ? theme : "var(--es-border)"),
                outline: selectedSection === i ? ("2px solid " + theme) : "none",
                borderRadius: 6, overflow: "hidden", background: "var(--es-bg-1)", cursor: onPickSection ? "pointer" : "default" }}>
              {s.imageUrl && <img src={s.imageUrl} alt="" style={{ width: "100%", height: 80, objectFit: "cover" }} />}
              <div style={{ padding: "6px 8px" }}>
                <div className="es-cap es-mut" style={{ fontSize: 10 }}>{i + 1} · {s.iconType}</div>
                <div style={{ fontWeight: 600, fontSize: 12 }}>{s.title}</div>
                <div className="es-cap es-mut es-clip" style={{ fontSize: 10, marginTop: 2 }}>{s.content}</div>
              </div>
            </div>
          ))}
        </div>
        {d.conclusion && <div className="es-cap es-mut" style={{ marginTop: 8, fontStyle: "italic" }}>{d.conclusion}</div>}
      </div>
    );
  }
  if (mode === "slides" && result.data) {
    const d = result.data;
    const slides = d.slides || [];
    const theme = d.themeColor || "var(--es-ws-video)";
    return (
      <div className="es-pv es-pv-slides" style={{ textAlign: "left", padding: 12, overflow: "auto", maxHeight: 380, width: "100%" }}>
        <div style={{ fontWeight: 700, fontSize: 15, color: theme }}>{d.mainTitle}</div>
        {d.subtitle && <div className="es-cap es-mut" style={{ marginBottom: 8 }}>{d.subtitle} · 共 {slides.length} 頁</div>}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 8 }}>
          {slides.map((s, i) => (
            <div key={i} style={{ border: "1px solid var(--es-border)", borderRadius: 6, overflow: "hidden", background: "var(--es-bg-1)" }}>
              {s.imageUrl
                ? <img src={s.imageUrl} alt="" style={{ width: "100%", height: 64, objectFit: "cover" }} />
                : <div style={{ height: 6, background: theme }} />}
              <div style={{ padding: "6px 8px" }}>
                <div className="es-cap es-mut" style={{ fontSize: 10 }}>{i + 1} · {s.layout}</div>
                <div style={{ fontWeight: 600, fontSize: 12 }} className="es-clip">{s.title}</div>
                {s.bulletPoints && s.bulletPoints.length > 0 && (
                  <div className="es-cap es-mut" style={{ fontSize: 10, marginTop: 2 }}>{s.bulletPoints.slice(0, 2).join("、")}</div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }
  return <div className="es-cap es-mut">已生成（此模式暫無圖片預覽）</div>;
}

// 視覺風格選項（對齊後端 presentation_themes 全 16 主題）。custom = 自訂 prompt。
const ES_STYLE_OPTIONS = [
  { v: "professional", label: "💼 專業商務" }, { v: "academic", label: "📚 暖色學術" },
  { v: "forest", label: "🌲 深綠教學" }, { v: "navy", label: "⚓ 深藍科技" },
  { v: "minimalist", label: "✨ 極簡" }, { v: "digital", label: "🌃 科技數位" },
  { v: "vibrant", label: "🎨 活力繽紛" }, { v: "nature", label: "🌿 自然清新" },
  { v: "pastel", label: "🧁 柔和粉彩" }, { v: "ocean", label: "🌊 海洋藍" },
  { v: "sunset", label: "🌅 日落暖橘" }, { v: "lavender", label: "💜 薰衣草" },
  { v: "cyberpunk", label: "⚡ 霓虹賽博" }, { v: "frieren", label: "🪄 幻境風" },
  { v: "naruto", label: "🔥 熱血風" }, { v: "earth", label: "🏔️ 大地色系" },
  { v: "custom", label: "自訂風格…" },
];
const ES_DENSITY_OPTIONS = [{ v: "minimal", label: "極簡" }, { v: "balanced", label: "均衡" }, { v: "detailed", label: "詳細" }];
// 簡報專屬：受眾／目的／語氣／視覺取向／動畫（對齊 infoCard PresentationStylePanel；空＝不指定）。
const ES_AUDIENCE_OPTIONS = ["大學生", "業界工程師", "企業主管", "投資人 / 客戶", "國高中學生"];
const ES_PURPOSE_OPTIONS = ["教學授課", "商業提案", "學術研究報告", "產品發表", "會議彙報"];
const ES_TONE_OPTIONS = ["親切教學", "嚴謹學術", "簡潔商業", "輕鬆科普", "啟發提問", "條列重點"];
const ES_VEMPHASIS_OPTIONS = [{ v: "visual", label: "🖼 圖像豐富" }, { v: "balanced", label: "⚖️ 均衡呈現" }, { v: "text", label: "📋 條列精煉" }];
const ES_ANIM_OPTIONS = [{ v: "fade", label: "淡入" }, { v: "slide", label: "滑入" }, { v: "zoom", label: "縮放" }, { v: "none", label: "無" }];
// 版式：直式＝海報、方形＝圖卡、橫式＝橫幅（合併後用版式區分用途）。
const ES_ASPECT_OPTIONS = [{ v: "vertical", label: "直式（海報）" }, { v: "square", label: "方形（圖卡）" }, { v: "horizontal", label: "橫式" }];
const ES_TYPO_OPTIONS = [{ v: "modern", label: "現代" }, { v: "classic", label: "古典" }, { v: "mono", label: "等寬" }, { v: "handwriting", label: "手寫" }];
// 各模式預設數量；count 拿來當 slideCount(slides)；poster 固定單張。
const ES_DEFAULT_COUNT = { slides: 10, poster: 1 };

const esSelectStyle = { width: "100%", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--es-border)", background: "var(--es-bg-1)", color: "var(--es-fg-1)", cursor: "pointer" };

// 生成依據：依使用者選的模式組 {text, files}。
//  title   = 只用標題（AI 自由發揮，舊教材模式）
//  content = 用內容/檔案（不帶標題，infoCard 原海報模式）
//  auto    = 有內容或檔案就以內容為主（忽略標題），否則退標題
function esBuildGenInput(mode, title, content, files) {
  const c = (content || "").trim(), t = (title || "").trim();
  const fs = files || [];
  if (mode === "title") return { text: t, files: [] };
  if (mode === "content") return { text: c, files: fs };
  // auto
  return (c || fs.length) ? { text: c, files: fs } : { text: t, files: [] };
}
// 讀檔成 base64 inline data（給多模態 Gemini）。
function esReadFileB64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => { const s = String(r.result || ""); resolve({ mimeType: file.type || "application/octet-stream", data: s.split(",")[1] || "", name: file.name }); };
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

function VisualComposer({ projectId, initialMode = "slides" }) {
  const [mode, setMode] = useState(initialMode);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("牛頓三大運動定律");
  const [content, setContent] = useState("");
  const [genSource, setGenSource] = useState("auto");   // 生成依據：title / content / auto
  const [files, setFiles] = useState([]);   // [{mimeType, data(base64), name}]
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");
  const [outlines, setOutlines] = useState(null);   // 兩階段大綱 Stage 1 結果（slides 模式）
  const [outlineBusy, setOutlineBusy] = useState(false);
  const vcFileRef = useRef(null);
  const [style, setStyle] = useState("academic");
  const [customPrompt, setCustomPrompt] = useState("");
  const [count, setCount] = useState(10);
  const [density, setDensity] = useState("balanced");
  const [aspect, setAspect] = useState("vertical");
  const [typography, setTypography] = useState("modern");
  // 簡報受眾／語氣引導（空＝不指定）+ 動畫 + 進階面板展開。
  const [audience, setAudience] = useState("");
  const [purpose, setPurpose] = useState("");
  const [tone, setTone] = useState("");
  const [vemph, setVemph] = useState("");
  const [animation, setAnimation] = useState("fade");
  const [advOpen, setAdvOpen] = useState(false);
  const m = VISUAL_MODES[mode];

  // 模式 → 後端 /api/generate mode。圖卡/海報合併走 poster（單張大圖）；資訊圖卡走 infographic（多區塊）。
  const backendMode = { poster: "poster", slides: "presentation", infographic: "infographic" }[mode] || null;

  // 切模式時重設數量為該模式預設，並清掉上一個結果/大綱。
  const pickMode = (k) => { setMode(k); setResult(null); setErr(""); setOutlines(null); setCount(ES_DEFAULT_COUNT[k] || 1); };

  // 共用生成核心：依使用者選項組 body；extra 可帶 selectedOutline 等覆寫欄位。
  const runGenerate = async (extra) => {
    setErr(""); setResult(null);
    if (!backendMode) { setErr(`${m.label}尚未接後端`); return; }
    setBusy(true);
    try {
      const gi = esBuildGenInput(genSource, title, content, files);
      const body = {
        mode: backendMode, text: gi.text, style,
        customStylePrompt: style === "custom" ? customPrompt : "",
        slideCount: mode === "slides" ? count : 10,
        aspectRatio: aspect, density, typography,
        animation, audience, purpose, tone, visualEmphasis: vemph,
        projectId: projectId || "",   // 有作用中課程→成品掛進該課程
        files: gi.files.map(f => ({ mimeType: f.mimeType, data: f.data })),
        ...(extra || {}),
      };
      const r = await fetch("/api/generate", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok || data.success === false) throw new Error(data.detail || data.error || "生成失敗");
      setResult(data);
    } catch (e) { setErr(String((e && e.message) || e)); }
    finally { setBusy(false); }
  };
  const generate = () => runGenerate();

  // 兩階段 Stage 1：預覽 3 個大綱方案（僅 slides 模式）。
  const previewOutlines = async () => {
    setErr(""); setOutlines(null); setOutlineBusy(true);
    try {
      const r = await fetch("/api/generate", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "outline", text: esBuildGenInput(genSource, title, content, files).text, files: esBuildGenInput(genSource, title, content, files).files.map(f => ({ mimeType: f.mimeType, data: f.data })), style,
          customStylePrompt: style === "custom" ? customPrompt : "", slideCount: mode === "slides" ? count : 10,
          audience, purpose, tone, visualEmphasis: vemph }),
      });
      const data = await r.json();
      if (!r.ok || data.success === false) throw new Error(data.detail || data.error || "大綱生成失敗");
      setOutlines((data.data && data.data.outlines) || []);
    } catch (e) { setErr(String((e && e.message) || e)); }
    finally { setOutlineBusy(false); }
  };
  // Stage 2：用選定大綱完整生成。
  const generateFromOutline = (o) => { setOutlines(null); runGenerate({ selectedOutline: o }); };

  // 簡報 PresentationData → 下載 .pptx（後端 python-pptx 渲染）。
  const exportPptx = async (deck) => {
    try {
      const r = await fetch("/api/export/pptx", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data: deck, filename: deck.mainTitle || title || "presentation" }),
      });
      if (!r.ok) { const e = await r.json().catch(() => ({})); setErr(e.detail || "匯出失敗"); return; }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = (deck.mainTitle || "presentation") + ".pptx";
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { setErr("匯出發生錯誤：" + ((e && e.message) || e)); }
  };

  // 結果分享：POST /api/share → 複製連結。
  const shareResult = async () => {
    if (!result) return;
    try {
      const payload = result.data || result;
      const r = await fetch("/api/share", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: backendMode || mode, title: title || m.label, data: payload }),
      });
      const d = await r.json();
      if (!r.ok || !d.url) throw new Error(d.detail || "分享失敗");
      const full = location.origin + d.url;
      if (navigator.clipboard) navigator.clipboard.writeText(full).then(() => setErr(""), () => {});
      setErr(""); alert("分享連結已複製：\n" + full);
    } catch (e) { setErr("分享發生錯誤：" + ((e && e.message) || e)); }
  };
  // 加入第一個 Project 的成品庫：POST /projects/{pid}/artifacts。
  const ES_MODE_ARTKIND = { poster: "image", slides: "deck", infographic: "infographic" };
  const addToProject = async () => {
    if (!result) return;
    try {
      const list = await fetch("/projects").then(r => r.json());
      const proj = (list || [])[0];
      if (!proj) { setErr("尚無 Project，請先到「素材」工作站建立"); return; }
      const r = await fetch("/projects/" + proj.project_id + "/artifacts", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: ES_MODE_ARTKIND[mode] || "image", produced_by: "infoCard", state: "draft", lang: "zh-TW" }),
      });
      if (!r.ok) { let d = r.status; try { d = (await r.json()).detail || d; } catch {} setErr("加入失敗：" + d); return; }
      setErr(""); alert("已加入 Project「" + (proj.title || proj.project_id) + "」的成品庫");
    } catch (e) { setErr("加入發生錯誤：" + ((e && e.message) || e)); }
  };

  // 單頁微調：對 slides 結果的某頁送修改指令，patch 回 result.data.slides[idx]。
  const [refineOpen, setRefineOpen] = useState(false);
  const [refineIdx, setRefineIdx] = useState(0);
  const [refineInstr, setRefineInstr] = useState("");
  const [refineBusy, setRefineBusy] = useState(false);
  const refineSlide = async () => {
    if (!result || !result.data || !result.data.slides) return;
    const slides = result.data.slides;
    const idx = Math.max(0, Math.min(refineIdx, slides.length - 1));
    if (!refineInstr.trim()) { setErr("請輸入修改指令"); return; }
    setRefineBusy(true); setErr("");
    try {
      const r = await fetch("/api/refine", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slide: slides[idx], instruction: refineInstr,
          slideIndex: idx, totalSlides: slides.length, style: "academic" }),
      });
      const data = await r.json();
      if (!r.ok || data.success === false) throw new Error(data.detail || "微調失敗");
      const next = slides.slice(); next[idx] = data.slide;
      setResult({ ...result, data: { ...result.data, slides: next } });
      setRefineInstr(""); setRefineOpen(false);
    } catch (e) { setErr("微調發生錯誤：" + ((e && e.message) || e)); }
    finally { setRefineBusy(false); }
  };

  // 資訊圖卡逐區 refine：選一個區塊（區域選擇）送修改指令 → POST /api/refine-section →
  // 後端回更新後的「單一區塊」（與 /api/refine 單頁微調同形狀），patch 回
  // result.data.sections[idx]。regenerateImage 可控是否一併重生配圖（省額度）。
  const [secOpen, setSecOpen] = useState(false);
  const [secIdx, setSecIdx] = useState(0);
  const [secInstr, setSecInstr] = useState("");
  const [secRegenImg, setSecRegenImg] = useState(false);
  const [secBusy, setSecBusy] = useState(false);
  const pickSection = (i) => { setSecIdx(i); setSecOpen(true); };
  const refineSection = async () => {
    if (!result || !result.data || !result.data.sections) return;
    const sections = result.data.sections;
    const idx = Math.max(0, Math.min(secIdx, sections.length - 1));
    if (!secInstr.trim()) { setErr("請輸入修改指令"); return; }
    setSecBusy(true); setErr("");
    try {
      const r = await fetch("/api/refine-section", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ section: sections[idx], instruction: secInstr,
          regenerateImage: secRegenImg }),
      });
      const data = await r.json();
      if (!r.ok || data.success === false) throw new Error(data.detail || "逐區微調失敗");
      const next = sections.slice(); next[idx] = data.section;   // 後端回更新後的單一區塊
      setResult({ ...result, data: { ...result.data, sections: next } });
      setSecInstr(""); setSecOpen(false);
    } catch (e) { setErr("逐區微調發生錯誤：" + ((e && e.message) || e)); }
    finally { setSecBusy(false); }
  };

  return (
    <Card className="es-vcomposer">
      <div className="es-vcomposer-grid">
        <div className="es-vc-input">
          <div className="es-field-label" style={{ marginBottom: 10 }}>選擇模式</div>
          <div className="es-vmode-grid">
            {Object.entries(VISUAL_MODES).map(([k, v]) => (
              <button key={k} className={"es-vmode" + (mode === k ? " is-active" : "")} style={{ "--ws-hue": v.hue }} onClick={() => pickMode(k)}>
                <Icon name={v.icon} size={20} />
                <span className="es-vmode-name">{v.label}</span>
                <span className="es-vmode-desc">{v.desc} · 已接後端</span>
              </button>
            ))}
          </div>

          <div className="es-vc-fields">
            <Field label="生成依據" hint="決定 AI 依什麼產生內容">
              <select style={esSelectStyle} value={genSource} onChange={(e) => setGenSource(e.target.value)}>
                <option value="auto">自動（有內容/檔案就以它為主，否則用標題）</option>
                <option value="title">只用標題（AI 自由發揮）</option>
                <option value="content">用內容／上傳檔案（不看標題）</option>
              </select>
            </Field>
            <Field label={genSource === "content" ? "主題 / 標題（此模式不使用）" : "主題 / 標題"}>
              <input className="es-input" value={title} onChange={(e) => setTitle(e.target.value)} disabled={genSource === "content"} style={genSource === "content" ? { opacity: 0.5 } : {}} />
            </Field>
            <Field label="內容（貼上教材／重點）" hint={genSource === "title" ? "此模式不使用內容" : "提供愈完整的內容，生成愈貼近你的教材"}>
              <textarea className="es-input" rows={5} value={content} onChange={(e) => setContent(e.target.value)} disabled={genSource === "title"}
                placeholder="貼上要轉成教學簡報／圖卡／海報的內容…"
                style={{ width: "100%", resize: "vertical", padding: "10px 12px", borderRadius: 8, border: "1px solid var(--es-border)", background: "var(--es-bg-1)", color: "var(--es-fg-1)", lineHeight: 1.6, opacity: genSource === "title" ? 0.5 : 1 }} />
            </Field>
            <Field label="參考檔案（選填，PDF／圖片）" hint="上傳後 AI 會讀取檔案內容生成">
              <input ref={vcFileRef} type="file" accept=".pdf,image/*" multiple style={{ display: "none" }}
                onChange={async (e) => {
                  const picked = Array.from(e.target.files || []);
                  const read = await Promise.all(picked.map(esReadFileB64));
                  setFiles(fs => [...fs, ...read].slice(0, 5));
                  if (vcFileRef.current) vcFileRef.current.value = "";
                }} />
              <div className="es-row es-gap-xs" style={{ flexWrap: "wrap" }}>
                <Button variant="default" size="sm" icon="upload" onClick={() => vcFileRef.current && vcFileRef.current.click()}>選擇檔案</Button>
                {files.map((f, i) => (
                  <Badge key={i} tone="neutral" icon="file">{f.name} <span style={{ cursor: "pointer", marginLeft: 4 }} onClick={() => setFiles(fs => fs.filter((_, j) => j !== i))}>✕</span></Badge>
                ))}
              </div>
            </Field>
            <div className="es-vc-row2">
              <Field label="視覺風格">
                <select style={esSelectStyle} value={style} onChange={(e) => setStyle(e.target.value)}>
                  {ES_STYLE_OPTIONS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
                </select>
              </Field>
              <Field label={mode === "slides" ? "張數" : "數量"}>
                {mode === "slides" ? (
                  <select style={esSelectStyle} value={count} onChange={(e) => setCount(Number(e.target.value))}>
                    {[6, 8, 10, 12, 15, 20].map(n => <option key={n} value={n}>{n} 張</option>)}
                  </select>
                ) : (
                  <div className="es-select-fake">{mode === "infographic" ? "自動分區" : "1 張"}</div>
                )}
              </Field>
            </div>
            {style === "custom" && (
              <Field label="自訂風格描述" hint="例如：水彩手繪、賽博龐克霓虹、復古日系">
                <input className="es-input" value={customPrompt} onChange={(e) => setCustomPrompt(e.target.value)} placeholder="描述你想要的視覺風格…" />
              </Field>
            )}
            <div className="es-vc-row2">
              <Field label="內容密度">
                <select style={esSelectStyle} value={density} onChange={(e) => setDensity(e.target.value)}>
                  {ES_DENSITY_OPTIONS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
                </select>
              </Field>
              {mode === "slides" && (
                <Field label="字型風格">
                  <select style={esSelectStyle} value={typography} onChange={(e) => setTypography(e.target.value)}>
                    {ES_TYPO_OPTIONS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
                  </select>
                </Field>
              )}
              {(mode === "poster" || mode === "infographic") && (
                <Field label="版式" hint="直式＝海報 · 方形＝圖卡">
                  <select style={esSelectStyle} value={aspect} onChange={(e) => setAspect(e.target.value)}>
                    {ES_ASPECT_OPTIONS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
                  </select>
                </Field>
              )}
            </div>

            {/* 簡報專屬：受眾／目的／語氣／視覺取向／動畫（對齊 infoCard 簡報設定面板）。 */}
            {mode === "slides" && (
              <div style={{ marginTop: 4 }}>
                <button className="es-row es-gap-xs" style={{ background: "none", border: "none", cursor: "pointer", padding: "6px 0", color: "var(--es-fg-2)" }} onClick={() => setAdvOpen(a => !a)}>
                  <Icon name={advOpen ? "chevron-down" : "chevron-right"} size={15} /> <span className="es-cap">簡報進階設定（受眾 · 目的 · 語氣 · 視覺取向 · 動畫）</span>
                </button>
                {advOpen && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingTop: 4 }}>
                    <div className="es-vc-row2">
                      <Field label="目標受眾" hint="影響用詞深淺與舉例">
                        <select style={esSelectStyle} value={audience} onChange={(e) => setAudience(e.target.value)}>
                          <option value="">不指定</option>
                          {ES_AUDIENCE_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                      </Field>
                      <Field label="簡報目的">
                        <select style={esSelectStyle} value={purpose} onChange={(e) => setPurpose(e.target.value)}>
                          <option value="">不指定</option>
                          {ES_PURPOSE_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                      </Field>
                    </div>
                    <div className="es-vc-row2">
                      <Field label="語氣風格">
                        <select style={esSelectStyle} value={tone} onChange={(e) => setTone(e.target.value)}>
                          <option value="">不指定</option>
                          {ES_TONE_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                      </Field>
                      <Field label="視覺取向">
                        <select style={esSelectStyle} value={vemph} onChange={(e) => setVemph(e.target.value)}>
                          <option value="">不指定（AI 自選）</option>
                          {ES_VEMPHASIS_OPTIONS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
                        </select>
                      </Field>
                    </div>
                    <Field label="切換動畫" hint="匯出/播放時投影片轉場效果">
                      <select style={esSelectStyle} value={animation} onChange={(e) => setAnimation(e.target.value)}>
                        {ES_ANIM_OPTIONS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
                      </select>
                    </Field>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="es-row es-gap-sm">
            <Button variant="primary" icon="wand" className="es-vc-gen" disabled={busy || outlineBusy} onClick={generate}>
              {busy ? <><Spinner size={16} /> 生成中…</> : <>生成{m.label}</>}
            </Button>
            {mode === "slides" && (
              <Button variant="default" icon="list" disabled={busy || outlineBusy} onClick={previewOutlines}>
                {outlineBusy ? <><Spinner size={15} /> 規劃中…</> : <>先預覽大綱</>}
              </Button>
            )}
          </div>

          {outlines && (
            <div className="es-vc-outlines" style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
              <div className="es-field-label">選擇大綱方案（共 {outlines.length} 個 · 點選即完整生成）</div>
              {outlines.map((o, i) => (
                <button key={o.id || i} className="es-src-opt" style={{ flexDirection: "column", alignItems: "flex-start", padding: 10, height: "auto" }}
                  onClick={() => generateFromOutline(o)} disabled={busy}>
                  <div style={{ fontWeight: 600 }}>{o.label} <span className="es-cap es-mut">· {o.slides ? o.slides.length : 0} 頁 · {o.recommendedAudience || "通用"}</span></div>
                  <div className="es-cap es-mut" style={{ textAlign: "left", marginTop: 2 }}>{o.approach}</div>
                </button>
              ))}
            </div>
          )}
          {err && <div className="es-cap" style={{ color: "var(--es-error)", marginTop: 8, display: "flex", gap: 5, alignItems: "center" }}><Icon name="alert-triangle" size={13} /> {err}</div>}
          {backendMode && <div className="es-cap es-mut" style={{ marginTop: 6 }}>＊真實呼叫合併 server /api/generate（Gemini，可能需數秒）</div>}
        </div>

        <div className="es-vc-preview">
          <div className="es-vc-preview-label"><Icon name="eye" size={13} /> {result ? "生成結果" : "即時預覽"} · {m.label}</div>
          <div className="es-vc-stage">{result
            ? <RealPreview mode={mode} result={result}
                selectedSection={mode === "infographic" && secOpen ? secIdx : -1}
                onPickSection={mode === "infographic" && result.data && result.data.sections ? pickSection : undefined} />
            : <VisualPreview mode={mode} />}</div>
          <div className="es-row es-gap-sm" style={{ justifyContent: "center", flexWrap: "wrap" }}>
            <Button variant="ghost" size="sm" icon="refresh-cw" disabled={busy} onClick={generate}>重新生成</Button>
            {mode === "slides" && result && result.data && result.data.slides ? (
              <Button variant="default" size="sm" icon="pencil" onClick={() => setRefineOpen(o => !o)}>微調單頁</Button>
            ) : null}
            {mode === "infographic" && result && result.data && result.data.sections ? (
              <Button variant="default" size="sm" icon="pencil" onClick={() => setSecOpen(o => !o)}>逐區微調</Button>
            ) : null}
            {mode === "slides" && result && result.data && (
              <Button variant="default" size="sm" icon="download" onClick={() => exportPptx(result.data)}>匯出 PPTX</Button>
            )}
            {result && <span className="es-cap es-mut" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><Icon name="check-circle" size={13} style={{ color: "var(--es-success)" }} /> {projectId ? "已存入此課程素材庫" : "已自動存入素材庫"}</span>}
            {result && <Button variant="default" size="sm" icon="share" onClick={shareResult}>分享</Button>}
          </div>
          {refineOpen && result && result.data && result.data.slides && (
            <div style={{ marginTop: 10, padding: 10, border: "1px solid var(--es-border)", borderRadius: 8, display: "flex", flexDirection: "column", gap: 8 }}>
              <div className="es-field-label">選擇頁面</div>
              <select className="es-input" value={refineIdx} onChange={e => setRefineIdx(Number(e.target.value))}
                style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid var(--es-border)", background: "var(--es-bg-1)", color: "var(--es-fg-1)" }}>
                {result.data.slides.map((s, i) => <option key={i} value={i}>第 {i + 1} 頁 · {s.title}</option>)}
              </select>
              <input className="es-input" placeholder="修改指令，例如：改成更口語、加一個例子、換成圖表"
                value={refineInstr} onChange={e => setRefineInstr(e.target.value)}
                style={{ padding: "8px 10px", borderRadius: 6, border: "1px solid var(--es-border)", background: "var(--es-bg-1)", color: "var(--es-fg-1)" }} />
              <Button variant="primary" size="sm" icon="wand" disabled={refineBusy} onClick={refineSlide}>
                {refineBusy ? <><Spinner size={14} /> 微調中…</> : <>套用微調</>}
              </Button>
            </div>
          )}
          {secOpen && result && result.data && result.data.sections && (
            <div style={{ marginTop: 10, padding: 10, border: "1px solid var(--es-border)", borderRadius: 8, display: "flex", flexDirection: "column", gap: 8 }}>
              <div className="es-field-label">選擇區塊（可直接點上方預覽的區塊）</div>
              <select className="es-input" value={secIdx} onChange={e => setSecIdx(Number(e.target.value))}
                style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid var(--es-border)", background: "var(--es-bg-1)", color: "var(--es-fg-1)" }}>
                {result.data.sections.map((s, i) => <option key={s.id || i} value={i}>第 {i + 1} 區 · {s.title}</option>)}
              </select>
              <input className="es-input" placeholder="修改指令，例如：數字改成 30%、語氣更精簡、換個比喻"
                value={secInstr} onChange={e => setSecInstr(e.target.value)}
                style={{ padding: "8px 10px", borderRadius: 6, border: "1px solid var(--es-border)", background: "var(--es-bg-1)", color: "var(--es-fg-1)" }} />
              <label className="es-row es-gap-xs" style={{ fontSize: 12, color: "var(--es-fg-2)", cursor: "pointer" }}>
                <input type="checkbox" checked={secRegenImg} onChange={e => setSecRegenImg(e.target.checked)} /> 一併重生此區配圖（較耗時／耗額度）
              </label>
              <Button variant="primary" size="sm" icon="wand" disabled={secBusy} onClick={refineSection}>
                {secBusy ? <><Spinner size={14} /> 微調中…</> : <>套用逐區微調</>}
              </Button>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

function VisualCard({ o, onLocalize, projectId = "" }) {
  const m = VISUAL_MODES[o.mode];
  return (
    <Card state={o.status === "queued" ? null : o.status} interactive className="es-vcard">
      <div className="es-vcard-thumb" style={{ "--ws-hue": m.hue }}>
        <Icon name={m.icon} size={26} />
        {o.status === "running" && <div className="es-vcard-run"><Spinner size={14} /> {o.progress}%</div>}
      </div>
      <div className="es-vcard-body">
        <div className="es-row es-gap-xs"><Badge tone="neutral">{m.label}</Badge><StatusPill status={o.status} size="sm" /></div>
        <div className="es-vcard-title">{o.title}</div>
        <div className="es-cap es-mut">{o.meta}{o.localized.length ? ` · ${o.localized.length} 種語言` : ""}</div>
        <div className="es-vcard-foot">
          <LocalizeMenu localized={o.localized} onChange={(l) => onLocalize(o.id, l)} text={o.title} projectId={projectId} />
          <IconButton icon="more-horizontal" />
        </div>
      </div>
    </Card>
  );
}

function VisualStation({ projectId, initialMode = "slides" }) {
  const [outputs, setOutputs] = useState(VISUAL_OUTPUTS);
  const localize = (id, l) => setOutputs(o => o.map(x => x.id === id ? { ...x, localized: l } : x));
  return (
    <div className="es-screen">
      <div className="es-screen-head">
        <div>
          <h1 className="es-h1">視覺工作站</h1>
          <p className="es-screen-sub">教學簡報、資訊圖卡與海報 — 由教材一鍵生成可審查的視覺成品。</p>
        </div>
      </div>
      <VisualComposer projectId={projectId} initialMode={initialMode} />
      <div className="es-list-head"><h2 className="es-h2">視覺成品</h2></div>
      <div className="es-vgrid">
        {outputs.map(o => <VisualCard key={o.id} o={o} onLocalize={localize} projectId={projectId} />)}
      </div>
    </div>
  );
}

Object.assign(window, { VisualStation });
/* eduStudio — 素材 · Project: 來源清單 + 跨類型成品庫 */

const IMPORT_KINDS = [
  { icon: "file-text", label: "PDF / 文件", hue: "var(--es-error)" },
  { icon: "github",    label: "程式 Repo", hue: "var(--es-fg-2)" },
  { icon: "link",      label: "網址 / 影片連結", hue: "var(--es-info)" },
  { icon: "film",      label: "影片檔", hue: "var(--es-ws-video)" },
  { icon: "image",     label: "圖片", hue: "var(--es-ws-visual)" },
  { icon: "mic",       label: "音訊", hue: "var(--es-accent)" },
];

const LIB_KIND_META = {
  video:    { label: "影片", icon: "video", hue: "var(--es-ws-video)" },
  slides:   { label: "簡報", icon: "presentation", hue: "var(--es-ws-video)" },
  card:     { label: "圖卡", icon: "layout-grid", hue: "var(--es-ws-material)" },
  subtitle: { label: "字幕", icon: "captions", hue: "var(--es-info)" },
};

// autoSolver source/artifact → 前端顯示類型對應。
const ES_SRC_KIND = { exam_pdf: "pdf", slides_pdf: "pdf", document: "pdf", repo: "repo", url: "url", youtube: "url" };
const ES_ART_KIND = { video: "video", deck: "slides", srt: "subtitle", infographic: "card", image: "card" };
const ES_ART_STATUS = { draft: "draft", awaiting_review: "review", approved: "approved", published: "published" };

// 匯入來源的後端 SourceType 選項。
const ES_SOURCE_TYPE_OPTS = [
  { v: "exam_pdf", label: "考卷 PDF" }, { v: "slides_pdf", label: "簡報 PDF" },
  { v: "document", label: "文件" }, { v: "repo", label: "程式 Repo" },
  { v: "url", label: "網址" }, { v: "youtube", label: "YouTube" },
];

const VLIB_TYPE_META = {
  poster: { label: "圖卡 · 海報", icon: "image", hue: "var(--es-ws-visual)" },
  presentation: { label: "教學簡報", icon: "presentation", hue: "var(--es-ws-video)" },
  infographic: { label: "資訊圖卡", icon: "layout-grid", hue: "var(--es-ws-material)" },
};

// 開圖：Chrome 禁止 window.open() 直接導向 data: URL（會「無法連上這個網站」），
// 先把 data URL 轉成 Blob URL 再開新分頁（blob: 允許頂層導覽）。非 data: 直接開。
function esOpenImage(src) {
  if (!src) return;
  if (!src.startsWith("data:")) { window.open(src, "_blank"); return; }
  try {
    const [head, b64] = src.split(",");
    const mime = (head.match(/data:([^;]+)/) || [])[1] || "image/png";
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    const url = URL.createObjectURL(new Blob([arr], { type: mime }));
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 60000);   // 留時間讓新分頁載入
  } catch (e) {
    window.open(src, "_blank");   // 退回原本行為
  }
}

// 視覺素材縮圖卡（素材庫 / 課程成品共用）。
function VlibCard({ item, onDelete }) {
  const t = VLIB_TYPE_META[item.type] || VLIB_TYPE_META.poster;
  return (
    <Card style={{ padding: 0, overflow: "hidden" }}>
      <div style={{ position: "relative", aspectRatio: "1 / 1", background: "var(--es-bg-2)", display: "flex", alignItems: "center", justifyContent: "center", cursor: item.thumb ? "pointer" : "default" }}
        onClick={() => esOpenImage(item.thumb)}>
        {item.thumb
          ? <img src={item.thumb} alt={item.title} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          : <Icon name={t.icon} size={28} style={{ color: t.hue }} />}
        <span style={{ position: "absolute", top: 6, left: 6, background: "rgba(0,0,0,.55)", color: "#fff", borderRadius: 5, padding: "1px 6px", fontSize: 10 }}>{t.label}</span>
      </div>
      <div style={{ padding: "8px 10px" }}>
        <div className="es-clip" style={{ fontWeight: 500, fontSize: 13 }}>{item.title || t.label}</div>
        <div className="es-row es-gap-xs" style={{ marginTop: 4, justifyContent: "space-between", alignItems: "center" }}>
          <span className="es-cap es-mut">{item.created_at ? new Date(item.created_at * 1000).toLocaleDateString("zh-TW") : ""}</span>
          {onDelete && <IconButton icon="trash-2" title="刪除素材" onClick={() => onDelete(item.id)} />}
        </div>
      </div>
    </Card>
  );
}

// 課程術語表編輯器（F9-2）：一課一份 glossary，逐角色固定譯名/讀音/縮寫展開，給旁白與翻譯
// 套用以保術語一致。後端 GET/PUT /projects/{pid}/glossary 已就緒，這裡只做整張載入→編輯→覆寫存回。
const ES_GLOSS_INPUT = { width: "100%", padding: "6px 8px", borderRadius: 7, border: "1px solid var(--es-border)", background: "var(--es-bg-1)", color: "var(--es-fg-1)", fontSize: 13 };
const esGlossBlankEntry = () => ({ term: "", reading: "", expansion: "", aliases: "", note: "", translations: [] });
// API entry（aliases 陣列 / translations dict）↔ 表單形（aliases 字串 / translations 列）互轉。
const esGlossFromApi = (e) => ({
  term: e.term || "", reading: e.reading || "", expansion: e.expansion || "", note: e.note || "",
  aliases: (e.aliases || []).join("、"),
  translations: Object.entries(e.translations || {}).map(([lang, name]) => ({ lang, name })),
});
const esGlossToApi = (e) => {
  const translations = {};
  (e.translations || []).forEach(t => { const l = (t.lang || "").trim(); const n = (t.name || "").trim(); if (l && n) translations[l] = n; });
  const out = { term: e.term.trim(), aliases: e.aliases.split(/[、,\n]/).map(s => s.trim()).filter(Boolean), translations };
  if (e.reading.trim()) out.reading = e.reading.trim();
  if (e.expansion.trim()) out.expansion = e.expansion.trim();
  if (e.note.trim()) out.note = e.note.trim();
  return out;
};

function GlossaryEditor({ projectId, projectTitle, onFlash }) {
  const [open, setOpen] = useState(false);
  const [course, setCourse] = useState("");
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  // 切換作用中課程→重載該課術語表。404「此課尚未建立」＝開一張空表起頭（course 預設課名）。
  useEffect(() => {
    if (!projectId) { setEntries([]); setCourse(""); return; }
    setLoading(true);
    fetch("/projects/" + projectId + "/glossary").then(async r => {
      if (r.status === 404) { setCourse(projectTitle || projectId); setEntries([]); return; }
      if (!r.ok) { onFlash && onFlash("讀取術語表失敗（" + r.status + "）"); return; }
      const d = await r.json();
      setCourse(d.course || projectTitle || projectId);
      setEntries((d.entries || []).map(esGlossFromApi));
    }).catch(() => onFlash && onFlash("讀取術語表發生錯誤"))
      .finally(() => setLoading(false));
  }, [projectId]);

  const patchEntry = (i, k, v) => setEntries(es => es.map((e, j) => j === i ? { ...e, [k]: v } : e));
  const addEntry = () => { setEntries(es => [...es, esGlossBlankEntry()]); setOpen(true); };
  const removeEntry = (i) => setEntries(es => es.filter((_, j) => j !== i));
  const addTrans = (i) => patchEntry(i, "translations", [...(entries[i].translations || []), { lang: "", name: "" }]);
  const patchTrans = (i, ti, k, v) => patchEntry(i, "translations", entries[i].translations.map((t, j) => j === ti ? { ...t, [k]: v } : t));
  const removeTrans = (i, ti) => patchEntry(i, "translations", entries[i].translations.filter((_, j) => j !== ti));

  const save = async () => {
    // term 為所有 map 的 key、後端驗證非空（空 term→422），存檔前先濾掉沒填 term 的列。
    const valid = entries.filter(e => e.term.trim());
    const payload = { course: (course.trim() || projectTitle || projectId), entries: valid.map(esGlossToApi) };
    setBusy(true);
    try {
      const r = await fetch("/projects/" + projectId + "/glossary", {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!r.ok) { let d = r.status; try { d = (await r.json()).detail || d; } catch {} onFlash && onFlash("儲存術語表失敗：" + d); return; }
      const d = await r.json();
      setEntries((d.entries || []).map(esGlossFromApi));   // 以後端回存的整張為準（已濾過空 term）
      onFlash && onFlash("已儲存術語表（" + (d.entries || []).length + " 條）");
    } catch (e) { onFlash && onFlash("儲存發生錯誤：" + e.message); }
    finally { setBusy(false); }
  };

  if (!projectId) return null;
  const transLangs = LANGS.filter(l => !l.source);
  return (
    <Card style={{ marginTop: 18, padding: 14 }}>
      <div className="es-row" style={{ justifyContent: "space-between", alignItems: "center", cursor: "pointer" }} onClick={() => setOpen(o => !o)}>
        <div className="es-row es-gap-sm" style={{ alignItems: "center" }}>
          <Icon name="book-open" size={16} style={{ color: "var(--es-fg-2)" }} />
          <h2 className="es-h2" style={{ margin: 0 }}>課程術語表 {entries.length > 0 && <span className="es-mut">{entries.length}</span>}</h2>
        </div>
        <Icon name={open ? "chevron-up" : "chevron-down"} size={18} style={{ color: "var(--es-fg-2)" }} />
      </div>
      <div className="es-cap es-mut" style={{ marginTop: 4 }}>固定譯名 / 讀音 / 縮寫展開，逐課一份；產旁白與翻譯時套用以保術語一致。</div>

      {open && (
        <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 10 }}>
          {loading ? <div className="es-mut" style={{ padding: 8 }}>載入術語表…</div> : (
            <>
              <Field label="課名（glossary.course）"><input style={ES_GLOSS_INPUT} value={course} onChange={e => setCourse(e.target.value)} placeholder={projectTitle || projectId} /></Field>
              {entries.length === 0 && <div className="es-mut" style={{ padding: "4px 0" }}>尚無術語。按下方「新增術語」開始建立這門課的固定譯名 / 讀音。</div>}
              {entries.map((e, i) => (
                <div key={i} style={{ border: "1px solid var(--es-border)", borderRadius: 9, padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                  <div className="es-row es-gap-xs" style={{ alignItems: "flex-end" }}>
                    <Field label="術語" className="es-grow"><input style={ES_GLOSS_INPUT} value={e.term} onChange={ev => patchEntry(i, "term", ev.target.value)} placeholder="自然頻率 / ω_n / PID" /></Field>
                    <IconButton icon="trash-2" title="刪除這條術語" onClick={() => removeEntry(i)} />
                  </div>
                  <div className="es-row es-gap-xs" style={{ flexWrap: "wrap" }}>
                    <Field label="讀音（TTS 覆寫）" className="es-grow"><input style={ES_GLOSS_INPUT} value={e.reading} onChange={ev => patchEntry(i, "reading", ev.target.value)} placeholder="P I D 控制器" /></Field>
                    <Field label="縮寫全稱" className="es-grow"><input style={ES_GLOSS_INPUT} value={e.expansion} onChange={ev => patchEntry(i, "expansion", ev.target.value)} placeholder="比例-積分-微分" /></Field>
                  </div>
                  <Field label="別名 / 變體（逗號或、分隔）"><input style={ES_GLOSS_INPUT} value={e.aliases} onChange={ev => patchEntry(i, "aliases", ev.target.value)} placeholder="wn、ωn、ω_n" /></Field>
                  <div>
                    <span className="es-field-label">固定譯名（逐語言）</span>
                    {(e.translations || []).map((t, ti) => (
                      <div key={ti} className="es-row es-gap-xs" style={{ marginTop: 4, alignItems: "center" }}>
                        <select style={{ ...ES_GLOSS_INPUT, width: "auto" }} value={t.lang} onChange={ev => patchTrans(i, ti, "lang", ev.target.value)}>
                          <option value="">語言…</option>
                          {transLangs.map(l => <option key={l.code} value={l.code}>{l.label}（{l.code}）</option>)}
                        </select>
                        <input style={ES_GLOSS_INPUT} value={t.name} onChange={ev => patchTrans(i, ti, "name", ev.target.value)} placeholder="natural frequency" />
                        <IconButton icon="x" title="移除此譯名" onClick={() => removeTrans(i, ti)} />
                      </div>
                    ))}
                    <Button variant="ghost" size="sm" icon="plus" style={{ marginTop: 6 }} onClick={() => addTrans(i)}>加譯名</Button>
                  </div>
                  <Field label="備註（純維護用）"><input style={ES_GLOSS_INPUT} value={e.note} onChange={ev => patchEntry(i, "note", ev.target.value)} placeholder="僅供維護參考，不參與替換" /></Field>
                </div>
              ))}
              <div className="es-row es-gap-sm" style={{ alignItems: "center", flexWrap: "wrap" }}>
                <Button variant="default" size="sm" icon="plus" onClick={addEntry}>新增術語</Button>
                <Button variant="primary" size="sm" icon="check" disabled={busy} onClick={save}>{busy ? "儲存中…" : "儲存術語表"}</Button>
              </div>
            </>
          )}
        </div>
      )}
    </Card>
  );
}

// 素材 · 課程工作空間：由右上「作用中課程」驅動。選課→看該課的 來源/任務/成品；全部→全域素材庫。
function ProjectStation({ activePid, projects, onProjectsChanged, onPickProject }) {
  const [sources, setSources] = useState([]);
  const [artifacts, setArtifacts] = useState([]);    // 課程成品（含 links.library_id）
  const [jobs, setJobs] = useState([]);               // 課程任務（已解析 /jobs）
  const [vlib, setVlib] = useState([]);               // 全域視覺素材庫（也供課程成品取縮圖）
  const [toast, setToast] = useState(null);
  const [impType, setImpType] = useState("document");
  const [impVal, setImpVal] = useState("");
  const flash = (msg) => { setToast(msg); setTimeout(() => setToast(null), 3000); };

  const activeProject = (projects || []).find(p => p.project_id === activePid) || null;

  const loadVlib = () => fetch("/api/visual-library").then(r => r.json())
    .then(d => setVlib(d.items || [])).catch(() => {});
  const loadNotebook = (id) => {
    if (!id) { setSources([]); setArtifacts([]); setJobs([]); return; }
    fetch("/projects/" + id + "/notebook").then(r => r.json()).then(async nb => {
      setSources((nb.sources || []).map(s => ({
        id: s.source_id, name: esBasename(s.path_or_url) || s.path_or_url || s.source_id,
        type: ES_SRC_KIND[s.type] || "pdf", meta: s.type + (s.lang ? " · " + s.lang : ""),
        added: s.indexed ? "已索引" : "已掛入",
      })));
      setArtifacts(nb.artifacts || []);
      const jobIds = new Set(nb.jobs || []);
      if (jobIds.size) {
        const all = await fetch("/jobs").then(r => r.json()).then(d => (d.jobs || d || [])).catch(() => []);
        setJobs(all.filter(j => jobIds.has(j.id)).map(esJobToTask));
      } else setJobs([]);
    }).catch(() => { setSources([]); setArtifacts([]); setJobs([]); });
  };
  useEffect(() => { loadVlib(); }, []);
  useEffect(() => { loadNotebook(activePid); }, [activePid]);

  const vlibById = {}; vlib.forEach(v => { vlibById[v.id] = v; });
  // 課程成品（有 library_id 且素材庫還在的視覺成品）→ 取縮圖。
  const courseVisuals = artifacts
    .map(a => vlibById[(a.links || {}).library_id])
    .filter(Boolean);

  const deleteVlib = async (id) => {
    try {
      const r = await fetch("/api/visual-library/" + id, { method: "DELETE" });
      if (!r.ok) { flash("刪除失敗（" + r.status + "）"); return; }
      flash("已刪除素材"); loadVlib();
    } catch (e) { flash("刪除發生錯誤：" + e.message); }
  };
  const addSource = async () => {
    if (!activePid) { flash("請先在右上選或建立課程"); return; }
    const val = impVal.trim(); if (!val) { flash("請填路徑或網址"); return; }
    try {
      const r = await fetch("/projects/" + activePid + "/sources", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: impType, path_or_url: val, lang: "zh-TW" }),
      });
      if (!r.ok) { let d = r.status; try { d = (await r.json()).detail || d; } catch {} flash("匯入失敗：" + d); return; }
      setImpVal(""); flash("已匯入來源"); loadNotebook(activePid);
    } catch (e) { flash("匯入發生錯誤：" + e.message); }
  };
  const removeSource = async (sid) => {
    try {
      const r = await fetch("/projects/" + activePid + "/sources/" + sid, { method: "DELETE" });
      if (!r.ok && r.status !== 404) { flash("刪除失敗（" + r.status + "）"); return; }
      flash("已移除來源"); loadNotebook(activePid);
    } catch (e) { flash("刪除發生錯誤：" + e.message); }
  };

  return (
    <div className="es-screen">
      <div className="es-screen-head">
        <div>
          <h1 className="es-h1">{activeProject ? activeProject.title + " · 工作空間" : "素材 · 課程工作空間"}</h1>
          <p className="es-screen-sub">{activeProject
            ? "這門課的來源、任務與成品集中管理（在右上切換或新建課程）。"
            : "一門課＝一個工作空間。右上選一門課即可看該課的來源/任務/成品；未選課時下方為全部視覺素材庫。"}</p>
        </div>
      </div>

      {!activePid ? (
        <>
          {/* 全部：全域視覺素材庫 */}
          <div className="es-list-head" style={{ marginTop: 4 }}>
            <h2 className="es-h2">視覺素材庫 {vlib.length > 0 && <span className="es-mut">{vlib.length}</span>}</h2>
            <span className="es-cap es-mut">所有生成成品（不限課程）· 生成成功即自動保存</span>
          </div>
          {vlib.length === 0
            ? <div className="es-mut" style={{ padding: "6px 0 16px" }}>尚無視覺素材。到「視覺」工作站生成圖卡／海報／簡報，成功後會自動出現在這裡。</div>
            : <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 12 }}>
                {vlib.map(a => <VlibCard key={a.id} item={a} onDelete={deleteVlib} />)}
              </div>}
        </>
      ) : (
        <div className="es-proj-grid">
          {/* sources */}
          <div className="es-proj-col">
            <div className="es-list-head"><h2 className="es-h2">來源素材 <span className="es-mut">{sources.length}</span></h2></div>
            <Card className="es-import" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div className="es-cap es-mut">匯入來源到「{activeProject ? activeProject.title : activePid}」（檔案填 server 路徑，或貼網址 / Repo / YouTube）</div>
              <div className="es-row es-gap-xs" style={{ flexWrap: "wrap" }}>
                <select style={{ ...esSelectStyle, width: "auto" }} value={impType} onChange={(e) => setImpType(e.target.value)}>
                  {ES_SOURCE_TYPE_OPTS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
                </select>
                <input className="es-input" style={{ flex: 1, minWidth: 160 }} value={impVal} onChange={(e) => setImpVal(e.target.value)}
                  placeholder={impType === "url" || impType === "youtube" || impType === "repo" ? "https://…" : "/path/to/file.pdf"} />
                <Button variant="primary" size="sm" icon="plus" onClick={addSource}>匯入</Button>
              </div>
            </Card>
            <div className="es-src-list">
              {sources.length === 0 && <div className="es-mut" style={{ padding: 12 }}>尚無來源。上方匯入這門課的教材。</div>}
              {sources.map(s => {
                const st = SOURCE_TYPES[s.type] || SOURCE_TYPES.pdf;
                return (
                  <div key={s.id} className="es-src-row">
                    <span className="es-src-rowico" style={{ background: `color-mix(in srgb, ${st.hue} 16%, transparent)`, color: st.hue }}><Icon name={st.icon} size={16} /></span>
                    <div className="es-grow" style={{ minWidth: 0 }}>
                      <div className="es-clip" style={{ fontWeight: 500 }}>{s.name}</div>
                      <div className="es-cap es-mut">{st.label} · {s.meta} · {s.added}</div>
                    </div>
                    <IconButton icon="trash-2" title="移除來源" onClick={() => removeSource(s.id)} />
                  </div>
                );
              })}
            </div>
          </div>

          {/* tasks + products */}
          <div className="es-proj-col">
            <div className="es-list-head"><h2 className="es-h2">這門課的任務 <span className="es-mut">{jobs.length}</span></h2></div>
            <div className="es-lib-list">
              {jobs.length === 0 && <div className="es-mut" style={{ padding: 12 }}>尚無任務。到「影片」工作站建立（會自動歸到這門課）。</div>}
              {jobs.map(t => {
                const tt = esTaskMeta(t.type);
                return (
                  <Card key={t.id} state={t.status === "queued" ? null : t.status} className="es-lib-row">
                    <span className="es-lib-ico" style={{ background: `color-mix(in srgb, ${tt.hue} 16%, transparent)`, color: tt.hue }}><Icon name={tt.icon} size={18} /></span>
                    <div className="es-grow" style={{ minWidth: 0 }}>
                      <div className="es-clip" style={{ fontWeight: 500 }}>{t.title}</div>
                      <div className="es-row es-gap-xs" style={{ marginTop: 4, flexWrap: "wrap", alignItems: "center" }}>
                        <span className="es-cap es-mut">{tt.label}</span>
                        <StatusPill status={t.status} size="sm" />
                        {(t.status === "running" || t.status === "queued") && <span className="es-cap es-mut">{t.progress}%</span>}
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>

            <div className="es-list-head" style={{ marginTop: 16 }}>
              <h2 className="es-h2">這門課的視覺成品 <span className="es-mut">{courseVisuals.length}</span></h2>
            </div>
            {courseVisuals.length === 0
              ? <div className="es-mut" style={{ padding: 12 }}>尚無視覺成品。到「視覺」工作站生成（會自動歸到這門課）。</div>
              : <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: 10 }}>
                  {courseVisuals.map(v => <VlibCard key={v.id} item={v} onDelete={(id) => { deleteVlib(id); }} />)}
                </div>}
          </div>
        </div>
      )}
      {activePid && <GlossaryEditor projectId={activePid} projectTitle={activeProject ? activeProject.title : activePid} onFlash={flash} />}
      {toast && <div className="es-toast"><Spinner size={15} /> {toast}</div>}
    </div>
  );
}

Object.assign(window, { ProjectStation });
/* eduStudio — 發布工作站: YouTube 上傳、PPTX/PDF/圖片匯出、分享連結 */

const CHANNEL_META = {
  youtube: { label: "YouTube", icon: "youtube", hue: "#FF4444" },
  pptx:    { label: "簡報匯出", icon: "presentation", hue: "var(--es-ws-video)" },
  image:   { label: "圖片匯出", icon: "image", hue: "var(--es-ws-visual)" },
};

/* ── 發布站接 autoSolver 後端（/library 平鋪 mp4 + /jobs/{id}/artifacts/{name}/publish YouTube）── */
// YoutubeUploadState → 前端發布狀態。沒上傳過(none)＝已核可可發布(approved)。
const ES_YT_STATE = { done: "published", uploading: "running", pending: "running", failed: "failed" };

function esFmtSize(b) {
  if (!b) return "";
  const mb = b / 1048576;
  return mb >= 1 ? mb.toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB";
}

// LibraryItem → 發布記錄列。channel 一律 youtube（/library 只平鋪 mp4）。
function esLibToPubRecord(it) {
  const yt = it.youtube || null;
  const status = yt ? (ES_YT_STATE[yt.state] || "approved") : "approved";
  const langs = it.srt_exists ? ["zh-TW"] : ["zh-TW"];  // 字幕語言之後由多語版本帶入
  const metaBits = [esFmtSize(it.mp4_size_bytes), it.srt_exists ? "含字幕 SRT" : "無字幕"].filter(Boolean);
  return {
    id: it.job_id + "/" + it.artifact_name,
    job_id: it.job_id, name: it.artifact_name,
    title: it.deck_title || it.artifact_name,
    channel: "youtube", status,
    meta: metaBits.join(" · "),
    artifact_url: it.artifact_url,
    yt_url: yt && yt.url ? yt.url : null,
    progress: yt && typeof yt.progress_percent === "number" ? yt.progress_percent : null,
    error: yt && yt.error ? yt.error : null,
    langs,
  };
}

function PublishComposer({ items, selected, onSelect, langs, onToggleLang, onPublish, onExport, onShare, publishing }) {
  const sel = items.find(x => x.id === selected) || items[0] || null;
  return (
    <Card className="es-pubcompose">
      <div className="es-pubcompose-grid">
        <div className="es-pubsel">
          <div className="es-field-label" style={{ marginBottom: 10 }}>選擇要發布的成品</div>
          {items.length ? (
            <select className="es-select-fake es-select-lg" value={sel ? sel.id : ""}
              onChange={e => onSelect(e.target.value)}
              style={{ width: "100%", appearance: "auto", cursor: "pointer" }}>
              {items.map(it => <option key={it.id} value={it.id}>{it.title} — {it.name}</option>)}
            </select>
          ) : (
            <div className="es-select-fake es-select-lg es-mut">尚無已渲染完成的影片成品</div>
          )}

          <div className="es-field-label" style={{ margin: "18px 0 10px" }}>發布語言版本</div>
          <div className="es-pub-langs">
            {LANGS.map(l => (
              <button key={l.code} className={"es-pub-lang" + (langs.includes(l.code) ? " is-on" : "") + (l.source ? " is-source" : "")}
                onClick={() => !l.source && onToggleLang(l.code)} disabled={l.source}>
                <span className="es-checkbox">{langs.includes(l.code) && <Icon name="check" size={12} />}</span>
                <span className="es-langchip-code">{l.code}</span>{l.native}
                {l.source && <span className="es-cap es-mut" style={{ marginLeft: "auto" }}>原始</span>}
              </button>
            ))}
          </div>
        </div>

        <div className="es-pubtargets">
          <div className="es-field-label" style={{ marginBottom: 10 }}>發布管道</div>
          <button className="es-pubtarget is-primary" disabled={!sel || publishing} onClick={() => sel && onPublish(sel)}>
            <span className="es-pubtarget-ico" style={{ background: "rgba(255,68,68,.16)", color: "#FF6B6B" }}><Icon name="youtube" size={22} /></span>
            <span className="es-col es-grow" style={{ gap: 2, alignItems: "flex-start" }}>
              <span style={{ fontWeight: 600 }}>{publishing ? "上傳中…" : "上傳至 YouTube"}</span>
              <span className="es-cap es-mut">{langs.length} 個語言版本 · 自動多語標題與字幕</span>
            </span>
            <Icon name="arrow-right" size={18} className="es-mut" />
          </button>
          <div className="es-pubtarget-row">
            <button className="es-pubtarget" disabled={!sel} onClick={() => sel && onExport(sel)}><span className="es-pubtarget-ico" style={{ color: "var(--es-ws-video)" }}><Icon name="download" size={18} /></span> 下載 MP4</button>
            <button className="es-pubtarget" disabled={!sel || !sel.srt_disabled} onClick={() => sel && onExport(sel, ".srt")} style={{ opacity: 1 }}><span className="es-pubtarget-ico" style={{ color: "var(--es-error)" }}><Icon name="file-text" size={18} /></span> 下載字幕</button>
          </div>
          <div className="es-pubtarget-row">
            <button className="es-pubtarget" disabled={!sel} onClick={() => sel && onShare(sel)}><span className="es-pubtarget-ico" style={{ color: "var(--es-accent)" }}><Icon name="share" size={18} /></span> 複製分享連結</button>
            {sel && sel.yt_url
              ? <a className="es-pubtarget" href={sel.yt_url} target="_blank" rel="noreferrer"><span className="es-pubtarget-ico" style={{ color: "#FF6B6B" }}><Icon name="youtube" size={18} /></span> 開啟 YouTube</a>
              : <button className="es-pubtarget" disabled><span className="es-pubtarget-ico" style={{ color: "var(--es-ws-visual)" }}><Icon name="youtube" size={18} /></span> 尚未上傳</button>}
          </div>
        </div>
      </div>
    </Card>
  );
}

function PublishStation() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState("");
  const [langs, setLangs] = useState(["zh-TW", "en"]);
  const [publishing, setPublishing] = useState(false);
  const [toast, setToast] = useState(null);
  const [view, setView] = useState("card");   // 影片庫檢視：卡片 / 清單
  const [picked, setPicked] = useState([]);    // 多選刪除

  const load = () => fetch("/library").then(r => r.json()).then(d => {
    const recs = (d.items || []).map(esLibToPubRecord);
    setRecords(recs);
    setSelected(s => s || (recs[0] ? recs[0].id : ""));
    setLoading(false);
    return recs;
  }).catch(() => { setRecords([]); setLoading(false); return []; });

  useEffect(() => { let alive = true; load().then(() => { if (!alive) {} }); return () => { alive = false; }; }, []);

  const toggleLang = (c) => setLangs(l => l.includes(c) ? l.filter(x => x !== c) : [...l, c]);
  const flash = (msg, tone) => { setToast({ msg, tone: tone || "info" }); setTimeout(() => setToast(null), 4000); };

  // YouTube：先抓預填 meta → POST publish → 輪詢 youtube_status 直到 done/failed。
  const publish = async (rec) => {
    setPublishing(true);
    flash("正在準備上傳 " + rec.title + "…", "info");
    try {
      const metaRes = await fetch(`/jobs/${rec.job_id}/artifacts/${rec.name}/youtube_meta`);
      const meta = metaRes.ok ? await metaRes.json() : { title: rec.title };
      const body = JSON.stringify({
        title: meta.title || rec.title, description: meta.description || "",
        tags: meta.tags || [], privacy: meta.privacy || "unlisted", category: meta.category || "27",
      });
      const res = await fetch(`/jobs/${rec.job_id}/artifacts/${rec.name}/publish`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body });
      if (res.status === 409) { flash("此影片已在上傳中或已上傳。", "warn"); setPublishing(false); return; }
      if (!res.ok) { flash("上傳請求失敗（" + res.status + "）。", "error"); setPublishing(false); return; }
      // 輪詢狀態
      const poll = async () => {
        const s = await fetch(`/jobs/${rec.job_id}/artifacts/${rec.name}/youtube_status`).then(r => r.json()).catch(() => null);
        if (!s) return;
        if (s.state === "done") { flash("上傳完成：" + (s.url || rec.title), "ok"); setPublishing(false); load(); return; }
        if (s.state === "failed") { flash("上傳失敗：" + (s.error || "未知錯誤（可能是 YouTube OAuth 未授權）"), "error"); setPublishing(false); load(); return; }
        flash("上傳中… " + (s.progress_percent || 0) + "%", "info");
        setTimeout(poll, 2500);
      };
      setTimeout(poll, 2000);
    } catch (e) {
      flash("上傳發生錯誤：" + e.message, "error"); setPublishing(false);
    }
  };

  const exportFile = (rec, suffix) => {
    const url = suffix ? rec.artifact_url.replace(/\.mp4$/i, suffix) : rec.artifact_url;
    window.open(url, "_blank");
  };
  const share = (rec) => {
    const url = location.origin + rec.artifact_url;
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(() => flash("已複製連結：" + url, "ok"), () => flash(url, "info"));
    else flash(url, "info");
  };
  // 多語字幕軌：用上方選的語言版本（排除原始 zh-TW），翻譯 SRT → 上傳成 caption track。
  const addCaptions = async (rec) => {
    const targets = (langs || []).filter(l => l !== "zh-TW");
    if (!targets.length) { flash("請在上方「發布語言版本」選要加的語言", "warn"); return; }
    flash("翻譯並上傳字幕中…（每語言需數秒）", "info");
    try {
      const r = await fetch(`/jobs/${rec.job_id}/artifacts/${rec.name}/captions`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ languages: targets, source_lang: "zh-TW" }),
      });
      const d = await r.json();
      if (!r.ok) { flash("字幕上傳失敗：" + (d.detail || r.status), "error"); return; }
      const ok = (d.captions || []).filter(c => c.caption_id).length;
      flash(`已上傳 ${ok}/${targets.length} 個語言字幕軌`, ok ? "ok" : "warn");
    } catch (e) { flash("字幕上傳錯誤：" + e.message, "error"); }
  };

  // 多選批次刪除：刪掉選取項目所屬的 job（DELETE /jobs/{id} 移除整 job 的成品）。
  const togglePick = (id) => setPicked(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id]);
  const batchDelete = async () => {
    if (!picked.length) return;
    if (!confirm(`確定刪除選取的 ${picked.length} 支影片？此動作會刪除整個 job 的成品，無法復原。`)) return;
    const jobIds = [...new Set(records.filter(r => picked.includes(r.id)).map(r => r.job_id))];
    flash(`刪除中…（${jobIds.length} 個 job）`, "info");
    let ok = 0;
    for (const jid of jobIds) {
      try { const r = await fetch("/jobs/" + jid, { method: "DELETE" }); if (r.ok || r.status === 404) ok++; } catch {}
    }
    setPicked([]); flash(`已刪除 ${ok}/${jobIds.length} 個 job`, "ok"); load();
  };

  return (
    <div className="es-screen">
      <div className="es-screen-head">
        <div>
          <h1 className="es-h1">發布工作站</h1>
          <p className="es-screen-sub">挑選已完成的成品 + 語言版本，一鍵發布到 YouTube 或下載 MP4 / 字幕（任務狀態請看「製作狀態」）。</p>
        </div>
      </div>

      {toast && <div className={"es-toast es-toast-" + toast.tone} style={{ marginBottom: 14 }}>{toast.msg}</div>}

      <PublishComposer items={records} selected={selected} onSelect={setSelected}
        langs={langs} onToggleLang={toggleLang} onPublish={publish}
        onExport={exportFile} onShare={share} publishing={publishing} />

      <div className="es-list-head">
        <h2 className="es-h2">影片庫 {records.length > 0 && <span className="es-mut">{records.length}</span>}</h2>
        <div className="es-row es-gap-sm" style={{ alignItems: "center" }}>
          {picked.length > 0 && (
            <>
              <span className="es-cap es-mut">已選 {picked.length}</span>
              <Button variant="default" size="sm" icon="trash-2" onClick={batchDelete}>刪除</Button>
              <Button variant="ghost" size="sm" onClick={() => setPicked([])}>取消</Button>
            </>
          )}
          <Segmented size="sm" value={view} onChange={setView} options={[{ value: "card", label: "卡片" }, { value: "list", label: "清單" }]} />
        </div>
      </div>
      {loading ? <div className="es-mut" style={{ padding: 24 }}>載入影片庫…</div> : null}
      {!loading && !records.length ? <div className="es-mut" style={{ padding: 24 }}>尚無已渲染完成的影片。先到「影片」工作站產出成品。</div> : null}

      {view === "card" ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 14 }}>
          {records.map(p => (
            <Card key={p.id} state={p.status === "published" ? "approved" : null} style={{ padding: 0, overflow: "hidden", outline: picked.includes(p.id) ? "2px solid var(--es-primary-soft)" : "none" }}>
              <div style={{ position: "relative" }}>
                <video src={p.artifact_url} controls preload="metadata" style={{ width: "100%", aspectRatio: "16/9", background: "#000", display: "block" }} />
                <label style={{ position: "absolute", top: 8, left: 8, background: "rgba(0,0,0,.55)", borderRadius: 6, padding: "3px 6px", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                  <input type="checkbox" checked={picked.includes(p.id)} onChange={() => togglePick(p.id)} />
                </label>
              </div>
              <div style={{ padding: 12 }}>
                <div className="es-clip" style={{ fontWeight: 500 }}>{p.title}</div>
                <div className="es-row es-gap-xs" style={{ marginTop: 4, flexWrap: "wrap", alignItems: "center" }}>
                  <StatusPill status={p.status} size="sm" />
                  <span className="es-cap es-mut">{p.meta}</span>
                </div>
                <div className="es-row es-gap-xs" style={{ marginTop: 8, flexWrap: "wrap" }}>
                  <a className="es-cap" href={p.artifact_url} download><Icon name="download" size={12} /> 下載</a>
                  {p.status !== "published" && <Button variant="ghost" size="sm" icon="upload" onClick={() => publish(p)}>發布</Button>}
                  {p.status === "published" && p.yt_url && <a className="es-cap es-mut" href={p.yt_url} target="_blank" rel="noreferrer"><Icon name="youtube" size={12} /> YouTube</a>}
                  {p.status === "published" && <Button variant="ghost" size="sm" icon="languages" onClick={() => addCaptions(p)}>多語字幕</Button>}
                </div>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <div className="es-pub-list">
          {records.map(p => {
            const c = CHANNEL_META[p.channel];
            return (
              <Card key={p.id} state={p.status === "published" ? "approved" : p.status} className="es-pub-row">
                <input type="checkbox" checked={picked.includes(p.id)} onChange={() => togglePick(p.id)} style={{ marginRight: 4 }} />
                <span className="es-lib-ico" style={{ background: `color-mix(in srgb, ${c.hue} 18%, transparent)`, color: c.hue }}><Icon name={c.icon} size={18} /></span>
                <div className="es-grow" style={{ minWidth: 0 }}>
                  <div className="es-clip" style={{ fontWeight: 500 }}>{p.title}</div>
                  <div className="es-row es-gap-xs" style={{ marginTop: 4, flexWrap: "wrap" }}>
                    <span className="es-cap es-mut">{p.meta}</span>
                    {p.langs.map(code => <LangChip key={code} code={code} />)}
                    <a className="es-cap" href={p.artifact_url} download><Icon name="download" size={12} /> 下載</a>
                  </div>
                </div>
                <div className="es-col" style={{ alignItems: "flex-end", gap: 6 }}>
                  <StatusPill status={p.status} size="sm" />
                  {p.status === "published" && p.yt_url && <a className="es-cap es-mut" href={p.yt_url} target="_blank" rel="noreferrer"><Icon name="youtube" size={12} /> 已發布</a>}
                  {p.status === "published" && <Button variant="default" size="sm" icon="languages" onClick={() => addCaptions(p)}>多語字幕</Button>}
                  {p.status === "running" && p.progress != null && <span className="es-cap es-mut">{p.progress}%</span>}
                  {p.status === "failed" && p.error && <span className="es-cap" style={{ color: "var(--es-error)", maxWidth: 220, textAlign: "right" }}>{p.error}</span>}
                  {p.status !== "published" && p.status !== "running" && <Button variant="primary" size="sm" icon="upload" onClick={() => publish(p)}>發布</Button>}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

Object.assign(window, { PublishStation });
// 設定頁：個人品牌 / API key / 模型選擇（接 /settings）。
function SettingsDrawer({ open, onClose }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!open) return;
    fetch("/settings").then(r => r.json()).then(d => {
      setData(d);
      setForm({ model_roles: d.model_roles || {},
        brand_speaker: d.brand_speaker || "", brand_org: d.brand_org || "", brand_url: d.brand_url || "", gemini_api_key: "" });
    }).catch(() => setMsg("讀取設定失敗"));
  }, [open]);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  // 逐角色 provider/model 覆寫（M-3 + F9-3c 本機可插拔 provider）。
  // 值表示法：扁平字串＝角色預設 provider（雲端）+ model 覆寫；巢狀 {provider,model}
  // ＝指到本機 provider（如 ollama）；空/未設＝清除回退系統預設（後端 _clean_model_roles 收斂）。
  const roleProvider = (role) => {
    const v = (form.model_roles || {})[role.role];
    if (v && typeof v === "object") return v.provider || role.provider;
    return role.provider;                  // 扁平字串或未設＝角色預設 provider
  };
  const roleModel = (role) => {
    const v = (form.model_roles || {})[role.role];
    if (!v) return "";
    return (typeof v === "object") ? (v.model || "") : v;
  };
  // 切 provider：回預設 provider（雲端）＝清除（本機專屬 model 對雲端無意義）；
  // 切到本機 provider＝巢狀存（沿用已填 model，空 model 後端清洗時丟棄）。
  const setRoleProvider = (role, provider) => setForm(f => {
    const mr = { ...(f.model_roles || {}) };
    const cur = mr[role.role];
    const model = (cur && typeof cur === "object") ? (cur.model || "") : (typeof cur === "string" ? cur : "");
    if (provider === role.provider) delete mr[role.role];
    else mr[role.role] = { provider, model };
    return { ...f, model_roles: mr };
  });
  const setRoleModel = (role, model) => setForm(f => {
    const mr = { ...(f.model_roles || {}) };
    const cur = mr[role.role];
    const prov = (cur && typeof cur === "object") ? (cur.provider || role.provider) : role.provider;
    const m = (model || "").trim();
    if (prov === role.provider) { if (m) mr[role.role] = m; else delete mr[role.role]; }  // 預設 provider：扁平字串
    else mr[role.role] = { provider: prov, model: m };                                    // 本機 provider：巢狀
    return { ...f, model_roles: mr };
  });
  const save = async () => {
    setBusy(true); setMsg("");
    try {
      const patch = { ...form };
      if (!patch.gemini_api_key) delete patch.gemini_api_key;  // 空不覆蓋既有金鑰
      const r = await fetch("/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
      const d = await r.json();
      if (!r.ok) { setMsg("儲存失敗：" + (d.detail || r.status)); return; }
      setData(d); setForm(f => ({ ...f, gemini_api_key: "" })); setMsg("已儲存");
      setTimeout(() => setMsg(""), 2500);
    } catch (e) { setMsg("儲存錯誤：" + e.message); }
    finally { setBusy(false); }
  };

  const inputStyle = { width: "100%", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--es-border)", background: "var(--es-bg-1)", color: "var(--es-fg-1)" };
  return (
    <>
      <div className={"es-drawer-scrim" + (open ? " is-open" : "")} onClick={onClose} />
      <aside className={"es-drawer" + (open ? " is-open" : "")} aria-hidden={!open}>
        <div className="es-drawer-head">
          <div className="es-row es-gap-sm"><Icon name="settings" size={18} style={{ color: "var(--es-fg-2)" }} /><h2 className="es-h2">設定</h2></div>
          <IconButton icon="x" onClick={onClose} />
        </div>
        <div className="es-drawer-body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <div className="es-cost-sec-title">AI 模型（逐角色）</div>
            {(data?.roles || []).map(role => {
              const opts = role.kind === "image" ? (data?.image_models || []) : (data?.text_models || []);
              const prov = roleProvider(role);
              const model = roleModel(role);
              const isDefaultProvider = prov === role.provider;   // 預設 provider（雲端）
              // 只有文字角色提供本機 provider 選擇；視覺/生圖角色預設留雲端（本機後端尚不支援生圖/讀圖）。
              const allowProvider = role.kind === "text" && (data?.providers || []).length > 1;
              return (
                <Field key={role.role} label={role.label}>
                  <div className="es-row es-gap-sm">
                    {allowProvider && (
                      <select style={{ ...inputStyle, flex: "0 0 9rem", width: "auto" }} value={prov}
                        onChange={e => setRoleProvider(role, e.target.value)}>
                        {(data?.providers || []).map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
                      </select>
                    )}
                    {isDefaultProvider ? (
                      <select style={{ ...inputStyle, flex: 1, width: "auto", minWidth: 0 }} value={model}
                        onChange={e => setRoleModel(role, e.target.value)}>
                        <option value="">預設（{role.default}）</option>
                        {opts.map(m => <option key={m.id} value={m.id}>{m.label}（{m.id}）</option>)}
                      </select>
                    ) : (
                      <input style={{ ...inputStyle, flex: 1, width: "auto", minWidth: 0 }} value={model}
                        onChange={e => setRoleModel(role, e.target.value)}
                        placeholder="本機模型名稱，例：translategemma" />
                    )}
                  </div>
                </Field>
              );
            })}
            <div className="es-cap es-mut" style={{ marginTop: 4 }}>留空＝沿用系統預設。文字角色可改用本機（Ollama）省雲端額度——本機跑前需自行啟動 ollama；認不出時自動退回雲端（可關）。語音（TTS）後端於 .env / tts_config.json 設定。</div>
            {(data?.specialized_models || []).length > 0 && (
              <details style={{ marginTop: 8 }}>
                <summary className="es-cap" style={{ cursor: "pointer" }}>專用 API 型號（已核對，尚未接入目前工作流程）</summary>
                <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
                  {data.specialized_models.map(m => (
                    <div key={m.id} className="es-cap es-mut">
                      <span style={{ color: "var(--es-fg-1)" }}>{m.label}</span><br />
                      <code>{m.id}</code> · {m.pipeline}
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>

          <div>
            <div className="es-cost-sec-title">API 金鑰</div>
            <Field label="Gemini API Key" hint={data?.has_gemini_api_key ? "已設定（留空＝不變更；輸入新值覆蓋）" : "尚未設定，請輸入"}>
              <input type="password" style={inputStyle} value={form.gemini_api_key || ""} onChange={e => set("gemini_api_key", e.target.value)}
                placeholder={data?.has_gemini_api_key ? "••••••••（已設定）" : "貼上你的 Gemini API Key"} />
            </Field>
          </div>

          <div>
            <div className="es-cost-sec-title">個人品牌</div>
            <Field label="講者 / 姓名"><input style={inputStyle} value={form.brand_speaker} onChange={e => set("brand_speaker", e.target.value)} placeholder="劉瑞弘" /></Field>
            <Field label="單位"><input style={inputStyle} value={form.brand_org} onChange={e => set("brand_org", e.target.value)} placeholder="國立勤益科技大學" /></Field>
            <Field label="連結 / 網站"><input style={inputStyle} value={form.brand_url} onChange={e => set("brand_url", e.target.value)} placeholder="doflab.cc" /></Field>
          </div>

          <div className="es-row es-gap-sm" style={{ alignItems: "center" }}>
            <Button variant="primary" icon="check" disabled={busy} onClick={save}>{busy ? "儲存中…" : "儲存設定"}</Button>
            {msg && <span className="es-cap es-mut">{msg}</span>}
          </div>
        </div>
      </aside>
    </>
  );
}

// 第五站「製作狀態」：所有任務即時進度看板（審核/進行中/完成/失敗），多任務同時可見。
function StatusStation({ onReview, onGoPublish }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);
  const flash = (m) => { setToast(m); setTimeout(() => setToast(null), 3000); };
  const refresh = () => fetch("/jobs").then(r => r.json())
    .then(d => { setTasks((d.jobs || d || []).map(esJobToTask)); setLoading(false); })
    .catch(() => setLoading(false));
  useEffect(() => { refresh(); }, []);
  const activeRef = useRef(false);
  useEffect(() => { activeRef.current = tasks.some(t => t.status === "running" || t.status === "queued"); }, [tasks]);
  useEffect(() => { const id = setInterval(() => { if (activeRef.current) refresh(); }, 4000); return () => clearInterval(id); }, []);

  // 任務管理（詳情/審查/發布/重試/刪除）統一在本頁；發布頁只負責挑成品 + 語言。
  const taskDelete = async (task) => {
    if (!confirm(`確定刪除任務「${task.title}」？此動作會刪除整個 job 的成品，無法復原。`)) return;
    try {
      const r = await fetch("/jobs/" + task.id, { method: "DELETE" });
      if (!r.ok && r.status !== 404) { flash("刪除失敗（" + r.status + "）"); return; }
      flash("已刪除任務"); refresh();
    } catch (e) { flash("刪除發生錯誤：" + e.message); }
  };
  const taskRetry = async (task) => {
    if (!task._stype || !task._src) { flash("無法重試：缺原始來源"); return; }
    try {
      const r = await fetch("/jobs", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_type: task._stype, source: task._src, options: {} }) });
      if (!r.ok) { let d = r.status; try { d = (await r.json()).detail || d; } catch {} flash("重試失敗：" + d); return; }
      flash("已重新建立任務"); refresh();
    } catch (e) { flash("重試發生錯誤：" + e.message); }
  };

  const groups = [
    { key: "review", label: "待審核", icon: "eye", items: tasks.filter(t => t.status === "review") },
    { key: "running", label: "進行中", icon: "loader", items: tasks.filter(t => t.status === "running" || t.status === "queued") },
    { key: "approved", label: "已完成", icon: "check-circle", items: tasks.filter(t => t.status === "approved") },
    { key: "failed", label: "失敗", icon: "alert-triangle", items: tasks.filter(t => t.status === "failed") },
  ];

  return (
    <div className="es-screen">
      <div className="es-screen-head">
        <div>
          <h1 className="es-h1">製作狀態</h1>
          <p className="es-screen-sub">所有任務集中管理：詳情、審查、發布、重試、刪除（每 4 秒自動更新）。</p>
        </div>
        <div className="es-row es-gap-xs es-stat-chips">
          {groups.map(g => <span key={g.key} className="es-stat-chip"><b>{g.items.length}</b> {g.label}</span>)}
        </div>
      </div>

      {loading ? <div className="es-mut" style={{ padding: 24 }}>載入任務…</div> : null}
      {!loading && !tasks.length ? <div className="es-mut" style={{ padding: 24 }}>尚無任務。到「影片」工作站建立。</div> : null}

      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        {groups.filter(g => g.items.length).map(g => (
          <div key={g.key}>
            <div className="es-list-head"><h2 className="es-h2"><Icon name={g.icon} size={16} /> {g.label} <span className="es-mut">{g.items.length}</span></h2></div>
            <div className="es-task-list">
              {g.items.map(t => <TaskCard key={t.id} task={t} onReview={onReview}
                onLocalize={() => {}} onRetry={taskRetry} onPublish={() => onGoPublish && onGoPublish()}
                onDelete={taskDelete} onRerender={() => { flash("已排程重渲染章節"); refresh(); }} />)}
            </div>
          </div>
        ))}
      </div>
      {toast && <div className="es-toast"><Spinner size={15} /> {toast}</div>}
    </div>
  );
}

/* ───────────────────────── Goal-first creator home ───────────────────────── */
function CreatorHome({ activeProject, onOpenWorkflow }) {
  const [requestText, setRequestText] = useState("");
  const [brief, setBrief] = useState(null);
  const [error, setError] = useState("");

  const selectWorkflow = (workflow) => {
    setError("");
    setBrief(createTaskBrief(workflow.id, requestText, activeProject));
  };

  const analyzeIntent = () => {
    const result = inferWorkflowIntent(requestText);
    if (result.workflow) {
      selectWorkflow(result.workflow);
      return;
    }
    setBrief(null);
    if (result.reason === "empty") {
      setError("請描述想製作的內容，或直接選擇下方成品類型。");
    } else if (result.reason === "ambiguous") {
      setError("需求同時包含多種成品，請先選擇這次的主要輸出。");
    } else {
      setError("目前無法確定成品類型，請從影片、簡報、圖卡或漫畫中選擇。");
    }
  };

  return (
    <div className="es-home">
      <section className="es-home-hero">
        <div className="es-home-eyebrow"><Icon name="sparkles" size={15} /> Goal-first Studio</div>
        <h1 className="es-home-title">這次想製作什麼？</h1>
        <p className="es-home-lead">
          直接描述素材、成品與讀者；eduStudio 會先整理成任務摘要，確認後才開啟需要的工作台。
        </p>

        <div className="es-intent-box">
          <textarea
            className="es-intent-input"
            value={requestText}
            onChange={(event) => { setRequestText(event.target.value); setError(""); }}
            onKeyDown={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key === "Enter") analyzeIntent();
            }}
            placeholder="例如：把這份齒輪箱講義做成 8 頁、給大學生看的教學漫畫"
            aria-label="描述這次想製作的內容"
          />
          <Button className="es-intent-action" variant="primary" icon="wand" onClick={analyzeIntent}>
            分析需求
          </Button>
        </div>
        {error && <div className="es-intent-error"><Icon name="alert-triangle" size={13} /> {error}</div>}
      </section>

      {brief && (
        <section className="es-task-brief" aria-live="polite">
          <div className="es-task-brief-main">
            <div className="es-task-brief-title">
              <span className="es-workflow-icon" style={{ "--wf-hue": brief.workflow.hue }}>
                <Icon name={brief.workflow.icon} size={20} />
              </span>
              已辨識為「{brief.workflow.label}」
            </div>
            <div className="es-task-brief-meta">
              <Badge tone="primary">{brief.projectLabel}</Badge>
              <Badge tone="neutral">下一步：{brief.workflow.nextStep}</Badge>
            </div>
            <div className="es-task-brief-request">
              {brief.requestText || `從「${brief.workflow.label}」開始，進入工作台後補齊來源與內容。`}
            </div>
            <div className="es-task-brief-boundary">確認只會開啟工作流程，不會立即呼叫 AI API。</div>
          </div>
          <div className="es-task-brief-actions">
            <Button variant="ghost" onClick={() => setBrief(null)}>重新選擇</Button>
            <Button variant="primary" iconRight="arrow-right" onClick={() => onOpenWorkflow(brief)}>
              確認並開啟
            </Button>
          </div>
        </section>
      )}

      <section>
        <div className="es-workflow-head">
          <div>
            <h2 className="es-h2">或直接選擇成品</h2>
            <p className="es-body-2 es-mut" style={{ marginTop: 5 }}>首頁只顯示主要產製方向，詳細設定進入工作台後才展開。</p>
          </div>
          <Badge tone={activeProject ? "success" : "neutral"}>{activeProject ? activeProject.title : "尚未指定 Project"}</Badge>
        </div>
        <div className="es-workflow-grid" style={{ marginTop: 14 }}>
          {WORKFLOWS.map((workflow) => (
            <button
              key={workflow.id}
              className="es-workflow-card"
              style={{ "--wf-hue": workflow.hue }}
              onClick={() => selectWorkflow(workflow)}
            >
              {workflow.badge && <Badge className="es-workflow-badge" tone="accent">{workflow.badge}</Badge>}
              <span className="es-workflow-icon"><Icon name={workflow.icon} size={21} /></span>
              <span className="es-workflow-label">{workflow.label}</span>
              <span className="es-workflow-summary">{workflow.summary}</span>
              <span className="es-workflow-go">建立任務摘要 <Icon name="arrow-right" size={14} /></span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

/* ───────────────────────── Comic workstation · Phase 1 shell ───────────────────────── */
const COMIC_FLOW = ["Series", "Brief", "Script", "Storyboard", "Image", "Layout", "QA"];

function ComicStationPhaseOne({ activeProject, launchContext }) {
  const [seriesTitle, setSeriesTitle] = useState("");
  const [episodeTitle, setEpisodeTitle] = useState("");
  const [audience, setAudience] = useState("大學生");
  const [pages, setPages] = useState(8);
  const [profile, setProfile] = useState("educational_evidence");
  const requestText = launchContext?.requestText || "";

  return (
    <div className="es-comic-shell">
      <div className="es-screen-head">
        <div>
          <div className="es-row es-gap-sm">
            <h1 className="es-h1">漫畫工作站</h1>
            <Badge tone="accent">內部 MVP · Phase 1</Badge>
          </div>
          <p className="es-screen-sub">由 Series Bible 與 Episode Brief 開始，逐步建立腳本、分鏡、畫面、版面與 QA。</p>
        </div>
      </div>

      <div className="es-comic-flow" aria-label="漫畫製作流程">
        {COMIC_FLOW.map((step, index) => (
          <div key={step} className={"es-comic-step" + (index < 2 ? " is-active" : "")}>{index + 1}. {step}</div>
        ))}
      </div>

      <div className="es-comic-grid">
        <Card className="es-comic-panel">
          <div>
            <h2 className="es-h2">Episode Brief</h2>
            <p className="es-body-2 es-mut" style={{ marginTop: 5 }}>先鎖定系列、集數與讀者；這一階段不呼叫生圖 API。</p>
          </div>
          <div className="es-comic-fields">
            <Field label="所屬 Project">
              <input className="es-input" value={activeProject?.title || "尚未指定 Project"} disabled readOnly />
            </Field>
            <Field label="內容治理模式">
              <select className="es-input" value={profile} onChange={(event) => setProfile(event.target.value)}>
                <option value="educational_evidence">教學內容 · Evidence required</option>
                <option value="general_serial">一般連載 · Continuity first</option>
                <option value="technical_story">技術故事 · Evidence + Continuity</option>
              </select>
            </Field>
            <Field label="系列名稱">
              <input className="es-input" value={seriesTitle} onChange={(event) => setSeriesTitle(event.target.value)} placeholder="例如：海風值班日誌" />
            </Field>
            <Field label="本集標題">
              <input className="es-input" value={episodeTitle} onChange={(event) => setEpisodeTitle(event.target.value)} placeholder="例如：齒間的線索" />
            </Field>
            <Field label="目標讀者">
              <input className="es-input" value={audience} onChange={(event) => setAudience(event.target.value)} />
            </Field>
            <Field label="預計頁數">
              <input className="es-input" type="number" min="1" max="60" value={pages} onChange={(event) => setPages(Number(event.target.value) || 1)} />
            </Field>
            <Field className="is-wide" label="本次構想">
              <textarea className="es-input" style={{ minHeight: 104, resize: "vertical" }} defaultValue={requestText} placeholder="描述本集主題、衝突、角色與希望讀者帶走的內容" />
            </Field>
          </div>
          <div className="es-comic-boundary">
            <Icon name="info" size={15} /> Phase 1 先建立作者端入口與資料欄位。正式儲存、Script API、Storyboard schema 與 image generation 尚未接線，因此不會把此畫面誤報為已完成漫畫系統。
          </div>
          <Button variant="primary" iconRight="arrow-right" disabled>下一步：建立 Script（Phase 2）</Button>
        </Card>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card className="es-comic-panel">
            <div><h2 className="es-h3">Series 必要資料</h2></div>
            <ul className="es-comic-checklist">
              <li>角色與外觀 anchor</li>
              <li>世界觀、畫風與色盤</li>
              <li>角色語氣與禁項</li>
              <li>前情、伏筆與 continuity</li>
              <li>輸出版本與連載節奏</li>
            </ul>
          </Card>
          <Card className="es-comic-panel">
            <div><h2 className="es-h3">本輪已帶入</h2></div>
            <div className="es-task-brief-meta">
              <Badge tone="neutral">{activeProject?.title || "未指定 Project"}</Badge>
              <Badge tone="neutral">{pages} 頁</Badge>
              <Badge tone="neutral">{audience}</Badge>
            </div>
            <div className="es-cap es-mut">Profile：{profile}</div>
          </Card>
        </div>
      </div>
    </div>
  );
}

/* eduStudio — App orchestrator */

function App() {
  const [ws, setWs] = useState("home");
  const [workflowContext, setWorkflowContext] = useState(null);
  // 一課一工作空間：真實 /projects + 記住目前作用中的課（空＝全部/不限）。
  const [projects, setProjects] = useState([]);
  const [activePid, setActivePid] = useState(() => localStorage.getItem("edustudio-active-project") || "");
  const [collapsed, setCollapsed] = useState(false);
  const [costOpen, setCostOpen] = useState(false);
  const [toolboxOpen, setToolboxOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [reviewTask, setReviewTask] = useState(null);
  const [completed, setCompleted] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("edustudio-theme-v2") || "soft");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("edustudio-theme-v2", theme);
  }, [theme]);

  const loadProjects = () => fetch("/projects").then(r => r.json())
    .then(list => setProjects(Array.isArray(list) ? list : [])).catch(() => {});
  useEffect(() => { loadProjects(); }, []);

  // 右上頭像顯示「個人品牌」設定的姓名（設定頁可改）；未設定退「師」。
  const [brandSpeaker, setBrandSpeaker] = useState("");
  const loadBrand = () => fetch("/settings").then(r => r.json())
    .then(d => setBrandSpeaker((d && d.brand_speaker) || "")).catch(() => {});
  useEffect(() => { loadBrand(); }, []);
  useEffect(() => { if (!settingsOpen) loadBrand(); }, [settingsOpen]);   // 存完設定即時更新

  // 成本面板真實用量：頂欄 pill 與抽屜共用一份 /api/usage；開抽屜時重抓刷新。
  const [usage, setUsage] = useState(null);
  const loadUsage = () => fetch("/api/usage").then(r => r.json())
    .then(d => setUsage(d && typeof d.used === "number" ? d : null)).catch(() => setUsage(null));
  useEffect(() => { loadUsage(); }, []);
  useEffect(() => { if (costOpen) loadUsage(); }, [costOpen]);

  const activeProject = projects.find(p => p.project_id === activePid) || null;
  const pickProject = (pid) => { setActivePid(pid || ""); localStorage.setItem("edustudio-active-project", pid || ""); };
  const createProject = async (id, title) => {
    const pid = (id || "").trim();
    if (!pid) return { ok: false, err: "請填課程 ID" };
    try {
      const r = await fetch("/projects", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: pid, title: (title || pid).trim(), target_languages: [] }) });
      if (r.status === 409) return { ok: false, err: "此課程 ID 已存在" };
      if (!r.ok) return { ok: false, err: "建立失敗（" + r.status + "）" };
      await loadProjects(); pickProject(pid);
      return { ok: true };
    } catch (e) { return { ok: false, err: String((e && e.message) || e) }; }
  };

  const currentWorkflow = workflowContext?.workflow || null;
  const wsTitle = currentWorkflow?.route === ws
    ? currentWorkflow.label
    : (WORKSTATIONS.find(w => w.key === ws) || {}).label || "";

  const openWorkflow = (brief) => {
    if (!brief?.workflow) return;
    setWorkflowContext(brief);
    setWs(brief.workflow.route);
  };

  const completeReview = () => {
    setCompleted(true);
    setTimeout(() => { setReviewTask(null); setCompleted(false); setWs("publish"); }, 1100);
  };

  return (
    <div className={"es-app" + (collapsed ? " is-collapsed" : "")}>
      <Sidebar active={ws} currentWorkflow={currentWorkflow} onNav={setWs} collapsed={collapsed}
        onToggle={() => setCollapsed(c => !c)} onOpenToolbox={() => setToolboxOpen(true)} />

      <div className="es-main">
        <Topbar projects={projects} activePid={activePid} activeProject={activeProject}
          onPickProject={pickProject} onCreateProject={createProject} avatarName={brandSpeaker ? brandSpeaker.trim()[0] : "師"}
          wsTitle={wsTitle} usage={usage} onOpenCost={() => setCostOpen(true)} onOpenSettings={() => setSettingsOpen(true)} theme={theme} onTheme={setTheme} />
        <main className="es-content" key={ws + activePid}>
          {ws === "home" && <CreatorHome activeProject={activeProject} onOpenWorkflow={openWorkflow} />}
          {ws === "video" && <VideoStation projectId={activePid} onReview={setReviewTask} onGoPublish={() => setWs("publish")} onGoStatus={() => setWs("status")} />}
          {ws === "visual" && <VisualStation projectId={activePid} initialMode={currentWorkflow?.visualMode || "slides"} />}
          {ws === "comic" && <ComicStudio activeProject={activeProject} launchContext={workflowContext} />}
          {ws === "material" && <ProjectStation activePid={activePid} projects={projects} onProjectsChanged={loadProjects} onPickProject={pickProject} />}
          {ws === "publish" && <PublishStation />}
          {ws === "status" && <StatusStation onReview={setReviewTask} onGoPublish={() => setWs("publish")} />}
        </main>
      </div>

      <CostPanel open={costOpen} onClose={() => setCostOpen(false)} usage={usage} />
      <Toolbox open={toolboxOpen} onClose={() => setToolboxOpen(false)} />
      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      {reviewTask && (
        <div className="es-overlay">
          <ReviewGate task={reviewTask} onClose={() => setReviewTask(null)} onComplete={completeReview} />
          {completed && (
            <div className="es-complete-toast">
              <Icon name="check-circle" size={20} /> 全部核准完成，前往發布…
            </div>
          )}
        </div>
      )}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
