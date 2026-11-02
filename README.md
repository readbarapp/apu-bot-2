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

1. 用瀏覽器打開 https://www.python.org/downloads/windows/ ，下載 **Python 3.12 或 3.13 的 Windows installer (64-bit)**。  
   **意思：** 由官方網站裝 Python，唔好用不明來源。  
   **唔好撳黃色大掣 Latest**（而家可能係 3.15）。最新版好多套件未有現成 Windows 檔，`pip` 就會叫你裝 Visual C++——**呢個 Bot 唔需要裝 Build Tools**。亦**唔好揀 32-bit**。  
   建議用 Python 3.13 最後一個有安裝檔嘅版本：https://www.python.org/downloads/release/python-31317/ → **Windows installer (64-bit)**。  
   或者 Python 3.12：https://www.python.org/downloads/release/python-31210/ → **Windows installer (64-bit)**。
2. 安裝時**一定要勾**最下面 **「Add python.exe to PATH」**，然後 Next 完成。  
   **意思：** 勾咗之後，PowerShell 先識得 `py` / `python` 呢啲指令。漏勾會變成「找不到 python」。
3. 打開 **PowerShell**：開始選單搜尋 `PowerShell`，Enter。  
   **意思：** PowerShell 係 Windows 嘅文字指令視窗，之後裝套件、開後台都喺度做。
4. 輸入：

```powershell
py --version
```

見到 `Python 3.13.x`、`3.12.x` 或 `3.14.x` 就得。如果見到 `3.15` 或者寫住 32-bit，請改裝上面嘅 3.12 或 3.13 64-bit。  
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
- `playwright install chromium`：下載一個備用 Chromium。Worker **會優先用你部機已裝嘅 Google Chrome**，冇就試 Microsoft Edge，再冇先用呢個備用 Chromium。可能要幾分鐘，等佢自己完成。

建議另外裝正式版 [Google Chrome](https://www.google.com/chrome/)。聽朝喺屋企跑時，用本機 Chrome 比 Playwright 內建瀏覽器更似平時上網，比較唔容易被當 bot。

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

## 最新實戰流程（盡量提高用到 Bot 嘅機會）

跟呢條，唔好一開始開訪客、唔好一次開多張卡。目標係：屋企機、本機 Chrome、已登入 Apple ID、測試模式行通一次，先至考慮真實下單。

### 0. 開跑之前（只做一次）

1. 用**最新程式**。要有「優先用本機 Google Chrome」呢段（GitHub 合併 PR 之後重新 Download ZIP，或者 `git pull`）。舊 ZIP 仍然會開 Playwright Chromium，較易被當 bot。
2. 裝正式版 [Google Chrome](https://www.google.com/chrome/)。
3. 關 VPN、加速器、Clash、公司代理。用**香港家用寬頻**。
4. Python 用 3.12 / 3.13 64-bit；虛擬環境已 `pip install` 同 `playwright install chromium`。

### 1. 開控制台

PowerShell 入專案 → `.\.venv\Scripts\Activate.ps1` → `py app.py` → 瀏覽器開 `http://127.0.0.1:8765`。PowerShell **唔好關**。唔好用 `preview.html`。

### 2. 第一次一定開測試模式，而且只開 1 張 Worker

控制台上面「測試模式」保持勾住。撳 **新增 Worker**（如果未有）。

建議第一張卡用呢組，成功率最高：

| 設定 | 揀呢個 | 點解 |
| --- | --- | --- |
| 結帳模式 | **Apple ID 登入** | 唔使過「以訪客身份繼續」嗰個最易 541 嘅關口 |
| 取貨方式 | **門市自取** | 步驟較短，亦係你原本最想用嘅路徑 |
| 機型 | 你要搶嗰款；如果而家只係試流程，可以揀官網顯示有貨嘅 iPhone | 測試模式唔扣款 |
| 門市 | 你真係去到嘅 1–2 間 | 勾太多會亂，上限又係全部門市加總 |
| 數量上限 | **1**（試流程）或 **2**（正式；Apple 同一型號通常每人最多 2 部） | 唔好開多個 Worker 用同一個 Apple ID 再疊加 |
| Session 資料夾 | 留預設，例如 `session_worker_1` | 每個 Apple ID 一個資料夾 |

填好撳 **儲存此 Worker**。

訪客模式可以遲啲先試。訪客要 POST `signInx`，係雲端最先被擋嗰步。

### 3. 登入，確認用緊本機 Chrome

撳 **登入 Apple ID**。會彈一個有頭視窗。Live Log 要見到 **「已用本機 Google Chrome」**。

- 見到 Playwright Chromium：未裝 Chrome，或者 Chrome 唔喺預設位置。裝好之後緊急停止，再開過。
- 喺嗰個視窗登入你自己嘅 Apple ID，等控制台變成「待命／已登入」。
- **唔好關**呢個視窗，亦唔好喺入面亂撳（人手干預會令嗰張卡自動暫停）。

### 4. 測試模式行通一次（聽朝搶貨前必做）

撳呢張卡嘅 **開始運作**（得一張卡時，同綠色「全部開始搶機」一樣）。然後等。

成功嘅樣子：

1. Live Log 寫已用本機 Google Chrome  
2. 偵測到貨 → 自動撳不換購、無 AppleCare+ → 加入購物袋  
3. 入結帳，用你已登入嘅 Apple ID 推到付款前  
4. 出現 **效能實測報告**，狀態變成測試模式完成，**唔扣款**

失敗嘅樣子：加車或結帳之後頁面變「找不到你想去的網頁」。暫停，等幾分鐘，跟 FAQ「屋企仍然 541」逐樣試，**唔好連撳**。

呢次成功，先代表呢部機、呢條網絡、呢個 Apple ID **用到 Bot**。未成功就唔好關測試模式。

### 5. 正式搶貨當日

1. 用**同一部電腦、同一個 Wi-Fi、同一張已登入嘅 Worker**。唔好刪 `sessions\`，唔好換資料夾。
2. 開控制台方法同上。視窗應該仍然係已登入；如果話未登入，再撳一次登入。
3. 確認機型、門市、上限（建議 2）。**儲存此 Worker**（如果有改過）。
4. 只有測試已行通，先取消測試模式。綠色掣／開始運作會再問你確認真實下單。
5. 仍然建議同一時間只跑 **1 個 Worker**。要第二個 Apple ID，先新增第二張卡、**另一個 session 資料夾**、另外登入。
6. 搶到上限會自動停。要停手：暫停運作，或者紅色緊急停止，或者 PowerShell `Control + C`。

### 6. 提高機會嘅硬規則

- 屋企寬頻 + 本機 Chrome + 已登入 Apple ID + 先測試模式。  
- 一次一張卡。541 就停手等。  
- 唔好 VPN。唔好用 `preview.html` 當真正 Bot。唔好喺 Bot 個瀏覽器手撳。  
- 同一 Apple ID 唔好開多張卡疊數量；官網通常同一型號每人 2 部。

---

## 控制台點用

1. 預設 **測試模式 (Test Mode / Dry Run)** 為開啟。建議先維持開啟。
2. 喺每張 Worker 卡揀 **結帳模式**（Apple ID 登入 或 訪客）同 **取貨方式**（門市自取 或 送貨上門），再揀機型、數量上限。Apple ID 模式要填 Session 資料夾；訪客模式要填英文姓名、電郵、電話、地址同信用卡。門市自取要勾香港分店同取貨天數；送貨上門要揀「幾日內必須送到」。撳 **儲存此 Worker**。
3. **Apple ID 模式：** 撳 **登入 Apple ID**，喺彈出嚟嘅視窗登入。**訪客模式：** 唔使登入，但資料未填齊就開始唔到。
4. **全部開始搶機** 要每個 Worker 都已儲存，而且 Apple ID 嘅已登入、訪客嘅已填齊。單張卡用 **開始運作 / 暫停運作**。運作中唔可以改設定。
5. 關閉測試模式後再按 **全部開始搶機** 或 **開始運作**，前端會先問你真實下單確認。
6. 如果頁面突然唔對、或者你用手喺瀏覽器撳咗嘢，嗰個 Worker 會**自動暫停**，視窗帶到最前。你手動處理好再撳 **開始運作**。
7. **緊急停止所有 Bot** 會關閉全部瀏覽器。

---

## 你點用（User Journey）同機械人點做（Worker Journey）

以下用日常說話說明。秒數係測試模式實測／預估，網絡慢會再長少少。四種組合共用同一個「你做嘅步驟」，分別主要喺機械人結帳嗰段。發現有貨之後，機械人會打開產品頁，**先撳「不換購」同「無 AppleCare+ 服務計劃保障」**（唔揀呢兩步，加入購物袋會一直灰色），然後先至加車。

### 你做嘅事（四種組合都一樣開頭）

1. 開 PowerShell，入專案資料夾，啟動 `.venv`，跑 `py app.py`，再用瀏覽器打開 `http://127.0.0.1:8765`。
2. 保持測試模式開啟。新增一張 Worker 卡，揀機型。
3. 揀結帳模式同取貨方式，填嗰種模式需要嘅資料，撳「儲存此 Worker」。
4. Apple ID 模式：登入。訪客模式：確認姓名、地址、卡資料已填。
5. 撳「開始運作」或綠色「全部開始搶機」。之後等機械人自己監察有冇貨。
6. 測試模式成功一次之後，Live Log 同 PowerShell 會出現效能實測報告（加車、入結帳、取貨或送貨、去到付款前最後一步、總秒數）。

### 組合 A：Apple ID + 門市自取

**你：** 揀 Apple ID 登入模式、門市自取，勾 ifc / 沙田等，揀一日內／兩日內／三日內，登入自己嘅 Apple ID，然後開始。

**機械人：** 發現有貨 → 打開產品頁，揀不換購同無 AppleCare+，再加入購物袋（約 4–8 秒）→ 進入結帳（約 2–5 秒）→ 自動揀門市自取、勾你指定嘅分店、撳畫面上**最早第一個**取貨時段（約 4–8 秒）→ 用帳戶入面已儲存嘅取貨人資料推到付款前最後一步（約 2–4 秒）。**合計大約 12–25 秒。** 測試模式喺呢度停，唔扣款。

### 組合 B：Apple ID + 送貨上門

**你：** 揀 Apple ID 登入模式、送貨上門，再揀例如「7 日內送到」，登入後開始。唔使勾門市。

**機械人：** 發現有貨 → 揀不換購同無 AppleCare+ 後加車（約 4–8 秒）→ 入結帳（約 2–5 秒）→ 揀送貨上門，讀網頁「預計送達日期」（約 4–8 秒）。如果 3 日後送到、你又設定 7 日內：繼續去付款前（約 2–4 秒），**合計大約 12–25 秒**。如果要等兩個星期：呢次機會放棄，返回監察，唔會亂填。

### 組合 C：訪客 + 門市自取

**你：** 揀訪客模式、門市自取，填英文姓名、電郵、香港電話、地址、信用卡、月份、年份、CVV，勾門市，**唔使登入 Apple ID**，儲存後開始。資料未填齊會彈提示，開始唔到。

**機械人：** 發現有貨 → 揀不換購同無 AppleCare+ 後加車（約 4–8 秒）→ 入訪客結帳（約 2–5 秒）→ 揀門市自取、最早時段，再逐格填你事先備好嘅訪客資料（約 6–12 秒）→ 去到付款前最後一步（約 2–4 秒）。**合計大約 14–29 秒。** 卡號同 CVV 唔會出現喺 Live Log。

### 組合 D：訪客 + 送貨上門

**你：** 揀訪客模式、送貨上門，填齊訪客資料同送貨時效（例如 7 日內），儲存後開始。

**機械人：** 發現有貨 → 揀不換購同無 AppleCare+ 後加車（約 4–8 秒）→ 入訪客結帳（約 2–5 秒）→ 揀送貨上門、填收貨地址同信用卡（約 6–12 秒）→ 核對預計送達日。符合就去付款前（約 2–4 秒），**合計大約 14–29 秒**。超出時效就放棄今次，繼續監察。

## 常見問題

### 撳「以訪客身份繼續」之後跳去 404？

呢粒掣**冇獨立網址**。真正動作係 POST 去 Apple ` /shop/signInx `。如果官網回 **HTTP 541**（風控），頁面就會跟住跳 ` /shop/541 ` → ` /shop/go/404 ` → 你見到嘅 404。

Bot 而家會撳 `data-autom="guest-checkout-btn"`（「以訪客身份繼續」），等真實結帳頁。若然仍然 404，多數係網絡被擋（例如機房 IP），唔係掣撳錯。請喺**香港家用網絡**開測試模式再試；測試模式仍然停在付款前最後一步，唔會落單。

聽朝喺屋企點分成功定 541：

- **成功：** 購物袋有貨 → 去到「登入以快速完成結帳」→ 撳訪客之後入到揀送貨／取貨、填姓名地址卡。Live Log 會出效能實測報告，測試模式停在付款前。
- **仍然 541：** 撳加車或「以訪客身份繼續」之後頁面變「找不到你想去的網頁」，Live Log 會寫官網拒絕訪客結帳。呢個係 Apple 風控，唔係掣認錯。

瀏覽器會用你本機嘅有頭視窗、香港時區，優先開 **本機 Google Chrome**（冇就 Edge，再冇先用 Playwright Chromium），並收埋 Playwright 預設嘅 `webdriver`／`--enable-automation` 標記。Live Log 會寫用咗邊個瀏覽器。

### 屋企 IP 都被當 bot／仍然 541，我可以點做？

Playwright 就算喺家用網絡，都可能帶自動化痕跡。按呢個次序試，一次改一樣：

1. **裝正式版 Google Chrome**（[google.com/chrome](https://www.google.com/chrome/)），然後重新撳登入或開始運作。Live Log 應該寫「已用本機 Google Chrome」。如果寫緊 Playwright Chromium，即係未搵到 Chrome。
2. **關 VPN、加速器、公司代理、Clash 等。** 用香港家用寬頻。VPN 出口好似機房 IP，好容易 541。
3. **測試模式只開 1 個 Worker。** 開太多連庫存查詢都會 541。
4. **541 之後唔好即刻再撳訪客／加車。** 暫停嗰張卡，等幾分鐘。連續撞風控會越擋越實。
5. **用手機熱點對照一次。** 熱點得、寬頻唔得：寬頻 IP 被標記。兩個都 541：確認 Live Log 係本機 Chrome，而唔係備用 Chromium。
6. Bot 用獨立 `sessions\` 資料夾，**唔會**開你平時嗰個已登入 Chrome 用戶檔，避免同日常瀏覽器搶檔。

自動化唔可能 100% 扮成人手。以上係降低屋企機被誤判嘅實際步驟，唔係保證。

### `pip install` 話要 Microsoft Visual C++ / Failed building wheel for pyyaml？

**唔使裝 Visual C++ Build Tools。** 呢個 Bot 唔使編譯 PyYAML。

原因：舊版 `requirements.txt` 用咗 `uvicorn[standard]`，會順便裝 PyYAML。如果你裝咗好新嘅 Python（3.14 / 3.15）或者 32-bit，PyPI 冇現成 Windows 檔，pip 就嘗試喺部機編譯，然後叫你裝 C++。

跟呢幾步（喺專案資料夾、已 `Activate.ps1` 見到 `(.venv)`）：

1. 離開虛擬環境：`deactivate`
2. 刪咗半裝嘅環境：

```powershell
rmdir /s /q .venv
```

3. 確認版本（要 `3.12` / `3.13` / `3.14`，64-bit）：

```powershell
py --version
```

如果唔啱，用上面「B. 安裝 Python」裝 **3.12 或 3.13 64-bit**，然後關咗 PowerShell 再開過。
4. 重建環境再裝一次：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

用更新後嘅 `requirements.txt`（入面係 `uvicorn`，**冇** `[standard]`）。仍然失敗就唔好再裝 C++，先檢查係咪裝咗 32-bit 或 3.15。

### `py app.py` 話 No module named 'tzdata' / No time zone found with key Asia/Hong_Kong？

呢個係 **Windows 正常現象**，唔係你裝錯 Python。Windows 本身冇帶 IANA 時區表，程式要用 `Asia/Hong_Kong` 就要額外裝 `tzdata`。

喺已經啟動 `.venv`（見到 `(.venv)`）嘅 PowerShell 跑：

```powershell
pip install tzdata
py app.py
```

如果 `py` 唔得，用 `python app.py`。之後新嘅 `requirements.txt` 已包含 `tzdata`，重新 `pip install -r requirements.txt` 都會一併裝到。

### 如果一直冇補貨，程式會點？

會**一直輪詢**，唔會因為「暫時冇貨」而自己停。

開始運作之後，每個 Worker 大約每 2.5 秒（加少少隨機間隔）問一次香港 Apple 官網：你揀嘅 **目標 SKU** 喺勾選門市、取貨天數內有冇貨。冇貨就繼續問，狀態顯示「監控庫存中」。有貨就自動入袋結帳。

會停嘅情況只有：你撳 **暫停運作**／**緊急停止**、你手動關咗嗰個瀏覽器、已經搶夠呢粒 Worker 的購買數量上限（全部勾選門市加總）、或者被 Apple 限制頻率（程式會自動等耐啲再問，唔會放棄）。

電腦要保持開機、PowerShell 唔好關、網絡要穩。

### http://127.0.0.1:8765 係咪每部電腦都唔同？

**唔同部電腦都係同一條。** `127.0.0.1` 永遠代表「呢部電腦自己」，`8765` 係程式寫死嘅埠。你朋友部機跑完，都係打呢條；但打喺手機 4G 或者另一部電腦，**唔會**連到你部機，因為呢條位址出唔到互聯網。

如果你部機 `8765` 已被其他程式佔用，後台會開唔到，Live Log／PowerShell 會報錯。呢個情況先要關佔用嘅程式，或者改程式碼入面嘅 port（一般用家唔使理）。

### 搶機期間改 Worker 設定會點？

運作中嗰粒 Worker **所有設定都鎖定**，包括儲存掣。要改機型、門市或數量：先撳 **暫停運作** → 改 → **儲存此 Worker** → 再 **開始運作**。

### 複選多過一間門市，購買數量上限係點計？

**每個 Worker 只有一個合計上限，唔係每間門市各計一次。**

例如勾選 ifc mall 同沙田 New Town Plaza，上限填 2：搶到 1 部 ifc + 1 部沙田之後就會停，總共 2 部。唔會變成「ifc 2 部 + 沙田 2 部 = 4 部」。

呢個上限係程式自己數成功結帳次數。Apple 官網對同一型號通常限制一個人最多買兩部；如果你用**同一個 Apple ID 開兩個 Worker**、每個上限都填 2，程式可能會嘗試總共 4 次，超出蘋果限制。一個 Apple ID 建議所有 Worker 的上限加起來唔好超過 2。

### 一個 Worker 可唔可以搶多過一個 SKU？

唔可以。每個 Worker 同一時間只監控同搶 **一個** 目標 SKU。要搶第二款，請 **新增 Worker**，用另一個 session 資料夾同另一個 Apple ID（或同一 ID 但唔好共用 session 資料夾）。

### 加入新 SKU 一定要係 iPhone 嗎？名稱點顯示？打錯點刪？會唔會永久留喺下拉選單？

唔一定要 iPhone。你可以輸入**任何 Apple 產品 SKU**（AirPods、Mac 等），只要香港 Apple Store 取貨接口支援嗰個編號。結帳流程係通用「產品頁 → 入袋 → 結帳」；非 iPhone 如果官網步驟好唔同，自動點擊可能失敗，視窗會留俾你手動接手。

程式**唔會**上網幫你搵官方產品名。內建 Duo 會顯示例如「iPhone Duo 256GB 夜空色」。你自己加嘅 SKU：可以同時填產品名稱；留空就顯示 **「自訂 SKU + 編號」**，例如 `自訂 SKU MX123ZA/A`。

呢啲自訂 SKU 只會記住喺**呢部電腦呢個瀏覽器**（localStorage）。清瀏覽器資料、換瀏覽器或換電腦就會消失。唔會寫入 GitHub、亦唔會同步去第二部機。

**打錯可以刪。** 加入之後，自訂 SKU 會出現喺輸入欄下面，撳 **刪除** 就會從呢個瀏覽器嘅下拉選單拎走。內建 Duo 機型刪唔到。如果有 Worker 正用嗰個 SKU 搶機，要先 **暫停運作**。刪咗之後，用緊嗰個編號嘅 Worker 會改回預設機型，請再撳 **儲存此 Worker**。

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

開始運作之後，Worker 每隔幾秒問香港 Apple 官網 `pickup-message`（帶住佢嘅目標 SKU）。回傳入面如果指定門市喺取貨天數內有貨，就會自動打開產品頁、先揀「不換購」同「無 AppleCare+ 服務計劃保障」（加車掣先會亮）、加入購物袋、進入結帳。測試模式會停在最後一步；真實模式會嘗試送出訂單。

### 初次點樣登入 Apple ID？幾時先開始搶機？

1. 新增 Worker，每個用唔同 **session 資料夾**（一個資料夾 = 一個 Apple ID）。
2. 揀機型、門市、上限，撳該卡嘅 **儲存此 Worker**。
3. 撳該 Worker 嘅 **登入 Apple ID**。系統會開該 Worker 的 Chromium、帶到最前，並打開 Apple 登入頁。
4. **喺嗰個彈出嚟嘅視窗登入 Apple ID**（每個新 session 登一次，含 2FA）。成功後控制台會顯示電郵，狀態變成 **待命（已登入）**。此時仍未搶機。
5. 全部 Worker 都登入好之後，撳綠色 **全部開始搶機**。測試模式會停在最後一步，唔會扣款。

### 搶夠指定數量之後？要唔要刪瀏覽器資料先換 Apple ID？

該 Worker 會**自動停止搶購**（狀態變成「已達數量上限」），視窗會留住方便你睇。上限係呢粒 Worker 喺全部勾選門市加總計，唔係每間門市各計。唔使手動刪瀏覽器資料。

換第二個 Apple ID：**新增 Worker** → 用**新的 session 資料夾** → 儲存此 Worker → 喺新卡登入另一個 Apple ID。舊 session 可以留低。

### 有冇資安問題？

呢個程式**設計成只喺你自己部電腦跑**，唔會把 Apple 密碼傳到另外一部伺服器：登入係喺本機 Chromium 對住 Apple 官網完成。不過仍然有幾樣你要知：

- **控制台冇密碼。** 任何可以喺呢部電腦開瀏覽器嘅人，去 `http://127.0.0.1:8765` 就可以撳開始／停止、甚至真實下單。唔好喺公用電腦跑，唔好開遠端桌面俾唔識嘅人。
- **後台綁死 `127.0.0.1`，唔會公開到互聯網。** 一般嚟講外面打唔入你部機。但唔好自行改成 `0.0.0.0` 或者做埠轉發。
- **Apple ID 登入狀態存在專案 `sessions\` 資料夾**（每個 Worker 獨立一條路徑，例如 `sessions\session_worker_1`）。呢個資料夾已加入 `.gitignore`，**唔會上傳 GitHub**。但檔案本身冇加密：任何人複製走，就可能用到你已登入嘅 Apple 商店 session。
- **訪客信用卡／CVV／地址** 唔會寫死喺程式碼，亦唔會出現喺 Live Log 或 PowerShell。儲存時加密寫入本機 `secrets\`，鑰匙放喺 `.env`（兩個都已 gitignore）。瀏覽器草稿亦唔會完整記住 CVV。
- **Live Log 可能出現 Apple ID 電郵。** 唔好截圖發公開頻道。卡號會被自動遮蓋。
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
bot/worker.py           登入 / 待命 / 開始或停止搶購、持久化 Chrome／Chromium
bot/checkout.py         加車／結帳／自取或送貨／訪客填表；測試模式停在最後一步並輸出計時
bot/secrets.py          本機加密訪客敏感資料
bot/manager.py          單一 Worker 登入／暫停／繼續、全部開始搶機、緊急停止
templates/index.html    真正控制台（要 python app.py）
static/css/app.css
static/js/app.js
sessions/               每個 Worker 獨立瀏覽器資料夾（不進 git）
secrets/                訪客加密資料（不進 git）
.env                    本機密鑰（不進 git）
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
