"""
TED (Tenders Electronic Daily) MCP Server
HTTP transport — ready for Railway deployment.

Search API:  https://api.ted.europa.eu/v3  (anonymous)
Downloads:   https://ted.europa.eu/{lang}/notice/{pub_number}/{format}

Payload reference (from official TED workshop Q&A):
{
    "query": "place-of-performance IN (LUX)",
    "fields": ["publication-number", "notice-title", "buyer-name"],
    "page": 1,
    "limit": 10,
    "scope": "ACTIVE",
    "checkQuerySyntax": false,
    "paginationMode": "PAGE_NUMBER"
}
"""

import os
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

SEARCH_URL  = "https://api.ted.europa.eu/v3/notices/search"
NOTICE_BASE = "https://ted.europa.eu"

HEADERS = {
    "User-Agent": "TED-MCP-Server/1.0 (MCP HTTP integration; anonymous reuser)",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# Fields accepted by the v3 API
DEFAULT_FIELDS = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "cpv-code",
    "publication-date",
    "deadline-receipt-request",
    "notice-type",
]

VALID_FORMATS = {"html", "pdf", "pdfs", "xml"}
VALID_LANGUAGES = {
    "bg", "cs", "da", "de", "el", "en", "es", "et", "fi", "fr",
    "ga", "hr", "hu", "it", "lt", "lv", "mt", "nl", "pl", "pt",
    "ro", "sk", "sl", "sv",
}

# ISO alpha-2 -> 3-letter country codes used by TED v3 query syntax
COUNTRY_MAP = {
    "AT": "AUT", "BE": "BEL", "BG": "BGR", "CY": "CYP", "CZ": "CZE",
    "DE": "DEU", "DK": "DNK", "EE": "EST", "ES": "ESP", "FI": "FIN",
    "FR": "FRA", "GR": "GRC", "HR": "HRV", "HU": "HUN", "IE": "IRL",
    "IT": "ITA", "LT": "LTU", "LU": "LUX", "LV": "LVA", "MT": "MLT",
    "NL": "NLD", "PL": "POL", "PT": "PRT", "RO": "ROU", "SE": "SWE",
    "SI": "SVN", "SK": "SVK",
    # non-EU but appear on TED
    "NO": "NOR", "CH": "CHE", "IS": "ISL", "GB": "GBR",
}

# ── Tools ──────────────────────────────────────────────────────────────────────

@mcp.tool()
async def search_notices(
    query: str,
    page: int = 1,
    page_size: int = 10,
    scope: str = "ALL",
) -> dict:
    """
    Search TED (Tenders Electronic Daily) EU procurement notices.

    IMPORTANT — use ONLY the TED v3 query syntax below. Any other syntax
    causes a 400 error.

    CORRECT syntax examples:
      plain keywords:        "defense equipment"
      by country:            "buyer-country IN (LUX)"
      by CPV code (exact):   "cpv-code IN (35000000)"
      by notice type:        "notice-type IN (cn-standard)"
      by date:               "publication-date >= 20240101"
      combined:              "buyer-country IN (FRA) AND cpv-code IN (35000000)"
      wildcard text search:  "defense"

    WRONG — never use this old syntax (causes 400):
      CY=[LU]  PC=[35*]  TD=[3]  ND=[...]  PD=[...]  SORT BY PD

    Common CPV codes for sectors:
      35000000 = defence / security equipment
      45000000 = construction works
      72000000 = IT services
      33000000 = medical equipment
      60000000 = transport services

    Common notice types:
      cn-standard = contract notice (open tender)
      can-standard = contract award notice
      pin-only = prior information notice

    Country codes (3-letter ISO used by TED v3):
      LUX=Luxembourg, FRA=France, DEU=Germany, BEL=Belgium,
      NLD=Netherlands, ESP=Spain, ITA=Italy, POL=Poland

    Args:
        query: Search string using TED v3 syntax shown above.
        page: Page number (1-based). Default 1.
        page_size: Results per page (1-100). Default 10.
        scope: "ACTIVE" (open tenders only) or "ALL" (all notices). Default "ALL".
    """
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    scope = scope.upper() if scope.upper() in ("ACTIVE", "ALL") else "ALL"

    payload = {
        "query": query,
        "fields": DEFAULT_FIELDS,
        "page": page,
        "limit": page_size,
        "scope": scope,
        "checkQuerySyntax": False,
        "paginationMode": "PAGE_NUMBER",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(SEARCH_URL, headers=HEADERS, json=payload)
        if resp.status_code >= 400:
            return {
                "error": f"TED API returned {resp.status_code}",
                "api_message": resp.text,
                "payload_sent": payload,
                "hint": (
                    "Use TED v3 syntax only: "
                    "'buyer-country IN (LUX)', 'cpv-code IN (45000000)', "
                    "'notice-type IN (cn-standard)'. "
                    "DO NOT use old syntax like CY=[LU] or PC=[35*]."
                ),
            }
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
) -> dict:
    """
    Retrieve full metadata for a specific TED notice by its publication number.

    Args:
        publication_number: TED publication number, e.g. '123456-2024' or
                            '00123456-2024'. Found in search results.
    """
    payload = {
        "query": f"publication-number IN ({publication_number.strip()})",
        "fields": DEFAULT_FIELDS,
        "page": 1,
        "limit": 1,
        "scope": "ALL",
        "checkQuerySyntax": False,
        "paginationMode": "PAGE_NUMBER",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(SEARCH_URL, headers=HEADERS, json=payload)
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
    For PDF / signed PDF: returns a direct download URL.

    Args:
        publication_number: TED publication number, e.g. '123456-2024'.
        format: 'html', 'pdf' (unsigned), 'pdfs' (signed), or 'xml'.
        language: Two-letter EU language code, e.g. 'en', 'fr', 'de'. Default 'en'.
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
        headers={"User-Agent": HEADERS["User-Agent"], "Accept": "text/html,application/xml,*/*"},
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
    Return the direct TED URL for a notice without downloading it.
    Useful for sharing links or opening in a browser.

    Args:
        publication_number: TED publication number, e.g. '123456-2024'.
        format: 'html', 'pdf', 'pdfs', or 'xml'.
        language: Two-letter EU language code. Default 'en'.
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
    scope: str = "ALL",
) -> dict:
    """
    Fetch the most recently published TED procurement notices.

    Args:
        count: Number of notices to return (1-50). Default 10.
        country: ISO 3166-1 alpha-2 country code, e.g. 'FR', 'DE', 'LU'.
                 Leave empty for all countries.
        cpv_code: Full CPV code to filter by, e.g. '45000000' for construction
                  or '72000000' for IT services. Leave empty for all sectors.
        scope: "ACTIVE" (open tenders) or "ALL" (all notices). Default "ALL".
    """
    count = min(50, max(1, count))
    scope = scope.upper() if scope.upper() in ("ACTIVE", "ALL") else "ALL"

    clauses = []
    if country:
        iso2 = country.upper().strip()
        iso3 = COUNTRY_MAP.get(iso2, iso2)   # map to 3-letter code if known
        clauses.append(f"buyer-country IN ({iso3})")
    if cpv_code:
        clauses.append(f"cpv-code IN ({cpv_code.strip()})")

    query = " AND ".join(clauses) if clauses else "*"

    payload = {
        "query": query,
        "fields": DEFAULT_FIELDS,
        "page": 1,
        "limit": count,
        "scope": scope,
        "checkQuerySyntax": False,
        "paginationMode": "PAGE_NUMBER",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(SEARCH_URL, headers=HEADERS, json=payload)
        resp.raise_for_status()
        data = resp.json()

    return {
        "filters": {"country": country, "cpv_code": cpv_code, "scope": scope},
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
