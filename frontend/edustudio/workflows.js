// eduStudio 目標導向入口的單一工作流程目錄。
//
// 為什麼獨立成檔案：首頁、側邊欄與後續 Intent Router 都需要同一份 workflow metadata；
// 若把 label／route／關鍵字散在 app.jsx，多入口很快會出現名稱與導向不一致。

export const WORKFLOWS = [
  {
    id: "video",
    label: "影片",
    icon: "video",
    route: "video",
    hue: "var(--es-ws-video)",
    summary: "旁白教學影片、配音、字幕與影音摘要",
    nextStep: "選擇來源與影片類型",
    keywords: ["影片", "video", "mp4", "旁白", "配音", "字幕", "影音", "youtube"],
  },
  {
    id: "slides",
    label: "簡報",
    icon: "presentation",
    route: "visual",
    visualMode: "slides",
    hue: "var(--es-ws-video)",
    summary: "由教材建立可審查、可匯出的教學簡報",
    nextStep: "設定簡報內容、受眾與視覺風格",
    keywords: ["簡報", "投影片", "ppt", "pptx", "slides", "slide", "deck"],
  },
  {
    id: "cards",
    label: "圖卡／海報",
    icon: "image",
    route: "visual",
    visualMode: "poster",
    hue: "var(--es-ws-visual)",
    summary: "製作單張圖卡、資訊圖表或印刷海報",
    nextStep: "選擇版式並設定圖卡內容",
    keywords: ["圖卡", "海報", "資訊圖", "infographic", "poster", "card", "社群圖"],
  },
  {
    id: "comic",
    label: "漫畫",
    icon: "book-open",
    route: "comic",
    hue: "var(--es-accent)",
    summary: "建立可連載的腳本、分鏡、畫面與版本化漫畫",
    nextStep: "建立 Series 與 Episode Brief",
    badge: "內部 MVP",
    keywords: ["漫畫", "連載", "分鏡", "comic", "manga", "episode", "storyboard"],
  },
];

export function getWorkflow(workflowId) {
  return WORKFLOWS.find((workflow) => workflow.id === workflowId) || null;
}

export function inferWorkflowIntent(input) {
  const normalized = String(input || "").trim().toLocaleLowerCase("zh-Hant");
  if (!normalized) return { workflow: null, reason: "empty" };

  const ranked = WORKFLOWS.map((workflow) => ({
    workflow,
    score: workflow.keywords.reduce(
      (total, keyword) => total + (normalized.includes(keyword.toLocaleLowerCase("zh-Hant")) ? 1 : 0),
      0,
    ),
  })).sort((a, b) => b.score - a.score);

  if (!ranked[0] || ranked[0].score === 0) {
    return { workflow: null, reason: "unmatched" };
  }

  // 同分代表需求同時提到多種成品；第一版不替使用者猜主要輸出，改由選單確認。
  if (ranked[1] && ranked[1].score === ranked[0].score) {
    return {
      workflow: null,
      reason: "ambiguous",
      candidates: ranked.filter((item) => item.score === ranked[0].score).map((item) => item.workflow.id),
    };
  }

  return { workflow: ranked[0].workflow, reason: "matched" };
}

export function createTaskBrief(workflowId, requestText, project) {
  const workflow = getWorkflow(workflowId);
  if (!workflow) return null;
  return {
    workflow,
    requestText: String(requestText || "").trim(),
    projectLabel: project?.title || "尚未指定 Project",
    projectId: project?.project_id || "",
  };
}
