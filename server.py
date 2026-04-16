"""
TED (Tenders Electronic Daily) MCP Server
HTTP transport — ready for Railway deployment.

Search API:  https://api.ted.europa.eu/v3  (anonymous)
Downloads:   https://ted.europa.eu/{lang}/notice/{pub_number}/{format}
"""

import io
import os
import re
import httpx
import pymupdf4llm
import pymupdf
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

# ── CPV code lookup table (EU 2008 version — official, unchanged since) ─────
# Abbreviated to the most-searched divisions and groups (~300 entries).
# Full 8-digit precision codes for common sectors; division-level for the rest.
CPV_DATA = {
    # Division 03 — Agriculture, farming, fishing, forestry
    "03000000": "Agricultural, farming, fishing, forestry and related products",
    "03100000": "Agricultural and horticultural products",
    "03200000": "Cereals, potatoes, vegetables, fruits and nuts",
    "03400000": "Forestry and logging products",
    "03500000": "Fishing and aquaculture products",
    # Division 09 — Petroleum, fuel, energy
    "09000000": "Petroleum products, fuel, electricity and other energy sources",
    "09100000": "Fuels",
    "09200000": "Petroleum, coal and oil products",
    "09300000": "Electricity, heating, solar and nuclear energy",
    # Division 14 — Mining
    "14000000": "Mining, basic metals and related products",
    # Division 15 — Food and beverages
    "15000000": "Food, beverages, tobacco and related products",
    "15100000": "Animal products, meat and meat products",
    "15200000": "Fish and other fishery products",
    "15500000": "Dairy products",
    "15800000": "Miscellaneous food products",
    # Division 18 — Clothing and footwear
    "18000000": "Clothing, footwear, luggage articles and accessories",
    "18100000": "Occupational clothing, workwear and safety garments",
    "18400000": "Specialist clothing and accessories",
    # Division 22 — Printed matter and publications
    "22000000": "Printed matter and related products",
    "22100000": "Printed books, brochures and leaflets",
    "22400000": "Stamps, cheque forms, banknotes, stock certificates",
    # Division 24 — Chemicals
    "24000000": "Chemical products",
    "24100000": "Gases",
    "24400000": "Fertilisers and pesticides",
    "24900000": "Fine chemicals and miscellaneous chemicals",
    # Division 30 — IT office equipment
    "30000000": "Office and computing machinery, equipment and supplies",
    "30100000": "Office machinery, equipment and supplies (except computers)",
    "30200000": "Computer equipment and supplies",
    "30210000": "Data-processing machines (hardware)",
    "30213000": "Personal computers",
    "30230000": "Computer-related equipment",
    "30232000": "Peripheral equipment",
    "30236000": "Miscellaneous computer equipment",
    # Division 31 — Electrical equipment
    "31000000": "Electrical machinery, apparatus, equipment and consumables",
    "31100000": "Electric motors, generators and transformers",
    "31200000": "Electricity distribution and control apparatus",
    "31500000": "Lighting equipment and electric lamps",
    "31600000": "Electrical equipment and apparatus",
    # Division 32 — Radio, TV, communications equipment
    "32000000": "Radio, television, communication, telecommunication equipment",
    "32200000": "Television transmitting apparatus",
    "32300000": "Television sets and radio receivers",
    "32400000": "Networks",
    "32500000": "Telecommunications equipment and supplies",
    "32520000": "Telecommunications cable and equipment",
    "32550000": "Telephone equipment",
    "32580000": "Data communications equipment",
    # Division 33 — Medical equipment
    "33000000": "Medical equipments, pharmaceuticals and personal care products",
    "33100000": "Medical equipment",
    "33110000": "Imaging equipment for medical, dental and veterinary use",
    "33120000": "Clinical analysers and support equipment",
    "33130000": "Dental and subspecialty equipment",
    "33140000": "Medical consumables",
    "33150000": "Radiotherapy, mechanotherapy, electrotherapy equipment",
    "33160000": "Operating techniques",
    "33170000": "Anaesthesia and resuscitation equipment",
    "33180000": "Functional support",
    "33190000": "Miscellaneous medical devices and products",
    "33600000": "Pharmaceutical products",
    # Division 34 — Transport equipment
    "34000000": "Transport equipment and auxiliary products to transportation",
    "34100000": "Motor vehicles",
    "34110000": "Passenger cars",
    "34120000": "Motor vehicles for 8 or more persons",
    "34130000": "Motor vehicles for transport of goods",
    "34140000": "Heavy-duty motor vehicles",
    "34200000": "Vehicle bodies, trailers or semi-trailers",
    "34300000": "Parts and accessories for vehicles",
    "34400000": "Motorcycles, bicycles and sidecars",
    "34500000": "Ships and boats",
    "34600000": "Railway and tramway locomotives and rolling stock",
    "34700000": "Aircraft and spacecraft",
    "34710000": "Helicopters, aeroplanes, spacecraft and other powered aircraft",
    "34711000": "Heavier-than-air aircraft",
    "34711200": "Fixed-wing aircraft",
    "34730000": "Parts for aircraft, spacecraft and helicopters",
    "34900000": "Miscellaneous transport equipment and spare parts",
    # Division 35 — Defence and security equipment
    "35000000": "Security, fire-fighting, police and defence equipment",
    "35100000": "Emergency and security equipment",
    "35110000": "Firefighting, rescue and safety equipment",
    "35120000": "Surveillance and security systems and devices",
    "35200000": "Police equipment",
    "35210000": "Police vehicles",
    "35300000": "Weapons, ammunition and associated parts",
    "35310000": "Miscellaneous weapons",
    "35320000": "Firearms",
    "35400000": "Military vehicles and associated parts",
    "35410000": "Military armoured vehicles",
    "35420000": "Parts for military vehicles",
    "35500000": "Warships and associated parts",
    "35600000": "Small arms and light weapons and related equipment",
    "35610000": "Military aircraft",
    "35612000": "Combat aircraft",
    "35613000": "Unmanned aerial vehicles (UAVs / drones)",
    "35620000": "Military vessels",
    "35700000": "Military electronic systems",
    "35710000": "Command, communications, control, computer and intelligence systems",
    "35720000": "Intelligence, surveillance, target acquisition and reconnaissance",
    "35730000": "Electronic warfare systems",
    "35800000": "Personnel and support equipment",
    "35810000": "Specialised individual equipment",
    "35820000": "Support equipment",
    # Division 37 — Musical instruments, sports, toys
    "37000000": "Musical instruments, sport goods, games, toys",
    # Division 38 — Laboratory equipment
    "38000000": "Laboratory, optical and precision equipment",
    "38100000": "Navigational and meteorological instruments",
    "38300000": "Measuring instruments",
    "38400000": "Industrial process control equipment",
    "38500000": "Checking and testing apparatus",
    "38600000": "Optical instruments",
    "38900000": "Miscellaneous evaluation and testing instruments",
    # Division 39 — Furniture
    "39000000": "Furniture, household appliances, cleaning products",
    "39100000": "Furniture",
    "39700000": "Domestic appliances",
    "39800000": "Cleaning and polishing products",
    # Division 41 — Water
    "41000000": "Collected and purified water",
    # Division 42 — Industrial machinery
    "42000000": "Industrial machinery",
    "42100000": "Machinery for production and use of mechanical power",
    "42600000": "Machine tools",
    "42900000": "Miscellaneous general and special-purpose machinery",
    # Division 43 — Mining and construction machinery
    "43000000": "Machinery for mining, quarrying, construction",
    "43200000": "Earthmoving and excavating machinery",
    "43300000": "Construction machinery",
    # Division 44 — Construction materials
    "44000000": "Construction structures and materials; auxiliary construction products",
    "44100000": "Construction materials and associated items",
    "44400000": "Miscellaneous fabricated products and related items",
    # Division 45 — Construction works
    "45000000": "Construction work",
    "45100000": "Site preparation work",
    "45200000": "Works for complete or part construction and civil engineering",
    "45210000": "Building construction work",
    "45211000": "Construction work for multi-dwelling buildings and individual houses",
    "45213000": "Construction work for commercial buildings, warehouses, industrial",
    "45215000": "Construction work for buildings relating to health and social services",
    "45216000": "Construction work for military or police buildings",
    "45220000": "Engineering works and construction works",
    "45230000": "Construction of pipelines, communication and power lines",
    "45231000": "Construction work for pipelines, long-distance",
    "45232000": "Ancillary works for pipelines and cables",
    "45233000": "Construction, foundation and surface works for highways",
    "45234000": "Railway construction works",
    "45240000": "Construction of water projects",
    "45250000": "Construction works for plants, mining and manufacturing",
    "45260000": "Roof works and other special trade construction works",
    "45300000": "Building installation work",
    "45310000": "Electrical installation work",
    "45320000": "Insulation work",
    "45330000": "Plumbing and sanitary engineering works",
    "45340000": "Fencing, railing and safety equipment installation",
    "45350000": "Mechanical installations",
    "45400000": "Building completion work",
    "45420000": "Joinery and carpentry installation work",
    "45430000": "Floor and wall covering work",
    "45440000": "Painting and glazing work",
    "45450000": "Other building completion work",
    "45500000": "Hiring of construction and civil engineering machinery and equipment",
    # Division 48 — Software
    "48000000": "Software package and information systems",
    "48100000": "Industry specific software package",
    "48200000": "Networking, internet and intranet software",
    "48300000": "Document creation, drawing, imaging, scheduling and productivity software",
    "48400000": "Transaction and business software packages",
    "48500000": "Communication and multimedia software package",
    "48600000": "Database and operating software package",
    "48700000": "Software package utilities",
    "48800000": "Information systems and servers",
    "48900000": "Miscellaneous software packages and computer systems",
    # Division 50 — Repair and maintenance
    "50000000": "Repair and maintenance services",
    "50100000": "Repair and maintenance services of vehicles",
    "50300000": "Repair, maintenance and associated services related to PCs",
    "50700000": "Repair and maintenance services of building installations",
    # Division 51 — Installation services
    "51000000": "Installation services (except software)",
    # Division 55 — Hotel and restaurant services
    "55000000": "Hotel, restaurant and retail trade services",
    "55100000": "Hotel services",
    "55300000": "Restaurant and food-serving services",
    "55500000": "Canteen and catering services",
    # Division 60 — Transport services
    "60000000": "Transport services (excl. waste transport)",
    "60100000": "Road transport services",
    "60120000": "Taxi services",
    "60130000": "Special-purpose road passenger-transport services",
    "60140000": "Non-scheduled passenger transport",
    "60160000": "Postal collection services by road",
    "60170000": "Hiring of vehicles for freight transport with driver",
    "60180000": "Hiring of goods-transport vehicles with driver",
    "60200000": "Rail transport services",
    "60400000": "Air transport services",
    "60410000": "Scheduled air transport services",
    "60420000": "Non-scheduled air transport services",
    "60440000": "Aerial and related services",
    "60441000": "Aerial photography services",
    "60442000": "Aerial surveillance services",
    "60443000": "Aerial firefighting services",
    "60500000": "Space transport services",
    "60600000": "Water transport services",
    # Division 63 — Cargo handling and storage
    "63000000": "Supporting and auxiliary transport services; travel agencies",
    "63100000": "Cargo handling and storage services",
    "63500000": "Travel agency, tour operator and tourist assistance services",
    # Division 64 — Postal and courier services
    "64000000": "Postal and telecommunications services",
    "64100000": "Post and courier services",
    "64200000": "Telecommunications services",
    "64210000": "Telephone and data transmission services",
    "64220000": "Telecommunications services except telephone and data transmission",
    # Division 65 — Public utilities
    "65000000": "Public utilities",
    "65100000": "Water distribution and related services",
    "65200000": "Gas distribution and related services",
    "65300000": "Electricity distribution and related services",
    # Division 66 — Financial services
    "66000000": "Financial and insurance services",
    "66100000": "Banking and investment services",
    "66500000": "Insurance and pension services",
    # Division 70 — Real estate
    "70000000": "Real estate services",
    "70100000": "Real estate services with own property",
    "70300000": "Real estate agency services on a fee or contract basis",
    # Division 71 — Architectural and engineering services
    "71000000": "Architectural, construction, engineering and inspection services",
    "71200000": "Architectural and related services",
    "71300000": "Engineering services",
    "71310000": "Consultative engineering and construction services",
    "71312000": "Structural engineering consultancy services",
    "71314000": "Energy and related services",
    "71315000": "Building services",
    "71317000": "Hazard protection and control consultancy services",
    "71320000": "Engineering design services",
    "71322000": "Engineering design services for construction works",
    "71324000": "Quantity surveying services",
    "71325000": "Foundation-design services",
    "71330000": "Miscellaneous engineering services",
    "71335000": "Engineering studies",
    "71340000": "Integrated engineering services",
    "71350000": "Exploration and geological survey services",
    "71400000": "Urban planning and landscape architectural services",
    "71500000": "Construction-related services",
    "71600000": "Technical testing, analysis and consultancy services",
    "71700000": "Monitoring and control services",
    "71800000": "Consulting services for water-supply and waste consultancy",
    "71900000": "Other engineering services",
    # Division 72 — IT services
    "72000000": "IT services: consulting, software development, internet, support",
    "72100000": "Hardware consultancy services",
    "72200000": "Software programming and consultancy services",
    "72210000": "Programming services of packaged software products",
    "72220000": "Systems and technical consultancy services",
    "72230000": "Custom software development services",
    "72240000": "Systems analysis and programming services",
    "72250000": "System and support services",
    "72260000": "Software-related services",
    "72300000": "Data services",
    "72310000": "Data processing services",
    "72312000": "Data entry services",
    "72314000": "Data collection and collation services",
    "72316000": "Data analysis services",
    "72317000": "Data storage services",
    "72320000": "Database services",
    "72400000": "Internet services",
    "72410000": "Provider services",
    "72415000": "Internet hosting services",
    "72420000": "Internet development services",
    "72500000": "Computer-related services",
    "72510000": "Computer management services",
    "72514000": "Computer facilities management services",
    "72540000": "Computer upgrading services",
    "72550000": "Computer maintenance services",
    "72560000": "Computer testing services",
    "72590000": "Computer-related professional services",
    "72600000": "Computer support and consultancy services",
    "72700000": "Computer network services",
    "72710000": "Local area network services",
    "72720000": "Wide area network services",
    "72800000": "Computer audit and testing services",
    "72900000": "Computer back-up and catalogue conversion services",
    # Division 73 — Research and development
    "73000000": "Research and development services and related consultancy",
    "73100000": "Research and experimental development services",
    "73110000": "Research services",
    "73120000": "Experimental development services",
    "73200000": "Research and development consultancy services",
    "73300000": "Design and execution of research and development services",
    # Division 75 — Public administration
    "75000000": "Administration, defence and social security services",
    "75100000": "Administration services",
    "75200000": "Provision of services to the community",
    "75210000": "Foreign affairs and other services",
    "75220000": "Defence services",
    "75230000": "Justice services",
    "75240000": "Public security, law and order services",
    "75250000": "Fire-brigade and rescue services",
    # Division 76 — Coal and oil services
    "76000000": "Services incidental to oil and gas extraction",
    # Division 77 — Agriculture services
    "77000000": "Agricultural, forestry, horticultural, aquaculture and apiculture services",
    "77100000": "Agricultural services",
    "77200000": "Forestry services",
    "77300000": "Horticultural services",
    # Division 79 — Business services
    "79000000": "Business services: law, marketing, consulting, recruitment, printing",
    "79100000": "Legal services",
    "79110000": "Legal advisory and information services",
    "79200000": "Accounting, auditing and fiscal services",
    "79300000": "Market and economic research; polling and statistics",
    "79400000": "Business and management consultancy and related services",
    "79410000": "Business and management consultancy services",
    "79420000": "Management-related services",
    "79500000": "Office-support services",
    "79600000": "Recruitment services",
    "79700000": "Investigation and security services",
    "79710000": "Security services",
    "79720000": "Investigation services",
    "79800000": "Printing and related services",
    "79900000": "Miscellaneous business and business-related services",
    # Division 80 — Education
    "80000000": "Education and training services",
    "80100000": "Primary education services",
    "80200000": "Secondary education services",
    "80300000": "Higher education services",
    "80400000": "Adult and other education services",
    "80500000": "Training services",
    "80510000": "Specialist training services",
    "80520000": "Technical and vocational training services",
    "80530000": "Vocational training services",
    "80540000": "Tobacco industry training services",
    # Division 85 — Health and social work
    "85000000": "Health and social work services",
    "85100000": "Health services",
    "85110000": "Hospital and related services",
    "85120000": "Medical practice and related services",
    "85130000": "Dental practice and related services",
    "85140000": "Miscellaneous health services",
    "85150000": "Medical imaging services",
    "85160000": "Optician services",
    "85200000": "Veterinary services",
    "85300000": "Social work and related services",
    # Division 90 — Sewage, waste, environmental
    "90000000": "Sewage, refuse, cleaning and environmental services",
    "90100000": "Sewage services",
    "90200000": "Site cleaning and sanitation services",
    "90300000": "Water and air pollution control services",
    "90400000": "Refuse disposal and treatment",
    "90500000": "Refuse and waste related services",
    "90510000": "Refuse disposal and treatment",
    "90511000": "Refuse collection services",
    "90512000": "Refuse transport services",
    "90520000": "Radioactive, toxic, medical and hazardous waste services",
    "90600000": "Cleaning and sanitation services in urban/rural areas",
    "90700000": "Environmental services",
    "90710000": "Environmental management",
    "90720000": "Environmental protection",
    "90730000": "Pollution tracking, monitoring and rehabilitation",
    "90740000": "Pollution gathering, storage and disposal of services",
    # Division 92 — Recreation, culture, sport
    "92000000": "Recreational, cultural and sporting services",
    "92100000": "Motion-picture and video production and related services",
    "92200000": "Radio and television services",
    "92300000": "Entertainment services",
    "92400000": "News agency services",
    "92500000": "Library, archives, museums and cultural services",
    "92600000": "Sporting services",
    "92700000": "Internet café services",
    # Division 98 — Other services
    "98000000": "Other community, social and personal services",
    "98100000": "Services provided by membership organisations",
    "98300000": "Miscellaneous services",
    "98310000": "Laundry and dry-cleaning services",
    "98320000": "Hairdressing and beauty treatment services",
    "98330000": "Physical well-being services",
    "98340000": "Accommodation and office services",
    "98350000": "Services provided in support of the public",
    "98360000": "Marine services",
    "98370000": "Funeral and related services",
    "98380000": "Dog-kennel services",
    "98390000": "Miscellaneous services",
    "98400000": "Services provided by household personnel",
    "98500000": "Private households with employed persons",
    "98900000": "Services provided by extra-territorial organisations and bodies",
}

def _search_cpv(keyword: str, max_results: int = 10) -> list[dict]:
    """Case-insensitive keyword search over the CPV dictionary."""
    kw = keyword.lower().strip()
    results = []
    for code, description in CPV_DATA.items():
        if kw in description.lower():
            results.append({"code": code, "description": description})
        if len(results) >= max_results:
            break
    return results


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



@mcp.tool()
async def read_notice_pdf(
    publication_number: str,
    language: str = "en",
    max_pages: int = 50,
) -> dict:
    """
    Download a TED notice PDF and extract its full text as Markdown for LLM analysis.

    Use this when you need to read and analyse the actual content of a tender document —
    contract requirements, technical specifications, award criteria, eligibility
    conditions, deadlines, budget, and so on.

    Text is extracted with pymupdf4llm which preserves headings, tables, and document
    structure as clean Markdown, optimised for LLM consumption.

    Args:
        publication_number: TED publication number, e.g. "123456-2024".
                            Use the value from search_notices or get_notice results.
        language: Two-letter EU language code, e.g. "en", "fr", "de", "el".
                  Default "en". Use the buyer country language for the most
                  complete version of the document.
        max_pages: Maximum pages to extract (1-200). Default 50.
                   Large procurement documents can exceed 100 pages.
    """
    lang = language.lower()
    if lang not in VALID_LANGUAGES:
        return {"error": f"Invalid language '{lang}'. Use a two-letter EU language code."}

    max_pages = min(200, max(1, max_pages))
    pdf_url = _notice_url(publication_number, "pdf", lang)

    # Download the PDF bytes
    async with httpx.AsyncClient(
        timeout=60,
        follow_redirects=True,
        headers={"User-Agent": HEADERS["User-Agent"]},
    ) as client:
        resp = await client.get(pdf_url)
        if resp.status_code >= 400:
            return {
                "error": f"Could not download PDF: HTTP {resp.status_code}",
                "url": pdf_url,
                "hint": "Try a different language code or check the publication number.",
            }
        pdf_bytes = resp.content

    if len(pdf_bytes) < 1000:
        return {
            "error": "Downloaded file is too small to be a valid PDF.",
            "url": pdf_url,
            "size_bytes": len(pdf_bytes),
        }

    # Open from bytes and extract as Markdown
    doc = pymupdf.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
    total_pages = len(doc)
    pages_to_read = min(total_pages, max_pages)

    md_text = pymupdf4llm.to_markdown(
        doc,
        pages=list(range(pages_to_read)),
    )
    doc.close()

    # Cap output to avoid overwhelming the LLM context window
    MAX_CHARS = 80_000
    truncated = len(md_text) > MAX_CHARS
    if truncated:
        md_text = md_text[:MAX_CHARS]

    return {
        "publication_number": publication_number,
        "language": lang,
        "source_url": pdf_url,
        "total_pages": total_pages,
        "pages_extracted": pages_to_read,
        "truncated": truncated,
        **({"truncation_note": f"Output truncated to {MAX_CHARS} chars. "
                               "Increase max_pages or re-call for additional pages."
           } if truncated else {}),
        "content": md_text,
    }


@mcp.tool()
def lookup_cpv_codes(
    keyword: str,
    max_results: int = 10,
) -> dict:
    """
    Search the EU Common Procurement Vocabulary (CPV) by keyword to find the
    correct 8-digit CPV code to use in search_notices or get_latest_notices.

    Always call this tool FIRST when the user mentions a sector or product
    category — before searching for notices — so you use the right CPV code.

    Examples:
      keyword="drone"         → 35613000 (Unmanned aerial vehicles)
      keyword="hospital"      → 45215000 (Construction for health services)
      keyword="software"      → 48000000 (Software packages)
      keyword="security"      → 35120000, 79710000 (Security systems / services)
      keyword="training"      → 80500000 (Training services)
      keyword="consulting"    → 79400000 (Management consultancy)

    Args:
        keyword:     Word or phrase to search for, e.g. "drone", "road construction",
                     "medical", "IT services", "surveillance", "catering".
        max_results: Maximum number of codes to return (1-20). Default 10.
    """
    max_results = min(20, max(1, max_results))
    matches = _search_cpv(keyword, max_results)

    if not matches:
        # Try each word individually for multi-word keywords
        words = keyword.lower().split()
        seen = set()
        for word in words:
            if len(word) > 3:   # skip short words like "for", "and"
                for m in _search_cpv(word, max_results):
                    if m["code"] not in seen:
                        matches.append(m)
                        seen.add(m["code"])
            if len(matches) >= max_results:
                break

    if not matches:
        return {
            "keyword": keyword,
            "matches": [],
            "hint": (
                "No CPV codes found. Try a broader term — e.g. 'construction' "
                "instead of 'road building', or 'security' instead of 'CCTV'."
            ),
        }

    return {
        "keyword": keyword,
        "total_matches": len(matches),
        "matches": matches,
        "usage_tip": (
            "Pass the 8-digit code (without check digit) to search_notices "
            "as the cpv_code parameter, e.g. cpv_code='35613000'."
        ),
    }


@mcp.tool()
async def summarise_notice(
    publication_number: str,
    language: str = "en",
    focus: str | None = None,
) -> dict:
    """
    Fetch all content for a TED notice so the LLM can produce a full analysis.

    This tool gathers EVERYTHING about a notice in one call:
      1. Full metadata from the TED Search API (buyer, dates, CPV, procedure type)
      2. Complete PDF text extracted as Markdown (titles, tables, requirements)

    After receiving this tool's output, you (the LLM) should immediately
    produce a structured procurement analysis covering:
      - Overview: title, buyer, country, CPV sector, notice type
      - Contract value and duration
      - Key dates and deadlines
      - Scope and technical requirements
      - Eligibility and selection criteria
      - Award criteria and weightings
      - Bidder action points (concrete next steps)
      - Notable clauses or requirements

    Use this when the user asks: "summarise this notice", "what is this tender
    about?", "analyse this procurement", "is this relevant for us?", or similar.

    Args:
        publication_number: TED publication number, e.g. "123456-2024".
        language: Two-letter language code for PDF, e.g. "en", "fr". Default "en".
        focus: Optional focus area, e.g. "eligibility criteria", "award criteria",
               "technical requirements". Leave empty for a full summary.
    """
    lang = language.lower()
    if lang not in VALID_LANGUAGES:
        return {"error": f"Invalid language '{lang}'."}

    # Step 1: Fetch metadata from TED Search API
    meta_payload = {
        "query": f"publication-number IN ({publication_number.strip()})",
        "fields": DEFAULT_FIELDS + ["description-lot", "title-lot"],
        "page": 1,
        "limit": 1,
        "scope": "ALL",
        "checkQuerySyntax": False,
        "paginationMode": "PAGE_NUMBER",
    }
    meta_result = await _post_search(meta_payload)
    if "error" in meta_result:
        return meta_result

    notices = meta_result.get("notices", [])
    if not notices:
        return {"error": f"Notice '{publication_number}' not found."}
    metadata = notices[0]

    # Step 2: Download and extract PDF text
    pdf_text = ""
    pdf_url = _notice_url(publication_number, "pdf", lang)
    pdf_pages_extracted = 0
    pdf_error = None
    try:
        async with httpx.AsyncClient(
            timeout=60, follow_redirects=True,
            headers={"User-Agent": HEADERS["User-Agent"]},
        ) as client:
            resp = await client.get(pdf_url)
            if resp.status_code < 400 and len(resp.content) > 1000:
                doc = pymupdf.open(stream=io.BytesIO(resp.content), filetype="pdf")
                pages_to_read = min(len(doc), 40)
                pdf_text = pymupdf4llm.to_markdown(
                    doc, pages=list(range(pages_to_read))
                )
                pdf_pages_extracted = pages_to_read
                doc.close()
                if len(pdf_text) > 60_000:
                    pdf_text = pdf_text[:60_000] + "\n\n[... content truncated at 60k chars ...]"
            else:
                pdf_error = f"HTTP {resp.status_code}"
    except Exception as e:
        pdf_error = str(e)

    return {
        "publication_number": publication_number,
        "language": lang,
        "focus": focus,
        "pdf_url": pdf_url,
        "pdf_pages_extracted": pdf_pages_extracted,
        "pdf_error": pdf_error,
        "instruction_for_llm": (
            f"Using the metadata and PDF text below, produce a structured procurement "
            f"analysis. {'Focus on: ' + focus + '. ' if focus else ''}"
            "Cover: overview, contract value & duration, key dates, scope & requirements, "
            "eligibility & selection criteria, award criteria, bidder action points, "
            "and any notable clauses. Use clear markdown headers for each section."
        ),
        "metadata": metadata,
        "pdf_text": pdf_text if pdf_text else "[PDF not available — analyse from metadata only]",
    }

# ── Helper ─────────────────────────────────────────────────────────────────────

def _notice_url(pub_number: str, fmt: str, lang: str) -> str:
    if fmt == "xml":
        return f"{NOTICE_BASE}/en/notice/{pub_number}/xml"
    return f"{NOTICE_BASE}/{lang}/notice/{pub_number}/{fmt}"


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
