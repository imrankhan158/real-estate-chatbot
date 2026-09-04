"""
Input guard – rejects questions that are clearly off-topic before they reach the LLM.

Two checks:
1. Keyword blocklist  – catches obvious dev/coding/travel requests instantly.
2. Topic allowlist    – the message must contain at least one real-estate signal,
                        OR be a short follow-up (<=6 words) to allow conversational
                        turns like "how much?" or "tell me more".
"""

import re

# ── Blocklist ──────────────────────────────────────────────────────────────────
# Patterns that are never real-estate topics.
_BLOCKED_PATTERNS: list[str] = [
    # coding / tech
    r"\bgenerate\b.{0,30}\b(code|component|function|class|script|snippet|html|css|sql|api)\b",
    r"\b(write|create|build|make)\b.{0,30}\b(app|application|website|component|function|script|bot|chatbot|program)\b",
    r"\b(react|vue|angular|django|flask|fastapi|express|nextjs|nodejs)\b",
    r"\b(python|javascript|typescript|java|golang|rust|php|ruby|swift|kotlin)\b",
    r"\b(algorithm|recursion|loop|async|await|promise|callback|api endpoint)\b",
    r"\bdebugg?(ing)?\b",
    r"\bunit test(s|ing)?\b",
    r"\brefactor\b",
    # travel / lifestyle
    r"\b(itinerary|travel plan|flight|hotel booking|tourist|sightseeing|visa)\b",
    r"\b(recipe|cook|restaurant recommendation|food review)\b",
    # general knowledge / other
    r"\b(write (me )?(a |an )?(poem|essay|story|song|joke|email|letter|resume|cover letter))\b",
    r"\b(explain (how|what|why).{0,20}(work|function|happen))\b",
    r"\b(history of|biography|who (is|was)|what is the capital)\b",
    r"\b(math|calculus|equation|physics|chemistry|biology)\b",
    r"\b(weather forecast|stock (price|market)|crypto(currency)?|bitcoin)\b",
    r"\b(weather|forecast|temperature|climate)\b",
    r"\btranslate\b",
    r"\bsummarise|summarize\b",
]

_BLOCKED_RE = re.compile("|".join(_BLOCKED_PATTERNS), re.IGNORECASE)

# ── Allowlist ──────────────────────────────────────────────────────────────────
# A message is on-topic if it contains at least one of these signals.
_REAL_ESTATE_SIGNALS: list[str] = [
    r"\b(property|properties|listing|listings)\b",
    r"\b(apartment|flat|studio|penthouse|duplex)\b",
    r"\b(villa|townhouse|mansion|residence)\b",
    r"\b(land|plot|development|project)\b",
    r"\b(commercial|office|warehouse|retail)\b",
    r"\b(buy|purchase|sale|sell|for sale)\b",
    r"\b(rent|rental|lease|for rent)\b",
    r"\b(price|cost|value|budget|afford)\b",
    r"\b(bedroom|bathroom|sqm|sq\.?\s?m|square meter|floor plan)\b",
    r"\b(amenities|pool|gym|parking|garden|terrace|balcony)\b",
    r"\b(location|neighbourhood|district|city|area|zone)\b",
    r"\b(dubai|riyadh|jeddah|dammam|abu dhabi|muscat|doha|london|marbella|neom|alula|kafd)\b",
    r"\b(uae|saudi arabia|oman|qatar|uk|ksa)\b",
    r"\b(darglobal|dar global|wasalt)\b",
    r"\b(aston martin|lamborghini|missoni|trump estates|elie saab|dolce|gabbana)\b",
    r"\b(invest|investment|roi|yield|capital gain)\b",
    r"\b(mortgage|down payment|financing|instalment)\b",
    r"\b(show|find|list|compare|recommend|search)\b.{0,30}\b(propert|home|house|flat|villa|apartment)\b",
    r"\b(most expensive|cheapest|affordable|luxury|premium|high.?end)\b",
    r"\b(how many|how much|what is the price|available)\b",
]

_SIGNAL_RE = re.compile("|".join(_REAL_ESTATE_SIGNALS), re.IGNORECASE)

# Short follow-up messages (≤6 words) are let through so conversational turns work.
_MAX_FOLLOWUP_WORDS = 6

REJECTION_MESSAGE = (
    "I'm a real estate assistant specialised in DarGlobal and Wasalt property listings. "
    "I can help you search for properties, compare listings, check prices, and explore "
    "locations across Dubai, Saudi Arabia, and beyond. "
    "Please ask me something related to real estate."
)


def is_allowed(message: str) -> bool:
    """
    Returns True if the message should be processed, False if it should be rejected.
    """
    text = message.strip()

    # Always block explicit off-topic patterns regardless of length
    if _BLOCKED_RE.search(text):
        return False

    # Short follow-ups are fine (conversational turns like "tell me more", "how much?")
    if len(text.split()) <= _MAX_FOLLOWUP_WORDS:
        return True

    # Longer messages must contain at least one real-estate signal
    return bool(_SIGNAL_RE.search(text))
