require('dotenv').config();
const puppeteer = require('puppeteer-core');
const { spawn, exec } = require('child_process');
const fs = require('fs/promises');
const util = require('util');
const execAsync = util.promisify(exec);

const CHROME_PATH = process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const CHROME_PROFILE_DIR = process.env.CHROME_PROFILE_DIR || 'C:\\temp\\chrome-dev-profile';
const DEBUG_PORT = process.env.DEBUG_PORT || 9222;

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function isProcessAlive(pid) {
  try {
    process.kill(pid, 0); // Signal 0 = existence check only
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * Kill zombie Chrome processes that were launched with a specific debugging port.
 */
async function killZombieChromeOnPort(port) {
  const targetFlag = `--remote-debugging-port=${port}`;
  try {
    const psCommand = [
      `Get-CimInstance Win32_Process -Filter "Name='chrome.exe'"`,
      `| Where-Object { $_.CommandLine -like '*${targetFlag}*' -and $_.CommandLine -notlike '*--type=*' }`,
      `| Select-Object -ExpandProperty ProcessId`,
    ].join(" ");

    const { stdout } = await execAsync(
      `powershell -NoProfile -NonInteractive -Command "${psCommand}"`,
      { encoding: "utf8", timeout: 10000 },
    );

    const pids = stdout
      .split(/\r?\n/)
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !isNaN(n) && n > 0);

    if (pids.length === 0) return;

    for (const pid of pids) {
      try {
        console.log(`Killing zombie Chrome (PID ${pid}) with ${targetFlag}...`);
        await execAsync(`taskkill /PID ${pid} /F /T`, { timeout: 5000 });
      } catch (e) {}
    }
  } catch (e) {}
}

/**
 * Force Chrome to the foreground using Windows API (PowerShell).
 */
async function bringChromeToFrontOS() {
  console.log("Bringing Chrome window to front (OS level)...");
  const psScript = `
$sig = @'
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
'@
Add-Type -MemberDefinition $sig -name NativeMethods -namespace Win32
$chrome = Get-Process chrome -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if ($chrome) {
  [Win32.NativeMethods]::ShowWindow($chrome.MainWindowHandle, 9)
  [Win32.NativeMethods]::SetForegroundWindow($chrome.MainWindowHandle)
}
`;
  const encoded = Buffer.from(psScript, 'utf16le').toString('base64');
  await execAsync(`powershell -NoProfile -NonInteractive -EncodedCommand ${encoded}`).catch(() => {});
}

/**
 * Connect to an existing Chrome instance or launch a new one.
 */
async function connectOrLaunchChrome() {
  let browser;
  try {
    console.log(`Checking if Chrome is already running on port ${DEBUG_PORT}...`);
    browser = await puppeteer.connect({
      browserURL: `http://127.0.0.1:${DEBUG_PORT}`,
      defaultViewport: null,
      protocolTimeout: 30000,
    });
    console.log("Connected to existing Chrome instance.");
    return browser;
  } catch (e) {
    console.log("Chrome not found on debugging port. Spawning new instance...");
    await killZombieChromeOnPort(DEBUG_PORT);
    await sleep(500);

    const chromeArgs = [
      `--remote-debugging-port=${DEBUG_PORT}`,
      `--user-data-dir=${CHROME_PROFILE_DIR}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--start-maximized"
    ];

    const chromeProcess = spawn(CHROME_PATH, chromeArgs, {
      detached: true,
      stdio: ["ignore", "ignore", "pipe"],
    });

    const chromePid = chromeProcess.pid;
    chromeProcess.unref();

    console.log(`Waiting for Chrome to initialize (PID: ${chromePid})...`);

    const CONNECT_MAX_RETRIES = 5;
    for (let attempt = 1; attempt <= CONNECT_MAX_RETRIES; attempt++) {
      const delayMs = Math.min(1000 + attempt * 1000, 10000);
      await sleep(delayMs);

      if (chromePid && !isProcessAlive(chromePid)) {
        throw new Error(`Chrome process (PID ${chromePid}) died prematurely.`);
      }

      try {
        browser = await puppeteer.connect({
          browserURL: `http://127.0.0.1:${DEBUG_PORT}`,
          defaultViewport: null,
          protocolTimeout: 30000,
        });
        console.log(`Connected to Chrome on attempt ${attempt}.`);
        return browser;
      } catch (error) {
        console.warn(`Connect attempt ${attempt}/${CONNECT_MAX_RETRIES} failed, retrying...`);
      }
    }
    throw new Error("Failed to connect to Chrome after multiple attempts.");
  }
}

async function startScraping() {
  try {
    const browser = await connectOrLaunchChrome();
    let pages = await browser.pages();
    let page = pages.length > 0 ? pages[0] : await browser.newPage();

    if (page) {
      console.log('Switching to target tab...');
      await page.bringToFront();
      await bringChromeToFrontOS();
    }

    console.log('Starting scrape loop...');

    let activePositions = new Map();
    let betLog = [];
    
    // 1. Load existing positions from data.json (so script remembers trades across restarts)
    try {
      const existingData = await fs.readFile('data.json', 'utf8');
      const parsedData = JSON.parse(existingData);
      parsedData.forEach(pos => {
        activePositions.set(pos.positionID, { data: pos, missingCount: 0 });
      });
      console.log(`Loaded ${activePositions.size} existing positions from data.json`);
    } catch(e) {}

    // 2. Load existing bet log if it exists
    try {
      const existingLog = await fs.readFile('bet_log.json', 'utf8');
      betLog = JSON.parse(existingLog);
    } catch(e) {}

    let scrapeCount = 0; // Tracks loop iterations for startup grace period

    while (true) {
      try {
        // If the page was closed manually, grab a new one
        if (page.isClosed()) {
          console.warn("Page was closed. Trying to get another open page...");
          pages = await browser.pages();
          page = pages.length > 0 ? pages[0] : await browser.newPage();
        }

        // Wait for the table AND its footer to ensure the component is actually rendered
        await page.waitForSelector('[data-testid="positions-display-table"]', { timeout: 5000 });
        await page.waitForSelector('.MuiDataGrid-footerContainer', { timeout: 5000 });

        scrapeCount++;

        // 1. Detect if the grid is actively fetching/loading data
        const isPageLoading = await page.evaluate(() => {
          return !!document.querySelector('.MuiDataGrid-loadingOverlay, .MuiCircularProgress-root, .MuiSkeleton-root');
        });

        if (isPageLoading) {
          console.log(`[Grace Period] Table is currently loading data. Pausing checks...`);
          await sleep(1000);
          continue; // Skip evaluating missing rows until loading finishes
        }

        const positions = await page.evaluate(() => {
          const rows = document.querySelectorAll('.MuiDataGrid-row');
          const data = [];

          rows.forEach(row => {
            const entryTime = row.querySelector('[data-field="entryTime"]')?.innerText?.trim() || '';
            const symbolName = row.querySelector('[data-field="symbolName"]')?.innerText?.trim() || '';
            const positionSize = row.querySelector('[data-field="positionSize"]')?.innerText?.trim() || '';
            const averagePrice = row.querySelector('[data-field="averagePrice"]')?.innerText?.trim() || '';
            const risk = row.querySelector('[data-field="risk"]')?.innerText?.trim() || '';
            const toMake = row.querySelector('[data-field="toMake"]')?.innerText?.trim() || '';
            const profitAndLoss = row.querySelector('[data-field="profitAndLoss"]')?.innerText?.trim() || '';
            
            const rowId = row.getAttribute('data-id');

            data.push({
              positionID: rowId,
              entryTime,
              symbolName,
              positionSize: parseInt(positionSize, 10) || 0,
              averagePrice: parseFloat(averagePrice.replace(/,/g, '')) || 0,
              risk,
              toMake,
              profitAndLoss
            });
          });

          return data;
        });

        const currentPosIds = new Set(positions.map(p => p.positionID));

        // 1. Handle New & Existing Positions
        for (const pos of positions) {
          if (!activePositions.has(pos.positionID)) {
            // New position detected
            activePositions.set(pos.positionID, { data: pos, missingCount: 0 });
            
            let action = pos.positionSize > 0 ? "buy" : "sell";
            let asset = pos.symbolName === "/GC" ? "GOLD" : pos.symbolName;
            let logMsg = `[NEW BET] ${action} ${Math.abs(pos.positionSize)} ${asset} (ID: ${pos.positionID})`;
            
            console.log(">>> " + logMsg);
            betLog.push({ time: new Date().toISOString(), type: 'OPEN', message: logMsg, positionID: pos.positionID, raw: pos });
            await fs.writeFile('bet_log.json', JSON.stringify(betLog, null, 2), 'utf8');
          } else {
            // Position exists, reset missing counter
            let existing = activePositions.get(pos.positionID);
            existing.missingCount = 0;
            existing.data = pos; // keep stats updated
          }
        }

        // 3. Handle Missing Positions (3 consecutive seconds)
        // We only enforce closing trades AFTER the first 5 successful scrapes (5s grace period on launch)
        if (scrapeCount > 5) {
          for (const [posID, record] of activePositions.entries()) {
            if (!currentPosIds.has(posID)) {
              record.missingCount++;
              if (record.missingCount >= 3) {
                let logMsg = `[CLOSE SIGNAL] Position disappeared for 3s. Signal to close trade (ID: ${posID})`;
                console.log(">>> " + logMsg);
                betLog.push({ time: new Date().toISOString(), type: 'CLOSE_SIGNAL', message: logMsg, positionID: posID });
                await fs.writeFile('bet_log.json', JSON.stringify(betLog, null, 2), 'utf8');
                
                activePositions.delete(posID);
              }
            }
          }
        } else if (scrapeCount <= 5) {
           console.log(`[Grace Period] Scrape ${scrapeCount}/5 - Verifying data stability before enforcing close signals...`);
        }

        console.clear(); 
        console.log(`--- Scraped at ${new Date().toLocaleTimeString()} ---`);
        console.table(positions);

        await fs.writeFile('data.json', JSON.stringify(positions, null, 2), 'utf8');
        await sleep(1000);
        
      } catch (error) {
        console.error('Waiting for table or an error occurred...', error.message);
        await sleep(3000);
      }
    }
  } catch (err) {
    console.error("Scraping failed to start:", err.message);
  }
}

startScraping();
