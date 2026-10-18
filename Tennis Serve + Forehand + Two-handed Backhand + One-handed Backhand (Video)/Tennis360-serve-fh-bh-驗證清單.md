# Tennis360 Serve + Forehand + Backhand 驗證清單 / Verification Checklist

> 範圍 Scope：只驗證發球、正手、反手（單手＋雙手）。其他動作不在此包內。
> Only serve, forehand, and backhand (one-handed + two-handed) are in this package. Other actions are not included.
> 測試版 Build：tennis360-serve-fh-bh.zip

## 1. 環境確認 / Environment

```bash
cd <專案資料夾 / project folder>
python -m pytest tests/ -q
```
- 確認測試全過 / Confirm all tests pass

## 2. Serve 發球

### 照片分析 / Photo analysis
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

## 5. 驗證通過標準 / Pass Criteria

- [ ] 照片分析結果正確 / Photo analysis correct
- [ ] Serve 影片找得到發球動作 / Serve video finds the serve motion
- [ ] Forehand 影片找得到揮拍動作 / Forehand video finds the swing
- [ ] Backhand（單手＋雙手）影片找得到揮拍動作 / Backhand (one + two handed) videos find the swing
- [ ] 正面／側面都不會誤判或當掉 / Front/side views: no misjudgment or crash
- [ ] 測試全過 / All tests pass

## 6. 驗證完之後 / After Verification

1. 更新 README：把 serve、forehand、backhand 的狀態從「✅ Implemented」改成「✅ Verified（已驗證）」＋各一句功能說明 / Update README: change serve, forehand, backhand status from "✅ Implemented" to "✅ Verified" with one-line descriptions
2. Commit：`Tennis360-serve-fh-bh: verify serve, forehand, backhand on real footage`
3. 發現 bug 貼給我 / Send me any bugs you find
