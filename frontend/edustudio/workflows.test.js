import test from "node:test";
import assert from "node:assert/strict";

import { createTaskBrief, inferWorkflowIntent } from "./workflows.js";

const cases = [
  ["把講義做成 8 頁教學漫畫", "comic"],
  ["整理成一份大二材料力學簡報", "slides"],
  ["做一張招生資訊圖卡", "cards"],
  ["產生五分鐘旁白影片", "video"],
];

for (const [input, expected] of cases) {
  test(`辨識工作流程：${expected}`, () => {
    assert.equal(inferWorkflowIntent(input).workflow?.id, expected);
  });
}

test("多種成品同分時要求使用者確認", () => {
  const result = inferWorkflowIntent("請同時製作影片和簡報");
  assert.equal(result.workflow, null);
  assert.equal(result.reason, "ambiguous");
});

test("不認得的需求不自行猜測", () => {
  const result = inferWorkflowIntent("整理一下這份資料");
  assert.equal(result.workflow, null);
  assert.equal(result.reason, "unmatched");
});

test("任務摘要保留 Project 與原始需求", () => {
  const brief = createTaskBrief("comic", "做成六頁漫畫", {
    project_id: "materials",
    title: "材料力學",
  });
  assert.equal(brief.workflow.id, "comic");
  assert.equal(brief.projectId, "materials");
  assert.equal(brief.projectLabel, "材料力學");
  assert.equal(brief.requestText, "做成六頁漫畫");
});
