"""Buying-signal taxonomy + a v0.2 keyword classifier.

v0.3 adds an LLM classifier that reads the full payload (title + excerpt + transcript)
and returns category + confidence. This module's classify() is what gets called either way.
"""
from __future__ import annotations
from typing import Literal

SignalCategory = Literal[
    "procurement", "partnerships", "facilities",
    "investments", "products", "major", "none",
]

# Keyword cues per category. Order matters: the first category whose cues
# match strongly wins. Tune as we see real traffic.
RULES: list[tuple[SignalCategory, list[str]]] = [
    ("procurement",  ["rfp", "rfq", "rfi", "carrier bid", "freight bid",
                      "transportation procurement", "vendor change",
                      "carrier selection", "logistics provider",
                      "carrier program", "freight program", "lane awards",
                      "transportation rfp"]),
    ("facilities",   ["new facility", "new plant", "new dc", "distribution center",
                      "cross-dock", "manufacturing plant", "processing plant",
                      "processing facility", "warehouse", "expansion",
                      "relocation", "automation", "breaks ground", "ribbon-cutting",
                      "opens new", "groundbreaking", "build a new", "new site"]),
    ("investments",  ["acquisition", "acquires", "to acquire", "merger",
                      "divest", "capex", "capital raise", "fleet",
                      "equipment investment", "ipo", "growth round",
                      "series ", "funding round"]),
    ("partnerships", ["partnership", "joint venture", "exclusive distribution",
                      "supplier agreement", "channel partner", "contract win",
                      "new customer", "inks deal", "strikes deal",
                      "multi-year agreement"]),
    ("products",     ["new product", "product launch", "line extension",
                      "new sku", "rolls out", "introduces", "launches new",
                      "unveils"]),
    ("major",        ["earnings", "guidance", "exec hire", "appoints",
                      "names new", "vp of supply chain", "head of logistics",
                      "coo", "restructuring", "recall", "regulatory",
                      "supply chain costs", "supply chain pain"]),
]


# Category weights for relevance scoring — high-value categories deserve a
# meaningful score bump because they survive the freshness gate's age-vs-score
# tradeoff better. Applied in newton.prospects.monitor.annotate().
CATEGORY_SCORE_BOOST: dict[SignalCategory, float] = {
    "procurement": 0.30,   # direct buying intent — biggest bump
    "facilities":  0.25,
    "investments": 0.25,
    "partnerships":0.20,
    "products":    0.15,
    "major":       0.10,
    "none":        0.00,
}


def classify(text: str) -> tuple[SignalCategory, list[str]]:
    """Return (category, matched_cues). Falls through to 'none'."""
    t = (text or "").lower()
    for category, cues in RULES:
        hits = [c for c in cues if c in t]
        if hits:
            return category, hits
    return "none", []
