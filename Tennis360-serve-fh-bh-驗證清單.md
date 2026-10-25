# Tennis360 Serve + Strokes 驗證清單 / Verification Checklist

> 範圍 Scope：驗證全部 12 個動作——發球、正手（上旋＋切球）、反手（上旋單手＋雙手、切球）、正手截擊、反手截擊、半截擊、高壓球、小球、挑高球。此包已完整。
> All 12 actions are in this package: Serve, Forehand: Topspin, Forehand: Slice, Backhand: Topspin – Two-Handed, Backhand: Topspin – One-Handed, Backhand: Slice, Volley: Forehand, Volley: Backhand, Half-Volley: Forehand, Overhead Smash, Drop Shot: Forehand, and Lob: Forehand. The package is now complete.
> 測試版 Build：tennis360-serve-fh-bh.zip

## 1. 環境確認 / Environment

```bash
cd <專案資料夾 / project folder>
python -m pytest tests/ -q
```
- 確認測試全過 / Confirm all tests pass

## 2. Serve 發球

### 照片分析 / Photo analysis（可跳過 / Optional — Hanna 2026-10-24 決定跳過，直接用影片驗證 / skipped by decision, verify with video instead）
```bash
streamlit run streamlit_app.py
```
- 上傳一張發球 Trophy Pose 照片 / Upload a serve Trophy Pose photo
- 確認：能抓到持拍手臂、手肘角度量得出來 / Confirm: racket arm detected, elbow angle measured

### 影片分析 / Video analysis
```bash
python -m tennis360.cli analyze <發球影片 serve video>.mp4 --action serve
```
- 確認：能找到發球準備段落、不會誤判、不會當掉 / Confirm: serve preparation found, no misjudgment, no crash
- 正面和側面影片各測一次 / Test one front-view and one side-view clip

## 3. Forehand 正手

```bash
python -m tennis360.cli analyze <正手影片 forehand video>.mp4 --action forehand
```
- 確認：找得到揮拍動作（引拍→擊球→隨揮）/ Confirm: swing found (backswing → contact → follow-through)
- 不會當掉 / No crash

## 4. Backhand 反手

```bash
python -m tennis360.cli analyze <反手影片 backhand video>.mp4 --action backhand-one
python -m tennis360.cli analyze <反手影片 backhand video>.mp4 --action backhand-two
```
- 單手和雙手各測一次 / Test one-handed and two-handed separately
- 確認：找得到揮拍動作、不會當掉 / Confirm: swing found, no crash

## 5. Slice 切球（正手＋反手 / Forehand + Backhand）

```bash
python -m tennis360.cli analyze <正手切球影片 forehand slice video>.mp4 --action forehand-slice
python -m tennis360.cli analyze <反手切球影片 backhand slice video>.mp4 --action backhand-slice
```
- 正手切球和反手切球各測一次（兩者共用同一套切球分析）/ Test forehand slice and backhand slice separately (both share the same slice analysis)
- 確認：找得到揮拍動作（引拍→擊球→隨揮）/ Confirm: swing found (backswing → contact → follow-through)
- 不會當掉 / No crash

## 6. Volley 截擊

```bash
python -m tennis360.cli analyze <正手截擊影片 volley video>.mp4 --action volley-forehand
python -m tennis360.cli analyze <反手截擊影片 volley video>.mp4 --action volley-backhand
```
- 正手截擊和反手截擊各測一次 / Test forehand volley and backhand volley separately
- 確認：找得到截擊動作（短引拍→擊球→向前推）/ Confirm: volley motion found (compact backswing → contact → forward push)
- 不會當掉 / No crash

## 7. Overhead 高壓球

```bash
python -m tennis360.cli analyze <高壓球影片 overhead video>.mp4 --action overhead
```
- 確認：找得到高壓球動作（準備→最高點擊球→隨揮）/ Confirm: overhead motion found (preparation → contact at highest point → follow-through)
- 不會當掉 / No crash

## 8. Drop-shot 小球

```bash
python -m tennis360.cli analyze <小球影片 drop-shot video>.mp4 --action drop-shot
```
- 確認：找得到小球動作（引拍→輕觸擊球→短隨揮）/ Confirm: drop-shot motion found (backswing → soft contact → short follow-through)
- 不會當掉 / No crash

## 9. Lob 挑高球

```bash
python -m tennis360.cli analyze <挑高球影片 lob video>.mp4 --action lob
```
- 確認：找得到挑高球動作（低引拍→由下往上擊球→高隨揮）/ Confirm: lob motion found (low backswing → upward contact → high follow-through)
- 不會當掉 / No crash

## 10. Half-volley 半截擊

```bash
python -m tennis360.cli analyze <半截擊影片 half-volley video>.mp4 --action half-volley
```
- 確認：找得到半截擊動作（屈膝→低點擊球→短揮）/ Confirm: half-volley motion found (knee bend → low contact right after the bounce → compact swing)
- 不會當掉 / No crash

## 11. 網站影片模式 / Website video mode

```bash
streamlit run streamlit_app.py
```
- 左側 Analysis Type 選「Stroke Video Analysis」/ In the sidebar, set Analysis Type to "Stroke Video Analysis"
- 選一個動作（Stroke Type）和手臂，上傳一支該動作的影片（MP4／MOV／M4V），按「Analyze Video」/ Pick a stroke (Stroke Type) and arm, upload one clip of that stroke (MP4/MOV/M4V), and click "Analyze Video"
- 確認：找得到動作時，畫面顯示關鍵時刻時間、量測值和建議清單 / Confirm: when the stroke is found, the page shows key-moment times, measured values, and the suggestions list
- 確認：找不到動作時，畫面顯示說明文字，不會當掉、也不會硬給分數 / Confirm: when no stroke is found, the page shows the explanation text — no crash and no invented score
- Serve 也各測一次：Analysis Type 選「Stroke Video Analysis」、Stroke Type 選 Serve，上傳發球影片 / Also test serve once: Analysis Type "Stroke Video Analysis", Stroke Type "Serve", upload a serve clip
- 確認：Serve 影片找得到 trophy 段落並顯示最佳影格時間和手肘角度 / Confirm: the serve clip finds the trophy segment and shows the best-frame time and elbow angle
- 確認：分析成功後出現骨架點陣圖，高亮手臂的角度和畫面上的量測值一致；角度超出範圍時有虛線目標手臂 / Confirm: after a successful analysis a skeleton dot diagram appears, the highlighted arm's angle matches the measured value shown, and an out-of-range angle shows a dashed ghost target arm

## 12. 成長紀錄 / Progress mode

- 同一個動作先分析兩次（Serve Photo Analysis 或 Stroke Video Analysis 都可以，成功量到角度才會存）/ Analyze the same action twice first (Serve Photo Analysis or Stroke Video Analysis; only successful measurements are saved)
- 左側 Analysis Type 選「Progress」，選剛才分析的動作 / In the sidebar, set Analysis Type to "Progress" and pick the action you just analyzed
- 確認：圖表出現至少 2 個量測點（由舊到新），表格列出這 2 筆紀錄（時間、角度、是否在目標範圍內、分析結果）/ Confirm: the chart shows at least 2 measurement points (oldest to newest) and the table lists both records (date/time, angle, in target range, Analysis Result)
- 確認：找不到動作或無法分析的結果不會被存進紀錄 / Confirm: not-found and cannot-analyze attempts are not saved to the history

## 13. 介面文字與多拍影片 / Interface Wording and Multi-Stroke Clips

- 確認：網站與 CLI 的標題、標籤、按鈕大小寫一致（Title Case，如 Analysis Settings、Stroke Type、Analyze Video），結果值顯示 Yes／No／Angle in Range / Confirm: titles, labels, and buttons use consistent Title Case throughout the website and CLI (e.g. Analysis Settings, Stroke Type, Analyze Video), and result values read Yes / No / Angle in Range
- 確認：Serve 影片結果的區段標題是「Detected Trophy Segments」，介面不再出現「Heuristic」字樣 / Confirm: the serve video result heading reads "Detected Trophy Segments" and the word "Heuristic" no longer appears in the interface
- 確認：Progress 表格欄位標題是「Analysis Result」（不是「Main Issue」），且在目標範圍內的紀錄顯示正面結果（如 Angle in Range），不會被寫成問題 / Confirm: the Progress table header reads "Analysis Result" (not "Main Issue"), and in-range records show a positive result (e.g. Angle in Range) instead of an issue
- 多拍影片檢查：用一支包含 2 次揮拍的影片分析，確認引拍（Backswing）、擊球（Contact）、隨揮（Follow-Through）三個時間點都來自同一次揮拍，且順序為引拍 < 擊球 < 隨揮 / Multi-stroke clip check: analyze a clip containing 2 swings and confirm the Backswing, Contact, and Follow-Through times all come from the same swing, in the order Backswing < Contact < Follow-Through

## 14. 驗證通過標準 / Pass Criteria

- [ ] （可跳過 Optional）照片分析結果正確 / Photo analysis correct
- [ ] Serve 影片找得到發球動作 / Serve video finds the serve motion
- [ ] Forehand 影片找得到揮拍動作 / Forehand video finds the swing
- [ ] Backhand（單手＋雙手）影片找得到揮拍動作 / Backhand (one + two handed) videos find the swing
- [ ] Slice（正手＋反手）影片找得到揮拍動作 / Slice (forehand + backhand) videos find the swing
- [ ] Volley（正手＋反手）影片找得到截擊動作 / Volley (forehand + backhand) videos find the volley motion
- [ ] Overhead 影片找得到高壓球動作 / Overhead video finds the overhead motion
- [ ] Drop-shot 影片找得到小球動作 / Drop-shot video finds the drop-shot motion
- [ ] Lob 影片找得到挑高球動作 / Lob video finds the lob motion
- [ ] Half-volley 影片找得到半截擊動作 / Half-volley video finds the half-volley motion
- [ ] 網站影片模式（Stroke Video Analysis）可分析並顯示結果 / Website Stroke Video Analysis mode analyzes a clip and shows results
- [ ] 成長紀錄（Progress）圖表和表格顯示同動作的多次量測 / Progress mode chart and table show repeated measurements for one action
- [ ] 介面文字：標題與標籤大小寫一致、無「Heuristic」字樣、Progress 欄位為「Analysis Result」/ Interface wording: consistent capitalization, no "Heuristic", Progress header reads "Analysis Result"
- [ ] 多拍影片：關鍵時刻來自同一次揮拍且順序正確 / Multi-stroke clip: key moments come from the same swing and are correctly ordered
- [ ] 正面／側面都不會誤判或當掉 / Front/side views: no misjudgment or crash
- [ ] 測試全過 / All tests pass

## 15. 驗證完之後 / After Verification

1. 更新 README：把全部 12 個動作的狀態從「✅ Implemented」改成「✅ Verified（已驗證）」＋各一句功能說明 / Update README: change all 12 actions' status from "✅ Implemented" to "✅ Verified" with one-line descriptions
2. Commit：`Tennis360-serve-fh-bh: verify all 12 actions on real footage`
3. 發現 bug 貼給我 / Send me any bugs you find
