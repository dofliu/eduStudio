import test from "node:test";
import assert from "node:assert/strict";

import {
  EXPRESSIONS,
  anchorOptions,
  castStatus,
  charactersText,
  parseCharacters,
  portraitAssetId,
  updateCharacter,
  withExpression,
  withMouthShape,
} from "./comic-cast.js";

const CAST = [{
  character_id: "aguang", name: "阿光", role: "值班工程師", visual_lock: "lock", voice: "沉穩",
  anchor_assets: ["aguang_front"], expressions: { happy: "aguang_happy" }, mouth_shapes: ["aguang_m1"],
}];
const ASSETS = [
  { asset_id: "aguang_front", kind: "character_anchor" },
  { asset_id: "aguang_happy", kind: "character_anchor" },
  { asset_id: "aguang_m1", kind: "character_anchor" },
  { asset_id: "scene_1", kind: "scene" },
];

test("存 Series Bible 不會洗掉在角色演出面板設定的立繪／表情／嘴型圖", () => {
  const merged = parseCharacters("aguang | 阿光 | 值班工程師 | lock | 沉穩", CAST);
  assert.deepEqual(merged[0].anchor_assets, ["aguang_front"]);
  assert.deepEqual(merged[0].expressions, { happy: "aguang_happy" });
  assert.deepEqual(merged[0].mouth_shapes, ["aguang_m1"]);
});

test("文字框改到的欄位照文字走，新角色補上空的演出欄位", () => {
  const merged = parseCharacters("aguang | 阿光師傅 | 領班 | lock2 | 爽朗\nxiaoru | 小儒", CAST);
  assert.equal(merged[0].name, "阿光師傅");
  assert.equal(merged[0].role, "領班");
  assert.deepEqual(merged[1], {
    character_id: "xiaoru", name: "小儒", role: "", visual_lock: "", voice: "",
    anchor_assets: [], expressions: {}, mouth_shapes: [],
  });
});

test("角色文字與解析可來回轉換", () => {
  assert.equal(charactersText({ characters: CAST }), "aguang | 阿光 | 值班工程師 | lock | 沉穩");
  assert.equal(parseCharacters(charactersText({ characters: CAST }), CAST)[0].character_id, "aguang");
});

test("立繪取 neutral 表情優先，其次第一張 anchor", () => {
  assert.equal(portraitAssetId(CAST[0]), "aguang_front");
  assert.equal(portraitAssetId({ ...CAST[0], expressions: { neutral: "aguang_neutral" } }), "aguang_neutral");
  assert.equal(portraitAssetId({}), "");
});

test("只有 character_anchor 能當立繪", () => {
  assert.deepEqual(anchorOptions(ASSETS), ["aguang_front", "aguang_happy", "aguang_m1"]);
});

test("嘴型圖可勾可取消，不重複", () => {
  assert.deepEqual(withMouthShape(CAST[0], "aguang_m2", true), ["aguang_m1", "aguang_m2"]);
  assert.deepEqual(withMouthShape(CAST[0], "aguang_m1", true), ["aguang_m1"]);
  assert.deepEqual(withMouthShape(CAST[0], "aguang_m1", false), []);
  assert.deepEqual(withMouthShape({ character_id: "x" }, "m", true), ["m"]);
});

test("表情變體可設定也可清除", () => {
  assert.deepEqual(withExpression(CAST[0], "angry", "aguang_angry"), { happy: "aguang_happy", angry: "aguang_angry" });
  assert.deepEqual(withExpression(CAST[0], "happy", ""), {});
});

test("更新角色不就地改原陣列", () => {
  const next = updateCharacter(CAST, "aguang", { mouth_shapes: [] });
  assert.deepEqual(next[0].mouth_shapes, []);
  assert.deepEqual(CAST[0].mouth_shapes, ["aguang_m1"]);
});

test("表情清單與後端一致（7 種，neutral 在最前）", () => {
  assert.equal(EXPRESSIONS.length, 7);
  assert.equal(EXPRESSIONS[0][0], "neutral");
  assert.deepEqual(EXPRESSIONS.map(([id]) => id).sort(),
    ["angry", "happy", "neutral", "questioning", "surprised", "thinking", "worried"]);
});

test("面板要說清楚這個角色會不會真的有立繪演出", () => {
  assert.equal(castStatus(CAST[0], ASSETS).active, true);
  assert.match(castStatus(CAST[0], ASSETS).reason, /1 張嘴型圖/);
  // 沒嘴型圖要講明嘴巴不會動 —— 全身立繪上合成嘴型不會像, 所以乾脆不做
  assert.match(castStatus({ ...CAST[0], mouth_shapes: [] }, ASSETS).reason, /嘴巴不會動/);
  // 勾到這一集沒有的 asset 不能算數
  assert.match(castStatus({ ...CAST[0], mouth_shapes: ["gone"] }, ASSETS).reason, /嘴巴不會動/);
  assert.equal(castStatus({ character_id: "narrator", name: "" }, ASSETS).active, false);
  assert.equal(castStatus({ character_id: "x", anchor_assets: [] }, ASSETS).active, false);
  // 角色指到這一集沒有的 asset → 要講出是哪一個，不能默默不演
  const stale = castStatus({ character_id: "x", anchor_assets: ["gone"] }, ASSETS);
  assert.equal(stale.active, false);
  assert.match(stale.reason, /gone/);
});
