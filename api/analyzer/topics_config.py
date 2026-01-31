# api/analyzer/topics_config.py

from typing import Dict, List

# Themen-Buckets basierend auf deinen KPIs (stark vereinfacht erstmal)
TOPIC_KEYWORDS: Dict[str, List[str]] = {
    # 1) Klima / Emissionen
    "climate_emissions": [
        "co2",
        "co₂",
        "ghg",
        "greenhouse gas",
        "emissions",
        "carbon footprint",
        "scope 1",
        "scope 2",
        "scope 3",
        "dekarbonisierung",
        "klimaneutral",
        "net zero",
    ],

    # 2) Wasser & Verschmutzung (inkl. Mikroplastik!)
    "water_pollution": [
        "water withdrawal",
        "water abstraction",
        "wasserentnahme",
        "groundwater",
        "surface water",
        "wastewater",
        "abwasser",
        "effluent",
        "discharge",
        "microplastic",
        "mikroplastik",
        "plastic pollution",
        "nutrient runoff",
        "eutrophication",
    ],

    # 3) Küsten- & Ökosystemschutz
    "ecosystems": [
        "biodiversity",
        "marine biodiversity",
        "wetlands",
        "mangroves",
        "seagrass",
        "coral reef",
        "reefs",
        "coastal protection",
        "coastline",
        "estuaries",
        "river basin",
        "watershed",
        "ocean health",
        "gewässer",
        "fluss",
        "see",
        "meer",
    ],

    # 4) Blue Carbon / Kohlenstoffbindung
    "blue_carbon": [
        "blue carbon",
        "carbon sequestration",
        "carbon sequestered",
        "carbon removal",
        "negative emissions",
    ],

    # 5) Sozio-ökonomische Wirkungen
    "socioeconomic": [
        "jobs created",
        "employment",
        "local communities",
        "fisheries",
        "artisanal fishers",
        "livelihoods",
        "women employed",
        "training",
        "capacity building",
        "education program",
    ],

    # 6) Allgemeine ESG / Nachhaltigkeit
    "generic_esg": [
        "sustainability report",
        "sustainability reporting",
        "nachhaltigkeitsbericht",
        "esg",
        "environmental performance",
        "sustainable development",
        "sdg",
        "sdgs",
        "un sdg",
        "materiality assessment",
        "non-financial report",
    ],
}

# Seiten, die sehr wahrscheinlich Müll sind (Login, Cookie, 404, etc.)
OBVIOUSLY_USELESS_HINTS: List[str] = [
    "cookie consent",
    "we use cookies",
    "all rights reserved",
    "page not found",
    "404 not found",
    "enable javascript",
    "sign in",
    "login",
    "register",
    "password",
    "current vacancies",
    "job openings",
    "career opportunities",
]
