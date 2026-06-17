# Workday Reporting Orchestration

This project automates the discovery, migration, and export of Workday custom reports using an orchestrated set of intelligent agents and browser automation.

## Architecture Flow

```mermaid
flowchart TD
    A[Report Discovery Agent<br/>(Web UI)] -->|User searches & selects reports| B[Selected Reports list]
    B --> C{Orchestrator}
    C -->|Spawns parallel agent| D[Report Migration Agent<br/>(Browser Automation)]
    C -->|Spawns parallel agent| E[Report Export Agent<br/>(Browser Automation)]
    
    D -->|Creates Config Package & Extracts| F[(Customer Central .dat File)]
    E -->|Downloads Report Outputs| G[(Excel .xlsx Files)]
```

## The Three Agents

### 1. Report Discovery Agent (Web UI)
The Discovery Agent provides an intuitive web interface for users to search for Workday reports. 
- **Hybrid Search**: Combines BM25 (keyword matching) and an LLM (semantic search/re-ranking) to find the most relevant reports from your Workday catalog.
- **Workday Sync**: Connects directly to a Workday RaaS (Report-as-a-Service) endpoint to keep the local report catalog up-to-date.
- **Handoff**: Once a user selects the desired reports and clicks "Proceed with Selected Reports", the agent saves the selection and seamlessly signals the Orchestrator to begin downstream automation.

### 2. Report Migration Agent (`run_agent.py`)
This agent uses Playwright browser automation to migrate the selected reports between Workday tenants (e.g., from DPT3 to Customer Central).
- **Configuration Package**: Automatically navigates Workday to create a new Configuration Package based on a generated Industry name.
- **Add Instances**: Searches for and adds all selected custom reports to the package.
- **Migrate & Extract**: Initiates the migration to Customer Central, pauses for the user to complete any required SSO prompts, and automatically downloads the final `.dat` configuration extract file.

### 3. Report Export Agent (`run_export.py`)
This agent runs in parallel with the Migration Agent to download the actual output data of the selected reports.
- **Global Search**: Automatically searches for each selected report in the Workday global search bar.
- **Report Definition**: Navigates directly to the report's "View Custom Report" or "Report Definition" page.
- **Excel Export**: Clicks the "Export to Excel" button and securely downloads the output `.xlsx` files to your local `downloads/` folder.

## Orchestrator (`orchestrator.py`)

The `orchestrator.py` script is the **recommended** entry point. It ties the three agents together into a single, seamless workflow:

1. It launches the **Report Discovery Agent** server and opens the Web UI in your default browser.
2. It waits for you to search and confirm your report selection.
3. Once confirmed, it takes your selected reports and launches both the **Migration Agent** and the **Export Agent** simultaneously in isolated browser contexts using `asyncio.gather`.
4. It provides a final summary table when both automation agents finish their tasks.

**To run the full flow:**
```cmd
set WD_USER=username
set WD_PASS=your-password
.venv\Scripts\python.exe orchestrator.py
```

## Setup

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
