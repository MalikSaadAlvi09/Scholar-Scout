"""
Academic Search Query Generator for ScholarScout Discovery Mode.
Generates focused, high-precision search queries combining degree level, subject,
specific research interests, country preferences, intake year, funding requirements,
and relevant academic/assistantship terminology.
"""

import json
from typing import List, Dict, Any, Optional

def clean_term(term: Any) -> str:
    if not term or not isinstance(term, str):
        return ""
    return term.strip().replace("\n", " ")

def parse_list_field(field_val: Any) -> List[str]:
    """Safely extracts a list of strings from JSON string or list."""
    if isinstance(field_val, list):
        return [str(x).strip() for x in field_val if str(x).strip()]
    if isinstance(field_val, str):
        field_val = field_val.strip()
        if field_val.startswith("[") and field_val.endswith("]"):
            try:
                parsed = json.loads(field_val)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except Exception:
                pass
        # Comma-separated fallback
        return [p.strip() for p in field_val.split(",") if p.strip()]
    return []

# Academic site restriction domains by country
COUNTRY_TLD_MAP = {
    "united states": "site:.edu",
    "usa": "site:.edu",
    "us": "site:.edu",
    "united kingdom": "site:.ac.uk",
    "uk": "site:.ac.uk",
    "germany": "site:.de",
    "canada": "site:.ca",
    "australia": "site:.edu.au",
    "switzerland": "site:.ch",
    "sweden": "site:.se",
    "netherlands": "site:.nl",
    "japan": "site:.ac.jp",
    "singapore": "site:.edu.sg",
    "france": "site:.fr",
    "ireland": "site:.ie",
    "new zealand": "site:.ac.nz",
    "italy": "site:.it",
    "spain": "site:.es",
    "norway": "site:.no",
    "finland": "site:.fi",
    "denmark": "site:.dk"
}

def generate_discovery_queries(
    profile: Dict[str, Any],
    max_queries: int = 6,
    custom_keywords: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Generates structured, targeted search queries based on candidate profile.
    
    Returns a list of query dicts:
    [
        {
            "query": "site:.edu 'Computer Science' 'Ph.D.' ('graduate research assistantship' OR 'GRA') 'Large Language Models' 2026",
            "intent": "funded_assistantships",
            "country": "United States",
            "category": "Graduate Assistantships & Lab Openings",
            "target_term": "Graduate Research Assistantship"
        },
        ...
    ]
    """
    degree = clean_term(profile.get("target_degree")) or "Ph.D."
    subject = clean_term(profile.get("broad_subject") or profile.get("target_field") or profile.get("current_major")) or "Computer Science"
    interests = clean_term(profile.get("specific_interests") or profile.get("research_interests"))
    intake = clean_term(profile.get("intended_intake")) or ""
    
    # Extract clean intake year (e.g. '2026' from 'Fall 2026')
    intake_year = ""
    for token in intake.split():
        if token.isdigit() and len(token) == 4 and (token.startswith("202") or token.startswith("203")):
            intake_year = token
            break

    countries = parse_list_field(profile.get("preferred_countries"))
    if not countries:
        countries = ["United States", "United Kingdom", "Germany", "Canada"]

    funding_needs = parse_list_field(profile.get("funding_needs"))
    
    # Specific interest keywords (take first 2-3 prominent subfields)
    interest_terms = []
    if interests:
        parts = [p.strip() for p in interests.replace(";", ",").split(",") if p.strip()]
        interest_terms = parts[:2]

    interest_str = f"\"{interest_terms[0]}\"" if interest_terms else ""

    queries: List[Dict[str, Any]] = []

    # 1. Official Institutional & Departmental Graduate Funding Queries
    for country in countries[:3]:
        c_lower = country.lower().strip()
        site_filter = COUNTRY_TLD_MAP.get(c_lower, "")
        site_clause = f"{site_filter} " if site_filter else ""
        year_clause = f" {intake_year}" if intake_year else ""

        # Template A: Department + Degree + Fully Funded Scholarship
        q1_text = f"{site_clause}\"{subject}\" \"{degree}\" (\"fully funded\" OR \"full tuition waiver\") scholarship{year_clause}".strip()
        queries.append({
            "query": q1_text,
            "intent": "institutional_scholarships",
            "country": country,
            "category": "Official Institutional Scholarships",
            "target_term": "Fully Funded Scholarship"
        })

        # Template B: Graduate Research Assistantship / GTA / Positions
        if "ph" in degree.lower() or "doct" in degree.lower() or "master" in degree.lower() or "m.s." in degree.lower():
            asst_terms = "(\"graduate research assistantship\" OR \"research assistant\" OR \"GRA\" OR \"fellowship\")"
            int_clause = f" {interest_str}" if interest_str else ""
            q2_text = f"{site_clause}\"{subject}\" {asst_terms}{int_clause} funding{year_clause}".strip()
            queries.append({
                "query": q2_text,
                "intent": "funded_assistantships",
                "country": country,
                "category": "Graduate Assistantships & Fellowships",
                "target_term": "Graduate Assistantship / Fellowship"
            })

    # 2. Specific Research Lab & Faculty Recruitment Queries (if research interests specified)
    if interest_terms:
        for iterm in interest_terms[:2]:
            country_target = countries[0] if countries else "United States"
            site_filter = COUNTRY_TLD_MAP.get(country_target.lower(), "site:.edu OR site:.ac.uk")
            q_lab = f"({site_filter}) \"{subject}\" \"{iterm}\" (\"accepting graduate students\" OR \"open positions\" OR \"prospective students\")".strip()
            queries.append({
                "query": q_lab,
                "intent": "faculty_lab_recruitment",
                "country": country_target,
                "category": "Faculty & Lab Direct Recruitment",
                "target_term": iterm
            })

    # 3. National / International External Excellence Grants (DAAD, Fulbright, Erasmus, Commonwealth)
    for country in countries:
        c_lower = country.lower()
        if "germany" in c_lower:
            queries.append({
                "query": f"site:daad.de OR site:.de \"{subject}\" \"{degree}\" (\"research grant\" OR \"scholarship\" OR \"doctoral funding\")",
                "intent": "national_funding_programs",
                "country": "Germany",
                "category": "National Academic Exchange (DAAD / Germany)",
                "target_term": "DAAD Academic Grants"
            })
        elif "kingdom" in c_lower or "uk" == c_lower:
            queries.append({
                "query": f"site:.ac.uk \"{subject}\" (\"EPSRC\" OR \"UKRI\" OR \"studentship\" OR \"fully funded PhD\")",
                "intent": "national_funding_programs",
                "country": "United Kingdom",
                "category": "UKRI / EPSRC Research Studentships",
                "target_term": "UKRI / EPSRC Studentships"
            })
        elif "canada" in c_lower:
            queries.append({
                "query": f"site:.ca \"{subject}\" \"{degree}\" (\"NSERC\" OR \"Vanier\" OR \"graduate funding package\")",
                "intent": "national_funding_programs",
                "country": "Canada",
                "category": "Canadian Research Councils & Graduate Funding",
                "target_term": "NSERC / Vanier / Funding Package"
            })

    # Add custom keywords if provided
    if custom_keywords:
        kw_list = parse_list_field(custom_keywords) if not isinstance(custom_keywords, list) else custom_keywords
        for kw in kw_list:
            if kw and str(kw).strip():
                clean_kw = str(kw).strip()
                queries.append({
                    "query": f"\"{subject}\" {clean_kw} \"{degree}\" scholarship funding",
                    "intent": "custom_search",
                    "country": countries[0] if countries else "Global",
                    "category": "Custom Academic Search",
                    "target_term": clean_kw
                })

    # Deduplicate queries by query string
    unique_queries = []
    seen = set()
    for q in queries:
        norm_q = q["query"].lower().strip()
        if norm_q not in seen:
            seen.add(norm_q)
            unique_queries.append(q)

    # Return top max_queries
    return unique_queries[:max_queries]
