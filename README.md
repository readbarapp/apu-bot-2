# 香港 iPhone 自動搶購 Bot 控制台

前端網頁完全主導生命週期：由控制台啟動、傳送 Worker 設定、聚焦瀏覽器視窗、即時看 log，以及緊急停止。後台只待命，不會自行開跑。

## 架構

```
app.py                  FastAPI：頁面、REST、WebSocket
bot/catalogs.py         香港門市、iPhone Duo SKU、取貨天數
bot/inventory.py        Apple /retail/pickup-message 庫存解析
bot/worker.py           每個 Worker 的持久化 Chromium + 輪詢迴圈
bot/checkout.py         加入購物袋 → 結帳；測試模式停在最後一步
bot/manager.py          啟動 / 緊急停止 / 全部或單一視窗聚焦
templates/index.html    控制台
static/css/app.css
static/js/app.js
sessions/               Apple ID 持久化資料夾（不進 git）
```

每個 Worker 是獨立 asyncio 任務，使用 Playwright persistent context（`headless=False`）載入自己的 `user_data_dir`，以既有 Apple ID 登入狀態避開重複 2FA。

庫存查詢走香港官網：

`https://www.apple.com/hk-zh/shop/retail/pickup-message?pl=true&parts.0=<SKU>&location=Hong%20Kong`

一次回傳全港 6 間 Apple Store，再依該 Worker 勾選的門市與取貨天數過濾。有貨時才進入結帳流程。

## 安裝

需要 Python 3.11+，以及可顯示視窗的桌面環境（瀏覽器不是無頭模式）。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 啟動

```bash
python app.py
```

用瀏覽器打開 http://127.0.0.1:8765

1. 預設 **測試模式 (Test Mode / Dry Run)** 為開啟。建議先維持開啟。
2. 新增 Worker：名稱、session 資料夾（例如 `session_worker_1`）、iPhone Duo 型號或自訂 SKU、香港門市、取貨限制（一日內 / 兩日內 / 三日內）、購買數量上限。
3. 第一次請先 **全域啟動**，在跳出的 Chromium 視窗登入 Apple ID；登入狀態會寫進 `sessions/`。
4. 點 **顯示此 Worker 視窗 (Bring to Front)** 可把該 Worker 的瀏覽器帶到最前。
5. 關閉測試模式後再按 **全域啟動**，前端會先 `window.confirm`：「警告：您目前未開啟測試模式，系統啟動後若偵測到有貨將會進行真實的信用卡扣款與下單！請問是否確定要啟動？」按取消則不會發啟動請求。
6. **緊急停止所有 Bot** 會立刻取消所有 Worker、關閉全部瀏覽器並重置。

## 內建資料

| 門市 | Store ID |
| --- | --- |
| ifc mall（中環） | R428 |
| Hysan Place（銅鑼灣） | R409 |
| Canton Road（尖沙咀） | R499 |
| Festival Walk（九龍塘） | R485 |
| apm Hong Kong（觀塘） | R673 |
| New Town Plaza（沙田） | R610 |

iPhone Duo 港行 SKU（ZA/A）已內建；也可用「輸入 Apple 產品 SKU」新增任何型號。

## 測試

```bash
pytest
```

單元測試覆蓋庫存解析、前端確認文案，以及用假 Worker 驗證啟動 / 聚焦 / 緊急停止。不會開啟真實瀏覽器，也不會對 Apple 下單。

## 注意

- 真實下單模式會在偵測到符合條件的貨源後嘗試送出訂單，可能產生信用卡扣款。預設請開著測試模式。
- Apple 官網對取貨查詢有頻率限制（常見 HTTP 541）。系統會自動退避，不要同時開過多 Worker 對同一出口 IP 狂刷。
- 結帳頁結構若被 Apple 改版，自動點擊可能失敗；Live Log 會寫原因，視窗會留著給你手動接手。
- 請自行遵守 Apple 網站條款與適用法律；本工具僅供本機、你自己的 Apple ID 使用。
