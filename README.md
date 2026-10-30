# 香港 iPhone 自動搶購 Bot 控制台

呢個程式喺**你自己部 Windows 電腦**上面跑。網頁控制台負責啟動、改 Worker、睇 log、緊急停止。後台只係待命，唔會自己開跑。

---

## 想先睇控制台個樣？（唔使裝 Python）

GitHub 網頁**唔會**直接顯示呢個控制台。但你可以喺部電腦用瀏覽器打開預覽檔：

1. 去 GitHub 專案頁，撳綠色 **Code** → **Download ZIP**。  
   **意思：** 把成個專案下載成一個壓縮檔到你部電腦。
2. 解壓縮 ZIP：喺檔案總管對住 ZIP **右鍵 → 全部解壓縮**。  
   **意思：** 解出一個資料夾，入面有 `app.py`、`preview.html` 等檔案。
3. 打開解壓後嘅資料夾，**雙擊 `preview.html`**。  
   **意思：** 用 Edge / Chrome 打開一個「假控制台」，只睇樣同試撳掣。
4. 你可以睇到按鈕、Worker 設定、門市、Live Log 區。

呢個預覽**唔會**開 Apple 瀏覽器、**唔會**搶貨、**唔會**扣款。真正用 Bot，跟下面「第一次安裝」同「每次點樣開」。

---

## 第一次安裝（Windows）

呢一大段**只需要做一次**。換電腦、或者你刪咗專案資料夾，先要再做。

你需要：一部有螢幕嘅 **Windows 電腦**、網絡、同你自己嘅 Apple ID。  
手機 / iPad 唔適合跑呢個程式。

### A. 下載專案

1. 用 Edge 或 Chrome 打開呢個 GitHub 專案。  
   **意思：** 去到放程式碼嘅網頁。
2. 撳綠色 **Code** → **Download ZIP**。  
   **意思：** 下載成個程式，唔使識用 git。
3. 喺檔案總管對住 ZIP 右鍵 → **全部解壓縮**。記住解壓後嘅資料夾位置，例如：

```
C:\Users\你的名字\Downloads\apu-bot-2-cursor-hk-iphone-bot-2570
```

**意思：** 之後所有指令都要喺呢個資料夾入面跑。資料夾名可能略有不同，入面要見到 `app.py`、`requirements.txt`、`preview.html`。

### B. 安裝 Python

Python 係跑呢個程式嘅語言。未裝過都得，跟住做：

1. 用瀏覽器打開 https://www.python.org/downloads/windows/ ，下載最新 Python 3 installer。  
   **意思：** 由官方網站裝 Python，唔好用不明來源。
2. 安裝時**一定要勾**最下面 **「Add python.exe to PATH」**，然後 Next 完成。  
   **意思：** 勾咗之後，PowerShell 先識得 `py` / `python` 呢啲指令。漏勾會變成「找不到 python」。
3. 打開 **PowerShell**：開始選單搜尋 `PowerShell`，Enter。  
   **意思：** PowerShell 係 Windows 嘅文字指令視窗，之後裝套件、開後台都喺度做。
4. 輸入：

```powershell
py --version
```

見到 `Python 3.12.x` 或 `Python 3.11.x` 就得。  
**意思：** 確認 Python 已裝好，而且 PowerShell 搵到佢。如果話唔識 `py`，多數係未勾 PATH，或者要**關掉 PowerShell 再開過**。

### C. 進入專案資料夾

1. 喺 PowerShell 打 `cd `（`cd` 後面有一個空格），**唔好急住 Enter**。  
   **意思：** `cd` = change directory，即係「行入某個資料夾」。
2. 用檔案總管把解壓後嗰個專案資料夾**拖入 PowerShell 視窗**，再 Enter。例如變成：

```powershell
cd "C:\Users\你的名字\Downloads\apu-bot-2-cursor-hk-iphone-bot-2570"
```

**意思：** 而家呢個視窗嘅「目前位置」就係專案資料夾。唔喺正確位置，後面嘅 `pip install` 會失敗。

3. 用呢行確認（要見到 `app.py`）：

```powershell
dir
```

**意思：** 列出而家資料夾入面有咩檔。見到 `app.py`、`requirements.txt` 就啱。

### D. 建立虛擬環境同安裝套件

呢一步只需要做**一次**。

1. 建立虛擬環境：

```powershell
py -m venv .venv
```

**意思：** 喺專案入面開一個叫 `.venv` 嘅獨立 Python 環境，避免同你電腦其他程式搶套件。

2. 啟動虛擬環境：

```powershell
.\.venv\Scripts\Activate.ps1
```

**意思：** 「行入」呢個獨立環境。成功嘅話，PowerShell 最前面會出現 `(.venv)`。

如果 Windows 話無法執行 script：先跑呢行，再重新跑上面嗰行 `Activate.ps1`：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**意思：** 允許你自己部電腦跑呢個啟動腳本。只影響你呢個 Windows 帳戶，唔係全機開放。

3. 安裝程式需要嘅套件：

```powershell
pip install -r requirements.txt
playwright install chromium
```

**意思：**  
- `pip install`：裝 FastAPI、Playwright 等 Python 套件（控制台同自動化瀏覽器）。  
- `playwright install chromium`：另外下載一個專用 Chrome（Chromium），之後每個 Worker 會開呢個瀏覽器去 Apple 網站。可能要幾分鐘，等佢自己完成。

---

## 每次點樣開控制台（真正用）

第一次安裝完成之後，**每次想用 Bot** 都跟呢幾步。唔使再裝 Python、唔使再 `pip install`。

1. 打開 **PowerShell**。  
   **意思：** 用指令視窗啟動後台。唔好用「雙擊 app.py」——多數會一閃就消失。

2. `cd` 入專案資料夾（同上，可拖資料夾）。  
   **意思：** 一定要行返入有 `app.py` 嗰個資料夾。

3. 啟動虛擬環境：

```powershell
.\.venv\Scripts\Activate.ps1
```

**意思：** 用返上次裝好嘅套件。見到 `(.venv)` 先繼續。如果話 `No module named ...`，多數係未做呢步。

4. 開後台：

```powershell
py app.py
```

如果 `py` 唔得，試：

```powershell
python app.py
```

**意思：** 喺呢部電腦啟動本機伺服器。佢**唔會**上傳你嘅 Apple ID 去任何我哋嘅伺服器；只係喺你部機開一個網頁後台。

5. 見到類似 `Uvicorn running on http://127.0.0.1:8765` 就代表開咗。**唔好關呢個 PowerShell 視窗。**  
   **意思：** 後台喺背景行緊。關咗呢個視窗，控制台同搶機都會停。

6. 打開 Edge / Chrome，網址列輸入：

```
http://127.0.0.1:8765
```

**意思：** 打開真正控制台。一定要打呢個位址，**唔係** GitHub 連結，亦**唔係** `preview.html`。

`127.0.0.1` 係固定意思「呢部電腦自己」，**每部電腦都係同一條**，唔會每人一條唔同嘅 link。`8765` 係呢個程式寫死嘅埠號。其他人喺互聯網打呢條 link **連唔到你部機**；只有你喺呢部電腦自己嘅瀏覽器先開到。

7. 預設 **測試模式** 係開住。第一次建議保持開啟：每張卡撳 **儲存此 Worker** → **登入 Apple ID**（喺彈出嚟嘅 Chromium 視窗登入）→ 全部登入好先撳綠色 **全部開始搶機**。  
   **意思：** 測試模式就算偵測到貨都唔會真扣款。熟悉流程之後先考慮關閉測試模式。

8. 要停程式：返去 PowerShell，撳 **Control + C**。或者喺網頁撳紅色「緊急停止所有 Bot」。  
   **意思：** Control + C 會停後台。緊急停止會關掉所有 Worker 瀏覽器。

---

## 控制台點用

1. 預設 **測試模式 (Test Mode / Dry Run)** 為開啟。建議先維持開啟。
2. 喺每張 Worker 卡改設定：名稱、session 資料夾、**目標機型（一個 Worker 只搶一個 SKU）**、香港門市、取貨限制、購買數量上限。撳該卡嘅 **儲存此 Worker**。
3. 撳該 Worker 嘅 **登入 Apple ID**：系統會開該 Worker 的 Chromium、帶到最前，並打開 Apple 登入頁。登入成功後會顯示該 Apple ID 電郵。
4. **全部開始搶機**（綠色大掣）要每個 Worker 都已儲存並且已登入先撳得。單張卡用 **開始運作 / 暫停運作**。運作中唔可以改設定。
5. 關閉測試模式後再按 **全部開始搶機** 或 **開始運作**，前端會先問你真實下單確認。
6. **緊急停止所有 Bot** 會關閉全部瀏覽器。手動關閉某個 Worker 視窗，嗰個會自動停搶，再撳 **開始運作** 可重開。

## 常見問題

### 如果一直冇補貨，程式會點？

會**一直輪詢**，唔會因為「暫時冇貨」而自己停。

開始運作之後，每個 Worker 大約每 2.5 秒（加少少隨機間隔）問一次香港 Apple 官網：你揀嘅 **目標 SKU** 喺勾選門市、取貨天數內有冇貨。冇貨就繼續問，狀態顯示「監控庫存中」。有貨就自動入袋結帳。

會停嘅情況只有：你撳 **暫停運作**／**緊急停止**、你手動關咗嗰個瀏覽器、已經搶夠購買數量上限、或者被 Apple 限制頻率（程式會自動等耐啲再問，唔會放棄）。

電腦要保持開機、PowerShell 唔好關、網絡要穩。

### http://127.0.0.1:8765 係咪每部電腦都唔同？

**唔同部電腦都係同一條。** `127.0.0.1` 永遠代表「呢部電腦自己」，`8765` 係程式寫死嘅埠。你朋友部機跑完，都係打呢條；但打喺手機 4G 或者另一部電腦，**唔會**連到你部機，因為呢條位址出唔到互聯網。

如果你部機 `8765` 已被其他程式佔用，後台會開唔到，Live Log／PowerShell 會報錯。呢個情況先要關佔用嘅程式，或者改程式碼入面嘅 port（一般用家唔使理）。

### 搶機期間改 Worker 設定會點？

運作中嗰粒 Worker **所有設定都鎖定**，包括儲存掣。要改機型、門市或數量：先撳 **暫停運作** → 改 → **儲存此 Worker** → 再 **開始運作**。

### 一個 Worker 可唔可以搶多過一個 SKU？

唔可以。每個 Worker 同一時間只監控同搶 **一個** 目標 SKU。要搶第二款，請 **新增 Worker**，用另一個 session 資料夾同另一個 Apple ID（或同一 ID 但唔好共用 session 資料夾）。

### 加入新 SKU 一定要係 iPhone 嗎？名稱點顯示？會唔會永久留喺下拉選單？

唔一定要 iPhone。你可以輸入**任何 Apple 產品 SKU**（AirPods、Mac 等），只要香港 Apple Store 取貨接口支援嗰個編號。結帳流程係通用「產品頁 → 入袋 → 結帳」；非 iPhone 如果官網步驟好唔同，自動點擊可能失敗，視窗會留俾你手動接手。

程式**唔會**上網幫你搵官方產品名。內建 Duo 會顯示例如「iPhone Duo 256GB 夜空色」。你自己加嘅 SKU：可以同時填產品名稱；留空就顯示 **「自訂 SKU + 編號」**，例如 `自訂 SKU MX123ZA/A`。

呢啲自訂 SKU 只會記住喺**呢部電腦呢個瀏覽器**（localStorage）。清瀏覽器資料、換瀏覽器或換電腦就會消失。唔會寫入 GitHub、亦唔會同步去第二部機。

### 關閉測試模式之後，彈出嚟嘅警告撳取消會點？

**全部開始搶機** 同 **開始運作** 喺測試模式關閉時都會先彈確認。撳 **取消** 就**唔會**開始搶貨、唔會開結帳；Live Log 會寫「使用者取消真實下單啟動」。只有撳確定先會真係啟動。

### 點樣偵測到已經登入 Apple ID？

系統會睇三樣嘢：瀏覽器係咪已經離開登入頁、Apple 商店 cookie（例如 `myacinfo`）、以及帳戶頁有冇電郵。偵測到就會喺 Worker 卡顯示電郵（或「已登入」），狀態變成待命。

### Apple ID session 檔案儲喺邊？點樣記得登入？

每個 Worker 的 Chromium 用持久化 user-data-dir，預設喺專案資料夾下面：

`sessions\session_worker_1`（名稱就係你喺卡上填嘅 session 資料夾）

入面係 Chrome 設定、cookie、本機儲存。所以同一資料夾下次再開會記住 Apple ID，通常唔使再 2FA。兩個 Worker **唔好**共用同一個資料夾。

### 手動關閉 Worker 嘅瀏覽器會點？

嗰個 Worker 會**自動停止搶購**，控制台徽章變成「瀏覽器已關閉（已停搶）」，Live Log 同卡上都會寫明。登入資料仍在 session 資料夾。只要該帳戶已登入，再撳 **開始運作** 就會重新打開瀏覽器繼續搶。

### 暫停之後點樣再搶？

撳嗰張卡嘅 **開始運作** 就得。唔使重新登入。關閉測試模式時，呢粒掣都會先彈真實下單確認。

### Worker 點樣知道有貨然後結帳？

開始運作之後，Worker 每隔幾秒問香港 Apple 官網 `pickup-message`（帶住佢嘅目標 SKU）。回傳入面如果指定門市喺取貨天數內有貨，就會自動打開產品頁、加入購物袋、進入結帳。測試模式會停在最後一步；真實模式會嘗試送出訂單。

### 初次點樣登入 Apple ID？幾時先開始搶機？

1. 新增 Worker，每個用唔同 **session 資料夾**（一個資料夾 = 一個 Apple ID）。
2. 揀機型、門市、上限，撳該卡嘅 **儲存此 Worker**。
3. 撳該 Worker 嘅 **登入 Apple ID**。系統會開該 Worker 的 Chromium、帶到最前，並打開 Apple 登入頁。
4. **喺嗰個彈出嚟嘅視窗登入 Apple ID**（每個新 session 登一次，含 2FA）。成功後控制台會顯示電郵，狀態變成 **待命（已登入）**。此時仍未搶機。
5. 全部 Worker 都登入好之後，撳綠色 **全部開始搶機**。測試模式會停在最後一步，唔會扣款。

### 搶夠指定數量之後？要唔要刪瀏覽器資料先換 Apple ID？

該 Worker 會**自動停止搶購**（狀態變成「已達數量上限」），視窗會留住方便你睇。唔使手動刪瀏覽器資料。

換第二個 Apple ID：**新增 Worker** → 用**新的 session 資料夾** → 儲存此 Worker → 喺新卡登入另一個 Apple ID。舊 session 可以留低。

### 有冇資安問題？

呢個程式**設計成只喺你自己部電腦跑**，唔會把 Apple 密碼傳到另外一部伺服器：登入係喺本機 Chromium 對住 Apple 官網完成。不過仍然有幾樣你要知：

- **控制台冇密碼。** 任何可以喺呢部電腦開瀏覽器嘅人，去 `http://127.0.0.1:8765` 就可以撳開始／停止、甚至真實下單。唔好喺公用電腦跑，唔好開遠端桌面俾唔識嘅人。
- **後台綁死 `127.0.0.1`，唔會公開到互聯網。** 一般嚟講外面打唔入你部機。但唔好自行改成 `0.0.0.0` 或者做埠轉發。
- **Apple ID 登入狀態存在專案 `sessions\` 資料夾**（Chrome cookie／本機資料），**冇加密**。呢個資料夾唔會上傳 GitHub。但任何人複製走呢個資料夾，就可能用到你已登入嘅 Apple 商店 session。請當佢同瀏覽器「記住登入」一樣敏感：唔好傳到雲端、WhatsApp、USB 俾人。唔用嘅舊 session 可以自己刪資料夾。
- **Live Log 可能出現 Apple ID 電郵。** 唔好截圖發公開頻道。
- **關閉測試模式 = 真嘅有機會扣信用卡。** 預設請開住測試模式。
- **自動化瀏覽器有機會被 Apple 偵測。** 帳戶可能被額外驗證或限制。請只用你自己嘅 Apple ID，並遵守 Apple 條款同適用法律。

呢個工具**唔係**銀行級加密保險庫；適合本機自己用，唔適合分享目錄或放公司共用電腦。

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
bot/manager.py          單一 Worker 登入／暫停／繼續、全部開始搶機、緊急停止
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

```powershell
pytest
```

## 注意

- 真實下單模式會在偵測到符合條件的貨源後嘗試送出訂單，可能產生信用卡扣款。預設請開著測試模式。
- Apple 官網對取貨查詢有頻率限制（常見 HTTP 541）。系統會自動退避，不要同時開過多 Worker。
- 結帳頁結構若被 Apple 改版，自動點擊可能失敗；Live Log 會寫原因，視窗會留著給你手動接手。
- 請自行遵守 Apple 網站條款與適用法律；本工具僅供本機、你自己的 Apple ID 使用。
