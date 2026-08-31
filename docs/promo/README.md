# docs/promo — eduStudio 介紹影片場景

9 個 standalone HTML 動畫場景（1920×1080），用專案自己的
`core/html_video.py`（虛擬時鐘無頭逐格擷取）渲成 MP4，再由
[`tools/build_promo_video.py`](../../tools/build_promo_video.py) 以 ffmpeg
xfade 轉場串接 + 本地合成配樂音效，產出完整介紹影片。

```bash
# 完整重建（渲染 9 景 + 配樂 + 串接）→ output/edustudio_intro.mp4
python tools/build_promo_video.py

# 已渲染過、只重組（改轉場/音效時快很多）
python tools/build_promo_video.py --skip-render

# 本機加 zh-TW 旁白（edge-tts；雲端 CI/代理環境連不上會自動退無旁白版）
python tools/build_promo_video.py --narrate
```

| 場景 | 內容 | 秒數 |
|---|---|---|
| scene01_open | 開場 logo + tagline（粒子/光環/掃光） | 7 |
| scene02_sources | 八種來源飛入工作空間核心 | 7 |
| scene03_video | 影片站：黑板逐題解答（粉筆手寫/公式/字幕列） | 8 |
| scene04_visual | 視覺站:簡報·圖卡·海報 3D 展開 + 16 主題色票 | 7 |
| scene05_comic | 漫畫站:分鏡格 + 對話泡泡 + 六道 QA gate 點亮 | 7 |
| scene06_localize | 在地化:配音波形 + 語言環繞飛入 | 7 |
| scene07_review | 審查關卡（戲劇轉折):錯誤數值被人工改正 + 核准章 | 8 |
| scene08_publish | 發布:YouTube 上傳進度 + 自動章節 + 火箭 | 7 |
| scene09_cta | 結尾:四工作站 + 開源自架 + repo 連結 | 7 |

- 每個 HTML 完全自含（可單獨丟進 `/app` 的「HTML 動畫 → 影片」上傳口）。
- 動畫一律以頁面載入 t=0 起算（CSS animation / rAF），與虛擬時鐘相容。
- 無頭 Chromium 版本與 playwright 對不上時，設 `EDUSTUDIO_CHROMIUM_PATH`
  指向瀏覽器執行檔（例:`/opt/pw-browsers/chromium`）。
- 場景由設計稿產生器維護於本資料夾外（歷史紀錄見 git）;直接改 HTML 亦可。
