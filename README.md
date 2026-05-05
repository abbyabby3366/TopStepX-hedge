# TopStepX to MT5 Hedge Copier

An automated high-speed trade copying system that scrapes live positions from the TopStepX web dashboard and mirrors them directly into MetaTrader 5 (MT5). The system is fully configurable via a local Tkinter GUI and sends real-time status, trade, and error alerts to a designated WhatsApp group.

## Prerequisites
- **Node.js** (v14+ installed)
- **Python** (v3.8+ installed)
- **MetaTrader 5** (Installed locally, logged into an account)
- **Google Chrome**

---

## 🛠️ Installation

### 1. Install Node.js Dependencies
Navigate to the root directory of this project in your terminal and install the required scraping library:
```bash
npm init -y
npm install puppeteer-core
```

### 2. Install Python Dependencies
You need the official MetaTrader5 Python module. In your terminal, run:
```bash
pip install MetaTrader5
```

---

## ⚙️ Configuration

1. Launch the bridge to open the **TopStepX Copier Configuration GUI**:
   ```bash
   python mt5_bridge.py
   ```
2. The GUI window will open. Expand the accordions and configure your settings:
   - **Scraper Settings**: Verify your `CHROME_PATH` points exactly to your Google Chrome executable.
   - **Trade Logic**: Set your multipliers and toggle `REVERSE_TRADING` if you want MT5 to do the opposite of TopStepX.
   - **MT5 Bridge Settings**: Input your MT5 `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, and `MT5_PATH` (path to `terminal64.exe`).
   - **Notifications**: Add your WhatsApp Group ID (`[number]@g.us`) and tick the notifications you wish to receive.
3. Click **Save Config**. The bridge is automatically listening on port 5000 in the background.

---

## 🚀 Usage

### Step 1: Start the MT5 Python Bridge
If it's not already running, start the bridge:
```bash
python mt5_bridge.py
```
*(Leave this terminal window running)*

### Step 2: Start the TopStepX Node Scraper
Open a **new** terminal window in the project directory and run:
```bash
node scraper.js
```
1. The scraper will automatically launch Google Chrome using your existing profile.
2. Navigate to `topstepx.com` and log in (if you aren't already).
3. The scraper will detect the URL and automatically wait for the positions table to load.
4. **You're done!** When a trade is opened or closed on TopStepX, it will instantly be copied to MT5 and logged to your WhatsApp.

---

## 🐛 Troubleshooting

- **WhatsApp Alert: "TopStepX position table has not been detected for over 15 seconds!"**
  - Ensure you are currently on the `topstepx.com` dashboard. If you navigate away or close the tab, the scraper will pause and alert you.
- **WhatsApp Alert: "Ticket XXX not found (Already closed?)"**
  - Ensure you aren't manually closing copied trades inside MT5. If you do, the bridge won't be able to find the MT5 ticket when TopStepX finally closes the original trade.
- **IPC Error / Bridge Connection Failed**
  - Ensure the `MT5_PATH` in your Configuration GUI points directly to the `terminal64.exe` inside your MetaTrader 5 folder.
