# Tennis360 Serve + Strokes 驗證清單 / Verification Checklist

> 範圍 Scope：驗證全部 11 個動作——發球、正手、反手（單手＋雙手）、切球、正手截擊、反手截擊、高壓球、小球、挑高球、半截擊。此包已完整。
> All 11 actions are in this package: serve, forehand, backhand (one-handed + two-handed), slice, volley-forehand, volley-backhand, overhead, drop-shot, lob, and half-volley. The package is now complete.
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

## 5. Slice 切球

```bash
python -m tennis360.cli analyze <切球影片 slice video>.mp4 --action slice
```
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

## 11. 驗證通過標準 / Pass Criteria

- [ ] 照片分析結果正確 / Photo analysis correct
- [ ] Serve 影片找得到發球動作 / Serve video finds the serve motion
- [ ] Forehand 影片找得到揮拍動作 / Forehand video finds the swing
- [ ] Backhand（單手＋雙手）影片找得到揮拍動作 / Backhand (one + two handed) videos find the swing
- [ ] Slice 影片找得到揮拍動作 / Slice video finds the swing
- [ ] Volley（正手＋反手）影片找得到截擊動作 / Volley (forehand + backhand) videos find the volley motion
- [ ] Overhead 影片找得到高壓球動作 / Overhead video finds the overhead motion
- [ ] Drop-shot 影片找得到小球動作 / Drop-shot video finds the drop-shot motion
- [ ] Lob 影片找得到挑高球動作 / Lob video finds the lob motion
- [ ] Half-volley 影片找得到半截擊動作 / Half-volley video finds the half-volley motion
- [ ] 正面／側面都不會誤判或當掉 / Front/side views: no misjudgment or crash
- [ ] 測試全過 / All tests pass

## 12. 驗證完之後 / After Verification

1. 更新 README：把全部 11 個動作的狀態從「✅ Implemented」改成「✅ Verified（已驗證）」＋各一句功能說明 / Update README: change all 11 actions' status from "✅ Implemented" to "✅ Verified" with one-line descriptions
2. Commit：`Tennis360-serve-fh-bh: verify all 11 actions on real footage`
3. 發現 bug 貼給我 / Send me any bugs you find
