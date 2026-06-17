# Browser Automation Tool (Playwright)

A small, config-driven browser automation runner. You describe what to do in a
JSON file — navigate to a URL, click things, scroll, type, take screenshots —
and `runner.py` executes the steps in order against a real browser.

## Setup

Python and Playwright are already installed in the local `.venv`. If you ever
need to recreate the environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## Interactive agent (Workday Configuration Package)

`run_agent.py` prompts for an **Industry name** and one or more **report names**, then runs
the whole Workday flow and shows a pop-up when done:

```powershell
$env:WD_USER = "username"
$env:WD_PASS = "your-password"
.\.venv\Scripts\python.exe run_agent.py
```

```CMD
set WD_USER=username
set WD_PASS=your-password
.\.venv\Scripts\python.exe run_agent.py
```

It will ask:
- **Industry name** → the package is named `<Industry>_Config_Package`
- **Report name(s)** → one per line (blank line to finish), or a single comma-separated line.
  Works for 1 report or 10–15.

Then it: creates the Configuration Package → sets implementation type **Custom Reports** →
adds each report (filter by name + select) → clicks **Migrate** → **launches Object
Transporter in Customer Central** (which opens in a **new browser tab** the agent switches to).
It then **pauses for you to complete the Customer Central SSO login** (a native pop-up — click
OK once the Workday home/search bar is visible), runs **Create Configuration Extract** (file
name `<Industry>_Configuration_Extract`, description, source tenant `dpt3`, type *Configuration
Package*), filters and selects the package created earlier, **refreshes the Extraction Reports
screen until Status = Completed**, and **downloads the extract file** `<Industry>_Config_Package.dat`.
Finally it shows **"Configuration Extract created successfully"**. On failure it shows an error
pop-up and saves `error.png`. Set `AGENT_NO_POPUP=1` to use console prompts (Enter to resume a
pause) instead of dialogs — useful for non-interactive runs.

> **Customer Central login URL:** `https://impl.workday.com/wday/authgwy/accenture_ptcc/login.htmld`
> The agent reaches it automatically via the "Launch Object Transporter" hand-off (new tab).
> The standalone `test_cc.py` harness opens it directly to iterate on the extract flow without
> re-running the dpt3 migration (the extract reads packages straight from the dpt3 source tenant).

> Configuration Package names must be **unique** in the tenant — use a fresh Industry name each run.

## Report Export Agent (Excel download — runs in parallel)

`run_export.py` downloads each report as an **Excel** file from the DPT3 tenant.
It runs in its **own browser window**, so you can launch it **at the same time** as
the migration agent (`run_agent.py`) from a second CMD window.

**CMD window 1 — Migration:**
```cmd
set WD_USER=username
set WD_PASS=your-password
.venv\Scripts\python.exe run_agent.py
```

**CMD window 2 — Export (parallel):**
```cmd
set WD_USER=username
set WD_PASS=your-password
.venv\Scripts\python.exe run_export.py
```

It will ask for report names (same input format: one per line or comma-separated).
For each report it: searches in global search → opens the **View Custom Report** page
→ clicks the report name in the header to open the report → clicks **Export to Excel**
→ clicks **Download** in the popup. Excel files are saved to the current directory
with the browser's suggested filename.

## Orchestrator — single command, both agents in parallel

`orchestrator.py` is the **recommended** way to run both agents. It takes your input
**once** (industry + report names), then launches Migration and Export simultaneously
in two isolated Playwright BrowserContexts within a single `asyncio.gather` call.

```cmd
set WD_USER=username
set WD_PASS=your-password
.venv\Scripts\python.exe orchestrator.py
```

- **One prompt** — enter industry + reports once; both agents share the same input
- **True parallelism** — each agent gets its own browser context (separate cookies/session)
- **Independent failures** — if one agent fails, the other continues to completion
- **Final summary** — prints a combined results table when both finish

> Architecture: `orchestrator.py` → builds configs via `run_agent.build_config()` and
> `run_export.build_config()` → runs both through `async_runner.run_config_async()` using
> `async_playwright` (not the sync API).

## Run (static config)

```powershell
# Headless (no visible window) using the example config
.\.venv\Scripts\python.exe runner.py config.json

# Watch it happen in a real browser window
.\.venv\Scripts\python.exe runner.py config.json --headed

# Slow each action down by 500ms so it's easy to follow
.\.venv\Scripts\python.exe runner.py config.json --headed --slowmo 500
```

On success the runner prints each step; on failure it writes `error.png` so you
can see where it stopped.

## Config format

```jsonc
{
  "browser": "chromium",          // chromium | firefox | webkit
  "headless": true,               // override with --headed
  "viewport": { "width": 1280, "height": 800 },
  "steps": [ /* see below */ ]
}
```

### Available step actions

| action             | required fields      | optional fields                        | what it does |
|--------------------|----------------------|----------------------------------------|--------------|
| `navigate`         | `url`                | `wait_until`, `timeout`                | Go to a URL. `wait_until`: `load` \| `domcontentloaded` \| `networkidle`. |
| `click`            | a *target* (below)   | `timeout`, `nth`                       | Click an element. |
| `click_text`       | `text`               | `exact`, `timeout`                     | Click an element by its visible text. |
| `scroll`           | —                    | `direction` (`down`/`up`/`top`/`bottom`), `pixels` | Scroll the page. |
| `scroll_into_view` | `selector`           | `timeout`                              | Scroll until an element is visible. |
| `type`             | a *target* + value   | `timeout`, `sequential`, `clear`, `delay` | Type into a field. `sequential: true` types key-by-key (needed by widgets that filter on real keystrokes); `clear: true` empties it first. |
| `press`            | `key`                | `selector`, `timeout`                  | Press a key (e.g. `Enter`, `Control+A`). |
| `wait_for`         | `selector`           | `state` (`visible`/`hidden`/...), `timeout` | Wait for an element. |
| `wait`             | —                    | `seconds`                              | Pause for N seconds. |
| `screenshot`       | —                    | `path`, `full_page`                    | Save a screenshot. |
| `pause`            | —                    | `title`, `message`                     | Block until the user confirms (e.g. a manual SSO login). Shows a modal Windows pop-up with **OK**; falls back to a console *Press Enter* prompt when there's no GUI or `AGENT_NO_POPUP=1`. |
| `download`         | a *target* (below)   | `path`, `timeout`, `nth`               | Click a target and save the file download it triggers. `path` sets the save location (defaults to the browser's suggested filename). |
| `dump`             | —                    | `selector`, `contains`, `html`, `limit` | Debug: print tag/`data-automation-id`/aria-label/text (and optionally `outerHTML`) for matches. Used to discover selectors in dynamic UIs. |

`click` also supports `confirm_hidden` (a selector that must disappear after the click — the
runner re-clicks up to `attempts` times until it does; ideal for flaky submit/OK buttons).
`type` supports `sequential` (focus + type key-by-key, avoids dropdowns intercepting a click)
and `clear`.

**Targeting** (for `click` / `type`) — provide exactly one of:
- `selector` — a raw CSS / Playwright selector
- `byLabel` — match a form field by its label text (`page.get_by_label`)
- `automation_label` — match `[data-automation-label="..."]` (handy for Workday prompt options)
- `text` — match by visible text (`click` only; for `type`, `text` is the value to type)

Add `nth` to pick the Nth match (negative allowed, e.g. `-1` = last); otherwise the first match is used.

**The value to type** (for `type`) — provide one of:
- `text` — a literal string
- `env` — read from an environment variable (kept out of the config)
- `secret_env` — like `env` but masked in logs (use for passwords)

Every step also accepts an optional `"label"` (run-log caption) and `"optional": true`
(a step allowed to fail without aborting the run — e.g. dismissing a cookie banner that
may not appear).

### Credentials & logging in

Never put passwords in the config. Reference environment variables instead and set them
before running:

```powershell
$env:WD_USER = "your-user"
$env:WD_PASS = "your-pass"
.\.venv\Scripts\python.exe runner.py workday.json --headed
```

```jsonc
{ "action": "type", "selector": "input[name='username']", "env": "WD_USER" },
{ "action": "type", "selector": "input[name='password']", "secret_env": "WD_PASS" }
```

### Choosing the browser

The bundled Chromium runs headless fine, but on some Windows machines it can't launch a
*headed* window (missing system runtime). Use an installed browser via `channel`:

```jsonc
{ "browser": "chromium", "channel": "chrome", "headless": false }
```

`channel` accepts `chrome` or `msedge`; it can also be passed on the CLI: `--channel chrome`.

### Example: search on a site

```json
{
  "browser": "chromium",
  "headless": false,
  "steps": [
    { "action": "navigate", "url": "https://duckduckgo.com/" },
    { "action": "type", "selector": "input[name='q']", "text": "playwright python" },
    { "action": "press", "key": "Enter" },
    { "action": "wait_for", "selector": "article", "label": "wait for results" },
    { "action": "scroll", "direction": "bottom" },
    { "action": "screenshot", "path": "results.png" }
  ]
}
```

## Selector tips

Playwright selectors are flexible:
- CSS: `button.submit`, `#login`, `input[name='q']`
- Text: `text=Sign in`
- Role: `role=button[name='Submit']`
