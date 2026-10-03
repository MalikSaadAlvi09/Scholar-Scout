"""
ScholarScout Global Directory of World Countries & Research Universities.
Provides canonical country normalization, ccTLD domain matching,
and a catalog of universities across all 195+ countries and regions.
"""

from typing import List, Dict, Any, Optional, Tuple

# Canonical Country Normalization Mapping
COUNTRY_NORMALIZATION_MAP = {
    "usa": "United States",
    "us": "United States",
    "united states of america": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "great britain": "United Kingdom",
    "britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "northern ireland": "United Kingdom",
    "uae": "United Arab Emirates",
    "u.a.e.": "United Arab Emirates",
    "emirates": "United Arab Emirates",
    "south korea": "South Korea",
    "korea, south": "South Korea",
    "republic of korea": "South Korea",
    "korea": "South Korea",
    "north korea": "North Korea",
    "dprk": "North Korea",
    "russia": "Russia",
    "russian federation": "Russia",
    "czechia": "Czech Republic",
    "the netherlands": "Netherlands",
    "holland": "Netherlands",
    "viet nam": "Vietnam",
    "syria": "Syria",
    "iran": "Iran",
    "islamic republic of iran": "Iran",
    "taiwan": "Taiwan",
    "taiwan, province of china": "Taiwan",
    "hong kong": "Hong Kong",
    "hong kong sar": "Hong Kong",
    "macau": "Macau",
    "macao": "Macau",
    "türkiye": "Turkey",
    "turkiye": "Turkey",
    "côte d'ivoire": "Ivory Coast",
    "ivory coast": "Ivory Coast",
    "eswatini": "Eswatini",
    "swaziland": "Eswatini",
    "dr congo": "DR Congo",
    "democratic republic of the congo": "DR Congo",
    "congo, democratic republic of the": "DR Congo",
    "congo": "Republic of the Congo",
    "republic of the congo": "Republic of the Congo",
    "tanzania": "Tanzania",
    "united republic of tanzania": "Tanzania",
    "laos": "Laos",
    "lao pdr": "Laos",
    "myanmar": "Myanmar",
    "burma": "Myanmar",
    "east timor": "Timor-Leste",
    "timor-leste": "Timor-Leste",
    "holy see": "Vatican City",
    "vatican": "Vatican City",
    "state of palestine": "Palestine",
    "palestine": "Palestine"
}

def normalize_country_name(raw_name: Optional[str]) -> str:
    """Normalizes any country name or alias into a canonical standard country name."""
    if not raw_name or not isinstance(raw_name, str):
        return "Unknown"
    cleaned = raw_name.strip()
    if not cleaned or cleaned.lower() in ("unknown", "n/a", "none", "all", "global"):
        return "Unknown"
    norm_key = cleaned.lower()
    return COUNTRY_NORMALIZATION_MAP.get(norm_key, cleaned.title())

# Global Academic Top-Level Domain (TLD) Mapping for all countries
COUNTRY_TLD_MAP = {
    "united states": "site:.edu",
    "united kingdom": "site:.ac.uk",
    "canada": "site:.ca",
    "germany": "site:.de",
    "australia": "site:.edu.au",
    "switzerland": "site:.ch",
    "netherlands": "site:.nl",
    "france": "site:.fr",
    "sweden": "site:.se",
    "japan": "site:.ac.jp",
    "singapore": "site:.edu.sg",
    "china": "site:.edu.cn",
    "south korea": "site:.ac.kr",
    "india": "site:.ac.in",
    "italy": "site:.it",
    "spain": "site:.es",
    "belgium": "site:.be",
    "austria": "site:.at",
    "denmark": "site:.dk",
    "norway": "site:.no",
    "finland": "site:.fi",
    "ireland": "site:.ie",
    "new zealand": "site:.ac.nz",
    "hong kong": "site:.edu.hk",
    "taiwan": "site:.edu.tw",
    "brazil": "site:.edu.br",
    "mexico": "site:.edu.mx",
    "south africa": "site:.ac.za",
    "saudi arabia": "site:.edu.sa",
    "united arab emirates": "site:.ae",
    "israel": "site:.ac.il",
    "turkey": "site:.edu.tr",
    "poland": "site:.edu.pl",
    "portugal": "site:.pt",
    "czech republic": "site:.cz",
    "greece": "site:.gr",
    "hungary": "site:.hu",
    "romania": "site:.ro",
    "malaysia": "site:.edu.my",
    "indonesia": "site:.ac.id",
    "thailand": "site:.ac.th",
    "vietnam": "site:.edu.vn",
    "philippines": "site:.edu.ph",
    "pakistan": "site:.edu.pk",
    "egypt": "site:.edu.eg",
    "nigeria": "site:.edu.ng",
    "kenya": "site:.ac.ke",
    "ghana": "site:.edu.gh",
    "argentina": "site:.edu.ar",
    "chile": "site:.cl",
    "colombia": "site:.edu.co",
    "qatar": "site:.edu.qa",
    "luxembourg": "site:.lu",
    "estonia": "site:.ee",
    "iceland": "site:.is"
}

# Master List of All 195+ Sovereign Countries and Territories with Flag Emojis and Regions
ALL_COUNTRIES_DATA = [
    # --- NORTH AMERICA & CARIBBEAN & CENTRAL AMERICA ---
    {"name": "United States", "code": "US", "flag": "🇺🇸", "region": "North America"},
    {"name": "Canada", "code": "CA", "flag": "🇨🇦", "region": "North America"},
    {"name": "Mexico", "code": "MX", "flag": "🇲🇽", "region": "North America"},
    {"name": "Antigua and Barbuda", "code": "AG", "flag": "🇦🇬", "region": "Caribbean"},
    {"name": "Bahamas", "code": "BS", "flag": "🇧🇸", "region": "Caribbean"},
    {"name": "Barbados", "code": "BB", "flag": "🇧🇧", "region": "Caribbean"},
    {"name": "Belize", "code": "BZ", "flag": "🇧🇿", "region": "Central America"},
    {"name": "Costa Rica", "code": "CR", "flag": "🇨🇷", "region": "Central America"},
    {"name": "Cuba", "code": "CU", "flag": "🇨🇺", "region": "Caribbean"},
    {"name": "Dominica", "code": "DM", "flag": "🇩🇲", "region": "Caribbean"},
    {"name": "Dominican Republic", "code": "DO", "flag": "🇩🇴", "region": "Caribbean"},
    {"name": "El Salvador", "code": "SV", "flag": "🇸🇻", "region": "Central America"},
    {"name": "Grenada", "code": "GD", "flag": "🇬🇩", "region": "Caribbean"},
    {"name": "Guatemala", "code": "GT", "flag": "🇬🇹", "region": "Central America"},
    {"name": "Haiti", "code": "HT", "flag": "🇭🇹", "region": "Caribbean"},
    {"name": "Honduras", "code": "HN", "flag": "🇭🇳", "region": "Central America"},
    {"name": "Jamaica", "code": "JM", "flag": "🇯🇲", "region": "Caribbean"},
    {"name": "Nicaragua", "code": "NI", "flag": "🇳🇮", "region": "Central America"},
    {"name": "Panama", "code": "PA", "flag": "🇵🇦", "region": "Central America"},
    {"name": "Saint Kitts and Nevis", "code": "KN", "flag": "🇰🇳", "region": "Caribbean"},
    {"name": "Saint Lucia", "code": "LC", "flag": "🇱🇨", "region": "Caribbean"},
    {"name": "Saint Vincent and the Grenadines", "code": "VC", "flag": "🇻🇨", "region": "Caribbean"},
    {"name": "Trinidad and Tobago", "code": "TT", "flag": "🇹🇹", "region": "Caribbean"},

    # --- SOUTH AMERICA ---
    {"name": "Argentina", "code": "AR", "flag": "🇦🇷", "region": "South America"},
    {"name": "Bolivia", "code": "BO", "flag": "🇧🇴", "region": "South America"},
    {"name": "Brazil", "code": "BR", "flag": "🇧🇷", "region": "South America"},
    {"name": "Chile", "code": "CL", "flag": "🇨🇱", "region": "South America"},
    {"name": "Colombia", "code": "CO", "flag": "🇨🇴", "region": "South America"},
    {"name": "Ecuador", "code": "EC", "flag": "🇪🇨", "region": "South America"},
    {"name": "Guyana", "code": "GY", "flag": "🇬🇾", "region": "South America"},
    {"name": "Paraguay", "code": "PY", "flag": "🇵🇾", "region": "South America"},
    {"name": "Peru", "code": "PE", "flag": "🇵🇪", "region": "South America"},
    {"name": "Suriname", "code": "SR", "flag": "🇸🇷", "region": "South America"},
    {"name": "Uruguay", "code": "UY", "flag": "🇺🇾", "region": "South America"},
    {"name": "Venezuela", "code": "VE", "flag": "🇻🇪", "region": "South America"},

    # --- EUROPE ---
    {"name": "Albania", "code": "AL", "flag": "🇦🇱", "region": "Europe"},
    {"name": "Andorra", "code": "AD", "flag": "🇦🇩", "region": "Europe"},
    {"name": "Armenia", "code": "AM", "flag": "🇦🇲", "region": "Europe"},
    {"name": "Austria", "code": "AT", "flag": "🇦🇹", "region": "Europe"},
    {"name": "Azerbaijan", "code": "AZ", "flag": "🇦🇿", "region": "Europe"},
    {"name": "Belarus", "code": "BY", "flag": "🇧🇾", "region": "Europe"},
    {"name": "Belgium", "code": "BE", "flag": "🇧🇪", "region": "Europe"},
    {"name": "Bosnia and Herzegovina", "code": "BA", "flag": "🇧🇦", "region": "Europe"},
    {"name": "Bulgaria", "code": "BG", "flag": "🇧🇬", "region": "Europe"},
    {"name": "Croatia", "code": "HR", "flag": "🇭🇷", "region": "Europe"},
    {"name": "Cyprus", "code": "CY", "flag": "🇨🇾", "region": "Europe"},
    {"name": "Czech Republic", "code": "CZ", "flag": "🇨🇿", "region": "Europe"},
    {"name": "Denmark", "code": "DK", "flag": "🇩🇰", "region": "Europe"},
    {"name": "Estonia", "code": "EE", "flag": "🇪🇪", "region": "Europe"},
    {"name": "Finland", "code": "FI", "flag": "🇫🇮", "region": "Europe"},
    {"name": "France", "code": "FR", "flag": "🇫🇷", "region": "Europe"},
    {"name": "Georgia", "code": "GE", "flag": "🇬🇪", "region": "Europe"},
    {"name": "Germany", "code": "DE", "flag": "🇩🇪", "region": "Europe"},
    {"name": "Greece", "code": "GR", "flag": "🇬🇷", "region": "Europe"},
    {"name": "Hungary", "code": "HU", "flag": "🇭🇺", "region": "Europe"},
    {"name": "Iceland", "code": "IS", "flag": "🇮🇸", "region": "Europe"},
    {"name": "Ireland", "code": "IE", "flag": "🇮🇪", "region": "Europe"},
    {"name": "Italy", "code": "IT", "flag": "🇮🇹", "region": "Europe"},
    {"name": "Kosovo", "code": "XK", "flag": "🇽🇰", "region": "Europe"},
    {"name": "Latvia", "code": "LV", "flag": "🇱🇻", "region": "Europe"},
    {"name": "Liechtenstein", "code": "LI", "flag": "🇱🇮", "region": "Europe"},
    {"name": "Lithuania", "code": "LT", "flag": "🇱🇹", "region": "Europe"},
    {"name": "Luxembourg", "code": "LU", "flag": "🇱🇺", "region": "Europe"},
    {"name": "Malta", "code": "MT", "flag": "🇲🇹", "region": "Europe"},
    {"name": "Moldova", "code": "MD", "flag": "🇲🇩", "region": "Europe"},
    {"name": "Monaco", "code": "MC", "flag": "🇲🇨", "region": "Europe"},
    {"name": "Montenegro", "code": "ME", "flag": "🇲🇪", "region": "Europe"},
    {"name": "Netherlands", "code": "NL", "flag": "🇳🇱", "region": "Europe"},
    {"name": "North Macedonia", "code": "MK", "flag": "🇲🇰", "region": "Europe"},
    {"name": "Norway", "code": "NO", "flag": "🇳🇴", "region": "Europe"},
    {"name": "Poland", "code": "PL", "flag": "🇵🇱", "region": "Europe"},
    {"name": "Portugal", "code": "PT", "flag": "🇵🇹", "region": "Europe"},
    {"name": "Romania", "code": "RO", "flag": "🇷🇴", "region": "Europe"},
    {"name": "Russia", "code": "RU", "flag": "🇷🇺", "region": "Europe"},
    {"name": "San Marino", "code": "SM", "flag": "🇸🇲", "region": "Europe"},
    {"name": "Serbia", "code": "RS", "flag": "🇷🇸", "region": "Europe"},
    {"name": "Slovakia", "code": "SK", "flag": "🇸🇰", "region": "Europe"},
    {"name": "Slovenia", "code": "SI", "flag": "🇸🇮", "region": "Europe"},
    {"name": "Spain", "code": "ES", "flag": "🇪🇸", "region": "Europe"},
    {"name": "Sweden", "code": "SE", "flag": "🇸🇪", "region": "Europe"},
    {"name": "Switzerland", "code": "CH", "flag": "🇨🇭", "region": "Europe"},
    {"name": "Turkey", "code": "TR", "flag": "🇹🇷", "region": "Europe"},
    {"name": "Ukraine", "code": "UA", "flag": "🇺🇦", "region": "Europe"},
    {"name": "United Kingdom", "code": "GB", "flag": "🇬🇧", "region": "Europe"},
    {"name": "Vatican City", "code": "VA", "flag": "🇻🇦", "region": "Europe"},

    # --- ASIA ---
    {"name": "Afghanistan", "code": "AF", "flag": "🇦🇫", "region": "Asia"},
    {"name": "Bahrain", "code": "BH", "flag": "🇧🇭", "region": "Middle East"},
    {"name": "Bangladesh", "code": "BD", "flag": "🇧🇩", "region": "Asia"},
    {"name": "Bhutan", "code": "BT", "flag": "🇧🇹", "region": "Asia"},
    {"name": "Brunei", "code": "BN", "flag": "🇧🇳", "region": "Asia"},
    {"name": "Cambodia", "code": "KH", "flag": "🇰🇭", "region": "Asia"},
    {"name": "China", "code": "CN", "flag": "🇨🇳", "region": "Asia"},
    {"name": "Hong Kong", "code": "HK", "flag": "🇭🇰", "region": "Asia"},
    {"name": "India", "code": "IN", "flag": "🇮🇳", "region": "Asia"},
    {"name": "Indonesia", "code": "ID", "flag": "🇮🇩", "region": "Asia"},
    {"name": "Iran", "code": "IR", "flag": "🇮🇷", "region": "Middle East"},
    {"name": "Iraq", "code": "IQ", "flag": "🇮🇶", "region": "Middle East"},
    {"name": "Israel", "code": "IL", "flag": "🇮🇱", "region": "Middle East"},
    {"name": "Japan", "code": "JP", "flag": "🇯🇵", "region": "Asia"},
    {"name": "Jordan", "code": "JO", "flag": "🇯🇴", "region": "Middle East"},
    {"name": "Kazakhstan", "code": "KZ", "flag": "🇰🇿", "region": "Asia"},
    {"name": "Kuwait", "code": "KW", "flag": "🇰🇼", "region": "Middle East"},
    {"name": "Kyrgyzstan", "code": "KG", "flag": "🇰🇬", "region": "Asia"},
    {"name": "Laos", "code": "LA", "flag": "🇱🇦", "region": "Asia"},
    {"name": "Lebanon", "code": "LB", "flag": "🇱🇧", "region": "Middle East"},
    {"name": "Macau", "code": "MO", "flag": "🇲🇴", "region": "Asia"},
    {"name": "Malaysia", "code": "MY", "flag": "🇲🇾", "region": "Asia"},
    {"name": "Maldives", "code": "MV", "flag": "🇲🇻", "region": "Asia"},
    {"name": "Mongolia", "code": "MN", "flag": "🇲🇳", "region": "Asia"},
    {"name": "Myanmar", "code": "MM", "flag": "🇲🇲", "region": "Asia"},
    {"name": "Nepal", "code": "NP", "flag": "🇳🇵", "region": "Asia"},
    {"name": "North Korea", "code": "KP", "flag": "🇰🇵", "region": "Asia"},
    {"name": "Oman", "code": "OM", "flag": "🇴🇲", "region": "Middle East"},
    {"name": "Pakistan", "code": "PK", "flag": "🇵🇰", "region": "Asia"},
    {"name": "Palestine", "code": "PS", "flag": "🇵🇸", "region": "Middle East"},
    {"name": "Philippines", "code": "PH", "flag": "🇵🇭", "region": "Asia"},
    {"name": "Qatar", "code": "QA", "flag": "🇶🇦", "region": "Middle East"},
    {"name": "Saudi Arabia", "code": "SA", "flag": "🇸🇦", "region": "Middle East"},
    {"name": "Singapore", "code": "SG", "flag": "🇸🇬", "region": "Asia"},
    {"name": "South Korea", "code": "KR", "flag": "🇰🇷", "region": "Asia"},
    {"name": "Sri Lanka", "code": "LK", "flag": "🇱🇰", "region": "Asia"},
    {"name": "Syria", "code": "SY", "flag": "🇸🇾", "region": "Middle East"},
    {"name": "Taiwan", "code": "TW", "flag": "🇹🇼", "region": "Asia"},
    {"name": "Tajikistan", "code": "TJ", "flag": "🇹🇯", "region": "Asia"},
    {"name": "Thailand", "code": "TH", "flag": "🇹🇭", "region": "Asia"},
    {"name": "Timor-Leste", "code": "TL", "flag": "🇹🇱", "region": "Asia"},
    {"name": "Turkmenistan", "code": "TM", "flag": "🇹🇲", "region": "Asia"},
    {"name": "United Arab Emirates", "code": "AE", "flag": "🇦🇪", "region": "Middle East"},
    {"name": "Uzbekistan", "code": "UZ", "flag": "🇺🇿", "region": "Asia"},
    {"name": "Vietnam", "code": "VN", "flag": "🇻🇳", "region": "Asia"},
    {"name": "Yemen", "code": "YE", "flag": "🇾🇪", "region": "Middle East"},

    # --- AFRICA ---
    {"name": "Algeria", "code": "DZ", "flag": "🇩🇿", "region": "Africa"},
    {"name": "Angola", "code": "AO", "flag": "🇦🇴", "region": "Africa"},
    {"name": "Benin", "code": "BJ", "flag": "🇧🇯", "region": "Africa"},
    {"name": "Botswana", "code": "BW", "flag": "🇧🇼", "region": "Africa"},
    {"name": "Burkina Faso", "code": "BF", "flag": "🇧🇫", "region": "Africa"},
    {"name": "Burundi", "code": "BI", "flag": "🇧🇮", "region": "Africa"},
    {"name": "Cabo Verde", "code": "CV", "flag": "🇨🇻", "region": "Africa"},
    {"name": "Cameroon", "code": "CM", "flag": "🇨🇲", "region": "Africa"},
    {"name": "Central African Republic", "code": "CF", "flag": "🇨🇫", "region": "Africa"},
    {"name": "Chad", "code": "TD", "flag": "🇹🇩", "region": "Africa"},
    {"name": "Comoros", "code": "KM", "flag": "🇰🇲", "region": "Africa"},
    {"name": "Republic of the Congo", "code": "CG", "flag": "🇨🇬", "region": "Africa"},
    {"name": "DR Congo", "code": "CD", "flag": "🇨🇩", "region": "Africa"},
    {"name": "Djibouti", "code": "DJ", "flag": "🇩🇯", "region": "Africa"},
    {"name": "Egypt", "code": "EG", "flag": "🇪🇬", "region": "Africa"},
    {"name": "Equatorial Guinea", "code": "GQ", "flag": "🇬🇶", "region": "Africa"},
    {"name": "Eritrea", "code": "ER", "flag": "🇪🇷", "region": "Africa"},
    {"name": "Eswatini", "code": "SZ", "flag": "🇸🇿", "region": "Africa"},
    {"name": "Ethiopia", "code": "ET", "flag": "🇪🇹", "region": "Africa"},
    {"name": "Gabon", "code": "GA", "flag": "🇬🇦", "region": "Africa"},
    {"name": "Gambia", "code": "GM", "flag": "🇬🇲", "region": "Africa"},
    {"name": "Ghana", "code": "GH", "flag": "🇬🇭", "region": "Africa"},
    {"name": "Guinea", "code": "GN", "flag": "🇬🇳", "region": "Africa"},
    {"name": "Guinea-Bissau", "code": "GW", "flag": "🇬🇼", "region": "Africa"},
    {"name": "Ivory Coast", "code": "CI", "flag": "🇨🇮", "region": "Africa"},
    {"name": "Kenya", "code": "KE", "flag": "🇰🇪", "region": "Africa"},
    {"name": "Lesotho", "code": "LS", "flag": "🇱🇸", "region": "Africa"},
    {"name": "Liberia", "code": "LR", "flag": "🇱🇷", "region": "Africa"},
    {"name": "Libya", "code": "LY", "flag": "🇱🇾", "region": "Africa"},
    {"name": "Madagascar", "code": "MG", "flag": "🇲🇬", "region": "Africa"},
    {"name": "Malawi", "code": "MW", "flag": "🇲🇼", "region": "Africa"},
    {"name": "Mali", "code": "ML", "flag": "🇲🇱", "region": "Africa"},
    {"name": "Mauritania", "code": "MR", "flag": "🇲🇷", "region": "Africa"},
    {"name": "Mauritius", "code": "MU", "flag": "🇲🇺", "region": "Africa"},
    {"name": "Morocco", "code": "MA", "flag": "🇲🇦", "region": "Africa"},
    {"name": "Mozambique", "code": "MZ", "flag": "🇲🇿", "region": "Africa"},
    {"name": "Namibia", "code": "NA", "flag": "🇳🇦", "region": "Africa"},
    {"name": "Niger", "code": "NE", "flag": "🇳🇪", "region": "Africa"},
    {"name": "Nigeria", "code": "NG", "flag": "🇳🇬", "region": "Africa"},
    {"name": "Rwanda", "code": "RW", "flag": "🇷🇼", "region": "Africa"},
    {"name": "Sao Tome and Principe", "code": "ST", "flag": "🇸🇹", "region": "Africa"},
    {"name": "Senegal", "code": "SN", "flag": "🇸🇳", "region": "Africa"},
    {"name": "Seychelles", "code": "SC", "flag": "🇸🇨", "region": "Africa"},
    {"name": "Sierra Leone", "code": "SL", "flag": "🇸🇱", "region": "Africa"},
    {"name": "Somalia", "code": "SO", "flag": "🇸🇴", "region": "Africa"},
    {"name": "South Africa", "code": "ZA", "flag": "🇿🇦", "region": "Africa"},
    {"name": "South Sudan", "code": "SS", "flag": "🇸🇸", "region": "Africa"},
    {"name": "Sudan", "code": "SD", "flag": "🇸🇩", "region": "Africa"},
    {"name": "Tanzania", "code": "TZ", "flag": "🇹🇿", "region": "Africa"},
    {"name": "Togo", "code": "TG", "flag": "🇹🇬", "region": "Africa"},
    {"name": "Tunisia", "code": "TN", "flag": "🇹🇳", "region": "Africa"},
    {"name": "Uganda", "code": "UG", "flag": "🇺🇬", "region": "Africa"},
    {"name": "Zambia", "code": "ZM", "flag": "🇿🇲", "region": "Africa"},
    {"name": "Zimbabwe", "code": "ZW", "flag": "🇿🇼", "region": "Africa"},

    # --- OCEANIA ---
    {"name": "Australia", "code": "AU", "flag": "🇦🇺", "region": "Oceania"},
    {"name": "Fiji", "code": "FJ", "flag": "🇫🇯", "region": "Oceania"},
    {"name": "Kiribati", "code": "KI", "flag": "🇰🇮", "region": "Oceania"},
    {"name": "Marshall Islands", "code": "MH", "flag": "🇲🇭", "region": "Oceania"},
    {"name": "Micronesia", "code": "FM", "flag": "🇫🇲", "region": "Oceania"},
    {"name": "Nauru", "code": "NR", "flag": "🇳🇷", "region": "Oceania"},
    {"name": "New Zealand", "code": "NZ", "flag": "🇳🇿", "region": "Oceania"},
    {"name": "Palau", "code": "PW", "flag": "🇵🇼", "region": "Oceania"},
    {"name": "Papua New Guinea", "code": "PG", "flag": "🇵🇬", "region": "Oceania"},
    {"name": "Samoa", "code": "WS", "flag": "🇼🇸", "region": "Oceania"},
    {"name": "Solomon Islands", "code": "SB", "flag": "🇸🇧", "region": "Oceania"},
    {"name": "Tonga", "code": "TO", "flag": "🇹🇴", "region": "Oceania"},
    {"name": "Tuvalu", "code": "TV", "flag": "🇹🇻", "region": "Oceania"},
    {"name": "Vanuatu", "code": "VU", "flag": "🇻🇺", "region": "Oceania"}
]

# Curated Premier Research Universities across All Continents and Countries
GLOBAL_UNIVERSITIES_CATALOG: List[Dict[str, Any]] = [
    # --- UNITED STATES ---
    {"name": "Carnegie Mellon University", "domain": "cmu.edu", "url": "https://cs.cmu.edu", "country": "United States", "region": "North America", "funding_type": "GRA / GTA / Fellowship", "specialty": "Computer Science, AI, Robotics"},
    {"name": "Stanford University", "domain": "stanford.edu", "url": "https://cs.stanford.edu", "country": "United States", "region": "North America", "funding_type": "Full Tuition + Stipend", "specialty": "AI, Systems, EE"},
    {"name": "Massachusetts Institute of Technology", "domain": "mit.edu", "url": "https://eecs.mit.edu", "country": "United States", "region": "North America", "funding_type": "Fellowship / Research Assistantship", "specialty": "EECS, Engineering, Physics"},
    {"name": "University of California, Berkeley", "domain": "berkeley.edu", "url": "https://eecs.berkeley.edu", "country": "United States", "region": "North America", "funding_type": "GSR / GSI / Departmental Aid", "specialty": "Computer Science, Data Science"},
    {"name": "Harvard University", "domain": "harvard.edu", "url": "https://seas.harvard.edu", "country": "United States", "region": "North America", "funding_type": "Full Funding Package", "specialty": "Applied Sciences, Bioengineering"},
    {"name": "Princeton University", "domain": "princeton.edu", "url": "https://www.cs.princeton.edu", "country": "United States", "region": "North America", "funding_type": "First-Year Fellowship + Assistantship", "specialty": "Computer Science, Math"},
    {"name": "California Institute of Technology", "domain": "caltech.edu", "url": "https://cms.caltech.edu", "country": "United States", "region": "North America", "funding_type": "Full GRA / Fellowship", "specialty": "Computing & Mathematical Sciences"},
    {"name": "Columbia University", "domain": "columbia.edu", "url": "https://www.cs.columbia.edu", "country": "United States", "region": "North America", "funding_type": "Dean's Fellowship / GRA", "specialty": "Computer Science, Data Science"},
    {"name": "Cornell University", "domain": "cornell.edu", "url": "https://www.cs.cornell.edu", "country": "United States", "region": "North America", "funding_type": "Graduate Assistantship", "specialty": "Computer Science, Tech"},
    {"name": "University of Washington", "domain": "washington.edu", "url": "https://www.cs.washington.edu", "country": "United States", "region": "North America", "funding_type": "RA / TA + Tuition Waiver", "specialty": "Allen School, AI, NLP"},
    {"name": "University of Illinois Urbana-Champaign", "domain": "illinois.edu", "url": "https://cs.illinois.edu", "country": "United States", "region": "North America", "funding_type": "Full Assistantship + Tuition Waiver", "specialty": "Computer Science, Systems"},
    {"name": "University of Michigan", "domain": "umich.edu", "url": "https://cse.engin.umich.edu", "country": "United States", "region": "North America", "funding_type": "Rackham Graduate Fellowship", "specialty": "CSE, AI, Robotics"},
    {"name": "Georgia Institute of Technology", "domain": "gatech.edu", "url": "https://www.cc.gatech.edu", "country": "United States", "region": "North America", "funding_type": "GRA / GTA Tuition Waiver", "specialty": "Computing, Interactive AI"},
    {"name": "University of Texas at Austin", "domain": "utexas.edu", "url": "https://www.cs.utexas.edu", "country": "United States", "region": "North America", "funding_type": "Graduate School Fellowship", "specialty": "Computer Science, AI"},
    {"name": "University of California, San Diego", "domain": "ucsd.edu", "url": "https://cse.ucsd.edu", "country": "United States", "region": "North America", "funding_type": "GSR / TA Funding Package", "specialty": "Computer Science, Bioinformatics"},
    {"name": "University of California, Los Angeles", "domain": "ucla.edu", "url": "https://www.cs.ucla.edu", "country": "United States", "region": "North America", "funding_type": "Departmental Fellowship", "specialty": "Computer Science, Engineering"},
    {"name": "Yale University", "domain": "yale.edu", "url": "https://cpsc.yale.edu", "country": "United States", "region": "North America", "funding_type": "Full Tuition + Living Stipend", "specialty": "Computer Science, Medicine"},
    {"name": "University of Pennsylvania", "domain": "upenn.edu", "url": "https://www.cis.upenn.edu", "country": "United States", "region": "North America", "funding_type": "Penn Engineering Fellowship", "specialty": "CIS, AI, Robotics"},
    {"name": "Purdue University", "domain": "purdue.edu", "url": "https://www.cs.purdue.edu", "country": "United States", "region": "North America", "funding_type": "Research / Teaching Assistantship", "specialty": "Computer Science, Security"},
    {"name": "University of Wisconsin-Madison", "domain": "wisc.edu", "url": "https://www.cs.wisc.edu", "country": "United States", "region": "North America", "funding_type": "GRA / Teaching Assistantship", "specialty": "Computer Science, Database"},
    {"name": "Johns Hopkins University", "domain": "jhu.edu", "url": "https://www.cs.jhu.edu", "country": "United States", "region": "North America", "funding_type": "Full Doctoral Fellowship", "specialty": "NLP, Medicine, Bioengineering"},
    {"name": "University of Maryland, College Park", "domain": "umd.edu", "url": "https://www.cs.umd.edu", "country": "United States", "region": "North America", "funding_type": "Dean's Fellowship / GRA", "specialty": "Computer Science, Quantum, AI"},
    {"name": "Northwestern University", "domain": "northwestern.edu", "url": "https://www.cs.northwestern.edu", "country": "United States", "region": "North America", "funding_type": "Graduate Fellowship", "specialty": "Computer Science, AI"},
    {"name": "New York University", "domain": "nyu.edu", "url": "https://cs.nyu.edu", "country": "United States", "region": "North America", "funding_type": "MacCracken Fellowship", "specialty": "Courant CS, Data Science"},
    {"name": "University of Southern California", "domain": "usc.edu", "url": "https://www.cs.usc.edu", "country": "United States", "region": "North America", "funding_type": "Annenberg / Viterbi Fellowship", "specialty": "Computer Science, Games, AI"},

    # --- UNITED KINGDOM ---
    {"name": "University of Oxford", "domain": "ox.ac.uk", "url": "https://www.ox.ac.uk", "country": "United Kingdom", "region": "Europe", "funding_type": "Clarendon / UKRI Studentships", "specialty": "Computer Science, AI, Humanities"},
    {"name": "University of Cambridge", "domain": "cam.ac.uk", "url": "https://www.cam.ac.uk", "country": "United Kingdom", "region": "Europe", "funding_type": "Gates Cambridge / Cambridge Trust", "specialty": "Computer Science, Engineering"},
    {"name": "Imperial College London", "domain": "imperial.ac.uk", "url": "https://www.imperial.ac.uk/computing", "country": "United Kingdom", "region": "Europe", "funding_type": "President's PhD Scholarships", "specialty": "Computing, Engineering"},
    {"name": "University College London", "domain": "ucl.ac.uk", "url": "https://www.ucl.ac.uk/computer-science", "country": "United Kingdom", "region": "Europe", "funding_type": "UCL Research Excellence / EPSRC", "specialty": "Computer Science, AI, Medical AI"},
    {"name": "University of Edinburgh", "domain": "ed.ac.uk", "url": "https://www.inf.ed.ac.uk", "country": "United Kingdom", "region": "Europe", "funding_type": "Informatics Doctoral Studentships", "specialty": "Informatics, NLP, Robotics"},
    {"name": "King's College London", "domain": "kcl.ac.uk", "url": "https://www.kcl.ac.uk/nms/depts/informatics", "country": "United Kingdom", "region": "Europe", "funding_type": "KAS Doctoral Scholarships", "specialty": "Informatics, Security, AI"},
    {"name": "University of Manchester", "domain": "manchester.ac.uk", "url": "https://www.cs.manchester.ac.uk", "country": "United Kingdom", "region": "Europe", "funding_type": "EPSRC / Dean's Award", "specialty": "Computer Science, Systems"},
    {"name": "University of Bristol", "domain": "bristol.ac.uk", "url": "https://www.bristol.ac.uk/engineering/departments/computerscience", "country": "United Kingdom", "region": "Europe", "funding_type": "CDT / University Studentships", "specialty": "Computer Science, Quantum"},
    {"name": "University of Southampton", "domain": "soton.ac.uk", "url": "https://www.ecs.soton.ac.uk", "country": "United Kingdom", "region": "Europe", "funding_type": "ECS Doctoral Awards", "specialty": "ECS, Web Science, AI"},
    {"name": "University of Warwick", "domain": "warwick.ac.uk", "url": "https://warwick.ac.uk/fac/sci/dcs", "country": "United Kingdom", "region": "Europe", "funding_type": "Chancellor's International Scholarship", "specialty": "Computer Science, Math"},

    # --- CANADA ---
    {"name": "University of Toronto", "domain": "utoronto.ca", "url": "https://web.cs.toronto.edu", "country": "Canada", "region": "North America", "funding_type": "Guaranteed Graduate Funding Package", "specialty": "Computer Science, AI (Vector Institute)"},
    {"name": "University of British Columbia", "domain": "ubc.ca", "url": "https://www.cs.ubc.ca", "country": "Canada", "region": "North America", "funding_type": "Four-Year Doctoral Fellowship (4YF)", "specialty": "Computer Science, Data Science"},
    {"name": "McGill University", "domain": "mcgill.ca", "url": "https://www.cs.mcgill.ca", "country": "Canada", "region": "North America", "funding_type": "MILA / GPS Doctoral Funding", "specialty": "Computer Science, AI (MILA)"},
    {"name": "University of Waterloo", "domain": "uwaterloo.ca", "url": "https://cs.uwaterloo.ca", "country": "Canada", "region": "North America", "funding_type": "Cheriton Graduate Scholarships", "specialty": "Computer Science, Quantum"},
    {"name": "University of Montreal", "domain": "umontreal.ca", "url": "https://diro.umontreal.ca", "country": "Canada", "region": "North America", "funding_type": "MILA AI Research Grants", "specialty": "DIRO, Deep Learning (MILA)"},
    {"name": "University of Alberta", "domain": "ualberta.ca", "url": "https://www.ualberta.ca/computing-science", "country": "Canada", "region": "North America", "funding_type": "Amii / Doctoral Funding Package", "specialty": "Computing Science, Reinforcement Learning"},
    {"name": "Simon Fraser University", "domain": "sfu.ca", "url": "https://www.sfu.ca/computing", "country": "Canada", "region": "North America", "funding_type": "Graduate Fellowship / RA", "specialty": "Computing Science, Vision"},
    {"name": "McMaster University", "domain": "mcmaster.ca", "url": "https://www.eng.mcmaster.ca/cas", "country": "Canada", "region": "North America", "funding_type": "Departmental Graduate Support", "specialty": "Computing & Software"},

    # --- GERMANY ---
    {"name": "Technical University of Munich (TUM)", "domain": "tum.de", "url": "https://www.cit.tum.de", "country": "Germany", "region": "Europe", "funding_type": "TV-L E13 Salaried Researcher / DAAD", "specialty": "CIT, Informatics, AI"},
    {"name": "Ludwig Maximilian University of Munich (LMU)", "domain": "lmu.de", "url": "https://www.ifi.lmu.de", "country": "Germany", "region": "Europe", "funding_type": "TV-L E13 Salaried / DAAD", "specialty": "Informatics, Data Science"},
    {"name": "Heidelberg University", "domain": "uni-heidelberg.de", "url": "https://www.uni-heidelberg.de", "country": "Germany", "region": "Europe", "funding_type": "DAAD / Salaried Doctoral Contract", "specialty": "Scientific Computing, Medicine"},
    {"name": "RWTH Aachen University", "domain": "rwth-aachen.de", "url": "https://www.cs.rwth-aachen.de", "country": "Germany", "region": "Europe", "funding_type": "TV-L Salaried Research Assistant", "specialty": "Computer Science, Engineering"},
    {"name": "Karlsruhe Institute of Technology (KIT)", "domain": "kit.edu", "url": "https://www.informatik.kit.edu", "country": "Germany", "region": "Europe", "funding_type": "Salaried Researcher / Helmholtz", "specialty": "Informatics, Autonomous Systems"},
    {"name": "Technical University of Berlin", "domain": "tu-berlin.de", "url": "https://www.eecs.tu-berlin.de", "country": "Germany", "region": "Europe", "funding_type": "BIFOLD / TV-L E13", "specialty": "EECS, Big Data, ML"},
    {"name": "University of Freiburg", "domain": "uni-freiburg.de", "url": "https://www.informatik.uni-freiburg.de", "country": "Germany", "region": "Europe", "funding_type": "Salaried Research Assistant", "specialty": "Informatics, Robotics"},
    {"name": "University of Tübingen", "domain": "uni-tuebingen.de", "url": "https://uni-tuebingen.de/en/faculties/faculty-of-science/departments/computer-science", "country": "Germany", "region": "Europe", "funding_type": "Cyber Valley / TV-L E13", "specialty": "Machine Learning, Vision"},
    {"name": "Saarland University", "domain": "uni-saarland.de", "url": "https://saarland-informatics-campus.de", "country": "Germany", "region": "Europe", "funding_type": "Max Planck / SIC Graduate School", "specialty": "Saarland Informatics Campus, MPI"},
    {"name": "Technical University of Darmstadt", "domain": "tu-darmstadt.de", "url": "https://www.informatik.tu-darmstadt.de", "country": "Germany", "region": "Europe", "funding_type": "Hessian.AI / TV-L E13", "specialty": "Computer Science, AI Systems"},

    # --- SWITZERLAND ---
    {"name": "ETH Zurich", "domain": "ethz.ch", "url": "https://inf.ethz.ch", "country": "Switzerland", "region": "Europe", "funding_type": "Salaried Doctoral Researcher (CHF 50k+)", "specialty": "Computer Science, Robotics, AI"},
    {"name": "EPFL (École Polytechnique Fédérale de Lausanne)", "domain": "epfl.ch", "url": "https://www.epfl.ch/schools/ic", "country": "Switzerland", "region": "Europe", "funding_type": "Doctoral Assistantship Salary", "specialty": "Computer & Communication Sciences"},
    {"name": "University of Zurich", "domain": "uzh.ch", "url": "https://www.ifi.uzh.ch", "country": "Switzerland", "region": "Europe", "funding_type": "Salaried Assistantship", "specialty": "Informatics, Neuroinformatics"},
    {"name": "University of Geneva", "domain": "unige.ch", "url": "https://www.unige.ch/cui", "country": "Switzerland", "region": "Europe", "funding_type": "Doctoral Research Contract", "specialty": "Computer Science, Security"},
    {"name": "University of Basel", "domain": "unibas.ch", "url": "https://dmi.unibas.ch", "country": "Switzerland", "region": "Europe", "funding_type": "Swiss National Science Foundation", "specialty": "Computer Science, Math"},

    # --- NETHERLANDS ---
    {"name": "Delft University of Technology (TU Delft)", "domain": "tudelft.nl", "url": "https://www.tudelft.nl/en/eemcs", "country": "Netherlands", "region": "Europe", "funding_type": "Full Salaried PhD Candidate (CAO-NU)", "specialty": "EEMCS, Computer Science, AI"},
    {"name": "University of Amsterdam", "domain": "uva.nl", "url": "https://ivi.uva.nl", "country": "Netherlands", "region": "Europe", "funding_type": "Salaried Researcher (UvA / ELLIS)", "specialty": "Informatics Institute, AI"},
    {"name": "Eindhoven University of Technology (TU/e)", "domain": "tue.nl", "url": "https://www.tue.nl/en/our-university/departments/mathematics-and-computer-science", "country": "Netherlands", "region": "Europe", "funding_type": "Salaried PhD Position", "specialty": "Computer Science, Systems"},
    {"name": "Utrecht University", "domain": "uu.nl", "url": "https://www.uu.nl/en/organisation/department-of-information-and-computing-sciences", "country": "Netherlands", "region": "Europe", "funding_type": "Salaried Researcher", "specialty": "Information & Computing Sciences"},
    {"name": "Leiden University", "domain": "universiteitleiden.nl", "url": "https://www.universiteitleiden.nl/en/science/computer-science", "country": "Netherlands", "region": "Europe", "funding_type": "Salaried PhD Position", "specialty": "LIACS, Computer Science"},

    # --- AUSTRALIA ---
    {"name": "University of Melbourne", "domain": "unimelb.edu.au", "url": "https://cis.unimelb.edu.au", "country": "Australia", "region": "Oceania", "funding_type": "Melbourne Research Scholarship (Full Stipend)", "specialty": "Computing and Information Systems"},
    {"name": "Australian National University (ANU)", "domain": "anu.edu.au", "url": "https://comp.anu.edu.au", "country": "Australia", "region": "Oceania", "funding_type": "ANU AGRTP / HDR Fee Merit Merit", "specialty": "School of Computing, AI"},
    {"name": "University of Sydney", "domain": "sydney.edu.au", "url": "https://www.sydney.edu.au/engineering/schools/school-of-computer-science.html", "country": "Australia", "region": "Oceania", "funding_type": "RTP Stipend + Tuition Waiver", "specialty": "Computer Science, Engineering"},
    {"name": "University of New South Wales (UNSW)", "domain": "unsw.edu.au", "url": "https://www.unsw.edu.au/engineering/our-schools/computer-science-and-engineering", "country": "Australia", "region": "Oceania", "funding_type": "UNSW Scientia / RTP Scholarship", "specialty": "CSE, AI, Cyber Security"},
    {"name": "University of Queensland", "domain": "uq.edu.au", "url": "https://eecs.uq.edu.au", "country": "Australia", "region": "Oceania", "funding_type": "UQ Graduate School Scholarship", "specialty": "IT & Electrical Engineering"},
    {"name": "Monash University", "domain": "monash.edu", "url": "https://www.monash.edu/it", "country": "Australia", "region": "Oceania", "funding_type": "Monash Graduate Scholarship", "specialty": "Faculty of IT, AI, Data"},

    # --- NEW ZEALAND ---
    {"name": "University of Auckland", "domain": "auckland.ac.nz", "url": "https://www.cs.auckland.ac.nz", "country": "New Zealand", "region": "Oceania", "funding_type": "University of Auckland Doctoral Scholarship", "specialty": "Computer Science, Software"},
    {"name": "University of Otago", "domain": "otago.ac.nz", "url": "https://www.cs.otago.ac.nz", "country": "New Zealand", "region": "Oceania", "funding_type": "Otago Doctoral Scholarship", "specialty": "Computer Science, Information Science"},

    # --- SINGAPORE ---
    {"name": "National University of Singapore (NUS)", "domain": "nus.edu.sg", "url": "https://www.comp.nus.edu.sg", "country": "Singapore", "region": "Asia", "funding_type": "NUS Research Scholarship / President's Fellowship", "specialty": "School of Computing, AI, Systems"},
    {"name": "Nanyang Technological University (NTU)", "domain": "ntu.edu.sg", "url": "https://www.ntu.edu.sg/scse", "country": "Singapore", "region": "Asia", "funding_type": "NTU Research Scholarship / Nanyang President", "specialty": "SCSE, Computing, Robotics"},
    {"name": "Singapore Management University", "domain": "smu.edu.sg", "url": "https://scis.smu.edu.sg", "country": "Singapore", "region": "Asia", "funding_type": "SMU PhD Fellowship", "specialty": "Computing & Information Systems"},

    # --- JAPAN ---
    {"name": "University of Tokyo", "domain": "u-tokyo.ac.jp", "url": "https://www.i.u-tokyo.ac.jp", "country": "Japan", "region": "Asia", "funding_type": "MEXT Scholarship / U-Tokyo Fellowship", "specialty": "Graduate School of Information Science"},
    {"name": "Kyoto University", "domain": "kyoto-u.ac.jp", "url": "https://www.i.kyoto-u.ac.jp", "country": "Japan", "region": "Asia", "funding_type": "MEXT / Kyoto iUP Research Aid", "specialty": "Informatics, AI, Systems"},
    {"name": "Tokyo Institute of Technology (Tokyo Tech)", "domain": "titech.ac.jp", "url": "https://www.titech.ac.jp/english/0/departments", "country": "Japan", "region": "Asia", "funding_type": "MEXT University Recommendation", "specialty": "School of Computing, Engineering"},
    {"name": "Osaka University", "domain": "osaka-u.ac.jp", "url": "https://www.ist.osaka-u.ac.jp", "country": "Japan", "region": "Asia", "funding_type": "MEXT / Osaka Fellowship", "specialty": "Information Science & Technology"},
    {"name": "Tohoku University", "domain": "tohoku.ac.jp", "url": "https://www.is.tohoku.ac.jp", "country": "Japan", "region": "Asia", "funding_type": "MEXT / President Fellowship", "specialty": "Information Sciences"},

    # --- CHINA, HONG KONG, TAIWAN ---
    {"name": "Tsinghua University", "domain": "tsinghua.edu.cn", "url": "https://www.cs.tsinghua.edu.cn", "country": "China", "region": "Asia", "funding_type": "Chinese Government Scholarship (CSC) / Tsinghua Fellowship", "specialty": "Computer Science, AI"},
    {"name": "Peking University", "domain": "pku.edu.cn", "url": "https://cs.pku.edu.cn", "country": "China", "region": "Asia", "funding_type": "CSC / PKU Presidential Fellowship", "specialty": "School of CS, NLP"},
    {"name": "Zhejiang University", "domain": "zju.edu.cn", "url": "https://www.cs.zju.edu.cn", "country": "China", "region": "Asia", "funding_type": "CSC / Zhejiang Scholarship", "specialty": "Computer Science, Vision"},
    {"name": "Fudan University", "domain": "fudan.edu.cn", "url": "https://cs.fudan.edu.cn", "country": "China", "region": "Asia", "funding_type": "CSC / Shanghai Government Scholarship", "specialty": "Computer Science"},
    {"name": "University of Hong Kong (HKU)", "domain": "hku.hk", "url": "https://www.cs.hku.hk", "country": "Hong Kong", "region": "Asia", "funding_type": "Hong Kong PhD Fellowship Scheme (HKPFS)", "specialty": "Computer Science, AI"},
    {"name": "Hong Kong University of Science and Technology (HKUST)", "domain": "hkust.edu.hk", "url": "https://cse.hkust.edu.hk", "country": "Hong Kong", "region": "Asia", "funding_type": "HKPFS / Postgraduate Studentship (PGS)", "specialty": "CSE, AI, Big Data"},
    {"name": "Chinese University of Hong Kong (CUHK)", "domain": "cuhk.edu.hk", "url": "https://www.cse.cuhk.edu.hk", "country": "Hong Kong", "region": "Asia", "funding_type": "HKPFS / Vice-Chancellor's Scholarship", "specialty": "CSE, Multimedia, Vision"},
    {"name": "National Taiwan University (NTU)", "domain": "ntu.edu.tw", "url": "https://www.csie.ntu.edu.tw", "country": "Taiwan", "region": "Asia", "funding_type": "MOE Taiwan Scholarship / NTU Diamond", "specialty": "CSIE, AI, Semiconductor"},
    {"name": "National Tsing Hua University", "domain": "nthu.edu.tw", "url": "https://cs.site.nthu.edu.tw", "country": "Taiwan", "region": "Asia", "funding_type": "NTHU International Scholarship", "specialty": "Computer Science, Hardware"},

    # --- SOUTH KOREA ---
    {"name": "Seoul National University (SNU)", "domain": "snu.ac.kr", "url": "https://cse.snu.ac.kr", "country": "South Korea", "region": "Asia", "funding_type": "Global Korea Scholarship (GKS) / SNU President", "specialty": "CSE, AI, Robotics"},
    {"name": "KAIST (Korea Advanced Institute of Science and Technology)", "domain": "kaist.ac.kr", "url": "https://cs.kaist.ac.kr", "country": "South Korea", "region": "Asia", "funding_type": "KAIST Full Scholarship (Tuition + Stipend)", "specialty": "School of Computing, Kim Jaechul AI"},
    {"name": "POSTECH (Pohang University of Science and Technology)", "domain": "postech.ac.kr", "url": "https://cse.postech.ac.kr", "country": "South Korea", "region": "Asia", "funding_type": "POSTECH Graduate Fellowship", "specialty": "CSE, AI Graduate School"},
    {"name": "Yonsei University", "domain": "yonsei.ac.kr", "url": "https://cs.yonsei.ac.kr", "country": "South Korea", "region": "Asia", "funding_type": "GKS / Yonsei Global Scholarship", "specialty": "Computer Science, AI"},
    {"name": "Korea University", "domain": "korea.ac.kr", "url": "https://cs.korea.ac.kr", "country": "South Korea", "region": "Asia", "funding_type": "Global Leader Fellowship", "specialty": "Computer Science & Engineering"},

    # --- FRANCE ---
    {"name": "Sorbonne University", "domain": "sorbonne-universite.fr", "url": "https://sciences.sorbonne-universite.fr", "country": "France", "region": "Europe", "funding_type": "Doctoral Contract / Inria Fellowship", "specialty": "LIP6, Computer Science, AI"},
    {"name": "Institut Polytechnique de Paris", "domain": "ip-paris.fr", "url": "https://www.ip-paris.fr", "country": "France", "region": "Europe", "funding_type": "Doctoral Contract (Contrat Doctoral)", "specialty": "Computer Science, Data, Physics"},
    {"name": "PSL Research University (Paris Sciences et Lettres)", "domain": "psl.eu", "url": "https://psl.eu", "country": "France", "region": "Europe", "funding_type": "PSL PhD Grant / Inria", "specialty": "ENS Paris CS, Applied Math"},
    {"name": "Université Paris-Saclay", "domain": "universite-paris-saclay.fr", "url": "https://www.universite-paris-saclay.fr", "country": "France", "region": "Europe", "funding_type": "Doctoral School Grant / Inria", "specialty": "LISN, AI, Mathematics"},
    {"name": "Grenoble Alpes University", "domain": "univ-grenoble-alpes.fr", "url": "https://www.univ-grenoble-alpes.fr", "country": "France", "region": "Europe", "funding_type": "MIAI AI Doctoral Grant", "specialty": "LIG, Informatics, Microelectronics"},

    # --- SWEDEN, DENMARK, NORWAY, FINLAND ---
    {"name": "KTH Royal Institute of Technology", "domain": "kth.se", "url": "https://www.kth.se/eecs", "country": "Sweden", "region": "Europe", "funding_type": "Salaried PhD Employment (SEK 32k+/mo)", "specialty": "EECS, Computer Science, Robotics"},
    {"name": "Lund University", "domain": "lu.se", "url": "https://cs.lth.se", "country": "Sweden", "region": "Europe", "funding_type": "WASP AI / Salaried PhD Position", "specialty": "LTH Computer Science, AI"},
    {"name": "Chalmers University of Technology", "domain": "chalmers.se", "url": "https://www.chalmers.se/en/departments/cse", "country": "Sweden", "region": "Europe", "funding_type": "WASP / Salaried PhD Position", "specialty": "CSE, Software Engineering"},
    {"name": "Uppsala University", "domain": "uu.se", "url": "https://www.it.uu.se", "country": "Sweden", "region": "Europe", "funding_type": "Salaried PhD Employment", "specialty": "Department of IT, Systems"},
    {"name": "University of Copenhagen", "domain": "ku.dk", "url": "https://diiku.dk", "country": "Denmark", "region": "Europe", "funding_type": "Salaried PhD Fellowship (DKK 33k+/mo)", "specialty": "DIKU, Computer Science, ML"},
    {"name": "Technical University of Denmark (DTU)", "domain": "dtu.dk", "url": "https://www.compute.dtu.dk", "country": "Denmark", "region": "Europe", "funding_type": "Salaried PhD Position", "specialty": "DTU Compute, AI, Algorithms"},
    {"name": "University of Oslo", "domain": "uio.no", "url": "https://www.mn.uio.no/ifi", "country": "Norway", "region": "Europe", "funding_type": "Salaried Research Fellow (NOK 500k+/yr)", "specialty": "IFI, Informatics, AI"},
    {"name": "Norwegian University of Science and Technology (NTNU)", "domain": "ntnu.no", "url": "https://www.ntnu.edu/idi", "country": "Norway", "region": "Europe", "funding_type": "Salaried PhD Position", "specialty": "IDI, Computer Science"},
    {"name": "University of Helsinki", "domain": "helsinki.fi", "url": "https://www.helsinki.fi/en/computer-science", "country": "Finland", "region": "Europe", "funding_type": "FCAI / Salaried Researcher", "specialty": "Computer Science, FCAI, AI"},
    {"name": "Aalto University", "domain": "aalto.fi", "url": "https://www.aalto.fi/en/department-of-computer-science", "country": "Finland", "region": "Europe", "funding_type": "Salaried Doctoral Candidate", "specialty": "Department of CS, ML"},

    # --- IRELAND & BELGIUM & AUSTRIA ---
    {"name": "Trinity College Dublin", "domain": "tcd.ie", "url": "https://www.scss.tcd.ie", "country": "Ireland", "region": "Europe", "funding_type": "SFI / Provost PhD Project Awards", "specialty": "SCSS, Computer Science"},
    {"name": "University College Dublin (UCD)", "domain": "ucd.ie", "url": "https://www.ucd.ie/cs", "country": "Ireland", "region": "Europe", "funding_type": "SFI / Insight Centre Scholarships", "specialty": "School of Computer Science, Data"},
    {"name": "KU Leuven", "domain": "kuleuven.be", "url": "https://wms.cs.kuleuven.be/cs", "country": "Belgium", "region": "Europe", "funding_type": "FWO / Doctoral Scholarship", "specialty": "Computer Science, DTAI"},
    {"name": "Ghent University", "domain": "ugent.be", "url": "https://www.ugent.be", "country": "Belgium", "region": "Europe", "funding_type": "BOF / FWO PhD Grant", "specialty": "Engineering & Architecture, AI"},
    {"name": "University of Vienna", "domain": "univie.ac.at", "url": "https://cs.univie.ac.at", "country": "Austria", "region": "Europe", "funding_type": "UniVie Doctoral Fellowship", "specialty": "Faculty of Computer Science"},
    {"name": "TU Wien (Vienna University of Technology)", "domain": "tuwien.at", "url": "https://informatics.tuwien.ac.at", "country": "Austria", "region": "Europe", "funding_type": "FWF / University Assistant Contract", "specialty": "Informatics, Logic, AI"},

    # --- ITALY & SPAIN & PORTUGAL ---
    {"name": "Sapienza University of Rome", "domain": "uniroma1.it", "url": "https://www.diag.uniroma1.it", "country": "Italy", "region": "Europe", "funding_type": "MIUR Italian Ministerial PhD Grant", "specialty": "DIAG, Computer Science, AI"},
    {"name": "Politecnico di Milano", "domain": "polimi.it", "url": "https://www.deib.polimi.it", "country": "Italy", "region": "Europe", "funding_type": "Polimi PhD Scholarship", "specialty": "DEIB, Computer Engineering"},
    {"name": "University of Bologna", "domain": "unibo.it", "url": "https://disi.unibo.it", "country": "Italy", "region": "Europe", "funding_type": "Doctoral Research Grant", "specialty": "DISI, Computer Science"},
    {"name": "Polytechnic University of Catalonia (UPC)", "domain": "upc.edu", "url": "https://www.fib.upc.edu", "country": "Spain", "region": "Europe", "funding_type": "FPU / Severo Ochoa PhD Grant", "specialty": "FIB, Informatics, Supercomputing"},
    {"name": "Universidad Autónoma de Madrid", "domain": "uam.es", "url": "https://www.uam.es/eps", "country": "Spain", "region": "Europe", "funding_type": "FPI / Autonomous Community Grant", "specialty": "EPS, Computer Science"},
    {"name": "University of Lisbon (Instituto Superior Técnico)", "domain": "tecnico.ulisboa.pt", "url": "https://tecnico.ulisboa.pt", "country": "Portugal", "region": "Europe", "funding_type": "FCT PhD Research Grant", "specialty": "IST, Computer Science & Engineering"},

    # --- INDIA & PAKISTAN & BANGLADESH ---
    {"name": "Indian Institute of Science (IISc Bangalore)", "domain": "iisc.ac.in", "url": "https://csa.iisc.ac.in", "country": "India", "region": "Asia", "funding_type": "MHRD / Institute Fellowship (Full Stipend)", "specialty": "CSA, AI, Electrical Sciences"},
    {"name": "IIT Bombay", "domain": "iitb.ac.in", "url": "https://www.cse.iitb.ac.in", "country": "India", "region": "Asia", "funding_type": "Institute Teaching Assistantship (TA)", "specialty": "CSE, AI, Systems"},
    {"name": "IIT Delhi", "domain": "iitd.ac.in", "url": "https://www.cse.iitd.ac.in", "country": "India", "region": "Asia", "funding_type": "Yardi School of AI / Institute TA", "specialty": "CSE, ScAI, NLP"},
    {"name": "IIT Madras", "domain": "iitm.ac.in", "url": "https://www.cse.iitm.ac.in", "country": "India", "region": "Asia", "funding_type": "HTRA Institute Fellowship", "specialty": "CSE, AI, Data Science"},
    {"name": "IIT Kanpur", "domain": "iitk.ac.in", "url": "https://www.cse.iitk.ac.in", "country": "India", "region": "Asia", "funding_type": "Institute Assistantship", "specialty": "CSE, Cyber Security"},
    {"name": "IIT Kharagpur", "domain": "iitkgp.ac.in", "url": "https://cse.iitkgp.ac.in", "country": "India", "region": "Asia", "funding_type": "Institute Research Fellowship", "specialty": "CSE, Center of Excellence in AI"},
    {"name": "IIIT Hyderabad", "domain": "iiit.ac.in", "url": "https://www.iiit.ac.in", "country": "India", "region": "Asia", "funding_type": "Kohli Center / Institute Assistantship", "specialty": "CVIT, LTRC, Robotics"},
    {"name": "LUMS (Lahore University of Management Sciences)", "domain": "lums.edu.pk", "url": "https://sbasse.lums.edu.pk/department/computer-science", "country": "Pakistan", "region": "Asia", "funding_type": "LUMS Doctoral Fellowship (Full Tuition + Stipend)", "specialty": "SBASSE Computer Science"},
    {"name": "NUST (National University of Sciences and Technology)", "domain": "nust.edu.pk", "url": "https://seecs.nust.edu.pk", "country": "Pakistan", "region": "Asia", "funding_type": "HEC Indigenous Scholarship / NUST Aid", "specialty": "SEECS, Computing & AI"},
    {"name": "Quaid-i-Azam University", "domain": "qau.edu.pk", "url": "https://qau.edu.pk/cs", "country": "Pakistan", "region": "Asia", "funding_type": "HEC Postgraduate Fellowship", "specialty": "Computer Science"},
    {"name": "BUET (Bangladesh University of Engineering and Technology)", "domain": "buet.ac.bd", "url": "https://cse.buet.ac.bd", "country": "Bangladesh", "region": "Asia", "funding_type": "BUET Graduate Teaching Assistantship", "specialty": "CSE, Algorithms, AI"},

    # --- MIDDLE EAST ---
    {"name": "KAUST (King Abdullah University of Science and Technology)", "domain": "kaust.edu.sa", "url": "https://cemse.kaust.edu.sa", "country": "Saudi Arabia", "region": "Middle East", "funding_type": "KAUST Fellowship (100% Tuition + $25k-$35k Stipend + Housing)", "specialty": "CEMSE, AI, Computer Science"},
    {"name": "King Fahd University of Petroleum and Minerals (KFUPM)", "domain": "kfupm.edu.sa", "url": "https://ccse.kfupm.edu.sa", "country": "Saudi Arabia", "region": "Middle East", "funding_type": "Full Graduate Assistantship + Stipend", "specialty": "CCSE, Computer Science, Engineering"},
    {"name": "Mohamed bin Zayed University of Artificial Intelligence (MBZUAI)", "domain": "mbzuai.ac.ae", "url": "https://mbzuai.ac.ae", "country": "United Arab Emirates", "region": "Middle East", "funding_type": "Full Presidential Scholarship (100% Tuition + Stipend + Housing)", "specialty": "Machine Learning, NLP, Computer Vision"},
    {"name": "Khalifa University", "domain": "ku.ac.ae", "url": "https://www.ku.ac.ae", "country": "United Arab Emirates", "region": "Middle East", "funding_type": "KU Graduate Scholarship (Full Support)", "specialty": "EECS, Robotics, Cyber Security"},
    {"name": "Qatar University", "domain": "qu.edu.qa", "url": "https://www.qu.edu.qa/engineering/academics/computer-science-and-engineering", "country": "Qatar", "region": "Middle East", "funding_type": "GSRA / QU Graduate Assistantship", "specialty": "Computer Science & Engineering"},
    {"name": "Technion – Israel Institute of Technology", "domain": "technion.ac.il", "url": "https://cs.technion.ac.il", "country": "Israel", "region": "Middle East", "funding_type": "Technion Graduate Fellowship", "specialty": "Taub Faculty of CS, AI, Theory"},
    {"name": "Tel Aviv University", "domain": "tau.ac.il", "url": "https://en-cs.tau.ac.il", "country": "Israel", "region": "Middle East", "funding_type": "Blavatnik / University Fellowship", "specialty": "Blavatnik School of CS"},
    {"name": "Hebrew University of Jerusalem", "domain": "huji.ac.il", "url": "https://www.cs.huji.ac.il", "country": "Israel", "region": "Middle East", "funding_type": "Benin / HUJI Doctoral Fellowship", "specialty": "Rachel and Selim Benin CS"},
    {"name": "Middle East Technical University (METU)", "domain": "metu.edu.tr", "url": "https://ceng.metu.edu.tr", "country": "Turkey", "region": "Middle East", "funding_type": "TÜBİTAK / University Assistantship", "specialty": "Computer Engineering, AI"},
    {"name": "Boğaziçi University", "domain": "boun.edu.tr", "url": "https://www.cmpe.boun.edu.tr", "country": "Turkey", "region": "Middle East", "funding_type": "TÜBİTAK / Departmental Fellowship", "specialty": "Computer Engineering"},
    {"name": "Bilkent University", "domain": "bilkent.edu.tr", "url": "https://www.cs.bilkent.edu.tr", "country": "Turkey", "region": "Middle East", "funding_type": "Full Bilkent Scholarship + Housing", "specialty": "Computer Science"},
    {"name": "American University of Beirut (AUB)", "domain": "aub.edu.lb", "url": "https://www.aub.edu.lb/msfea/ece", "country": "Lebanon", "region": "Middle East", "funding_type": "Graduate Assistantship / GA Fellowship", "specialty": "ECE & Computer Science"},

    # --- LATIN AMERICA ---
    {"name": "University of São Paulo (USP)", "domain": "usp.br", "url": "https://www.ime.usp.br", "country": "Brazil", "region": "South America", "funding_type": "CAPES / FAPESP Full Doctoral Stipend", "specialty": "IME, Computer Science, Data"},
    {"name": "State University of Campinas (UNICAMP)", "domain": "unicamp.br", "url": "https://www.ic.unicamp.br", "country": "Brazil", "region": "South America", "funding_type": "FAPESP / CNPq Fellowship", "specialty": "Institute of Computing"},
    {"name": "National Autonomous University of Mexico (UNAM)", "domain": "unam.mx", "url": "https://www.iimas.unam.mx", "country": "Mexico", "region": "North America", "funding_type": "CONAHCYT Full Fellowship", "specialty": "IIMAS, Applied Math & Computing"},
    {"name": "Monterrey Institute of Technology (Tec de Monterrey)", "domain": "tec.mx", "url": "https://tec.mx", "country": "Mexico", "region": "North America", "funding_type": "Tec / CONAHCYT Graduate Excellence", "specialty": "Computer Science & Engineering"},
    {"name": "Pontifical Catholic University of Chile", "domain": "uc.cl", "url": "https://www.ing.uc.cl/computacion", "country": "Chile", "region": "South America", "funding_type": "ANID Doctoral Fellowship", "specialty": "Computer Science, Data Science"},
    {"name": "University of Buenos Aires (UBA)", "domain": "uba.ar", "url": "https://dc.uba.ar", "country": "Argentina", "region": "South America", "funding_type": "CONICET Full Research Fellowship", "specialty": "Computer Science, Math"},
    {"name": "University of the Andes (UniAndes)", "domain": "uniandes.edu.co", "url": "https://sistemas.uniandes.edu.co", "country": "Colombia", "region": "South America", "funding_type": "MinCiencias / UniAndes Graduate Aid", "specialty": "Systems and Computing Engineering"},

    # --- AFRICA ---
    {"name": "University of Cape Town (UCT)", "domain": "uct.ac.za", "url": "https://www.cs.uct.ac.za", "country": "South Africa", "region": "Africa", "funding_type": "NRF / UCT Postgraduate Funding", "specialty": "Computer Science, AI in Africa"},
    {"name": "University of the Witwatersrand (Wits)", "domain": "wits.ac.za", "url": "https://www.wits.ac.za/csam", "country": "South Africa", "region": "Africa", "funding_type": "NRF / Wits Postgraduate Merit Award", "specialty": "Computer Science & Applied Math"},
    {"name": "Stellenbosch University", "domain": "sun.ac.za", "url": "https://cs.sun.ac.za", "country": "South Africa", "region": "Africa", "funding_type": "NRF / SU Postgraduate Merit", "specialty": "Computer Science, Machine Learning"},
    {"name": "Cairo University", "domain": "cu.edu.eg", "url": "https://fci.cu.edu.eg", "country": "Egypt", "region": "Africa", "funding_type": "Egyptian Government Graduate Scholarship", "specialty": "Faculty of Computers and AI"},
    {"name": "American University in Cairo (AUC)", "domain": "aucegypt.edu", "url": "https://sse.aucegypt.edu/departments/cse", "country": "Egypt", "region": "Africa", "funding_type": "AUC Graduate Fellowship", "specialty": "Computer Science & Engineering"},
    {"name": "University of Ibadan", "domain": "ui.edu.ng", "url": "https://sci.ui.edu.ng/computerscience", "country": "Nigeria", "region": "Africa", "funding_type": "TETFund / UI Postgraduate Grant", "specialty": "Computer Science"},
    {"name": "University of Lagos (UNILAG)", "domain": "unilag.edu.ng", "url": "https://unilag.edu.ng", "country": "Nigeria", "region": "Africa", "funding_type": "TETFund Graduate Support", "specialty": "Computer Sciences"},
    {"name": "University of Nairobi", "domain": "uonbi.ac.ke", "url": "https://computing.uonbi.ac.ke", "country": "Kenya", "region": "Africa", "funding_type": "DAAD In-Region / UoN Fellowship", "specialty": "School of Computing and Informatics"},
    {"name": "Makerere University", "domain": "mak.ac.ug", "url": "https://cis.mak.ac.ug", "country": "Uganda", "region": "Africa", "funding_type": "Sida / DAAD East Africa Grant", "specialty": "Computing & Informatics Technology"},
    {"name": "Kwame Nkrumah University of Science and Technology (KNUST)", "domain": "knust.edu.gh", "url": "https://cos.knust.edu.gh/computer-science", "country": "Ghana", "region": "Africa", "funding_type": "KNUST Bursary / DAAD", "specialty": "Computer Science"},
    {"name": "University of Ghana", "domain": "ug.edu.gh", "url": "https://dcs.ug.edu.gh", "country": "Ghana", "region": "Africa", "funding_type": "UG Postgraduate Scholarship", "specialty": "Department of Computer Science"},
    {"name": "Mohammed V University in Rabat", "domain": "um5.ac.ma", "url": "https://www.um5.ac.ma", "country": "Morocco", "region": "Africa", "funding_type": "CNRST National Excellence Fellowship", "specialty": "Informatics & Engineering"}
]

def get_all_global_countries() -> List[Dict[str, Any]]:
    """Returns sorted list of all countries with code, flag, region, and university count."""
    counts = {}
    for u in GLOBAL_UNIVERSITIES_CATALOG:
        c_name = u["country"]
        counts[c_name] = counts.get(c_name, 0) + 1

    result = []
    for c in ALL_COUNTRIES_DATA:
        result.append({
            "name": c["name"],
            "code": c["code"],
            "flag": c["flag"],
            "region": c["region"],
            "universities_count": counts.get(c["name"], 0)
        })

    # Sort alphabetically by country name
    result.sort(key=lambda x: x["name"])
    return result

def get_global_universities_by_country(country: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    """Filters universities from the global directory by country name and optional search term."""
    norm_country = normalize_country_name(country) if country and country != "all" else None
    results = []

    for u in GLOBAL_UNIVERSITIES_CATALOG:
        if norm_country and u["country"].lower() != norm_country.lower():
            continue
        if search and search.strip():
            s = search.strip().lower()
            if not (s in u["name"].lower() or s in u["domain"].lower() or s in u.get("specialty", "").lower() or s in u["country"].lower()):
                continue
        results.append(u)

    return results
