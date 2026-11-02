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

## 控制台點用

1. 預設 **測試模式 (Test Mode / Dry Run)** 為開啟。建議先維持開啟。
2. 喺每張 Worker 卡揀 **結帳模式**（Apple ID 登入 或 訪客）同 **取貨方式**（門市自取 或 送貨上門），再揀機型、數量上限。Apple ID 模式要填 Session 資料夾；訪客模式第一次要填晒英文姓名、電郵、電話、**兩欄地址**（街道／區域 同 大廈／座／樓／單位）、信用卡、有效月份／年份同 CVV，**未填齊唔可以儲存，亦唔可以開始運作**。儲存後卡號會變成 •••• 後四位，打錯可以再改再儲存，唔使刪卡重開；再儲存成功時 Live Log 會出「worker1 訪客資料已修改成功」。控制台有效年份顯示 2028，機械人填官網時會轉成 Apple 嘅 **MM/YY**（例如 12/28），**唔會填 12/2028**。門市自取要勾香港分店同取貨天數；送貨上門要揀「幾日內必須送到」。撳 **儲存此 Worker**。
3. **Apple ID 模式：** 撳 **登入 Apple ID**，喺彈出嚟嘅視窗登入。**訪客模式：** 唔使登入，但第一次資料未填齊就儲存唔到、開始唔到。儲存後可以改返資料再儲存。
4. **全部開始搶機** 要每個 Worker 都已儲存，而且 Apple ID 嘅已登入、訪客嘅已填齊。單張卡用 **開始運作 / 暫停運作**。運作中唔可以改設定。
5. 關閉測試模式後再按 **全部開始搶機** 或 **開始運作**，前端會先問你真實下單確認。
6. 如果頁面突然唔對、或者你用手喺瀏覽器撳咗嘢，嗰個 Worker 會**自動暫停**，視窗帶到最前。你手動處理好再撳 **開始運作**。
7. **緊急停止所有 Bot** 會關閉全部瀏覽器。

---

## 你點用（User Journey）同機械人點做（Worker Journey）

以下用日常說話說明。發現有貨之後，機械人會打開產品頁，**先撳「不換購」同「無 AppleCare+ 服務計劃保障」**（唔揀呢兩步，加入購物袋會一直灰色），然後先至加車。

秒數假設**冇 HTTP 541／404**。前半截用 MagSafe 配件喺官網實測過：打開產品頁 0.4–1.0 秒、加入購物袋 0.9–1.4 秒、撳結帳去到「登入—安全結帳」約 1.6 秒，**加車到登入牆大約 3.2–3.9 秒**。iPhone 要多撳不換購／無 AppleCare+（大約 0.2–2 秒）。後半截（揀門市、填訪客、去到付款前）雲端被擋，未完整行完；下面係按 MagSafe 前半截推算。屋企網絡慢會再長。Duo 冇貨時請用下面 FAQ 嘅有貨 iPhone 先試。

### 你做嘅事（四種組合都一樣開頭）

1. 開 PowerShell，入專案資料夾，啟動 `.venv`，跑 `py app.py`，再用瀏覽器打開 `http://127.0.0.1:8765`。
2. 保持測試模式開啟。新增一張 Worker 卡，揀機型。
3. 揀結帳模式同取貨方式，填嗰種模式需要嘅資料，撳「儲存此 Worker」。
4. Apple ID 模式：登入。訪客模式：確認姓名、兩欄地址、卡資料已填。
5. 撳「開始運作」或綠色「全部開始搶機」。之後等機械人自己監察有冇貨。
6. 測試模式成功一次之後，Live Log 同 PowerShell 會出現效能實測報告（加車、入結帳、取貨或送貨、去到付款前最後一步、總秒數）。

### 組合 A：Apple ID + 門市自取

**你：** 揀 Apple ID 登入模式、門市自取，勾 ifc / 沙田等，揀一日內／兩日內／三日內，登入自己嘅 Apple ID，然後開始。

**機械人：** 發現有貨 → 打開產品頁，揀不換購同無 AppleCare+，再加入購物袋（約 2–4 秒）→ 進入結帳（約 1.5–2 秒；已登入 Apple ID 過登入牆約 0.5–2 秒）→ 自動揀門市自取、勾你指定嘅分店、撳畫面上**最早第一個**取貨時段（約 3–6 秒）→ 用帳戶入面已儲存嘅取貨人資料推到付款前最後一步（約 2–4 秒）。**合計大約 8–16 秒，多數約 12 秒。** 測試模式喺呢度停，唔扣款。

### 組合 B：Apple ID + 送貨上門

**你：** 揀 Apple ID 登入模式、送貨上門，再揀例如「7 日內送到」，登入後開始。唔使勾門市。

**機械人：** 發現有貨 → 揀不換購同無 AppleCare+ 後加車（約 2–4 秒）→ 入結帳（約 1.5–2 秒；已登入過登入牆約 0.5–2 秒）→ 揀送貨上門，讀網頁「預計送達日期」（約 2–4 秒）。如果 3 日後送到、你又設定 7 日內：繼續去付款前（約 2–4 秒），**合計大約 8–15 秒，多數約 11 秒**。如果要等兩個星期：呢次機會放棄，返回監察，唔會亂填。

### 訪客模式搶購流程（對照而家 Apple 香港官網）

控制台已揀 SKU（例如 iPhone 17e 嘅 `MHRV4ZA/A`），機械人會開 `goto/product/SKU`，等跳到已揀顏色／容量嘅產品頁（唔好喺系列頁就撳）。卡號同 CVV 唔會出現喺 Live Log。加車要真正去到配件頁或購物袋先算成功；如果加車請求回 541，會暫停而唔會當已入袋。

**兩種取貨方式前半截一樣：**

1. 監察到有貨，開始搶。
2. 開該 SKU 產品頁 → 揀 **不換購**、**無 AppleCare+**。
3. 撳 **加入購物袋**。
4. 去到配件頁（網址有 `step=attach`）→ 撳 **查看購物袋**。
5. 去 `https://www.apple.com/hk-zh/shop/bag`。如果數量上限係 2 而且未買過，購物袋下拉揀 **2**。
6. 撳 **結帳**。**唔會撳「使用 Apple Pay 結帳」**。
7. 去到登入牆 → 撳 **以訪客身份繼續**。
8. 去到 `checkout?_s=Fulfillment-init`。呢到可以揀門市取貨定送貨上門。

之後按你張卡揀嘅取貨方式行其中一條。

### 組合 C：訪客 + 門市自取

**你：** 揀訪客模式、門市自取，填英文姓名、電郵、香港電話、兩欄地址、信用卡、月份、年份、CVV，勾門市，**唔使登入 Apple ID**，儲存後開始。資料未填齊會彈提示，開始唔到。

**機械人（接上面第 8 步）：**

9. 撳 **我會前來取貨**。
10. 揀監察到有貨嗰間分店。
11. 如果頁面有取貨時段，撳畫面上**最早嗰個**；搵唔到就跳過。
12. 去到 `checkout?_s=PickupContact-init`。
13. 只填 **姓氏、名字、電郵、手提電話**。呢頁唔填地址、唔填信用卡。
14. 撳 **繼續前往付款**。
15. 去到 `checkout?_s=Billing-init`，跟下面「帳單」段。

### 組合 D：訪客 + 送貨上門

**你：** 揀訪客模式、送貨上門，填齊訪客資料（包括兩欄地址）同送貨時效（例如 7 日內），儲存後開始。唔使勾門市。

**機械人（接上面第 8 步）：**

9. 撳 **我希望送貨**。
10. 去到 `checkout?_s=Shipping-init`。
11. 填 **姓氏、名字** → 兩欄地址（第一欄：區域、地區、街道名稱及號碼；第二欄：屋苑或大廈／座數／樓層／單位）→ 地區揀 **香港**（官網多數已 default 香港）→ **電郵、手提電話**。
12. 撳 **繼續前往付款**。
13. 如果頁面寫住嘅預計送達日超出你設定嘅「幾日內必須送到」，呢次機會放棄，返回監察。
14. 去到 `checkout?_s=Billing-init`，跟下面「帳單」段（同門市取貨一樣）。

### 訪客帳單（門市取貨同送貨上門共用）

去到 `checkout?_s=Billing-init` 之後：

1. 撳 **信用卡或扣帳卡**。
2. 填卡號、到期日 **MM/YY**（控制台顯示 2028 就填 **12/28**，**唔會填 12/2028**）、CVV。
3. 地區揀香港；再填姓氏、名字；帳單地址又係嗰**兩欄**（同你喺控制台填嘅街道／大廈資料）。
4. 撳 **檢查你的訂單**。
5. **測試模式**停喺呢度，**唔會撳立即下單**。關閉測試模式先至會送出訂單。

## 常見問題

### 撳「以訪客身份繼續」之後跳去 404？

呢粒掣**冇獨立網址**。真正動作係 POST 去 Apple ` /shop/signInx `。如果官網回 **HTTP 541**（風控），頁面就會跟住跳 ` /shop/541 ` → ` /shop/go/404 ` → 你見到嘅 404。

Bot 會等畫面出現藍色 **「以訪客身份繼續」** 掣先撳（唔單止靠 `data-autom`；標題「訪客結帳」唔會當掣）。撳到之後 Live Log 會寫「已撳「以訪客身份繼續」」。若然仍然 404，多數係網絡被擋（例如機房 IP），唔係掣撳錯。請喺**香港家用網絡**開測試模式再試；測試模式仍然停在付款前最後一步，唔會落單。

聽朝喺屋企點分成功定 541：

- **成功：** 購物袋有貨 → 去到「登入以快速完成結帳」→ 撳訪客之後入到揀送貨／取貨、填姓名地址卡。Live Log 會出效能實測報告，測試模式停在付款前。
- **仍然 541：** 撳加車或「以訪客身份繼續」之後頁面變「找不到你想去的網頁」，Live Log 會寫官網拒絕訪客結帳。呢個係 Apple 風控，唔係掣認錯。

瀏覽器會用你本機嘅有頭視窗、香港時區，優先開 **本機 Google Chrome**（冇就 Edge，再冇先用 Playwright Chromium），並收埋 Playwright 預設嘅 `webdriver`／`--enable-automation` 標記。Windows 唔會再傳 `--no-sandbox`，避免頂部黃條擋住撳掣。Live Log 會寫用咗邊個瀏覽器。

### 屋企 IP 都被當 bot／仍然 541，我可以點做？

Playwright 就算喺家用網絡，都可能帶自動化痕跡。按呢個次序試，一次改一樣：

1. **裝正式版 Google Chrome**（[google.com/chrome](https://www.google.com/chrome/)），然後重新撳登入或開始運作。Live Log 應該寫「已用本機 Google Chrome」。如果寫緊 Playwright Chromium，即係未搵到 Chrome。
2. **關 VPN、加速器、公司代理、Clash 等。** 用香港家用寬頻。VPN 出口好似機房 IP，好容易 541。
3. **測試模式只開 1 個 Worker。** 開太多連庫存查詢都會 541。
4. **541 之後唔好即刻再撳訪客／加車。** 暫停嗰張卡，等幾分鐘。連續撞風控會越擋越實。
5. **用手機熱點對照一次。** 熱點得、寬頻唔得：寬頻 IP 被標記。兩個都 541：確認 Live Log 係本機 Chrome，而唔係備用 Chromium。
6. Bot 用獨立 `sessions\` 資料夾，**唔會**開你平時嗰個已登入 Chrome 用戶檔，避免同日常瀏覽器搶檔。

自動化唔可能 100% 扮成人手。以上係降低屋企機被誤判嘅實際步驟，唔係保證。

### Duo 冇貨，測試模式會唔會一直等？應該點測試？

**會一直等。** Bot 只喺庫存接口話有貨，先至開產品頁加車。Duo 顯示「暫無供應」就會停喺「輪詢中：尚未找到符合條件的貨源」，**加車同結帳試唔到**，所以 541／404 嗰段亦試唔到。

用一款而家有貨嘅 **iPhone** 試流程（測試模式唔扣款）。步驟同 Duo 一樣：不換購 → 無 AppleCare+ → 加車 → 結帳。**唔好用 MagSafe 做主測試**，配件頁通常冇不換購／AppleCare 嗰兩步。

例如（官網有貨先得；無貨就換另一款 iPhone，SKU 喺產品頁網址 `/shop/goto/product/` 後面）：

1. 測試模式勾住，只開 **1 張** Worker：結帳模式 **Apple ID 登入**，取貨 **門市自取**。
2. 「輸入 Apple 產品 SKU」填例如 `MHRV4ZA/A`，產品名稱可寫 `iPhone 17e 256GB 黑色`，撳 **加入此 SKU**。
3. **儲存此 Worker** → **登入 Apple ID**。Live Log 要見到「已用本機 Google Chrome」。
4. 撳 **開始運作**，等 Live Log 出現效能實測報告。測試模式停在付款前，**唔扣款**。

### 測試成功之後，可唔可以揀返 Duo？

**可以。** 登入狀態喺 `sessions\`，唔會因為換 SKU 而冇。

1. 如果仲喺運作中，先 **暫停運作**。
2. 機型下拉選單改返你要嘅 Duo，撳 **儲存此 Worker**。
3. 測試完成會顯示例如 1/1「已達數量上限」。呢個數字只喺呢次 `py app.py` 記住。喺 PowerShell 撳 **Control + C** 停後台，再跑一次 `py app.py`，開返 `http://127.0.0.1:8765`。登入通常仲喺；如果話未登入，再撳一次 **登入 Apple ID**。
4. 確認機型已係 Duo，再 **開始運作**。冇貨就繼續監察；有貨先至結帳。聽搶貨當日先取消測試模式。

### 本機出事，唔識睇 code，應該點話俾我聽？

**唔使睇程式。** Live Log 出現以「【請複製呢段到對話】」開頭嗰行，**整句複製**貼返嚟就得。Bot 如果加車或訪客被 541／404，而家會自動暫停，唔會當成功。

再補呢幾樣（用普通說話）：

1. Live Log 有冇「已用本機 Google Chrome」？定係 Playwright Chromium／Edge？
2. 彈出嚟嗰個視窗，網址列同大標題寫咩（例如「找不到你想去的網頁」）。
3. 去到邊一步：不換購、加車、結帳、以訪客身份繼續、填表。
4. **對照（最緊要）：** 開你**平時用嘅 Chrome**（唔係 Bot 彈出嚟嗰個），同一款 iPhone，人手撳不換購 → 加車 → 結帳 → 訪客。  
   - 平時 Chrome **得**、Bot **唔得**：較似自動化被認到，唔單止家用 IP。  
   - **兩個都** 541／404：較似網絡／IP。  
   - Bot **加車得**、撳訪客先 541：改用 **Apple ID 登入** 模式，唔好用訪客。

卡號同 CVV 唔好貼出嚟。

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
