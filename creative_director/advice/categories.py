"""Content-category classification, per niche.

Categories are CONTENT subtopics *within a niche* (a food reel is a recipe /
baking / drinks…; a fitness reel is calisthenics / powerlifting / mobility…),
distinct from the talking-vs-demo archetype. We classify from the caption via
keyword rules: high precision where they fire, and where they don't the UI
falls back to a "pick your category" dropdown (so the creator's correction
becomes a free training label).

The taxonomy is niche-scoped: ``classify(text, niche)`` and
``dropdown_options(niche)`` only ever consider the categories that belong to
that niche, so a food reel can never be offered "Powerlifting". ``label_for``
stays global — keys are unique across niches, so a key alone identifies a label.

Method comparison that led here (see scripts/classify_categories*.py):
  - thumbnail CLIP zero-shot: full coverage but ~noise (random-frame thumbs)
  - caption-embedding zero-shot: ~noise (casual/promo captions)
  - caption keyword rules: best precision, ~57% coverage  <-- this
The no-keyword gap is fundamental (many captions are personal/promo, not
descriptive) — handled by the override dropdown, not by more keywords/data.
"""
from __future__ import annotations

import re
from typing import Optional

# --- global key -> display label (keys are UNIQUE across all niches) ---------
# label_for() reads this, niche-agnostically; NICHE_CATEGORIES below restricts
# which keys are *offered* for a given niche.
CATEGORIES: dict[str, str] = {
    # fitness
    "calisthenics": "Calisthenics / bodyweight",
    "weights": "Gym weights / bodybuilding",
    "mobility": "Mobility / rehab",
    "yoga": "Yoga / pilates",
    "functional": "Functional / HIIT",
    "powerlifting": "Powerlifting",
    "running": "Running / outdoor",
    "nutrition": "Nutrition / supplements",
    # food
    "recipe": "Recipe / cooking",
    "baking": "Baking / desserts",
    "drinks": "Drinks / cocktails",
    "restaurant": "Restaurant / food tour",
    "mealprep": "Meal prep",
    "quickeats": "Quick & easy eats",
    # travel
    "destination": "Destination guide",
    "traveltips": "Travel tips / hacks",
    "travelvlog": "Travel vlog",
    "budget": "Budget travel",
    "luxury": "Luxury travel",
    "adventure": "Adventure / outdoor",
    # fashion
    "ootd": "Outfit of the day",
    "haul": "Haul / try-on",
    "styling": "Styling tips",
    "thrift": "Thrift / vintage",
    "accessories": "Accessories",
    "grwm": "Get ready with me",
}

CATEGORY_KEYS = list(CATEGORIES)

# --- which categories belong to which niche ----------------------------------
NICHE_CATEGORIES: dict[str, list[str]] = {
    "fitness": [
        "calisthenics", "weights", "mobility", "yoga",
        "functional", "powerlifting", "running", "nutrition",
    ],
    "food": ["recipe", "baking", "drinks", "restaurant", "mealprep", "quickeats"],
    "travel": [
        "destination", "traveltips", "travelvlog", "budget", "luxury", "adventure",
    ],
    "fashion": ["ootd", "haul", "styling", "thrift", "accessories", "grwm"],
}

# Legacy / alias niche names that map onto a base taxonomy.
_NICHE_SYNONYMS: dict[str, str] = {
    "cooking": "food",
    "beauty": "fashion",
}


def _base(niche: Optional[str]) -> Optional[str]:
    """Resolve a stored niche string to a base taxonomy key, or None.

    Handles the platform prefix and candidate-pool suffix conventions, e.g.
    ``ig_food`` / ``ig_food_candidates`` / ``cooking`` -> ``"food"``.
    Returns None for niches with no defined taxonomy (caller falls back to the
    full union so the dropdown still works).
    """
    if not niche:
        return None
    n = niche.strip().lower()
    for pre in ("ig_", "yt_", "youtube_", "instagram_"):
        if n.startswith(pre):
            n = n[len(pre):]
            break
    if n.endswith("_candidates"):
        n = n[: -len("_candidates")]
    n = _NICHE_SYNONYMS.get(n, n)
    return n if n in NICHE_CATEGORIES else None


def _keys_for(niche: Optional[str]) -> list[str]:
    """Category keys offered for a niche (full union when niche is unknown)."""
    base = _base(niche)
    return NICHE_CATEGORIES[base] if base is not None else CATEGORY_KEYS


# --- keyword rules (per category) --------------------------------------------
_KEYWORDS: dict[str, list[str]] = {
    # ---- fitness ----
    "calisthenics": [
        r"calisthenic", r"pull[- ]?up", r"chin[- ]?up", r"\bdips?\b", r"muscle[- ]?up",
        r"push[- ]?up", r"handstand", r"planche", r"front lever", r"\bbar(s)?\b",
        r"bodyweight", r"street workout",
    ],
    "weights": [
        r"bodybuild", r"hypertroph", r"dumbbell", r"bicep", r"tricep", r"chest day",
        r"back day", r"leg day", r"isolation", r"\bmachine", r"\bcable", r"physique",
        r"\bbulk", r"\bcut(ting)?\b", r"delts?", r"quads?", r"hip thrust", r"glute",
    ],
    "mobility": [
        r"mobility", r"stretch", r"\brehab", r"prehab", r"flexibilit", r"hip flexor",
        r"range of motion", r"\brom\b", r"posture", r"sciatic", r"knee pain",
        r"shoulder pain", r"warm[- ]?up", r"\bpain\b",
    ],
    "yoga": [r"\byoga", r"pilates", r"vinyasa", r"namaste", r"asana", r"breathwork"],
    "functional": [
        r"\bhiit\b", r"crossfit", r"conditioning", r"functional", r"circuit",
        r"\bamrap\b", r"\bemom\b", r"\bwod\b", r"kettlebell", r"burpee", r"metcon",
    ],
    "powerlifting": [
        r"powerlift", r"\bsquat", r"deadlift", r"bench press", r"\b1rm\b", r"\bpr\b",
        r"one rep max", r"big 3", r"\bsumo\b", r"lockout", r"barbell",
    ],
    "running": [
        r"\brun(ning|ner)?\b", r"\b5k\b", r"\b10k\b", r"marathon", r"sprint",
        r"\bjog", r"\bpace\b", r"mileage", r"\btrail",
    ],
    "nutrition": [
        r"\bprotein\b", r"\bcreatine\b", r"supplement", r"\bmacros?\b", r"calorie",
        r"\bdiet\b", r"\bbcaa", r"pre[- ]?workout", r"electrolyte", r"\bcut(ting)? weight",
    ],
    # ---- food ----
    "recipe": [
        r"recipe", r"how to make", r"ingredient", r"\bcook(ing)?\b", r"homemade",
        r"\bdish\b", r"savou?ry", r"\bsauce\b", r"\bmarinade", r"\bseason(ing)?",
    ],
    "baking": [
        r"bak(e|ing|ed)", r"\bcake", r"cookie", r"dessert", r"pastry", r"\bdough",
        r"frosting", r"\bbread\b", r"\bpie\b", r"muffin", r"brownie", r"\bsweet",
    ],
    "drinks": [
        r"cocktail", r"mocktail", r"smoothie", r"\bdrink", r"\blatte", r"\bcoffee",
        r"matcha", r"\bjuice", r"beverage", r"\bboba", r"espresso",
    ],
    "restaurant": [
        r"restaurant", r"\beat(ing)? out", r"food tour", r"hidden gem", r"\bcafe\b",
        r"\bmenu\b", r"\breview", r"\bfoodie", r"best .* in", r"where to eat",
    ],
    "mealprep": [
        r"meal[- ]?prep", r"high[- ]?protein", r"\bportion", r"batch cook",
        r"\bprep\b", r"weekly meals", r"lunch box", r"\bbento",
    ],
    "quickeats": [
        r"\b\d+[- ]?minute", r"\bquick\b", r"\beasy\b", r"\bsnack", r"\d+[- ]?ingredient",
        r"\blazy\b", r"air ?fryer", r"\b5 min", r"no[- ]?cook", r"\bfast\b",
    ],
    # ---- travel ----
    "destination": [
        r"\bguide\b", r"things to do", r"must[- ]?(visit|see|do)", r"\btop \d+",
        r"itinerary", r"where to go", r"bucket list", r"\bin \d+ days", r"hidden gem",
    ],
    "traveltips": [
        r"travel tip", r"travel hack", r"\bpacking\b", r"\bvisa\b", r"carry[- ]?on",
        r"\bairport", r"layover", r"jet ?lag", r"travel mistake", r"\bbooking",
    ],
    "travelvlog": [
        r"\bvlog", r"\bday \d+", r"\btrip\b", r"\bjourney", r"come with me",
        r"travel diary", r"\bdiaries", r"\bgetaway", r"\bweekend in",
    ],
    "budget": [
        r"\bbudget", r"\bcheap", r"affordable", r"under \$?\d+", r"backpack",
        r"\bhostel", r"save money", r"on a budget", r"\bbroke\b",
    ],
    "luxury": [
        r"luxur(y|ious)", r"\b5[- ]?star", r"\bresort", r"first class", r"business class",
        r"\bvilla", r"\bspa\b", r"\bsuite\b", r"overwater", r"private",
    ],
    "adventure": [
        r"hik(e|ing)", r"\btrek", r"\bdive\b", r"\bsurf", r"\bsafari", r"mountain",
        r"waterfall", r"\bjungle", r"adventure", r"\bclimb", r"\bcamp(ing)?",
    ],
    # ---- fashion ----
    "ootd": [
        r"\bootd\b", r"\boutfit", r"what i wore", r"\bfit check", r"\blookbook",
        r"daily look", r"\bwore\b", r"outfit of the day",
    ],
    "haul": [
        r"\bhaul", r"try[- ]?on", r"unboxing", r"\bshein", r"\bzara\b", r"\bordered",
        r"\bbought", r"\bnew in\b", r"\bwishlist",
    ],
    "styling": [
        r"how to style", r"styling", r"style tip", r"\bpair(ing|ed)?\b", r"\bcapsule",
        r"fashion tip", r"\bstyle (it|this)", r"ways to wear", r"dress code",
    ],
    "thrift": [
        r"thrift", r"\bvintage", r"second[- ]?hand", r"\bflip\b", r"upcycl",
        r"\bdepop", r"\bpreloved", r"\bthrifted",
    ],
    "accessories": [
        r"\bbag\b", r"\bshoes\b", r"\bheels\b", r"jewel(ry|lery)", r"\bwatch\b",
        r"sunglasses", r"\bpurse", r"\bearring", r"\bnecklace", r"\bsneaker",
    ],
    "grwm": [
        r"\bgrwm\b", r"get ready with me", r"\bmakeup", r"skincare", r"\bglam",
        r"\bbeauty", r"\bmua\b", r"\bhair(style)?", r"\bnails\b",
    ],
}
_COMPILED = {k: [re.compile(p, re.IGNORECASE) for p in pats] for k, pats in _KEYWORDS.items()}


def classify(
    text: Optional[str], niche: Optional[str] = None
) -> tuple[Optional[str], list[tuple[str, int]]]:
    """Return (best_category_key | None, ranked [(key, hit_count), ...]).

    Only categories belonging to ``niche`` are considered (full union when the
    niche has no defined taxonomy). ``best`` is None when no keyword fires (the
    UI shows the dropdown). The ranked list lets the UI pre-sort the dropdown.
    """
    keys = _keys_for(niche)
    blob = text or ""
    scores = {k: sum(1 for rx in _COMPILED[k] if rx.search(blob)) for k in keys}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best = ranked[0][0] if ranked and ranked[0][1] > 0 else None
    return best, ranked


def label_for(key: Optional[str]) -> str:
    """Human display label for a category key (or 'Uncategorized')."""
    return CATEGORIES.get(key or "", "Uncategorized")


def dropdown_options(niche: Optional[str] = None) -> list[dict]:
    """Category options for the override dropdown, scoped to ``niche``."""
    return [{"key": k, "label": CATEGORIES[k]} for k in _keys_for(niche)]
