# pagetype · code · 程式碼頁

---

## 版面結構（左 60% 程式碼 + 右 40% 說明）

```javascript
const slide = pres.addSlide({ masterName: "JOURNAL" });
slide.addText("§ I.iii · 實作範例  Implementation", { placeholder: "chapter" });

// 題眉 + 標題
slide.addText("§ I.iii · MATLAB 實作範例", {
  x: 0.83, y: 0.90, w: 11.67, h: 0.35,
  fontFace: "Georgia", fontSize: 20, italic: true, color: "8A7C65",
});
slide.addText("PID 控制器 MATLAB 實作", {
  x: 0.83, y: 1.20, w: 11.67, h: 0.65,
  fontFace: "Noto Serif TC", fontSize: 44, color: "1E1A14",
});

// 程式碼底色區塊（深墨色背景）
slide.addText("", {
  x: 0.83, y: 2.00, w: 7.50, h: 4.20,
  fill: { color: "1E1A14" },
});

// 程式碼行（Consolas，用 x 偏移做縮排）
const INDENT = 0.30;
const codeLines = [
  { indent: 0, text: "Kp = 1.2; Ki = 0.5; Kd = 0.1;", color: "F4EEE3" },
  { indent: 0, text: "sys = tf([1], [1 2 1]);", color: "F4EEE3" },
  { indent: 0, text: "C = pid(Kp, Ki, Kd);", color: "C9A35B" },  // 強調
  { indent: 0, text: "T = feedback(C * sys, 1);", color: "F4EEE3" },
  { indent: 0, text: "step(T);", color: "F4EEE3" },
];
codeLines.forEach((line, i) => {
  slide.addText(line.text, {
    x: 0.83 + INDENT * line.indent + 0.15,
    y: 2.15 + i * 0.60,
    w: 7.20, h: 0.52,
    fontFace: "Consolas", fontSize: 18,
    color: line.color,
  });
});

// 右側說明（3 項）
const notes = [
  { num: "i.", text: "Kp/Ki/Kd 需依系統模型調整" },
  { num: "ii.", text: "feedback() 建立閉迴路系統" },
  { num: "iii.", text: "step() 驗證步階響應" },
];
notes.forEach((note, i) => {
  slide.addText(`${note.num} ${note.text}`, {
    x: 8.60, y: 2.10 + i * 1.10, w: 3.90, h: 0.90,
    fontFace: "Noto Serif TC", fontSize: 20, color: "1E1A14", valign: "top",
  });
});
```

---

## 注意事項

- Consolas 縮排：**用 `x` 偏移**，不用空白字元
- Consolas **不設定** `charSpacing`
- 程式碼底色：`1E1A14`（Journal），文字 `F4EEE3`
- 關鍵字 / 函式名可用強調色（Journal 暗墨綠 `2C4A35` 或暖金 `C9A35B`）
- 程式碼字級 **18pt**（等寬字視覺較大，18 即可）
