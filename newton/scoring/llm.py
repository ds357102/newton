"""LLM relevance + classification pass (v0.5).

One Claude Haiku call per event returns a unified result:
  - score: 0..1 actionability (does this prospect look ready to talk to a freight broker?)
  - category: which buying-signal bucket this falls into
  - reason: one-sentence justification, so the UI can show "why"
  - key_phrases: up to three phrases lifted from the text (also serves as matched_cues)

Designed to no-op cleanly when:
  - ANTHROPIC_API_KEY is missing
  - the `anthropic` SDK isn't installed
  - the model returns malformed JSON

In any of those cases, callers fall back to the rules-based result.

Results are cached in-memory by (url, title) hash so the same article isn't
re-classified on every refresh. Swap to Redis when we wire that up properly.
"""
from __future__ import annotations
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Optional

from ..config import settings
from ..events import Event
from ..prospects.signals import SignalCategory

log = logging.getLogger("newton.scoring.llm")

try:
    from anthropic import AsyncAnthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


# Module-level cache. (url, title) hash → LLMResult.
_CACHE: dict[str, "LLMResult"] = {}

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class LLMResult:
    score: float
    category: SignalCategory
    reason: str
    key_phrases: list[str]


SYSTEM_PROMPT = """\
You are a buying-signal classifier for a freight brokerage's prospect monitor.
For each news item about a prospect company, score it for ACTIONABILITY (how
strongly it suggests the company may need transportation services soon) and
classify the buying signal.

Categories:
- procurement: RFP/RFQ/RFI, carrier bid, vendor change, transportation procurement, freight program review (direct buying intent)
- partnerships: new customer wins, supplier deals, JVs, exclusive distribution (new volume implies new lanes)
- facilities: new plants/DCs, expansions, relocations, automation (footprint changes redraw lanes)
- investments: capex, fleet/equipment, capital raises, acquisitions, divestitures (leading indicator)
- products: launches, line extensions, new SKUs, retail expansions (new freight programs often follow)
- major: earnings + guidance, exec hires in supply chain/ops, restructuring, regulatory, recalls (material disclosures)
- none: generic mention with no buying signal

Score guidance:
- 0.85-1.00: clear, current, actionable. Owner should reach out this week.
- 0.65-0.85: relevant context. Worth saving as background.
- 0.00-0.65: mentioned but not actionable.

Output ONLY a JSON object, no prose, no code fences:
{"score": 0.0, "category": "procurement", "reason": "one sentence", "key_phrases": ["phrase1", "phrase2"]}
"""


def _cache_key(event: Event) -> str:
    url = event.payload.get("url", "") or ""
    title = event.payload.get("title", "") or ""
    return hashlib.sha1(f"{url}::{title}".encode()).hexdigest()


def _strip_fences(text: str) -> str:
    """LLMs sometimes wrap JSON in ```json ... ``` despite instructions. Strip it."""
    t = text.strip()
    if t.startswith("```"):
        parts = t.split("```")
        if len(parts) >= 2:
            t = parts[1]
            if t.startswith("json"):
                t = t[4:]
    return t.strip()


async def score_and_classify(
    event: Event,
    prospect_name: str,
    prospect_industry: str | None = None,
    *,
    model: str = DEFAULT_MODEL,
) -> Optional[LLMResult]:
    """Run the LLM pass. Returns None when key/SDK missing or call fails;
    callers should fall back to their rules-based result."""
    if not settings.anthropic_api_key:
        return None
    if not _ANTHROPIC_AVAILABLE:
        log.warning("anthropic SDK not installed; skipping LLM pass")
        return None

    cache_key = _cache_key(event)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached

    title = event.payload.get("title", "") or ""
    excerpt = event.payload.get("excerpt", "") or ""
    industry_clause = f" ({prospect_industry})" if prospect_industry else ""
    user_msg = f"Prospect: {prospect_name}{industry_clause}\nHeadline: {title}\nExcerpt: {excerpt}"

    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            model=model,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = resp.content[0].text
        data = json.loads(_strip_fences(text))
        result = LLMResult(
            score=max(0.0, min(1.0, float(data["score"]))),
            category=data["category"],
            reason=data.get("reason", ""),
            key_phrases=list(data.get("key_phrases") or [])[:3],
        )
        _CACHE[cache_key] = result
        return result
    except Exception as e:  # broad on purpose — never let LLM failure break ingestion
        log.warning(f"LLM classification failed for {title[:60]!r}: {e}")
        return None


def clear_cache() -> None:
    """For tests."""
    _CACHE.clear()
