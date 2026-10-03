"""
URL Normalizer & Domain Classification Engine for ScholarScout.
Performs canonical URL normalization, tracking parameter stripping, duplicate detection,
and separation of official university domains from external scholarship providers.
"""

import re
from typing import Tuple, Optional
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from backend.logging_utils import logger

# Tracking and session query parameters to strip for canonical deduplication
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "msclkid", "ref", "source", "sessionid", "jsessionid",
    "phpsessid", "aspsessionid", "_ga", "_gl", "_hsenc", "_hsmi", "mc_cid", "mc_eid"
}

# Index filenames to strip
INDEX_FILES = (
    "/index.html", "/index.htm", "/index.php", "/index.asp", "/index.aspx",
    "/default.html", "/default.htm", "/default.php", "/default.asp", "/default.aspx",
    "/home.html", "/home.htm"
)

# Recognized external scholarship agencies and international funding portals
RECOGNIZED_SCHOLARSHIP_PROVIDERS = {
    "daad.de": "DAAD (German Academic Exchange Service)",
    "daad-germany.de": "DAAD Germany",
    "fulbrightonline.org": "Fulbright U.S. Student Program",
    "fulbrightprogram.org": "Fulbright Foreign Scholarship Program",
    "cies.org": "Fulbright Scholar Program (CIES)",
    "chevening.org": "Chevening UK Government Scholarships",
    "erasmus-plus.ec.europa.eu": "European Union Erasmus+ Program",
    "eacea.ec.europa.eu": "Erasmus Mundus Joint Master Degrees",
    "nsf.gov": "U.S. National Science Foundation (NSF GRFP)",
    "nih.gov": "U.S. National Institutes of Health (NIH)",
    "gatescambridge.org": "Gates Cambridge Scholarship",
    "rhodesscholar.org": "Rhodes Trust Oxford Scholarships",
    "si.se": "Swedish Institute Scholarships for Global Professionals",
    "campusfrance.org": "Campus France (Eiffel Excellence Scholarships)",
    "studyinjapan.go.jp": "MEXT Japanese Government Scholarships",
    "csc.edu.cn": "China Scholarship Council",
    "australiaawards.gov.au": "Australia Awards Scholarships",
    "sbfi.admin.ch": "Swiss Government Excellence Scholarships",
    "commonwealthscholarships.org": "Commonwealth Scholarship Commission",
    "vanier.gc.ca": "Vanier Canada Graduate Scholarships",
    "banting.fellowships.gc.ca": "Banting Postdoctoral Fellowships (Canada)"
}

def normalize_url(url: str) -> str:
    """
    Produces a canonical normalized representation of a URL for deduplication.
    - Strips fragment `#...`
    - Lowercases scheme and hostname
    - Removes standard default ports (:80, :443)
    - Normalizes path slashes and removes index documents
    - Strips tracking query parameters (utm_*, gclid, session IDs)
    - Deterministically sorts remaining query parameters
    """
    if not url or not isinstance(url, str):
        return ""

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception:
        return url

    # Scheme and netloc
    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    netloc = parsed.netloc.lower()
    
    # Strip port if standard
    if ":" in netloc:
        host, port = netloc.split(":", 1)
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host

    # Normalize Path
    path = parsed.path or "/"
    # Collapse multiple consecutive slashes
    path = re.sub(r"/+", "/", path)

    # Strip default index files
    path_lower = path.lower()
    for index_file in INDEX_FILES:
        if path_lower.endswith(index_file):
            path = path[:-len(index_file)] or "/"
            break

    # Strip trailing slash if path is more than just '/'
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Normalize Query Parameters
    query_string = ""
    if parsed.query:
        pairs = parse_qsl(parsed.query, keep_blank_values=False)
        cleaned_pairs = [
            (k, v) for k, v in pairs
            if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
        ]
        if cleaned_pairs:
            # Sort deterministically
            cleaned_pairs.sort(key=lambda x: (x[0], x[1]))
            query_string = urlencode(cleaned_pairs)

    # Reassemble without fragment
    return urlunparse((scheme, netloc, path, "", query_string, ""))

def get_root_institutional_domain(domain: str) -> str:
    """
    Extracts the root academic institution domain (e.g. 'cmu.edu' from 'cs.cmu.edu', 'ox.ac.uk' from 'cs.ox.ac.uk').
    """
    domain = domain.lower().replace("www.", "")
    parts = domain.split(".")
    
    # Multi-part TLDs like .ac.uk, .edu.au, .gov.uk, .ac.in
    if len(parts) >= 3 and parts[-2] in ("ac", "edu", "gov", "org", "co", "res"):
        return ".".join(parts[-3:])
    elif len(parts) >= 2:
        return ".".join(parts[-2:])
    return domain

def is_same_institution_domain(url: str, base_domain: str) -> bool:
    """
    Checks if a candidate URL belongs to the target university or its departmental subdomains.
    E.g., if base is 'https://cs.cmu.edu', 'https://cmu.edu' and 'https://eecs.cmu.edu' are true.
    """
    try:
        parsed = urlparse(url)
        url_host = parsed.netloc.lower().replace("www.", "")
        base_host = base_domain.lower().replace("www.", "")

        if url_host == base_host:
            return True

        root_base = get_root_institutional_domain(base_host)
        root_url = get_root_institutional_domain(url_host)

        if root_url == root_base:
            return True

        if url_host.endswith(f".{root_base}") or url_host.endswith(f".{base_host}"):
            return True

        return False
    except Exception:
        return False

def classify_domain_type(url: str, base_domain: str) -> Tuple[str, str]:
    """
    Classifies a discovered link as:
    1. 'official_university' - Belongs to target university root domain / subdomains.
    2. 'external_scholarship_provider' - Recognized national/global funding body (e.g. DAAD, Fulbright, NSF).
    3. 'third_party_lead' - External website or portal discovered during crawl.
    
    Returns: (domain_type: str, provider_name_or_domain: str)
    """
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower().replace("www.", "")

        if is_same_institution_domain(url, base_domain):
            return "official_university", base_domain

        # Check recognized scholarship providers
        for provider_domain, provider_name in RECOGNIZED_SCHOLARSHIP_PROVIDERS.items():
            if host == provider_domain or host.endswith(f".{provider_domain}"):
                return "external_scholarship_provider", provider_name

        return "third_party_lead", host
    except Exception:
        return "third_party_lead", "external"
