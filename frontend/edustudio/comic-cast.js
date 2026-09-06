/**
 * 漫畫站「角色演出」的純邏輯：表情變體、立繪 anchor、嘴巴座標。
 *
 * 抽成獨立模組是為了能用 `node --test` 驗證（comic-cast.test.js），JSX 只負責畫面。
 * 對應後端 core.comics.Character.expressions / .mouth 與 Dialogue.expression。
 */

/** 影片端支援的表情（順序 = UI 顯示順序）；值要與 core.comic_video.EXPRESSIONS 一致。 */
export const EXPRESSIONS = [
  ['neutral', '平常'],
  ['happy', '開心'],
  ['surprised', '驚訝'],
  ['questioning', '疑問'],
  ['worried', '擔心'],
  ['thinking', '沉吟'],
  ['angry', '生氣'],
];

/** 沒指定時嘴巴的預設寬高（相對立繪 0~1）；位置一定要使用者點或後端自動推估。 */
export const DEFAULT_MOUTH_SIZE = [0.1, 0.02];

const clamp01 = value => Math.min(1, Math.max(0, Number(value) || 0));
const round4 = value => Number(clamp01(value).toFixed(4));

/**
 * Series Bible 的角色文字（ID | 名稱 | 職責 | visual lock | 語氣）→ 角色陣列。
 *
 * 會依 character_id 合併既有角色的 anchor_assets / expressions / mouth：這些是在
 * 「角色演出」面板設定的，不在文字框裡，存 Bible 時不可以被洗掉。
 */
export function parseCharacters(value, existing = []) {
  const prior = new Map((existing || []).map(item => [item.character_id, item]));
  return String(value || '')
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const [character_id, name, role = '', visual_lock = '', voice = ''] = line.split('|').map(item => item.trim());
      const id = character_id || `character_${index + 1}`;
      const kept = prior.get(id) || {};
      return {
        ...kept,
        character_id: id,
        name: name || id,
        role,
        visual_lock,
        voice,
        anchor_assets: kept.anchor_assets || [],
        expressions: kept.expressions || {},
        mouth: kept.mouth || [],
      };
    });
}

export function charactersText(series) {
  return (series?.characters || [])
    .map(item => [item.character_id, item.name, item.role, item.visual_lock, item.voice].join(' | '))
    .join('\n');
}

/** 這個角色影片裡用哪張立繪：neutral 表情優先，其次第一張 anchor。 */
export function portraitAssetId(character) {
  return character?.expressions?.neutral || character?.anchor_assets?.[0] || '';
}

/** 可當立繪／表情變體的 asset（只有 character_anchor）。 */
export function anchorOptions(assets) {
  return (assets || []).filter(asset => asset.kind === 'character_anchor').map(asset => asset.asset_id);
}

/** 點立繪 → 嘴巴座標 [cx, cy, w, h]；寬高沿用原本的，沒有就用預設。 */
export function mouthFromClick(x, y, prior = []) {
  const [w, h] = prior.length === 4 ? [prior[2], prior[3]] : DEFAULT_MOUTH_SIZE;
  return [round4(x), round4(y), round4(w), round4(h)];
}

/** 改嘴巴的寬或高；還沒定位過就不動（位置要先點過才有意義）。 */
export function withMouthSize(mouth, key, value) {
  if (!mouth || mouth.length !== 4) return mouth || [];
  const next = [...mouth];
  next[key === 'w' ? 2 : 3] = round4(value);
  return next;
}

/** 更新某個角色，回傳新的角色陣列（不就地改）。 */
export function updateCharacter(characters, characterId, updates) {
  return (characters || []).map(item => (item.character_id === characterId ? { ...item, ...updates } : item));
}

/** 設定 / 清除一個表情變體（asset_id 空字串＝清除）。 */
export function withExpression(character, name, assetId) {
  const next = { ...(character.expressions || {}) };
  if (assetId) next[name] = assetId;
  else delete next[name];
  return next;
}

/**
 * 這個角色在影片裡會不會有立繪演出，以及為什麼沒有。
 * 影片端 (core.comic_video.resolve_portraits) 的規則：narrator 不做立繪，其餘要有可解析的 neutral。
 */
export function castStatus(character, assets) {
  if (character.character_id === 'narrator') {
    return { active: false, narratorAvatar: true, reason: '旁白不做立繪；這裡選的 anchor 會當片頭／片尾卡與旁白字幕條旁的頭像' };
  }
  const assetId = portraitAssetId(character);
  if (!assetId) return { active: false, reason: '尚未指定立繪（選一張 character_anchor）' };
  if (!anchorOptions(assets).includes(assetId)) return { active: false, reason: `這一集沒有 ${assetId} 這個 anchor asset` };
  return { active: true, reason: character.mouth?.length === 4 ? '嘴巴位置已手動指定' : '嘴巴位置由去背立繪自動推估' };
}
