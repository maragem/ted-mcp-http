# TED MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that gives LLMs tools to search, retrieve, read, and analyse **EU public procurement notices** from [TED — Tenders Electronic Daily](https://ted.europa.eu).

Runs over **Streamable HTTP transport** — ready to deploy anywhere, including Railway.

> **No API keys required.** All 7 tools work anonymously using the public TED v3 API.

---

## Tools

| Tool | Description |
|---|---|
| `lookup_cpv_codes` | Search the EU CPV vocabulary by keyword to find the correct 8-digit procurement category code |
| `search_notices` | Search TED notices using structured parameters (keywords, country, CPV code, notice type) |
| `get_notice` | Retrieve full metadata for a specific notice by publication number |
| `get_latest_notices` | Get the most recently published notices, filterable by country and CPV code |
| `download_notice` | Fetch notice content as HTML or XML inline, or get a direct PDF download URL |
| `get_notice_url` | Return the direct TED URL for a notice without downloading it |
| `read_notice_pdf` | Download a notice PDF and extract its full text as Markdown for LLM analysis |
| `summarise_notice` | Fetch metadata + full PDF text in one call so the LLM can produce a structured procurement analysis |

---

## Recommended Workflow

The tools are designed to work together in a natural sequence:

1. **`lookup_cpv_codes`** — find the right CPV code for a sector (e.g. `"drone"` → `35613000`)
2. **`search_notices`** — search using the CPV code, country, and keywords
3. **`summarise_notice`** — fetch the full notice content so the LLM can analyse it
4. **`read_notice_pdf`** or **`download_notice`** — go deeper into a specific document

---

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run locally

```bash
python server.py
```

The MCP endpoint is available at `http://localhost:8000/mcp`.

### 3. Test with the MCP Inspector

```bash
npx @modelcontextprotocol/inspector http://localhost:8000/mcp
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `PORT` | Set by Railway automatically | Port the server listens on |

No API keys required. All tools work anonymously.

---

## Deploy to Railway

Full step-by-step instructions are in **[TUTORIAL.html](./TUTORIAL.html)** — open it in a browser.

**Short version:**

1. Push this folder to a GitHub repository.
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo.
3. Select your repo. Railway detects the `Dockerfile` automatically and deploys.
4. In your service settings → Networking → click **Generate Domain**.
5. Your server is live at `https://your-domain.up.railway.app/mcp`.

> **Note:** The build takes 2–4 minutes because PyMuPDF includes native binaries. This is normal.

---

## Connect to Claude Desktop

Add this to your `claude_desktop_config.json`:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ted": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://YOUR-DOMAIN.up.railway.app/mcp"
      ]
    }
  }
}
```

Restart Claude Desktop. The TED tools will appear in the tools panel (the hammer icon).

---

## Example Prompts

### CPV lookup
- *"What CPV code should I use for drone surveillance tenders?"*
- *"Find the CPV code for hospital construction"*
- *"What codes cover IT consulting services?"*

### Searching notices
- *"Find defence equipment tenders in Greece"*
- *"Show me the 5 most recent IT services tenders from Luxembourg"*
- *"Any open construction tenders in Belgium?"*

### Reading and analysing
- *"Summarise notice 00123456-2024"*
- *"What are the eligibility criteria in notice 00654321-2024?"*
- *"Read the PDF of notice 00123456-2024 in French and explain the award criteria"*

### Combined workflows
- *"Find drone tenders in Greece, then summarise the most recent one"*
- *"Search for IT consulting tenders in Luxembourg, read the top result, and tell me if a small company could apply"*

---

## Tool Reference

### `lookup_cpv_codes`

Searches the built-in EU CPV (Common Procurement Vocabulary) database by keyword.
Always use this before searching if you are unsure of the correct CPV code.

```
keyword="drone"        → 35613000 – Unmanned aerial vehicles
keyword="hospital"     → 45215000 – Construction for health services
keyword="IT services"  → 72000000 – IT services: consulting, software, support
keyword="surveillance" → 35120000, 79720000 – Security systems / Investigation
keyword="training"     → 80500000 – Training services
```

### `search_notices`

Structured search — pass parameters directly, no raw query string needed.

| Parameter | Type | Description |
|---|---|---|
| `keywords` | string | Free-text search, e.g. `"drone UAV surveillance"` |
| `country` | string | 2-letter ISO code: `"LU"`, `"FR"`, `"GR"`, `"BE"` |
| `cpv_code` | string | 8-digit CPV code, e.g. `"35613000"` |
| `notice_type` | string | `"cn-standard"` (contract notice), `"can-standard"` (award), `"pin-only"` (prior info) |
| `page` | int | Page number, default 1 |
| `page_size` | int | Results per page, max 100, default 10 |
| `scope` | string | `"ACTIVE"` (open tenders only) or `"ALL"`, default `"ALL"` |

### `summarise_notice`

Fetches metadata + full PDF text in one call and instructs the LLM to produce a structured analysis covering: overview, contract value, key dates, scope, eligibility, award criteria, bidder action points, and notable clauses.

Optional `focus` parameter narrows the analysis, e.g. `focus="eligibility criteria"`.

### `read_notice_pdf`

Downloads the PDF and returns the full extracted text as clean Markdown. Supports up to 200 pages. Use when you need raw document content for detailed analysis beyond what `summarise_notice` provides.

---

## Project Structure

```
ted-mcp-http/
├── server.py          # MCP server — all 7 tools
├── requirements.txt   # Python dependencies
├── Dockerfile         # Container build for Railway
├── railway.json       # Railway config-as-code
├── TUTORIAL.html      # Step-by-step Railway deployment guide
├── README.md          # This file
└── .gitignore
```

---

## API Details

| Endpoint | Base URL |
|---|---|
| Search | `https://api.ted.europa.eu/v3/notices/search` |
| Notice (HTML/PDF) | `https://ted.europa.eu/{lang}/notice/{pub_number}/{format}` |
| Notice (XML) | `https://ted.europa.eu/en/notice/{pub_number}/xml` |

### TED v3 Query Syntax (built by the server automatically)

| Field | Example |
|---|---|
| Country | `buyer-country IN (LUX)` |
| CPV code | `classification-cpv IN (35613000)` |
| Notice type | `notice-type IN (cn-standard)` |
| Publication date | `publication-date >= 20240101` |
| Combined | `buyer-country IN (FRA) AND classification-cpv IN (72000000)` |

Country codes use 3-letter ISO format (`LUX`, `FRA`, `DEU`, `GRC`). The server converts 2-letter codes automatically.

### Rate Limits (TED fair usage policy)

| Operation | Limit |
|---|---|
| Notice visualisation/download | 600 per 6 minutes per IP |
| HTTP requests | 700 per minute |

---

## Requirements

- Python 3.10+
- `mcp[cli]` >= 1.0.0
- `httpx` >= 0.27.0
- `uvicorn` >= 0.30.0
- `pymupdf` >= 1.24.0
- `pymupdf4llm` >= 0.0.17

---

## License

MIT — free to use, modify, and distribute.
