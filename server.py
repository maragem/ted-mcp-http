"""
TED (Tenders Electronic Daily) MCP Server
HTTP transport — ready for Railway deployment.

Search API:  https://api.ted.europa.eu/v3  (anonymous)
Downloads:   https://ted.europa.eu/{lang}/notice/{pub_number}/{format}
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

# Verified valid field names (from TED v3 API error response)
DEFAULT_FIELDS = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "classification-cpv",   # NOTE: NOT "cpv-code"
    "publication-date",
    "deadline-receipt-request",
    "notice-type",
    "procedure-type",
    "dispatch-date",
    "links",
]

VALID_FORMATS = {"html", "pdf", "pdfs", "xml"}
VALID_LANGUAGES = {
    "bg", "cs", "da", "de", "el", "en", "es", "et", "fi", "fr",
    "ga", "hr", "hu", "it", "lt", "lv", "mt", "nl", "pl", "pt",
    "ro", "sk", "sl", "sv",
}

# ISO alpha-2 -> 3-letter country codes used by TED v3
COUNTRY_MAP = {
    "AT": "AUT", "BE": "BEL", "BG": "BGR", "CY": "CYP", "CZ": "CZE",
    "DE": "DEU", "DK": "DNK", "EE": "EST", "ES": "ESP", "FI": "FIN",
    "FR": "FRA", "GR": "GRC", "HR": "HRV", "HU": "HUN", "IE": "IRL",
    "IT": "ITA", "LT": "LTU", "LU": "LUX", "LV": "LVA", "MT": "MLT",
    "NL": "NLD", "PL": "POL", "PT": "PRT", "RO": "ROU", "SE": "SWE",
    "SI": "SVN", "SK": "SVK",
    "NO": "NOR", "CH": "CHE", "IS": "ISL", "GB": "GBR",
}

# ── Query builder ──────────────────────────────────────────────────────────────

def _build_query(
    keywords: str | None,
    country: str | None,
    cpv_code: str | None,
    notice_type: str | None,
    buyer_name: str | None,
) -> str:
    """Build a valid TED v3 query from structured parameters."""
    clauses = []

    if keywords:
        # Free-text search — wrap multi-word in quotes
        words = keywords.strip()
        clauses.append(words if " " not in words else f'"{words}"')

    if country:
        iso2 = country.upper().strip()
        iso3 = COUNTRY_MAP.get(iso2, iso2)
        clauses.append(f"buyer-country IN ({iso3})")

    if cpv_code:
        clauses.append(f"classification-cpv IN ({cpv_code.strip()})")

    if notice_type:
        clauses.append(f"notice-type IN ({notice_type.strip()})")

    if buyer_name:
        clauses.append(f"buyer-name IN ({buyer_name.strip()})")

    return " AND ".join(clauses) if clauses else "*"


async def _post_search(payload: dict) -> dict:
    """Execute a search and return structured result or error dict."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(SEARCH_URL, headers=HEADERS, json=payload)
        if resp.status_code >= 400:
            return {
                "error": f"TED API returned {resp.status_code}",
                "api_message": resp.text[:500],   # truncate huge error messages
                "payload_sent": payload,
            }
        data = resp.json()
    return {
        "total_results": data.get("total", 0),
        "notices": data.get("notices", []),
    }


# ── Tools ──────────────────────────────────────────────────────────────────────

@mcp.tool()
async def search_notices(
    keywords: str | None = None,
    country: str | None = None,
    cpv_code: str | None = None,
    notice_type: str | None = None,
    page: int = 1,
    page_size: int = 10,
    scope: str = "ALL",
) -> dict:
    """
    Search TED (Tenders Electronic Daily) EU procurement notices.

    Pass structured parameters — do NOT write raw query strings.
    The server builds the correct TED v3 query automatically.

    Args:
        keywords: Free-text keywords to search for, e.g. "drone UAV surveillance"
                  or "hospital construction". Searches titles and descriptions.
        country:  Buyer country as 2-letter ISO code: "LU", "FR", "DE", "GR", "BE" etc.
        cpv_code: Full 8-digit CPV code for procurement category, e.g.:
                    "35000000" = defence/security equipment
                    "35610000" = military aircraft
                    "35613000" = unmanned aerial vehicles
                    "45000000" = construction works
                    "72000000" = IT services
                    "33000000" = medical equipment
        notice_type: Type of notice:
                    "cn-standard"  = contract notice (open tender)
                    "can-standard" = contract award notice
                    "pin-only"     = prior information notice
        page:       Page number (1-based). Default 1.
        page_size:  Results per page (1-100). Default 10.
        scope:      "ACTIVE" = open tenders only, "ALL" = all notices. Default "ALL".
    """
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    scope = "ACTIVE" if scope.upper() == "ACTIVE" else "ALL"

    query = _build_query(keywords, country, cpv_code, notice_type, None)

    payload = {
        "query": query,
        "fields": DEFAULT_FIELDS,
        "page": page,
        "limit": page_size,
        "scope": scope,
        "checkQuerySyntax": False,
        "paginationMode": "PAGE_NUMBER",
    }

    result = await _post_search(payload)
    result["page"] = page
    result["page_size"] = page_size
    return result


@mcp.tool()
async def get_notice(
    publication_number: str,
) -> dict:
    """
    Retrieve full metadata for a specific TED notice by its publication number.

    Args:
        publication_number: TED publication number, e.g. "123456-2024" or
                            "00123456-2024". Found in search results.
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

    result = await _post_search(payload)
    if "error" in result:
        return result

    notices = result.get("notices", [])
    if not notices:
        return {
            "error": f"Notice '{publication_number}' not found.",
            "hint": "Check the format, e.g. '123456-2024'.",
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

    For HTML and XML: returns the full text inline.
    For PDF / signed PDF: returns a direct download URL.

    Args:
        publication_number: TED publication number, e.g. "123456-2024".
        format: "html", "pdf" (unsigned), "pdfs" (signed), or "xml".
        language: Two-letter EU language code, e.g. "en", "fr", "de". Default "en".
    """
    fmt  = format.lower()
    lang = language.lower()

    if fmt not in VALID_FORMATS:
        return {"error": f"Invalid format '{fmt}'. Choose: html, pdf, pdfs, xml"}
    if lang not in VALID_LANGUAGES:
        return {"error": f"Invalid language '{lang}'."}

    url = _notice_url(publication_number, fmt, lang)

    if fmt in ("pdf", "pdfs"):
        return {
            "format": fmt, "language": lang,
            "publication_number": publication_number,
            "download_url": url,
            "note": "Open this URL to download the PDF.",
        }

    async with httpx.AsyncClient(
        timeout=30, follow_redirects=True,
        headers={"User-Agent": HEADERS["User-Agent"], "Accept": "text/html,application/xml,*/*"},
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content = resp.text

    MAX = 40_000
    truncated = len(content) > MAX
    return {
        "format": fmt, "language": lang,
        "publication_number": publication_number,
        "source_url": url,
        "content": content[:MAX] if truncated else content,
        "truncated": truncated,
        **({"truncation_note": f"Truncated to {MAX} chars."} if truncated else {}),
    }


@mcp.tool()
def get_notice_url(
    publication_number: str,
    format: str = "html",
    language: str = "en",
) -> dict:
    """
    Return the direct TED URL for a notice without downloading it.

    Args:
        publication_number: TED publication number, e.g. "123456-2024".
        format: "html", "pdf", "pdfs", or "xml".
        language: Two-letter EU language code. Default "en".
    """
    fmt  = format.lower()
    lang = language.lower()
    if fmt not in VALID_FORMATS:
        return {"error": f"Invalid format '{fmt}'."}
    if lang not in VALID_LANGUAGES:
        return {"error": f"Invalid language '{lang}'."}
    return {
        "publication_number": publication_number,
        "format": fmt, "language": lang,
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
        count:    Number of notices to return (1-50). Default 10.
        country:  Buyer country as 2-letter ISO code, e.g. "FR", "DE", "LU".
        cpv_code: Full 8-digit CPV code, e.g. "35000000" for defence equipment.
        scope:    "ACTIVE" (open tenders only) or "ALL". Default "ALL".
    """
    count = min(50, max(1, count))
    scope = "ACTIVE" if scope.upper() == "ACTIVE" else "ALL"

    query = _build_query(None, country, cpv_code, None, None)

    payload = {
        "query": query,
        "fields": DEFAULT_FIELDS,
        "page": 1,
        "limit": count,
        "scope": scope,
        "checkQuerySyntax": False,
        "paginationMode": "PAGE_NUMBER",
    }

    result = await _post_search(payload)
    result["filters"] = {"country": country, "cpv_code": cpv_code, "scope": scope}
    return result


# ── Helper ─────────────────────────────────────────────────────────────────────

def _notice_url(pub_number: str, fmt: str, lang: str) -> str:
    if fmt == "xml":
        return f"{NOTICE_BASE}/en/notice/{pub_number}/xml"
    return f"{NOTICE_BASE}/{lang}/notice/{pub_number}/{fmt}"


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
