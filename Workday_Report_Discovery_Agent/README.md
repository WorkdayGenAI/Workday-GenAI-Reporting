# Workday Report Discovery Agent
## BM25 + LLM Semantic Search for Legacy Reports

A two-stage report discovery agent that helps users find the most relevant legacy reports from a catalog of ~11,000+ Workday reports using natural language queries.

---

## Architecture

```
                          ONLINE QUERY PATH
┌──────────────┐    ┌──────────────────┐    ┌────────────────┐
│  User Query  │───>│ Query Preprocess │───>│  BM25 Search   │
│  (natural    │    │ • Tokenize       │    │ • Full catalog │
│   language)  │    │ • Stem & Synonyms│    │ • Top-50 cands │
└──────────────┘    └──────────────────┘    └───────┬────────┘
                                                    │
                                                    ▼
                    ┌──────────────────┐    ┌────────────────┐
                    │  Final Response  │<───│  LLM Scorer    │
                    │ • Ranked reports │    │ • Groq LLaMA   │
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
Report_Ranking_Agent/
├── README.md               ← You are here
├── requirements.txt        ← Python dependencies
├── .env.example            ← Environment variable template
├── config.py               ← Configuration and thresholds
├── api_server.py           ← FastAPI backend server
├── agent.py                ← Main orchestrator (the Agent)
├── bm25_engine.py          ← Keyword search engine (from scratch)
├── llm_scorer.py           ← LLM candidate re-ranker (Groq API)
├── report_catalog.py       ← Data loading & validation
├── stemmer.py              ← Custom suffix-stripping & tokenization
├── synonyms.py             ← Workday & HR synonym dictionaries
├── sync_catalog.py         ← Workday RaaS syncing logic
├── cli.py                  ← Command-line interface
├── evaluation.py           ← Automated accuracy evaluations
├── data/                   ← Stored JSON catalogs
├── prompts/                ← LLM instructions (scoring_prompt.txt)
└── static/                 ← Frontend Vanilla HTML/JS UI
    ├── index.html
    ├── styles.css
    └── app.js
```

---

## Tech Stack

- **Frontend**: Vanilla HTML5, CSS3 (Custom Dark Mode UI), JavaScript (ES6+)
- **Backend**: Python 3.10+, FastAPI, Uvicorn
- **Search Engine**: Custom Python BM25 Implementation
- **LLM Provider**: Groq API (Meta LLaMA models)

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
```
Edit `.env` and add your:
- Groq/OpenAI API key
- Workday RaaS URL and ISU Credentials

### 3. Run the Web Application
```bash
python api_server.py
```
Open your browser to `http://localhost:8000`.

### 4. Or use the CLI
```bash
python cli.py
```

### 5. Or use programmatically
```python
from agent import ReportDiscoveryAgent

agent = ReportDiscoveryAgent()
results = agent.search("I want a report that gives pre-hire details")
for r in results:
    print(f"[{r['band']}] {r['report_name']} — {r['score']}/100")
    print(f"  Why: {r['explanation']}")
```

---

## Configuration

The `.env` file controls core behavior:

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Your Groq API key |
| `OPENAI_BASE_URL`| `https://api.groq.com/openai/v1` | Groq API URL |
| `MODEL_NAME` | `meta-llama/llama-4-scout-17b-16e-instruct` | LLM for scoring |
| `BM25_TOP_N` | `30` | Fallback candidates passed to LLM |
| `WORKDAY_RAAS_URL` | — | URL to JSON Workday Report export |
| `WORKDAY_ISU_USERNAME`| — | Integration System User name |

*Note: You can tweak scoring boosts in `config.py`.*

---

## Key Features & Fixes Included

1. **Semantic Scoring with Strict Guardrails**: The LLM evaluates missing fields and descriptions and explicitly penalizes empty reports (capping at score 40) preventing false-positive rankings.
2. **HR Synonym Engine**: Built-in synonym handling for leave/absence, payroll, pre-hire, compliance, diversity, benefits, and contingent worker terminology.
3. **Hyphenated Tokenization**: Smart handling of HR terms like "Pre-Hire" vs "Pre Hire" so they map to the same token.
4. **Live Workday Sync**: Pull down the latest catalog from the Workday RaaS API instantly via the web UI.

---

## Deployment on Vercel

This project includes a [vercel.json](file:///c:/Users/rishabh.saklani/OneDrive%20-%20Accenture/Desktop/Report_Ranking_Agent/Report_Ranking_Agent/vercel.json) configuration file that handles:
- Routing `/api/*` endpoints to the FastAPI application.
- Natively serving static files under `/static` directly via Vercel's global CDN for maximum speed.

### Steps to Deploy:
1. Push the repository to GitHub.
2. In Vercel, select **Import Project** and choose this repository.
3. Keep the **Build and Output Settings** at their **defaults** (do not override them, as `vercel.json` configures everything automatically).
4. Add the required **Environment Variables** in the Vercel dashboard:
   - `OPENAI_API_KEY`: `<Your Groq/OpenAI API Key>`
   - `OPENAI_BASE_URL`: `https://api.groq.com/openai/v1`
   - `MODEL_NAME`: `meta-llama/llama-4-scout-17b-16e-instruct`
   - `WORKDAY_RAAS_URL`: `<Your Workday RaaS URL>`
   - `WORKDAY_ISU_USERNAME`: `<ISU Username>`
   - `WORKDAY_ISU_PASSWORD`: `<ISU Password>`
5. Click **Deploy**.

---

## License

Internal use only. Not for redistribution.
