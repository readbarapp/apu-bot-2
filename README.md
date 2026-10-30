# 香港 iPhone 自動搶購 Bot 控制台

前端網頁完全主導生命週期：由控制台啟動、傳送 Worker 設定、聚焦瀏覽器視窗、即時看 log，以及緊急停止。後台只待命，不會自行開跑。

---

## 想先睇控制台個樣？（唔使裝 Python）

GitHub 網頁**唔會**直接顯示呢個控制台。但你可以喺部電腦用瀏覽器打開預覽檔：

1. 去 GitHub 專案頁，撳綠色 **Code** → **Download ZIP**。
2. 解壓縮 ZIP（Mac 雙擊即可；Windows 右鍵「全部解壓縮」）。
3. 打開解壓後嘅資料夾，**雙擊 `preview.html`**。
4. 檔案會用 Chrome / Safari / Edge 打開。你可以睇到按鈕、Worker 設定、門市、Live Log 區。

呢個預覽**唔會**開 Apple 瀏覽器、**唔會**搶貨、**唔會**扣款。撳「全域啟動」會提示你要先用 Python 開後台。

真正用 Bot，先要跟下面「第一次安裝」同「每次點樣開」。

---

## 第一次安裝（未用過 Python 都可以）

你需要：一部有螢幕嘅電腦（Mac 或 Windows）、網絡、同你自己嘅 Apple ID。  
手機 / iPad 唔適合跑呢個程式。

### A. 下載專案

1. 用瀏覽器打開呢個 GitHub 專案。
2. 撳綠色 **Code** → **Download ZIP**。
3. 解壓縮。記住資料夾位置，例如：
   - Mac：`下載項目/apu-bot-2-cursor-hk-iphone-bot-2570`
   - Windows：`下載\apu-bot-2-cursor-hk-iphone-bot-2570`

（資料夾名可能略有不同，入面要見到 `app.py`、`requirements.txt`、`preview.html`。）

### B. 安裝 Python

#### Mac

1. 打開 **「終端機」（Terminal）**：Spotlight（Command + 空白）輸入 `終端機` 或 `Terminal`，Enter。
2. 輸入下面呢行，然後 Enter：

```bash
python3 --version
```

3. 如果見到類似 `Python 3.12.3`（3.11 或更新就得）：Python 已裝好，跳去 **C**。
4. 如果話 `command not found`：用瀏覽器打開 https://www.python.org/downloads/ ，下載 macOS installer，安裝。安裝時如果有 **Add Python to PATH** 就勾選。裝完**關掉終端機再開過**，再跑一次 `python3 --version`。

#### Windows

1. 用瀏覽器打開 https://www.python.org/downloads/windows/ ，下載最新 Python 3 installer。
2. 安裝時**一定要勾**最下面 **「Add python.exe to PATH」**，然後 Next 完成。
3. 打開 **PowerShell**：開始選單搜尋 `PowerShell`。
4. 輸入：

```powershell
py --version
```

見到 `Python 3.12.x` 就得。

### C. 進入專案資料夾

**Mac（終端機）**  
可以輸入 `cd `（後面有一個空格），然後把資料夾從 Finder **拖入終端機視窗**，再 Enter。例如變成：

```bash
cd "/Users/你的名字/Downloads/apu-bot-2-cursor-hk-iphone-bot-2570"
```

**Windows（PowerShell）** 一樣：打 `cd `（有空格），把資料夾拖入視窗，Enter。例如：

```powershell
cd "C:\Users\你的名字\Downloads\apu-bot-2-cursor-hk-iphone-bot-2570"
```

用呢行確認你喺正確位置（要見到 `app.py`）：

```bash
ls
```

Windows 如果 `ls` 唔得，用：

```powershell
dir
```

### D. 建立虛擬環境同安裝套件

呢一步只需要做**一次**（換電腦或刪咗資料夾先要再做）。

**Mac：**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

**Windows（PowerShell）：**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

如果 Windows 話無法執行 script：先跑呢行，再重新 `Activate.ps1`：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

成功嘅話，終端機最前面會出現 `(.venv)`。`playwright install chromium` 會下載一個 Chrome，可能要幾分鐘，等佢自己完成。

---

## 每次點樣開控制台（真正用）

1. 打開終端機 / PowerShell。
2. `cd` 入專案資料夾（同上，可拖資料夾）。
3. 啟動虛擬環境：
   - Mac：`source .venv/bin/activate`
   - Windows：`.\.venv\Scripts\Activate.ps1`
4. 開後台：

```bash
python app.py
```

Windows 如果 `python` 唔得，用：

```powershell
py app.py
```

5. 見到類似 `Uvicorn running on http://127.0.0.1:8765` 就代表開咗。**唔好關呢個視窗。**
6. 打開 Chrome / Edge / Safari，網址列輸入：

```
http://127.0.0.1:8765
```

注意：一定要打呢個位址，唔係 GitHub 連結，亦唔係 `preview.html`。`127.0.0.1` 即係「呢部電腦自己」。

7. 預設 **測試模式** 係開住。第一次建議保持開啟：先撳該 Worker 嘅 **登入 Apple ID**，喺彈出嚟嘅 Chromium 視窗登入；登入成功變成待命後，先撳 **開始運作** 或 **全域啟動**。
8. 要停程式：返去終端機，撳 **Control + C**。或者喺網頁撳紅色「緊急停止所有 Bot」。

如果終端機一閃就消失、或者話 `No module named ...`，多數係未做 `source .venv/bin/activate`（或 Windows 嘅 Activate），或者未 `pip install`。

---

## 控制台點用

1. 預設 **測試模式 (Test Mode / Dry Run)** 為開啟。建議先維持開啟。
2. 喺 Worker Profiles 改設定：名稱、session 資料夾、**目標機型下拉選單**（或輸入 SKU 再撳「加入此 SKU」）、香港門市、取貨限制、購買數量上限。
3. 撳綠色 **儲存設定**。全域啟動**只會用已儲存**嘅 Worker 設定。
4. 撳該 Worker 嘅 **登入 Apple ID**：系統會開該 Worker 的 Chromium、帶到最前，並打開 Apple 登入頁。登入成功後會顯示該 Apple ID 電郵，狀態變成 **待命（已登入）**。未登入時狀態係 **未登入 Apple ID**，不能搶機。
5. 每個 Worker 有自己的 **開始運作 / 停止運作**。停止運作只係停搶貨，唔會登出。**全域啟動** 只會叫已經登入、真正待命嘅 Worker 去相應頁面搶 iPhone；未登入嘅會跳過。
6. 點 **顯示此 Worker 視窗** 或已登入時的 **重新登入 / 帶到最前**，可把該 Worker 的瀏覽器帶到最前。
7. 關閉測試模式後再按 **全域啟動** 或 **開始運作**，前端會先問你：「警告：您目前未開啟測試模式，系統啟動後若偵測到有貨將會進行真實的信用卡扣款與下單！請問是否確定要啟動？」按取消則不會發啟動請求。
8. **緊急停止所有 Bot** 會立刻取消所有 Worker、關閉全部瀏覽器並重置。

## 常見問題

### 全域啟動期間改 Worker 設定會點？

正在「運作」嘅嗰粒 Worker 設定會鎖定，改動唔會套用。其他未運作嘅 Worker 仍可改、登入或開始運作。要改正在跑嘅 Worker：先撳佢嘅「停止運作」→ 改 → 儲存 → 再開始運作。

### 初次點樣登入 Apple ID？幾時先開始搶機？

1. 新增 Worker，每個用唔同 **session 資料夾**（一個資料夾 = 一個 Apple ID）。
2. 揀機型、門市、上限，撳 **儲存設定**。
3. 撳該 Worker 嘅 **登入 Apple ID**。系統會開該 Worker 的 Chromium、帶到最前，並打開 Apple 登入頁。
4. **喺嗰個彈出嚟嘅視窗登入 Apple ID**（每個新 session 登一次，含 2FA）。登入狀態會寫入 `sessions/`，下次唔使再 2FA。成功後控制台會顯示電郵，狀態變成 **待命（已登入）**。此時仍未搶機。
5. 再撳該 Worker 嘅 **開始運作**，或撳 **全域啟動**：已登入嘅 Worker 先會去產品／庫存頁開始搶。測試模式會停在最後一步，唔會扣款。未登入嘅 Worker 會被跳過。

### 搶夠指定數量之後？要唔要刪瀏覽器資料先換 Apple ID？

該 Worker 會**自動停止搶購**（狀態變成「已達數量上限」），視窗會留住方便你睇。唔使手動刪瀏覽器資料。

換第二個 Apple ID：緊急停止（或等佢停）→ 撳 **複製做新 Apple ID**（或新增 Worker）→ 用**新的 session 資料夾** → 儲存 → 再啟動 → 喺新視窗登入另一個 Apple ID。舊 session 可以留低，之後同一 Apple ID 會記住登入。

---

## 架構

```
app.py                  FastAPI：頁面、REST、WebSocket
preview.html            唔使 Python 都可以用瀏覽器睇個樣
bot/catalogs.py         香港門市、iPhone Duo SKU、取貨天數
bot/account.py          從商店頁偵測已登入 Apple ID 電郵
bot/inventory.py        Apple /retail/pickup-message 庫存解析
bot/worker.py           登入 / 待命 / 開始或停止搶購、持久化 Chromium
bot/checkout.py         加入購物袋 → 結帳；測試模式停在最後一步
bot/manager.py          單一 Worker 登入／運作／暫停、全域啟動、緊急停止
templates/index.html    真正控制台（要 python app.py）
static/css/app.css
static/js/app.js
sessions/               Apple ID 持久化資料夾（不進 git）
```

庫存查詢走香港官網 `pickup-message`，一次回傳全港 6 間 Apple Store，再依該 Worker 勾選的門市與取貨天數過濾。

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

## 測試（開發用）

```bash
pytest
```

## 注意

- 真實下單模式會在偵測到符合條件的貨源後嘗試送出訂單，可能產生信用卡扣款。預設請開著測試模式。
- Apple 官網對取貨查詢有頻率限制（常見 HTTP 541）。系統會自動退避，不要同時開過多 Worker。
- 結帳頁結構若被 Apple 改版，自動點擊可能失敗；Live Log 會寫原因，視窗會留著給你手動接手。
- 請自行遵守 Apple 網站條款與適用法律；本工具僅供本機、你自己的 Apple ID 使用。
