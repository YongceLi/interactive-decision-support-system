"""Keyword dictionaries for enriching electronics reviews."""

POSITIVE_FEATURES = {
    "performance": ["fast", "smooth", "fps", "performance", "powerful", "speed", "overclock", "stable"],
    "thermals": ["cool", "temps", "temperature", "thermal", "quiet", "noise"],
    "value": ["value", "price", "worth", "deal", "affordable"],
    "software": ["driver", "software", "bios", "firmware"],
    "build": ["build", "quality", "sturdy", "solid", "design"],
}

NEGATIVE_FEATURES = {
    "performance": ["slow", "lag", "stutter", "bottleneck", "crash", "artifact"],
    "thermals": ["hot", "overheat", "thermal", "fan", "loud"],
    "value": ["expensive", "overpriced", "cost", "pricey"],
    "software": ["driver", "bug", "software", "update"],
    "build": ["cheap", "plastic", "bend", "sag"],
}

SETUP_CUES = [
    "my pc",
    "my build",
    "my setup",
    "my rig",
    "my system",
    "in my case",
]

USAGE_PATTERNS = {
    "gaming": ["gaming", "gamer", "fps", "ray tracing", "rtx"],
    "content_creation": ["render", "editing", "premiere", "blender", "stream"],
    "productivity": ["workstation", "cad", "productivity", "office"],
    "ai_research": ["ml", "ai", "training", "inference"],
}

PERFORMANCE_CUES = {
    "high-end": ["flagship", "high end", "enthusiast", "halo", "80", "90", "ti"],
    "mid-range": ["mid", "balanced", "mainstream", "70", "60"],
    "entry": ["budget", "starter", "entry", "50", "40"]
}

PRICE_KEYWORDS = {
    "budget": ["budget", "cheap", "affordable", "under", "less than"],
    "mid-range": ["mid", "reasonable", "value"],
    "premium": ["premium", "expensive", "high end", "top"],
}
