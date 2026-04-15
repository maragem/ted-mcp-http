# TED MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that gives LLMs tools to search, retrieve, and download **EU public procurement notices** from [TED — Tenders Electronic Daily](https://ted.europa.eu).

Runs over **Streamable HTTP transport** — ready to deploy anywhere, including Railway.

> All tools use the anonymous TED Search API. No API key required.

---

## Tools

| Tool | Description |
|---|---|
| `search_notices` | Full-text + filter search across all TED notices. Supports TED expert-search syntax. |
| `get_notice` | Retrieve full metadata for a specific notice by publication number. |
| `download_notice` | Fetch notice content as HTML or XML inline, or get a PDF download URL. |
| `get_notice_url` | Build a direct TED URL for a notice without downloading it. |
| `get_latest_notices` | Get the most recently published notices, filterable by country or CPV code. |

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

## Deploy to Railway

Full step-by-step instructions are in **[TUTORIAL.html](./TUTORIAL.html)** — open it in a browser.

**Short version:**

1. Push this folder to a GitHub repository.
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo.
3. Select your repo. Railway detects the `Dockerfile` automatically and deploys.
4. In your service settings → Networking → click **Generate Domain**.
5. Your server is live at `https://your-domain.up.railway.app/mcp`.

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

Restart Claude Desktop. The TED tools will appear in the tools panel.

---

## Example Prompts

Once connected to an LLM, you can ask things like:

- *"Find IT services tenders in Luxembourg published this year"*
- *"Show me the 5 most recent construction tenders from France"*
- *"Get the full details of notice 00123456-2024"*
- *"Download notice 00654321-2024 as HTML in French"*
- *"Give me the PDF link for notice 00123456-2024"*
- *"Find hospital construction tenders in Belgium and summarise the top result"*

### TED Expert Search Syntax

The `search_notices` tool supports TED's expert-search syntax for precise filtering:

| Syntax | Meaning |
|---|---|
| `CY=[LU]` | Filter by country (ISO code) |
| `TD=[3]` | Notice type (3 = Contract notice) |
| `PC=[45*]` | CPV code prefix (45 = construction works) |
| `PC=[72*]` | CPV code prefix (72 = IT services) |
| `PD=[20240101,20241231]` | Publication date range |
| `ND=[00123456-2024]` | Specific notice by publication number |

Combine with `AND` / `OR`: `TD=[3] AND CY=[FR] AND PC=[72*]`

---

## Project Structure

```
ted-mcp-http/
├── server.py          # MCP server — FastMCP + Streamable HTTP transport
├── requirements.txt   # Python dependencies (mcp, httpx, uvicorn)
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

---

## License

MIT — free to use, modify, and distribute.
