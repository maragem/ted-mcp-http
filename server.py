"""
TED (Tenders Electronic Daily) MCP Server
HTTP transport — ready for Railway deployment.

Search API:  https://api.ted.europa.eu/v3  (anonymous)
Downloads:   https://ted.europa.eu/{lang}/notice/{pub_number}/{format}
"""

import os
import json
import httpx
from mcp.server.fastmcp import FastMCP

# ── Server ─────────────────────────────────────────────────────────────────────

port = int(os.environ.get("PORT", 8000))

mcp = FastMCP(
    "TED Procurement Notices",
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",
    port=port,
)

# ── Constants ──────────────────────────────────────────────────────────────────

SEARCH_API_BASE = "https://api.ted.europa.eu/v3"
NOTICE_BASE     = "https://ted.europa.eu"

HEADERS = {
    "User-Agent": "TED-MCP-Server/1.0 (MCP HTTP integration; anonymous reuser)",
    "Accept": "application/json",
}

VALID_FORMATS = {"html", "pdf", "pdfs", "xml"}
VALID_LANGUAGES = {
    "bg", "cs", "da", "de", "el", "en", "es", "et", "fi", "fr",
    "ga", "hr", "hu", "it", "lt", "lv", "mt", "nl", "pl", "pt",
    "ro", "sk", "sl", "sv",
}

# ── Tools ──────────────────────────────────────────────────────────────────────

@mcp.tool()
async def search_notices(
    query: str,
    page: int = 1,
    page_size: int = 10,
) -> dict:
    """
    Search TED (Tenders Electronic Daily) EU procurement notices.

    Supports plain keywords (e.g. 'hospital construction Luxembourg') or
    TED expert-search syntax:
      - CY=[LU]           — filter by country (ISO code)
      - TD=[3]            — notice type (3 = Contract notice)
      - PC=[45*]          — CPV code prefix (45 = construction)
      - PD=[20240101,20241231] — publication date range
      - ND=[00123456-2024] — specific notice number
    Combine with AND / OR, e.g. 'TD=[3] AND CY=[FR] AND PC=[72*]'

    Returns publication numbers, titles, buyers, countries, CPV codes,
    and publication dates.

    Args:
        query: Free-text or expert-syntax search string.
        page: Page number (1-based). Default 1.
        page_size: Results per page, max 100. Default 10.
    """
    page = max(1, page)
    page_size = min(100, max(1, page_size))

    payload = {
        "query": query,
        "page": page,
        "limit": page_size,
        "fields": [
            "publication-number", "title", "buyer-name",
            "country", "cpv", "publication-date",
            "deadline-receipt-request", "notice-type",
        ],
        "scope": "ALL",
        "paginationMode": "PAGE_NUMBER",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{SEARCH_API_BASE}/notices/search",
            headers={**HEADERS, "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    return {
        "total_results": data.get("total", 0),
        "page": page,
        "page_size": page_size,
        "notices": data.get("notices", []),
    }


@mcp.tool()
async def get_notice(
    publication_number: str,
    fields: list[str] | None = None,
) -> dict:
    """
    Retrieve full metadata for a specific TED notice by its publication number.

    Args:
        publication_number: TED publication number, e.g. '123456-2024' or
                            '00123456-2024'. Found in search results.
        fields: Optional list of specific fields to return. Leave empty for
                all available fields.
    """
    payload: dict = {
        "query": f"ND=[{publication_number.strip()}]",
        "page": 1,
        "limit": 1,
        "scope": "ALL",
        "paginationMode": "PAGE_NUMBER",
    }
    if fields:
        payload["fields"] = fields

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{SEARCH_API_BASE}/notices/search",
            headers={**HEADERS, "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    notices = data.get("notices", [])
    if not notices:
        return {
            "error": f"Notice '{publication_number}' not found.",
            "hint": "Check the number format, e.g. '123456-2024'.",
        }
    return {"notice": notices[0]}


@mcp.tool()
async def download_notice(
    publication_number: str,
    format: str = "html",
    language: str = "en",
) -> dict:
    """
    Download or fetch the content of a TED notice.

    For HTML and XML: returns the full text content inline.
    For PDF / signed PDF: returns a direct download URL (binary files
    are not returned inline).

    Args:
        publication_number: TED publication number, e.g. '123456-2024'.
        format: 'html' (rendered HTML), 'pdf' (unsigned PDF),
                'pdfs' (signed PDF), or 'xml' (raw eForms/TED-schema XML).
        language: Two-letter EU language code, e.g. 'en', 'fr', 'de'.
                  Defaults to 'en'. (XML is always returned in English.)
    """
    fmt  = format.lower()
    lang = language.lower()

    if fmt not in VALID_FORMATS:
        return {"error": f"Invalid format '{fmt}'. Choose from: html, pdf, pdfs, xml"}
    if lang not in VALID_LANGUAGES:
        return {"error": f"Invalid language '{lang}'. Use a two-letter EU language code."}

    url = _notice_url(publication_number, fmt, lang)

    if fmt in ("pdf", "pdfs"):
        return {
            "format": fmt,
            "language": lang,
            "publication_number": publication_number,
            "download_url": url,
            "note": "Open or download this URL to get the PDF.",
        }

    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        headers={**HEADERS, "Accept": "text/html,application/xml,*/*"},
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content = resp.text

    MAX = 40_000
    truncated = len(content) > MAX
    return {
        "format": fmt,
        "language": lang,
        "publication_number": publication_number,
        "source_url": url,
        "content": content[:MAX] if truncated else content,
        "truncated": truncated,
        **({"truncation_note": f"Content truncated to {MAX} chars."} if truncated else {}),
    }


@mcp.tool()
def get_notice_url(
    publication_number: str,
    format: str = "html",
    language: str = "en",
) -> dict:
    """
    Return the direct TED URL for a notice — without downloading it.
    Useful for sharing links or opening in a browser.

    Args:
        publication_number: TED publication number, e.g. '123456-2024'.
        format: 'html', 'pdf', 'pdfs', or 'xml'.
        language: Two-letter EU language code. Defaults to 'en'.
    """
    fmt  = format.lower()
    lang = language.lower()

    if fmt not in VALID_FORMATS:
        return {"error": f"Invalid format '{fmt}'. Choose from: html, pdf, pdfs, xml"}
    if lang not in VALID_LANGUAGES:
        return {"error": f"Invalid language '{lang}'."}

    return {
        "publication_number": publication_number,
        "format": fmt,
        "language": lang,
        "url": _notice_url(publication_number, fmt, lang),
    }


@mcp.tool()
async def get_latest_notices(
    count: int = 10,
    country: str | None = None,
    cpv_code: str | None = None,
) -> dict:
    """
    Fetch the most recently published TED procurement notices.
    Useful for monitoring new tenders in real time.

    Args:
        count: Number of notices to return (1–50). Default 10.
        country: ISO 3166-1 alpha-2 country code, e.g. 'FR', 'DE', 'LU'.
                 Leave empty for all countries.
        cpv_code: CPV code prefix to filter by sector, e.g. '45' for
                  construction, '72' for IT services. Leave empty for all.
    """
    count = min(50, max(1, count))

    clauses = []
    if country:
        clauses.append(f"CY=[{country.upper().strip()}]")
    if cpv_code:
        clauses.append(f"PC=[{cpv_code.strip()}*]")

    # Append sort to query using TED expert syntax
    base_query = " AND ".join(clauses) if clauses else "*"
    query = f"{base_query} SORT BY PD DESC"

    payload = {
        "query": query,
        "page": 1,
        "limit": count,
        "fields": [
            "publication-number", "title", "buyer-name", "country",
            "cpv", "publication-date", "deadline-receipt-request", "notice-type",
        ],
        "scope": "ALL",
        "paginationMode": "PAGE_NUMBER",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{SEARCH_API_BASE}/notices/search",
            headers={**HEADERS, "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    return {
        "filters": {"country": country, "cpv_code": cpv_code},
        "count_requested": count,
        "notices": data.get("notices", []),
    }


# ── Helper ─────────────────────────────────────────────────────────────────────

def _notice_url(pub_number: str, fmt: str, lang: str) -> str:
    if fmt == "xml":
        return f"{NOTICE_BASE}/en/notice/{pub_number}/xml"
    return f"{NOTICE_BASE}/{lang}/notice/{pub_number}/{fmt}"


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
