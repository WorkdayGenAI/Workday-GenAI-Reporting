# Workday Report Discovery Agent
## BM25 + LLM Semantic Search for Legacy Workday Reports

A two-stage hybrid search and discovery engine that enables users to find relevant Workday reports from a catalog of **4,581 custom reports** using plain natural language queries (e.g., *"employee termination reports with performance ratings"*).

---

## Architecture

```
                          ONLINE QUERY PATH
┌──────────────┐    ┌──────────────────┐    ┌────────────────┐
│  User Query  │───>│ Query Preprocess │───>│  BM25 Search   │
│  (natural    │    │ • Tokenize       │    │ • Full catalog │
│   language)  │    │ • Stem & Synonyms│    │ • Top-30 cands │
└──────────────┘    └──────────────────┘    └───────┬────────┘
                                                    │
                                                    ▼
                    ┌──────────────────┐    ┌────────────────┐
                    │  Final Response  │<───│  LLM Scorer    │
                    │ • Ranked reports │    │ • Groq / OpenAI│
                    │ • Explanations   │    │ • Score 0-100  │
                    └──────────────────┘    └────────────────┘

                         OFFLINE PREPARATION
┌──────────────────────────────────────────────────────────┐
│  Workday RaaS  →  JSON Catalog  →  Composite BM25 Index  │
└──────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
Workday_Report_Discovery_Agent/
├── README.md               ← You are here
├── config.py               ← Configuration settings and field boost weights
├── api_server.py           ← FastAPI backend server & sub-app mount
├── agent.py                ← Main pipeline orchestrator (ReportDiscoveryAgent)
├── bm25_engine.py          ← Keyword search engine with field boosting
├── llm_scorer.py           ← LLM candidate re-ranker with payload auto-reduction
├── report_catalog.py       ← Catalog data loader & schema normalizer
├── stemmer.py              ← Custom suffix-stripping & tokenization
├── synonyms.py             ← Workday & HR domain synonym dictionaries
├── sync_catalog.py         ← Workday RaaS sync tool
├── cli.py                  ← Command-line discovery interface
├── evaluation.py           ← Search quality benchmark test harness
├── data/
│   └── All_Custom_Reports_Enabled_as_RAAS.json  ← 4,581 custom reports extract
├── prompts/
│   └── scoring_prompt.txt  ← LLM system prompt & scoring rules
└── static/                 ← Standalone Web UI
    ├── index.html
    ├── styles.css
    └── app.js
```

---

## Tech Stack

* **Search Engine**: Custom in-memory BM25 with multi-field boosting (Name, Description, Data Source, Fields Displayed, Fields Referenced).
* **LLM Re-Ranking**: Groq Cloud API / OpenAI API with automatic prompt chunking and payload reduction.
* **Backend**: Python 3.10+, FastAPI, Uvicorn.
* **Frontend**: Vanilla HTML5, modern CSS3 (custom dark mode), JavaScript (ES6+).

---

## Quick Start

### 1. Run via CLI
```powershell
.venv\Scripts\python.exe Workday_Report_Discovery_Agent/cli.py "Termination by performance"
```

### 2. Run Standalone Web Server
```powershell
.venv\Scripts\python.exe Workday_Report_Discovery_Agent/api_server.py
```
Open your browser to `http://localhost:8000`.

### 3. Programmatic Usage in Python
```python
from Workday_Report_Discovery_Agent.agent import ReportDiscoveryAgent

agent = ReportDiscoveryAgent()
results = agent.search("employee terminations with performance rating", llm_top_k=5)

for r in results:
    print(f"[{r['band']}] {r['report_name']} — Score: {r['score']}%")
    print(f"  Explanation: {r['explanation']}\n")
```

---

## Configuration

Configuration is loaded from the root `.env` file:

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Groq Cloud or OpenAI API key |
| `OPENAI_BASE_URL`| `https://api.groq.com/openai/v1` | LLM API endpoint |
| `MODEL_NAME` | `llama-3.3-70b-versatile` | Model name for candidate re-ranking |
| `BM25_TOP_N` | `30` | Top candidates retrieved by BM25 for LLM scoring |
| `LLM_TOP_K` | `5` | Number of final ranked reports returned |
| `WORKDAY_RAAS_URL` | — | URL to Workday RaaS JSON export |
| `WORKDAY_ISU_USERNAME`| — | Integration System User username |
| `WORKDAY_ISU_PASSWORD`| — | Integration System User password |

---

## Key Features

1. **Semantic Scoring with Completeness Guardrails**: The LLM evaluates metadata richness (Name + Description + Fields) and explains the score rationale for every recommendation.
2. **Payload Size Resilience**: Dynamically detects token limit ceilings (`413 Payload Too Large`) and auto-reduces candidate prompt volume on the fly without crashing.
3. **HR Domain Synonym Expansion**: Maps industry terms across benefits, leave/absence, payroll, contingent workers, pre-hires, and talent management.
4. **Live Workday RaaS Sync**: Synchronize the local JSON catalog directly from a Workday RaaS endpoint on demand.
