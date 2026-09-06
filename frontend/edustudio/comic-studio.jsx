import React, { useEffect, useMemo, useState } from 'react';

import {
  EXPRESSIONS, anchorOptions, castStatus, charactersText, mouthFromClick,
  parseCharacters, portraitAssetId, updateCharacter, withExpression, withMouthSize,
} from './comic-cast.js';

const TABS = [
  ['overview', '總覽'],
  ['bible', 'Series Bible'],
  ['story', '劇本與分鏡'],
  ['pages', '頁面編輯'],
  ['evidence', 'Evidence'],
  ['assets', 'Assets'],
  ['qa', 'QA Gate'],
  ['release', '匯出與發布'],
];

const FLOW = ['BRIEF', 'STORYBOARD', 'IMAGE', 'LAYOUT', 'QA', 'CURRENT'];
const QA_GATES = [
  ['anatomy', '人物／肢體'],
  ['technical', '技術與來源'],
  ['text', '對白／版面'],
  ['safety', '安全邊界'],
  ['page_render', '逐頁 render'],
  ['human_approval', '教師最終核准'],
];

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch { /* response 不是 JSON */ }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

function Btn({ children, variant = 'default', size = 'md', busy = false, ...props }) {
  return <button className={`es-btn es-btn-${variant} es-btn-${size}`} disabled={busy || props.disabled} {...props}>
    {busy ? '處理中…' : children}
  </button>;
}

function Field({ label, hint, children, wide = false }) {
  return <label className={`es-field${wide ? ' is-wide' : ''}`}>
    <span className="es-field-label">{label}</span>
    {children}
    {hint && <span className="es-field-hint">{hint}</span>}
  </label>;
}

function StatePill({ value }) {
  const tone = value === 'PASS' || value === 'CURRENT' ? 'success'
    : value === 'FAIL' ? 'error'
      : value === 'HOLD' ? 'warning' : 'info';
  return <span className={`es-badge es-badge-${tone}`}>{value}</span>;
}

function splitLines(value) {
  return String(value || '').split(/\r?\n/).map(item => item.trim()).filter(Boolean);
}

function glossaryText(series) {
  return (series?.glossary || []).map(item => `${item.term} | ${item.definition}`).join('\n');
}

function parseGlossary(value) {
  return splitLines(value).map(line => {
    const separator = line.indexOf('|');
    return {
      term: (separator >= 0 ? line.slice(0, separator) : line).trim(),
      definition: (separator >= 0 ? line.slice(separator + 1) : '').trim(),
      aliases: [],
    };
  }).filter(item => item.term && item.definition);
}

function dialogueText(page) {
  return (page.dialogues || []).map(item => `${item.speaker_id} | ${item.text}`).join('\n');
}

function parseDialogues(value, pageNo, existing = []) {
  return splitLines(value).map((line, index) => {
    const separator = line.indexOf('|');
    const speaker = separator >= 0 ? line.slice(0, separator).trim() : 'narrator';
    const text = separator >= 0 ? line.slice(separator + 1).trim() : line;
    const prior = existing[index] || {};
    return {
      ...prior,
      dialogue_id: `p${String(pageNo).padStart(2, '0')}_d${String(index + 1).padStart(2, '0')}`,
      speaker_id: speaker || 'narrator', text, bubble_style: 'rounded_callout',
      layout_mode: prior.layout_mode || 'AUTO',
      x: prior.x ?? (index % 2 ? 0.55 : 0.06),
      y: prior.y ?? (0.08 + (index % 3) * 0.2),
      w: prior.w ?? 0.38, h: prior.h ?? 0.13,
      font_size: prior.font_size || 16, tail_target: prior.tail_target || '',
      tail_x: prior.tail_x ?? (index % 2 ? 0.7 : 0.3), tail_y: prior.tail_y ?? 0.78,
    };
  });
}

function readFileDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error || new Error('檔案讀取失敗'));
    reader.readAsDataURL(file);
  });
}

export default function ComicStudio({ activeProject, launchContext }) {
  const pid = activeProject?.project_id || '';
  const [capabilities, setCapabilities] = useState(null);
  const [seriesList, setSeriesList] = useState([]);
  const [seriesId, setSeriesId] = useState('');
  const [series, setSeries] = useState(null);
  const [episodes, setEpisodes] = useState([]);
  const [episode, setEpisode] = useState(null);
  const [tab, setTab] = useState('overview');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [offlineMock, setOfflineMock] = useState(false);
  const [validation, setValidation] = useState(null);
  const [exports, setExports] = useState([]);
  const [videoJob, setVideoJob] = useState(null);
  const [voiceSpecs, setVoiceSpecs] = useState({});
  const [placing, setPlacing] = useState({});   // page_no → speaker_id 正在點圖定位
  const [mouthPicking, setMouthPicking] = useState('');   // character_id 正在點立繪標嘴巴
  const [discovery, setDiscovery] = useState(null);

  const [newSeries, setNewSeries] = useState({
    series_id: 'teaching_series', title: '我的教學漫畫', description: '',
    visual_bible: 'cinematic educational manga, clean line art, restrained cel shading, professional adult characters',
    world_lock: '',
  });
  const [newEpisode, setNewEpisode] = useState({
    story_id: 'EP001', title: '', week: '', page_count: 8,
    audience: '大學生', story_brief: launchContext?.requestText || '',
    learning_objectives: '', technical_topics: '',
  });
  const [seriesDraft, setSeriesDraft] = useState({ visual_bible: '', world_lock: '', characters: '', glossary: '' });
  const [evidenceDraft, setEvidenceDraft] = useState({
    source_id: 'src_01', title: '', source_type: 'course_material', publisher: '', url: '',
    citation: '', supported_claims: '', limits: '',
  });
  const [assetDraft, setAssetDraft] = useState({ kind: 'character_anchor', file: null });
  const [qaDrafts, setQaDrafts] = useState({});
  const [importPath, setImportPath] = useState('');
  const [holdReason, setHoldReason] = useState('');
  const [forkVersion, setForkVersion] = useState('v0.2');

  const base = pid ? `/projects/${encodeURIComponent(pid)}/comics` : '';
  const editable = episode && episode.state !== 'CURRENT';

  const selectedAsset = useMemo(() => {
    const map = {};
    for (const asset of episode?.assets || []) map[asset.asset_id] = asset;
    return map;
  }, [episode?.assets]);

  useEffect(() => {
    setEpisode(null); setSeries(null); setSeriesList([]); setEpisodes([]); setError(''); setNotice('');
    if (pid) bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  useEffect(() => {
    if (!series) return;
    setSeriesDraft({
      visual_bible: series.visual_bible || '',
      world_lock: series.world_lock || '',
      characters: charactersText(series),
      glossary: glossaryText(series),
    });
  }, [series]);

  async function run(label, action) {
    setBusy(label); setError(''); setNotice('');
    try {
      const result = await action();
      setNotice(`${label}完成`);
      return result;
    } catch (err) {
      setError(err.message || String(err));
      throw err;
    } finally {
      setBusy('');
    }
  }

  async function bootstrap(preferredSeries = '') {
    try {
      const [caps, allSeries] = await Promise.all([
        fetchJson(`${base}/capabilities`), fetchJson(`${base}/series`),
      ]);
      setCapabilities(caps); setSeriesList(allSeries);
      const chosen = allSeries.find(item => item.series_id === preferredSeries) || allSeries[0];
      if (chosen) await chooseSeries(chosen, allSeries);
    } catch (err) { setError(err.message); }
  }

  async function chooseSeries(item, knownList = seriesList) {
    setSeriesId(item.series_id); setSeries(item); setEpisode(null); setValidation(null);
    const list = await fetchJson(`${base}/episodes?series_id=${encodeURIComponent(item.series_id)}`);
    setEpisodes(list);
    const current = list[0];
    if (current) setEpisode(current);
    if (!knownList.some(value => value.series_id === item.series_id)) setSeriesList([...knownList, item]);
  }

  async function reloadEpisode(value = episode) {
    if (!value) return;
    const refreshed = await fetchJson(`${base}/episodes/${encodeURIComponent(value.story_id)}?version=${encodeURIComponent(value.version)}`);
    setEpisode(refreshed);
    const list = await fetchJson(`${base}/episodes?series_id=${encodeURIComponent(refreshed.series_id)}`);
    setEpisodes(list);
    return refreshed;
  }

  async function createSeries() {
    const created = await run('建立 Series', () => fetchJson(`${base}/series`, {
      method: 'POST', body: JSON.stringify({
        ...newSeries,
        characters: [
          { character_id: 'mentor', name: '導師', role: 'Subject Mentor', visual_lock: 'adult professional mentor, consistent face and wardrobe', voice: '冷靜、清楚', anchor_assets: [] },
          { character_id: 'learner', name: '學習者', role: 'Reader Proxy', visual_lock: 'adult learner, curious expression, consistent face and wardrobe', voice: '好奇、敢問', anchor_assets: [] },
        ],
      }),
    }));
    await bootstrap(created.series_id);
    setTab('bible');
  }

  async function saveSeries() {
    const saved = await run('儲存 Series Bible', () => fetchJson(`${base}/series/${encodeURIComponent(series.series_id)}`, {
      method: 'PUT', body: JSON.stringify({
        ...series,
        visual_bible: seriesDraft.visual_bible,
        world_lock: seriesDraft.world_lock,
        characters: parseCharacters(seriesDraft.characters, series?.characters),
        glossary: parseGlossary(seriesDraft.glossary),
      }),
    }));
    setSeries(saved);
  }

  async function createEpisode() {
    const created = await run('建立 Episode', () => fetchJson(`${base}/episodes`, {
      method: 'POST', body: JSON.stringify({
        series_id: seriesId,
        story_id: newEpisode.story_id,
        title: newEpisode.title || newEpisode.story_id,
        version: 'v0.1', week: newEpisode.week, audience: newEpisode.audience,
        page_count: Number(newEpisode.page_count), story_brief: newEpisode.story_brief,
        learning_objectives: splitLines(newEpisode.learning_objectives),
        technical_topics: splitLines(newEpisode.technical_topics),
        characters: (series?.characters || []).map(item => item.character_id),
      }),
    }));
    setEpisode(created); setEpisodes([created, ...episodes]); setTab('story');
  }

  async function saveEpisode(updates) {
    const saved = await run('儲存 Episode', () => fetchJson(`${base}/episodes/${encodeURIComponent(episode.story_id)}?version=${encodeURIComponent(episode.version)}`, {
      method: 'PATCH', body: JSON.stringify({ updates }),
    }));
    setEpisode(saved); return saved;
  }

  async function generate(kind) {
    const saved = await run(kind === 'script' ? 'AI 劇本草稿' : 'AI 分鏡草稿', () => fetchJson(
      `${base}/episodes/${encodeURIComponent(episode.story_id)}/generate/${kind}?version=${encodeURIComponent(episode.version)}`,
      { method: 'POST', body: JSON.stringify({ mock: offlineMock }) },
    ));
    setEpisode(saved);
  }

  async function composePrompts() {
    const saved = await run('組合 Prompts', () => fetchJson(
      `${base}/episodes/${encodeURIComponent(episode.story_id)}/compose-prompts?version=${encodeURIComponent(episode.version)}`,
      { method: 'POST' },
    ));
    setEpisode(saved);
  }

  async function generatePageImage(pageNo) {
    const result = await run(`生成 P${pageNo} 圖片`, () => fetchJson(
      `${base}/episodes/${encodeURIComponent(episode.story_id)}/generate/images?version=${encodeURIComponent(episode.version)}`,
      { method: 'POST', body: JSON.stringify({ mock: offlineMock, page_numbers: [pageNo], use_references: true }) },
    ));
    const laidOut = await fetchJson(
      `${base}/episodes/${encodeURIComponent(episode.story_id)}/auto-layout?version=${encodeURIComponent(episode.version)}`,
      { method: 'POST' },
    );
    setEpisode(laidOut);
    if (result.failed?.length) setError(result.failed.map(item => `P${item.page_no}: ${item.error}`).join('；'));
  }

  function updatePage(pageNo, updates) {
    setEpisode(current => ({
      ...current,
      pages: current.pages.map(page => page.page_no === pageNo ? { ...page, ...updates } : page),
    }));
  }

  function updateDialogue(pageNo, dialogueIndex, updates) {
    setEpisode(current => ({
      ...current,
      pages: current.pages.map(page => page.page_no === pageNo ? {
        ...page,
        dialogues: page.dialogues.map((dialogue, index) => index === dialogueIndex ? { ...dialogue, ...updates } : dialogue),
      } : page),
    }));
  }

  async function autoLayout() {
    const saved = await run('依畫面配置泡泡', async () => {
      await saveEpisode({ pages: episode.pages });   // 先存 (含 speaker_positions), 再依存檔排版
      return fetchJson(
        `${base}/episodes/${encodeURIComponent(episode.story_id)}/auto-layout?version=${encodeURIComponent(episode.version)}`,
        { method: 'POST' },
      );
    });
    setEpisode(saved);
  }

  async function locateSpeakers(pageNo) {
    const saved = await run('AI 定位角色', async () => {
      await saveEpisode({ pages: episode.pages });
      return fetchJson(
        `${base}/episodes/${encodeURIComponent(episode.story_id)}/locate-speakers?version=${encodeURIComponent(episode.version)}`,
        { method: 'POST', body: JSON.stringify({ mock: offlineMock, page_numbers: pageNo ? [pageNo] : [] }) },
      );
    });
    setEpisode(saved);
  }

  function placeSpeaker(page, event) {
    const speaker = placing[page.page_no];
    if (!speaker || !editable) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
    updatePage(page.page_no, { speaker_positions: { ...(page.speaker_positions || {}), [speaker]: [Number(x.toFixed(4)), Number(y.toFixed(4))] } });
  }

  // ---- 角色演出 (表情 / 立繪 / 嘴巴): 角色住在 series, 所以改完要存回 series ----
  function updateCast(characterId, updates) {
    setSeries(current => ({ ...current, characters: updateCharacter(current?.characters, characterId, updates) }));
  }

  function pickMouth(character, event) {
    if (mouthPicking !== character.character_id || !editable) return;
    const rect = event.currentTarget.getBoundingClientRect();
    updateCast(character.character_id, {
      mouth: mouthFromClick((event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height, character.mouth),
    });
    setMouthPicking('');
  }

  async function saveCast() {
    const saved = await run('儲存角色演出', () => fetchJson(`${base}/series/${encodeURIComponent(series.series_id)}`, {
      method: 'PUT', body: JSON.stringify(series),
    }));
    setSeries(saved);
  }

  async function savePages() {
    await saveEpisode({ pages: episode.pages });
  }

  async function addEvidence() {
    const source = {
      ...evidenceDraft,
      accessed_at: new Date().toISOString().slice(0, 10),
      supported_claims: splitLines(evidenceDraft.supported_claims),
      limits: splitLines(evidenceDraft.limits), page_mapping: [],
    };
    const saved = await run('儲存 Evidence', () => fetchJson(
      `${base}/episodes/${encodeURIComponent(episode.story_id)}/evidence/${encodeURIComponent(source.source_id)}?version=${encodeURIComponent(episode.version)}`,
      { method: 'PUT', body: JSON.stringify(source) },
    ));
    setEpisode(saved);
    setEvidenceDraft({ ...evidenceDraft, source_id: `src_${String(saved.evidence.length + 1).padStart(2, '0')}`, title: '', url: '', citation: '', supported_claims: '', limits: '' });
  }

  async function uploadAsset() {
    if (!assetDraft.file) return;
    const dataUrl = await readFileDataUrl(assetDraft.file);
    const saved = await run('上傳 Asset', () => fetchJson(
      `${base}/episodes/${encodeURIComponent(episode.story_id)}/assets?version=${encodeURIComponent(episode.version)}`,
      { method: 'POST', body: JSON.stringify({ filename: assetDraft.file.name, data_url: dataUrl, kind: assetDraft.kind, provenance: 'user_upload' }) },
    ));
    setEpisode(saved); setAssetDraft({ ...assetDraft, file: null });
  }

  async function refreshValidation() {
    const report = await run('驗證', () => fetchJson(
      `${base}/episodes/${encodeURIComponent(episode.story_id)}/validation?version=${encodeURIComponent(episode.version)}`,
    ));
    setValidation(report);
  }

  async function saveQa(gate) {
    const draft = qaDrafts[gate] || {};
    const record = { gate, result: draft.result || 'UNVERIFIED', evidence: draft.evidence || '', reviewer: draft.reviewer || '' };
    const saved = await run(`QA ${gate}`, () => fetchJson(
      `${base}/episodes/${encodeURIComponent(episode.story_id)}/qa/${gate}?version=${encodeURIComponent(episode.version)}`,
      { method: 'PUT', body: JSON.stringify(record) },
    ));
    setEpisode(saved); await refreshValidation();
  }

  async function transition(target) {
    const saved = await run(`狀態 → ${target}`, () => fetchJson(
      `${base}/episodes/${encodeURIComponent(episode.story_id)}/state?version=${encodeURIComponent(episode.version)}`,
      { method: 'POST', body: JSON.stringify({ target, reason: target === 'HOLD' ? holdReason : '' }) },
    ));
    setEpisode(saved); await refreshValidation();
  }

  async function fork() {
    const saved = await run(`建立 ${forkVersion}`, () => fetchJson(
      `${base}/episodes/${encodeURIComponent(episode.story_id)}/fork`,
      { method: 'POST', body: JSON.stringify({ from_version: episode.version, new_version: forkVersion }) },
    ));
    setEpisode(saved); setTab('story');
  }

  async function exportKind(kind) {
    const result = await run(`匯出 ${kind.toUpperCase()}`, () => fetchJson(
      `${base}/episodes/${encodeURIComponent(episode.story_id)}/exports/${kind}?version=${encodeURIComponent(episode.version)}`,
      { method: 'POST' },
    ));
    setEpisode(result.episode); setExports(current => [result, ...current.filter(item => item.kind !== kind)]);
  }

  async function renderVideo() {
    const started = await run('渲染動態漫畫影片', () => fetchJson(
      `${base}/episodes/${encodeURIComponent(episode.story_id)}/video`,
      { method: 'POST', body: JSON.stringify({ version: episode.version, mock: offlineMock, voices: Object.fromEntries(Object.entries(voiceSpecs).filter(([, v]) => v && v.trim())) }) },
    ));
    setVideoJob({ ...started, progress: 0 });
    const poll = async () => {
      try {
        const rec = await fetchJson(started.status_url);
        const mp4 = (rec.artifacts || []).find(item => item.kind === 'mp4');
        setVideoJob(current => ({ ...(current || started), state: rec.state, progress: rec.progress ?? 0, error: rec.error, mp4 }));
        if (rec.state !== 'done' && rec.state !== 'failed') setTimeout(poll, 2500);
        else if (rec.state === 'done') {
          const saved = await fetchJson(`${base}/episodes/${encodeURIComponent(episode.story_id)}?version=${encodeURIComponent(episode.version)}`);
          setEpisode(saved);
        }
      } catch (err) {
        setVideoJob(current => ({ ...(current || started), state: 'failed', error: err.message || String(err) }));
      }
    };
    setTimeout(poll, 1500);
  }

  async function publish() {
    const saved = await run('發布到內部 Reader', () => fetchJson(
      `${base}/episodes/${encodeURIComponent(episode.story_id)}/publish?version=${encodeURIComponent(episode.version)}`,
      { method: 'POST', body: JSON.stringify({ published_by: 'Teacher / Editor', channel: 'internal_reader' }) },
    ));
    setEpisode(saved);
  }

  async function withdraw(release) {
    const saved = await run('撤回 Release', () => fetchJson(
      `${base}/episodes/${encodeURIComponent(episode.story_id)}/${encodeURIComponent(episode.version)}/releases/${encodeURIComponent(release.release_id)}/withdraw`,
      { method: 'POST' },
    ));
    setEpisode(saved);
  }

  async function discoverPackage(importNow = false) {
    const path = `${base}/${importNow ? 'import' : 'discover'}`;
    const result = await run(importNow ? '匯入既有 Package' : '唯讀掃描 Package', () => fetchJson(path, {
      method: 'POST', body: JSON.stringify({ package_path: importPath, series_id: seriesId }),
    }));
    if (importNow) {
      setEpisode(result); setEpisodes([result, ...episodes]); setTab('overview');
    } else setDiscovery(result);
  }

  if (!activeProject) {
    return <div className="es-comic-empty es-card">
      <h2>先選擇或建立 Project</h2>
      <p>漫畫 Series、Episode、sources、assets 與 release 都必須歸屬一個 Project，避免形成無主檔案。</p>
    </div>;
  }

  return <div className="es-comic-studio">
    <header className="es-comic-studio-head">
      <div>
        <span className="es-home-eyebrow">COMIC PRODUCTION SYSTEM · INTERNAL</span>
        <h1>{episode?.title || series?.title || '建立漫畫製作空間'}</h1>
        <p>{activeProject.title} · File-first · Evidence-gated · Versioned release</p>
      </div>
      <div className="es-comic-head-actions">
        {episode && <><StatePill value={episode.state} /><span className="es-badge">{episode.story_id} · {episode.version} · r{episode.revision}</span></>}
        {capabilities && <span className={`es-badge es-badge-${capabilities.gemini_configured ? 'success' : 'warning'}`}>
          AI API {capabilities.gemini_configured ? '已設定' : '未設定'}
        </span>}
      </div>
    </header>

    {(error || notice) && <div className={`es-comic-message ${error ? 'is-error' : 'is-success'}`} role="status">{error || notice}</div>}

    {!seriesList.length ? <section className="es-card es-comic-onboard">
      <h2>建立第一個 Series</h2>
      <p>Series Bible 管理世界觀、固定角色、視覺 lock 與禁項；不限定離岸風電主題。</p>
      <div className="es-comic-form-grid">
        <Field label="Series ID"><input className="es-input" value={newSeries.series_id} onChange={e => setNewSeries({ ...newSeries, series_id: e.target.value })} /></Field>
        <Field label="系列名稱"><input className="es-input" value={newSeries.title} onChange={e => setNewSeries({ ...newSeries, title: e.target.value })} /></Field>
        <Field label="說明" wide><textarea className="es-textarea" value={newSeries.description} onChange={e => setNewSeries({ ...newSeries, description: e.target.value })} /></Field>
        <Field label="視覺風格" wide><textarea className="es-textarea" value={newSeries.visual_bible} onChange={e => setNewSeries({ ...newSeries, visual_bible: e.target.value })} /></Field>
      </div>
      <Btn variant="primary" onClick={createSeries} busy={busy === '建立 Series'}>建立 Series</Btn>
    </section> : <>
      <div className="es-comic-toolbar">
        <label>Series
          <select className="es-select" value={seriesId} onChange={e => {
            const chosen = seriesList.find(item => item.series_id === e.target.value); if (chosen) chooseSeries(chosen);
          }}>{seriesList.map(item => <option key={item.series_id} value={item.series_id}>{item.title}</option>)}</select>
        </label>
        <label>Episode
          <select className="es-select" value={episode ? `${episode.story_id}@${episode.version}` : ''} onChange={e => {
            if (!e.target.value) {
              setEpisode(null);
              return;
            }
            const [story, version] = e.target.value.split('@');
            fetchJson(`${base}/episodes/${encodeURIComponent(story)}?version=${encodeURIComponent(version)}`).then(setEpisode).catch(err => setError(err.message));
          }}>
            <option value="">新增 Episode…</option>
            {episodes.map(item => <option key={`${item.story_id}@${item.version}`} value={`${item.story_id}@${item.version}`}>{item.title} · {item.version}</option>)}
          </select>
        </label>
        <label className="es-comic-mock"><input type="checkbox" checked={offlineMock} onChange={e => setOfflineMock(e.target.checked)} /> 離線 MOCK（不可發布）</label>
      </div>

      {!episode ? <section className="es-card es-comic-onboard">
        <h2>建立 Episode</h2>
        <div className="es-comic-form-grid">
          <Field label="Story ID"><input className="es-input" value={newEpisode.story_id} onChange={e => setNewEpisode({ ...newEpisode, story_id: e.target.value })} /></Field>
          <Field label="標題"><input className="es-input" value={newEpisode.title} onChange={e => setNewEpisode({ ...newEpisode, title: e.target.value })} /></Field>
          <Field label="週次／期數"><input className="es-input" value={newEpisode.week} onChange={e => setNewEpisode({ ...newEpisode, week: e.target.value })} /></Field>
          <Field label="頁數"><input className="es-input" type="number" min="1" max="80" value={newEpisode.page_count} onChange={e => setNewEpisode({ ...newEpisode, page_count: e.target.value })} /></Field>
          <Field label="受眾"><input className="es-input" value={newEpisode.audience} onChange={e => setNewEpisode({ ...newEpisode, audience: e.target.value })} /></Field>
          <Field label="Learning objectives（一行一項）"><textarea className="es-textarea" value={newEpisode.learning_objectives} onChange={e => setNewEpisode({ ...newEpisode, learning_objectives: e.target.value })} /></Field>
          <Field label="故事構想" wide><textarea className="es-textarea" value={newEpisode.story_brief} onChange={e => setNewEpisode({ ...newEpisode, story_brief: e.target.value })} /></Field>
          <Field label="技術主題（一行一項）" wide><textarea className="es-textarea" value={newEpisode.technical_topics} onChange={e => setNewEpisode({ ...newEpisode, technical_topics: e.target.value })} /></Field>
        </div>
        <Btn variant="primary" onClick={createEpisode} busy={busy === '建立 Episode'}>建立 Episode</Btn>
      </section> : <>
        <nav className="es-comic-tabs" aria-label="漫畫製作階段">
          {TABS.map(([id, label]) => <button key={id} className={tab === id ? 'is-active' : ''} onClick={() => setTab(id)}>{label}</button>)}
        </nav>

        {tab === 'overview' && <Overview episode={episode} series={series} selectedAsset={selectedAsset} onTab={setTab} />}

        {tab === 'bible' && <section className="es-card es-comic-panel">
          <div className="es-comic-section-head"><div><h2>Series Bible</h2><p>角色、世界觀與視覺 lock 會組進每一頁 Prompt。</p></div><Btn variant="primary" onClick={saveSeries} busy={busy === '儲存 Series Bible'}>儲存</Btn></div>
          <div className="es-comic-form-grid">
            <Field label="Visual Bible" wide><textarea className="es-textarea es-codearea" value={seriesDraft.visual_bible} onChange={e => setSeriesDraft({ ...seriesDraft, visual_bible: e.target.value })} /></Field>
            <Field label="World / Equipment Lock" wide><textarea className="es-textarea es-codearea" value={seriesDraft.world_lock} onChange={e => setSeriesDraft({ ...seriesDraft, world_lock: e.target.value })} /></Field>
            <Field label="角色（每行：ID | 名稱 | 職責 | visual lock | 語氣）" wide><textarea className="es-textarea es-codearea is-tall" value={seriesDraft.characters} onChange={e => setSeriesDraft({ ...seriesDraft, characters: e.target.value })} /></Field>
            <Field label="Glossary（每行：術語 | 定義）" wide><textarea className="es-textarea es-codearea" value={seriesDraft.glossary} onChange={e => setSeriesDraft({ ...seriesDraft, glossary: e.target.value })} /></Field>
          </div>
        </section>}

        {tab === 'story' && <section className="es-card es-comic-panel">
          <div className="es-comic-section-head"><div><h2>Episode Brief → Script → Storyboard</h2><p>AI 只建立草稿；內容仍保留教師審查。</p></div></div>
          <div className="es-comic-form-grid">
            <Field label="故事構想" wide><textarea className="es-textarea" disabled={!editable} value={episode.story_brief} onChange={e => setEpisode({ ...episode, story_brief: e.target.value })} /></Field>
            <Field label="Learning objectives（一行一項）"><textarea className="es-textarea" disabled={!editable} value={(episode.learning_objectives || []).join('\n')} onChange={e => setEpisode({ ...episode, learning_objectives: splitLines(e.target.value) })} /></Field>
            <Field label="Technical topics（一行一項）"><textarea className="es-textarea" disabled={!editable} value={(episode.technical_topics || []).join('\n')} onChange={e => setEpisode({ ...episode, technical_topics: splitLines(e.target.value) })} /></Field>
            <Field label="故事摘要" wide><textarea className="es-textarea" disabled={!editable} value={episode.story_summary || ''} onChange={e => setEpisode({ ...episode, story_summary: e.target.value })} /></Field>
          </div>
          <div className="es-comic-actions">
            <Btn onClick={() => saveEpisode({ story_brief: episode.story_brief, story_summary: episode.story_summary, learning_objectives: episode.learning_objectives, technical_topics: episode.technical_topics })} disabled={!editable}>儲存 Brief</Btn>
            <Btn variant="primary" onClick={() => generate('script')} disabled={!editable} busy={busy === 'AI 劇本草稿'}>AI 產生劇本</Btn>
            <Btn variant="primary" onClick={() => generate('storyboard')} disabled={!editable} busy={busy === 'AI 分鏡草稿'}>AI 產生分鏡</Btn>
            <Btn variant="accent" onClick={composePrompts} disabled={!editable || !episode.pages.length} busy={busy === '組合 Prompts'}>組合 Image Prompts</Btn>
          </div>
          {!!episode.story_beats?.length && <div className="es-comic-beats">{episode.story_beats.map((beat, index) => <span key={`${beat}-${index}`}>{index + 1}. {beat}</span>)}</div>}
        </section>}

        {tab === 'pages' && <section className="es-comic-pages">
          <div className="es-comic-section-head"><div><h2>逐頁 Storyboard 與 Dialogue</h2><p>對白採「speaker ID | 文字」；泡泡會依場景留白自動配置，也可逐顆手動微調。</p></div><div className="es-comic-actions"><Btn onClick={autoLayout} disabled={!editable || !episode.pages.length} busy={busy === '依畫面配置泡泡'}>依畫面配置泡泡</Btn><Btn variant="primary" onClick={savePages} disabled={!editable || !episode.pages.length}>儲存全部頁面</Btn></div></div>
          {!episode.pages.length && <div className="es-card es-comic-placeholder">請先在「劇本與分鏡」產生或建立 storyboard。</div>}
          {episode.pages.map(page => <article key={page.page_no} className="es-card es-comic-page-card">
            <div className={`es-comic-page-preview${placing[page.page_no] ? ' is-placing' : ''}`} onClick={e => placeSpeaker(page, e)} title={placing[page.page_no] ? `點圖標記 ${placing[page.page_no]} 的頭部位置` : undefined}>
              {Object.entries(page.speaker_positions || {}).map(([sid, [px, py]]) => <span key={sid} className="es-comic-speaker-marker" style={{ left: `${px * 100}%`, top: `${py * 100}%` }}><i /><b>{sid}</b></span>)}
              {page.image_asset_id ? <img src={`${base}/episodes/${encodeURIComponent(episode.story_id)}/${episode.version}/assets/${encodeURIComponent(page.image_asset_id)}`} alt={page.alt_text} /> : <div className="es-comic-no-image">P{String(page.page_no).padStart(2, '0')}<small>尚無場景圖</small></div>}
              {(page.dialogues || []).map((dialogue, index) => <React.Fragment key={dialogue.dialogue_id || index}>
                <svg className="es-comic-bubble-tail" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><polygon points={`${((dialogue.tail_x ?? (dialogue.x + dialogue.w / 2)) - 0.018) * 100},${(dialogue.y + dialogue.h - 0.004) * 100} ${((dialogue.tail_x ?? (dialogue.x + dialogue.w / 2)) + 0.018) * 100},${(dialogue.y + dialogue.h - 0.004) * 100} ${(dialogue.tail_x ?? (dialogue.x + dialogue.w / 2)) * 100},${(dialogue.tail_y ?? (dialogue.y + dialogue.h + 0.1)) * 100}`} /></svg>
                <div className="es-comic-live-bubble" style={{ left: `${dialogue.x * 100}%`, top: `${dialogue.y * 100}%`, width: `${dialogue.w * 100}%`, height: `${dialogue.h * 100}%` }}>{dialogue.text}</div>
              </React.Fragment>)}
              <span className="es-badge">{page.beat || '未命名 beat'}</span>
            </div>
            <div className="es-comic-page-editor">
              <h3>P{String(page.page_no).padStart(2, '0')}</h3>
              <Field label="場景"><textarea className="es-textarea" disabled={!editable} value={page.scene_description} onChange={e => updatePage(page.page_no, { scene_description: e.target.value })} /></Field>
              <div className="es-comic-inline-fields"><Field label="Camera"><input className="es-input" disabled={!editable} value={page.camera} onChange={e => updatePage(page.page_no, { camera: e.target.value })} /></Field><Field label="Learning point"><input className="es-input" disabled={!editable} value={page.learning_point} onChange={e => updatePage(page.page_no, { learning_point: e.target.value })} /></Field></div>
              <Field label="對白（一行一顆泡泡）"><textarea className="es-textarea" disabled={!editable} value={dialogueText(page)} onChange={e => updatePage(page.page_no, { dialogues: parseDialogues(e.target.value, page.page_no, page.dialogues) })} /></Field>
              {!!page.dialogues?.length && <div className="es-comic-speaker-tools">
                <span>說話者位置</span>
                {[...new Set(page.dialogues.map(d => d.speaker_id).filter(sid => sid && sid !== 'narrator'))].map(sid => <button key={sid} type="button" className={`es-chip${placing[page.page_no] === sid ? ' is-active' : ''}${page.speaker_positions?.[sid] ? ' is-set' : ''}`} disabled={!editable} onClick={() => setPlacing(current => ({ ...current, [page.page_no]: current[page.page_no] === sid ? null : sid }))}>{sid}{page.speaker_positions?.[sid] ? ' ✓' : ''}</button>)}
                <Btn size="sm" onClick={() => locateSpeakers(page.page_no)} disabled={!editable || !page.image_asset_id} busy={busy === 'AI 定位角色'}>AI 定位角色</Btn>
                {placing[page.page_no] && <small>點場景圖上 {placing[page.page_no]} 的頭部；之後按「依畫面配置泡泡」</small>}
              </div>}
              {!!page.dialogues?.length && <details className="es-comic-bubble-controls"><summary>泡泡版面與指向設定</summary><div className="es-comic-bubble-list">{page.dialogues.map((dialogue, dialogueIndex) => <article key={dialogue.dialogue_id || dialogueIndex}>
                <div><strong>{dialogue.speaker_id}</strong><select className="es-select" disabled={!editable} value={dialogue.layout_mode || 'AUTO'} onChange={e => updateDialogue(page.page_no, dialogueIndex, { layout_mode: e.target.value })}><option value="AUTO">AUTO</option><option value="MANUAL">MANUAL</option></select>
                  {dialogue.speaker_id !== 'narrator' && <select className="es-select" title="說這句時的表情" disabled={!editable} value={dialogue.expression || ''} onChange={e => updateDialogue(page.page_no, dialogueIndex, { expression: e.target.value })}><option value="">表情：依語氣自動</option>{EXPRESSIONS.map(([id, label]) => <option key={id} value={id}>表情：{label}</option>)}</select>}</div>
                <div className="es-comic-coordinate-grid">{[
                  ['x', '左', dialogue.x], ['y', '上', dialogue.y], ['w', '寬', dialogue.w], ['h', '高', dialogue.h],
                  ['tail_x', '指向 X', dialogue.tail_x], ['tail_y', '指向 Y', dialogue.tail_y],
                ].map(([key, label, value]) => <Field key={key} label={`${label} %`}><input className="es-input" type="number" min="0" max="100" step="1" disabled={!editable} value={Math.round((value ?? 0) * 100)} onChange={e => updateDialogue(page.page_no, dialogueIndex, { [key]: Math.min(1, Math.max(0, Number(e.target.value) / 100)), layout_mode: 'MANUAL' })} /></Field>)}</div>
              </article>)}</div></details>}
              <Field label="Alt text"><input className="es-input" disabled={!editable} value={page.alt_text} onChange={e => updatePage(page.page_no, { alt_text: e.target.value })} /></Field>
              <details><summary>Image Prompt</summary><textarea className="es-textarea es-codearea is-tall" disabled={!editable} value={page.image_prompt} onChange={e => updatePage(page.page_no, { image_prompt: e.target.value })} /></details>
              <Btn variant="accent" size="sm" disabled={!editable || !page.image_prompt} onClick={() => generatePageImage(page.page_no)} busy={busy === `生成 P${page.page_no} 圖片`}>生成／重生本頁圖片</Btn>
            </div>
          </article>)}
        </section>}

        {tab === 'evidence' && <section className="es-comic-two-col">
          <div className="es-card es-comic-panel"><h2>Evidence Pack</h2>{episode.evidence.length ? episode.evidence.map(item => <article className="es-comic-evidence" key={item.source_id}><div><StatePill value={item.source_type} /><strong>{item.title}</strong></div><p>{item.citation}</p><small>Supports：{item.supported_claims.join('；') || 'TBD'}<br />Limits：{item.limits.join('；') || 'TBD'}</small></article>) : <p className="es-mut">尚無來源；發布 gate 會維持 HOLD。</p>}</div>
          <div className="es-card es-comic-panel"><h2>新增／更新來源</h2><div className="es-comic-form-grid one-col">
            <Field label="Source ID"><input className="es-input" value={evidenceDraft.source_id} onChange={e => setEvidenceDraft({ ...evidenceDraft, source_id: e.target.value })} /></Field>
            <Field label="Title"><input className="es-input" value={evidenceDraft.title} onChange={e => setEvidenceDraft({ ...evidenceDraft, title: e.target.value })} /></Field>
            <Field label="類型"><select className="es-select" value={evidenceDraft.source_type} onChange={e => setEvidenceDraft({ ...evidenceDraft, source_type: e.target.value })}>{['OEM', 'official_guidance', 'standard', 'research_paper', 'course_material', 'inference'].map(value => <option key={value}>{value}</option>)}</select></Field>
            <Field label="URL"><input className="es-input" value={evidenceDraft.url} onChange={e => setEvidenceDraft({ ...evidenceDraft, url: e.target.value })} /></Field>
            <Field label="Citation"><textarea className="es-textarea" value={evidenceDraft.citation} onChange={e => setEvidenceDraft({ ...evidenceDraft, citation: e.target.value })} /></Field>
            <Field label="Supported claims（一行一項）"><textarea className="es-textarea" value={evidenceDraft.supported_claims} onChange={e => setEvidenceDraft({ ...evidenceDraft, supported_claims: e.target.value })} /></Field>
            <Field label="Limits／不可推論事項"><textarea className="es-textarea" value={evidenceDraft.limits} onChange={e => setEvidenceDraft({ ...evidenceDraft, limits: e.target.value })} /></Field>
          </div><Btn variant="primary" onClick={addEvidence} disabled={!editable || !evidenceDraft.title}>儲存 Evidence</Btn></div>
        </section>}

        {tab === 'assets' && <><section className="es-comic-two-col">
          <div className="es-card es-comic-panel"><h2>Asset Library</h2><div className="es-comic-asset-grid">{episode.assets.map(asset => <article key={asset.asset_id}><img src={`${base}/episodes/${encodeURIComponent(episode.story_id)}/${episode.version}/assets/${encodeURIComponent(asset.asset_id)}`} alt={asset.kind} /><strong>{asset.asset_id}</strong><span>{asset.kind} · {asset.status}</span><small>{asset.provenance}</small></article>)}</div>{!episode.assets.length && <p className="es-mut">尚無 anchor、equipment reference 或 scene assets。</p>}</div>
          <div className="es-card es-comic-panel"><h2>上傳 Reference</h2><Field label="Asset 類型"><select className="es-select" value={assetDraft.kind} onChange={e => setAssetDraft({ ...assetDraft, kind: e.target.value })}>{['character_anchor', 'equipment_reference', 'scene', 'draft', 'precise_edit'].map(value => <option key={value}>{value}</option>)}</select></Field><Field label="PNG / JPG / WEBP"><input className="es-input" type="file" accept="image/png,image/jpeg,image/webp" onChange={e => setAssetDraft({ ...assetDraft, file: e.target.files?.[0] || null })} /></Field><Btn variant="primary" onClick={uploadAsset} disabled={!editable || !assetDraft.file}>上傳並記錄 provenance</Btn>
            <div className="es-comic-boundary">角色 anchor 與設備 reference 會送進 Gemini image API；scene 圖仍禁止生成可讀中文與 speech bubble。</div>
          </div>
        </section>

        <section className="es-card es-comic-panel es-comic-cast">
          <div className="es-comic-section-head">
            <div><h2>角色演出（表情 · 嘴型）</h2><p>指定立繪後，角色說話時會在動態漫畫影片的畫框角落現身：依台詞語氣換表情、講話時嘴會開合。設定存在 Series，整個連載共用。</p></div>
            <Btn variant="primary" onClick={saveCast} disabled={!editable || !series?.characters?.length} busy={busy === '儲存角色演出'}>儲存角色演出</Btn>
          </div>
          {!series?.characters?.length && <p className="es-mut">請先在 Series Bible 建立角色。</p>}
          <div className="es-comic-cast-grid">{(series?.characters || []).map(character => {
            const options = anchorOptions(episode.assets);
            const status = castStatus(character, episode.assets);
            const portrait = portraitAssetId(character);
            const assetUrl = id => `${base}/episodes/${encodeURIComponent(episode.story_id)}/${episode.version}/assets/${encodeURIComponent(id)}`;
            const picking = mouthPicking === character.character_id;
            return <article key={character.character_id} className="es-comic-cast-card">
              <header><strong>{character.name || character.character_id}</strong><small>{character.character_id}</small><span className={`es-badge es-badge-${status.active ? 'success' : 'info'}`}>{status.active ? '會演出' : '不演出'}</span></header>
              <div className={`es-comic-cast-portrait${picking ? ' is-picking' : ''}`}>
                {portrait && options.includes(portrait)
                  ? <div className="es-comic-cast-figure" onClick={e => pickMouth(character, e)} title={picking ? '點立繪上這個角色的嘴巴' : undefined}>
                    {/* 座標是相對「立繪本身」, 所以標記與點擊都掛在圖片盒上, 不是外框 (外框有留白) */}
                    <img src={assetUrl(portrait)} alt={character.name} />
                    {character.mouth?.length === 4 && <span className="es-comic-mouth-marker" style={{ left: `${character.mouth[0] * 100}%`, top: `${character.mouth[1] * 100}%`, width: `${character.mouth[2] * 100}%`, height: `${character.mouth[3] * 100}%` }} />}
                  </div>
                  : <div className="es-comic-no-image"><small>尚無立繪</small></div>}
              </div>
              <small className="es-mut">{status.reason}</small>
              <Field label="立繪（character_anchor）">
                <select className="es-select" disabled={!editable} value={character.anchor_assets?.[0] || ''} onChange={e => updateCast(character.character_id, { anchor_assets: e.target.value ? [e.target.value] : [] })}>
                  <option value="">（不指定 → 不演出）</option>
                  {options.map(id => <option key={id} value={id}>{id}</option>)}
                </select>
              </Field>
              {!status.narratorAvatar && <div className="es-comic-cast-mouth">
                <span>嘴巴位置</span>
                <button type="button" className={`es-chip${picking ? ' is-active' : ''}${character.mouth?.length === 4 ? ' is-set' : ''}`} disabled={!editable || !portrait} onClick={() => setMouthPicking(picking ? '' : character.character_id)}>{picking ? '點立繪上的嘴巴…' : '點圖標記'}</button>
                {character.mouth?.length === 4 && <>
                  <button type="button" className="es-chip" disabled={!editable} onClick={() => updateCast(character.character_id, { mouth: [] })}>清除（改回自動）</button>
                  {[['w', '寬', character.mouth[2]], ['h', '高', character.mouth[3]]].map(([key, label, value]) => <label key={key}>{label} %<input className="es-input" type="number" min="1" max="60" step="1" disabled={!editable} value={Math.round(value * 100)} onChange={e => updateCast(character.character_id, { mouth: withMouthSize(character.mouth, key, Number(e.target.value) / 100) })} /></label>)}
                </>}
              </div>}
              {!status.narratorAvatar && <details className="es-comic-cast-expressions"><summary>表情變體（{Object.keys(character.expressions || {}).length} / {EXPRESSIONS.length}）</summary>
                <div>{EXPRESSIONS.map(([id, label]) => <Field key={id} label={`${label}${id === 'neutral' ? '（預設立繪）' : ''}`}>
                  <select className="es-select" disabled={!editable} value={character.expressions?.[id] || ''} onChange={e => updateCast(character.character_id, { expressions: withExpression(character, id, e.target.value) })}>
                    <option value="">（沒有變體）</option>
                    {options.map(assetId => <option key={assetId} value={assetId}>{assetId}</option>)}
                  </select>
                </Field>)}</div>
                <div className="es-comic-boundary">沒準備變體的表情會用預設立繪，改以動態與情緒符號表現，不會沒反應。</div>
              </details>}
            </article>;
          })}</div>
          <div className="es-comic-boundary">立繪要<strong>去背 PNG</strong>：嘴巴沒手動標時，系統靠輪廓自動推估位置。表情不指定則依台詞語氣自動判斷，可在「頁面編輯 → 泡泡版面與指向設定」逐句覆寫。</div>
        </section></>}

        {tab === 'qa' && <section className="es-comic-qa-layout">
          <div className="es-card es-comic-panel"><div className="es-comic-section-head"><div><h2>Validation Report</h2><p>系統檢查與人工 QA 分開記錄。</p></div><Btn onClick={refreshValidation}>重新驗證</Btn></div>{validation ? <div className="es-comic-validation"><div className="es-comic-validation-result"><StatePill value={validation.result} /><strong>{validation.publish_ready ? '可以進入 CURRENT' : '尚不可發布'}</strong></div>{validation.items.map(item => <div key={item.check}><StatePill value={item.result} /><span>{item.check}</span><small>{item.detail}</small></div>)}</div> : <p className="es-mut">按「重新驗證」取得最新 gate 狀態。</p>}</div>
          <div className="es-card es-comic-panel"><h2>Human QA Records</h2>{QA_GATES.map(([gate, label]) => {
            const existing = episode.qa_records.find(item => item.gate === gate);
            const draft = qaDrafts[gate] || existing || { result: 'UNVERIFIED', evidence: '', reviewer: '' };
            return <article className="es-comic-qa-row" key={gate}><div><strong>{label}</strong>{existing && <StatePill value={existing.result} />}</div><select className="es-select" value={draft.result} onChange={e => setQaDrafts({ ...qaDrafts, [gate]: { ...draft, result: e.target.value } })}>{['UNVERIFIED', 'PASS', 'FAIL', 'HOLD'].map(value => <option key={value}>{value}</option>)}</select><input className="es-input" placeholder="檢查證據／檔案／頁面" value={draft.evidence} onChange={e => setQaDrafts({ ...qaDrafts, [gate]: { ...draft, evidence: e.target.value } })} /><input className="es-input" placeholder="Reviewer" value={draft.reviewer} onChange={e => setQaDrafts({ ...qaDrafts, [gate]: { ...draft, reviewer: e.target.value } })} /><Btn size="sm" onClick={() => saveQa(gate)} disabled={!editable}>寫入</Btn></article>;
          })}</div>
          <div className="es-card es-comic-panel es-comic-state-panel"><h2>State Gate</h2><div className="es-comic-flow">{FLOW.map(step => <div key={step} className={`es-comic-step${episode.state === step ? ' is-active' : ''}`}>{step}</div>)}</div><div className="es-comic-actions"><Btn onClick={() => transition('QA')} disabled={!editable}>進入 QA</Btn><Btn variant="success" onClick={() => transition('CURRENT')} disabled={!editable || !validation?.publish_ready}>核准 CURRENT</Btn></div><Field label="HOLD 原因"><input className="es-input" value={holdReason} onChange={e => setHoldReason(e.target.value)} /></Field><Btn variant="danger" onClick={() => transition('HOLD')} disabled={!editable || !holdReason.trim()}>設為 HOLD</Btn></div>
        </section>}

        {tab === 'release' && <section className="es-comic-two-col">
          <div className="es-card es-comic-panel"><h2>Exports</h2><p>PDF 是閱讀版；DOCX 優先使用 Word native Shapes，環境不支援時會明確標記 editable-table fallback。</p><div className="es-comic-actions">{['html', 'pdf', 'docx', 'source'].map(kind => <Btn key={kind} onClick={() => exportKind(kind)} disabled={(kind === 'pdf' || kind === 'docx') && !episode.pages.every(page => page.image_asset_id)}>{kind.toUpperCase()}</Btn>)}</div><div className="es-comic-export-list">{exports.map(item => <a key={item.kind} href={item.download_url} target="_blank" rel="noreferrer"><strong>{item.kind.toUpperCase()}</strong><span>{item.mode} · {(item.size_bytes / 1024).toFixed(1)} KB</span></a>)}</div></div>
          <div className="es-card es-comic-panel"><h2>動態漫畫影片</h2><p>不用影片生成模型：每頁一張場景圖 + 運鏡 + 對白泡泡跟旁白逐句浮現，輸出 MP4 + SRT，完成後同時出現在影片庫可一鍵上傳 YouTube。非 CURRENT 版本會烙「草稿預覽」水印。</p>
            <div className="es-comic-voices">{['narrator', ...(episode.characters || [])].map(id => <label key={id}><span>{id === 'narrator' ? '旁白' : id}</span><input value={voiceSpecs[id] || ''} placeholder={id === 'narrator' ? 'default（tts_config 設定的聲音，例：老師 F5）' : 'edge:zh-TW-YunJheNeural 或留空=default'} onChange={e => setVoiceSpecs(current => ({ ...current, [id]: e.target.value }))} /></label>)}</div>
            <div className="es-comic-actions"><Btn onClick={renderVideo} busy={busy === '渲染動態漫畫影片'} disabled={!episode.pages.length || !episode.pages.every(page => page.image_asset_id) || (videoJob && !['done', 'failed'].includes(videoJob.state))}>渲染 MP4</Btn>
              {episode.exports?.video_html && <a className="es-btn" href={`${base}/episodes/${encodeURIComponent(episode.story_id)}/${encodeURIComponent(episode.version)}/exports/${episode.exports.video_html.split('/').pop()}`} target="_blank" rel="noreferrer">HTML 即時預覽</a>}</div>
            {videoJob && <p className="es-comic-video-status">{videoJob.state === 'done' ? '完成' : videoJob.state === 'failed' ? `失敗：${videoJob.error || ''}` : `渲染中 ${videoJob.progress || 0}%`}{videoJob.preview_label ? ` · ${videoJob.preview_label}` : ''}
              {videoJob.state === 'done' && <> · <a href={videoJob.download_url} target="_blank" rel="noreferrer">下載 MP4</a> · <a href={videoJob.download_url.replace(/\.mp4$/, '.srt')} target="_blank" rel="noreferrer">SRT</a></>}</p>}
          </div>
          <div className="es-card es-comic-panel"><h2>Serialized Reader</h2><p>只有 QA PASS 且 state=CURRENT 的版本可發布；stable URL 會指向目前有效 release。</p><div className="es-comic-actions"><Btn variant="success" onClick={publish} disabled={episode.state !== 'CURRENT'}>發布到內部 Reader</Btn><a className="es-btn es-btn-outline es-btn-md" href={`${base}/reader/series/${encodeURIComponent(seriesId)}`} target="_blank" rel="noreferrer">開啟 Series Archive ↗</a></div>{episode.releases.map(release => <article className="es-comic-release" key={release.release_id}><StatePill value={release.withdrawn_at ? 'HOLD' : 'PASS'} /><div><strong>{release.public_version}</strong><small>{release.published_at} · {release.published_by}</small></div><div className="es-comic-release-actions"><a href={release.url} target="_blank" rel="noreferrer">Reader ↗</a>{!release.withdrawn_at && <button onClick={() => withdraw(release)}>撤回</button>}</div></article>)}</div>
          <div className="es-card es-comic-panel"><h2>既有 Package Discovery / Import</h2><p>來源資料夾只讀；匯入時複製 normalized metadata 與 assets，不修改舊版。</p><Field label="Episode package 絕對路徑"><input className="es-input" value={importPath} onChange={e => setImportPath(e.target.value)} /></Field><div className="es-comic-actions"><Btn onClick={() => discoverPackage(false)} disabled={!importPath}>唯讀掃描</Btn><Btn variant="primary" onClick={() => discoverPackage(true)} disabled={!importPath || !!discovery?.missing_files?.length}>匯入副本</Btn></div>{discovery && <pre className="es-comic-discovery">{JSON.stringify(discovery, null, 2)}</pre>}</div>
          <div className="es-card es-comic-panel"><h2>Version Revision</h2><p>CURRENT 不可直接改稿；建立新版本後再重新 QA。</p><div className="es-comic-actions"><input className="es-input" value={forkVersion} onChange={e => setForkVersion(e.target.value)} /><Btn onClick={fork} disabled={episode.state !== 'CURRENT'}>Fork 新版本</Btn></div></div>
        </section>}
      </>}
    </>}
  </div>;
}

function Overview({ episode, series, selectedAsset, onTab }) {
  const pageReady = episode.pages.filter(page => page.scene_description && page.dialogues?.length).length;
  const imageReady = episode.pages.filter(page => page.image_asset_id).length;
  const qaPass = episode.qa_records.filter(item => item.result === 'PASS').length;
  return <div className="es-comic-overview">
    <section className="es-card es-comic-panel es-comic-overview-hero">
      <div><span className="es-home-eyebrow">{series.title}</span><h2>{episode.title}</h2><p>{episode.story_summary || episode.story_brief || '尚未建立故事摘要。'}</p></div>
      <div className="es-comic-metrics"><div><strong>{pageReady}/{episode.page_count}</strong><span>Storyboard</span></div><div><strong>{imageReady}/{episode.page_count}</strong><span>Scene assets</span></div><div><strong>{episode.evidence.length}</strong><span>Sources</span></div><div><strong>{qaPass}/6</strong><span>QA PASS</span></div></div>
    </section>
    <section className="es-comic-flow-large">{FLOW.map((step, index) => {
      const activeIndex = FLOW.indexOf(episode.state);
      return <button key={step} className={`${episode.state === step ? 'is-active' : ''}${activeIndex > index ? ' is-done' : ''}`} onClick={() => onTab(index < 2 ? 'story' : index < 4 ? 'pages' : index === 4 ? 'qa' : 'release')}><span>{index + 1}</span><strong>{step}</strong></button>;
    })}</section>
    <section className="es-comic-overview-grid">
      <button className="es-card" onClick={() => onTab('story')}><strong>劇本與分鏡</strong><span>{episode.story_beats.length} beats · {pageReady} 頁已填</span></button>
      <button className="es-card" onClick={() => onTab('evidence')}><strong>Evidence Pack</strong><span>{episode.evidence.length} sources · {episode.evidence_boundary}</span></button>
      <button className="es-card" onClick={() => onTab('assets')}><strong>Assets</strong><span>{Object.keys(selectedAsset).length} assets · provenance tracked</span></button>
      <button className="es-card" onClick={() => onTab('qa')}><strong>QA Dashboard</strong><span>{qaPass} / 6 required gates PASS</span></button>
    </section>
    {episode.hold_reason && <div className="es-comic-boundary"><strong>HOLD：</strong>{episode.hold_reason}</div>}
  </div>;
}
