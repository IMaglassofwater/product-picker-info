"""Evidence-first discovery primitives used by the Phase 11 shadow path.

The module is deliberately deterministic: it classifies source records,
normalizes identities, extracts already-stored facts, and groups only
conservative product identities.  It performs no network or AI calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Iterable

from models import Product


ELIGIBILITY_VERSION = "eligibility-v1"
NORMALIZATION_VERSION = "identity-v1"
GROUPING_VERSION = "family-v1"
EVIDENCE_VERSION = "evidence-v1"
CONCRETE_VERSION = "concrete-v1"


@dataclass(frozen=True)
class EligibilityResult:
    content_type: str
    eligibility_status: str
    reason: str
    version: str = ELIGIBILITY_VERSION


@dataclass(frozen=True)
class ProductIdentity:
    source_title: str
    normalized_product_name: str | None
    normalized_product_name_zh: str | None
    method: str
    confidence: str
    version: str = NORMALIZATION_VERSION


@dataclass(frozen=True)
class ConcreteProductResult:
    status: str
    reason: str
    version: str = CONCRETE_VERSION


@dataclass(frozen=True)
class EvidenceFact:
    metric_name: str
    numeric_value: float | None = None
    text_value: str | None = None
    evidence_type: str = "SOURCE_NATIVE_METRIC"


@dataclass(frozen=True)
class EvidenceStrength:
    strength: str
    reasons: list[str]
    metrics_used: list[str]
    version: str = EVIDENCE_VERSION


@dataclass(frozen=True)
class FamilyMatch:
    family_key: str
    canonical_name: str
    product_type: str
    match_method: str
    match_score: float
    tokens: tuple[str, ...] = field(default_factory=tuple)


_NON_PRODUCT_PATTERNS = (
    r"\bshort film\b", r"\bfeature film\b", r"\bfilm festival\b",
    r"\bdance film\b", r"\bhorror film\b", r"\bmovie\b",
    r"\bmusic album\b", r"\blive album\b", r"\bart exhibition\b",
    r"\bdonation(?:s)? only\b", r"\bsupport (?:our|my|the) (?:film|festival|album|event)\b",
    r"\b(?:concert|music|band|fall|summer|winter|north american|european) tour 20\d{2}\b",
)
_EDITORIAL_PATTERNS = (
    r"^\d+\s+(?:best|top)\b", r"\broundup\b", r"\bnews\b",
    r"\bfilm festival support\b",
)
_PHYSICAL_HINTS = (
    "bag", "backpack", "pouch", "organizer", "holder", "bottle", "tumbler",
    "lamp", "pillow", "wallet", "opener", "board", "box", "tool", "chair",
    "table", "sleeve", "cover", "case", "rack", "container", "keychain",
    "charger", "adapter", "shoe", "hanger", "toothbrush", "headphone",
    "battery", "keyboard", "vacuum", "fan", "thermometer", "watch", "camera",
    "printer", "mower", "kettle", "scissors", "mirror", "rug", "tent", "cable",
)
_SOFTWARE_HINTS = (
    "software", "app", "api", "dashboard", "browser", "extension", "saas",
    "automation", "editor", "workspace", "agent", "analytics", "macos",
)
_STOPWORDS = {
    "a", "an", "and", "for", "the", "with", "without", "of", "to", "in",
    "on", "my", "new", "best", "review", "compact", "simple", "small",
    "lightweight", "portable", "everyday", "recycled",
}
_MATERIALS = {
    "nylon", "leather", "polyester", "abs", "titanium", "wooden", "wood",
    "steel", "aluminum", "silicone", "plastic",
}
_FAMILY_NOUNS = {
    "backpack", "pouch", "bag", "pillow", "bottle", "tumbler", "wallet",
    "lamp", "organizer", "opener", "board", "box", "holder", "sleeve",
    "software", "app", "extension", "dashboard", "agent", "editor",
}


def _has_hint(text: str, hints: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(hint)}s?\b", text) for hint in hints)


def classify_eligibility(product: Product) -> EligibilityResult:
    """Classify whether a stored source record contains an eligible product."""
    source = product.source_platform.casefold()
    text = " ".join((product.title, product.description, product.category)).casefold()
    non_product_match = any(re.search(pattern, text) for pattern in _NON_PRODUCT_PATTERNS)
    if non_product_match and not (
        source == "yanko_design" and _has_hint(text, _PHYSICAL_HINTS + _SOFTWARE_HINTS)
    ):
        return EligibilityResult(
            "NON_PRODUCT_CONTENT", "INELIGIBLE",
            "Obvious film, event, album, donation, or creator-support content.",
        )
    if source in {"indiegogo", "kickstarter"} and re.search(r"\bfilm\b", text):
        if not _has_hint(text, _PHYSICAL_HINTS + _SOFTWARE_HINTS):
            return EligibilityResult(
                "NON_PRODUCT_CONTENT", "INELIGIBLE",
                "Crowdfunding record is a film/content project without an identifiable product.",
            )
    if any(re.search(pattern, product.title.casefold()) for pattern in _EDITORIAL_PATTERNS):
        if not _has_hint(text, _PHYSICAL_HINTS + _SOFTWARE_HINTS):
            return EligibilityResult(
                "NON_PRODUCT_CONTENT", "INELIGIBLE",
                "Generic editorial/news content with no identifiable product.",
            )
    if source == "product_hunt":
        return EligibilityResult(
            "SOFTWARE_PRODUCT", "ELIGIBLE",
            "Product Hunt defaults to software unless explicit physical evidence exists.",
        )
    if source == "amazon":
        return EligibilityResult(
            "PHYSICAL_PRODUCT", "ELIGIBLE",
            "Amazon consumer trend record represents a catalog product.",
        )
    if source == "yanko_design":
        if _has_hint(text, _PHYSICAL_HINTS):
            return EligibilityResult(
                "PRODUCT_DESIGN", "ELIGIBLE",
                "Concrete product/design object is identifiable in the article.",
            )
        return EligibilityResult(
            "AMBIGUOUS", "AMBIGUOUS",
            "Design article does not deterministically identify one product object.",
        )
    if _has_hint(text, _SOFTWARE_HINTS):
        return EligibilityResult("SOFTWARE_PRODUCT", "ELIGIBLE", "Software product is identifiable.")
    if _has_hint(text, _PHYSICAL_HINTS) or (
        "reddit" in source and (
            "leather journal" in text or "dragonfly ultra" in text
        )
    ):
        return EligibilityResult("PHYSICAL_PRODUCT", "ELIGIBLE", "Physical product is identifiable.")
    if source == "kickstarter" and product.category.casefold() in {
        "product design", "design", "gadgets", "technology", "hardware",
    }:
        return EligibilityResult("PHYSICAL_PRODUCT", "ELIGIBLE", "Product campaign category is eligible.")
    return EligibilityResult(
        "AMBIGUOUS", "AMBIGUOUS", "A concrete product identity cannot be established deterministically."
    )


def classify_concrete_product(
    product: Product, eligibility: EligibilityResult,
) -> ConcreteProductResult:
    """Decide whether one browseable product object is deterministically present."""
    if eligibility.eligibility_status == "INELIGIBLE":
        return ConcreteProductResult("NON_CONCRETE", "The source record is ineligible content.")
    source = product.source_platform.casefold()
    title = " ".join(product.title.split()).casefold()
    body = " ".join(product.description.split()).casefold()
    text = f"{title} {body}"
    if source in {"amazon", "product_hunt"}:
        return ConcreteProductResult(
            "CONCRETE",
            "Catalog/software source record represents one named product.",
        )
    non_concrete_patterns = (
        r"\btrip report\b", r"\bitinerary\b", r"\b\d+\s*(?:day|week)s?\s+in\b",
        r"\bwhat do you (?:use|carry|recommend)\b", r"\bif you could redesign\b",
        r"\blong-time lurker\b", r"\bcustomer service\b", r"\bpacking list\b",
        r"\bgeneral (?:travel )?advice\b", r"\bweekend packing\b",
        r"\bseeking advi[cs]e\b",
        r"^remaining gear advice\b", r"\bpacking and bag advice\b",
        r"^help me optimize.*\b(?:setup|packing)\b",
        r"^(?:carry today|today'?s edc|on my own .*carry|night walk bag dump|monday)$",
        r"\b(?:adding|add) an edc item\b",
        r"^what backpack would you recommend(?: for me)?\??$",
        r"^save space by leaving headphones behind\??$",
        r"\b(?:comparison|compared?|tested).*\b\d+\b.*\b(?:products?|pillows?|bags?|items?)\b",
        r"\b(?:comparison|compared?|tested).*\b(?:two|three|four|five|six|seven|eight|nine|ten)\b.*\b(?:products?|pillows?|bags?|items?)\b",
    )
    if any(re.search(pattern, title) for pattern in non_concrete_patterns):
        return ConcreteProductResult(
            "NON_CONCRETE", "Trip report, itinerary, general advice, or broad discussion."
        )
    if re.search(r"\bmy edc\b|\bedc loadout\b", title):
        return ConcreteProductResult(
            "NON_CONCRETE", "Multi-item EDC/loadout record is not one product object."
        )
    if re.match(r"^\d+\s+(?:best|top)\b", title) or "best gadgets" in title:
        return ConcreteProductResult(
            "NON_CONCRETE", "Listicle or multi-product collection is not one product object."
        )
    if eligibility.eligibility_status == "AMBIGUOUS":
        return ConcreteProductResult("AMBIGUOUS", "Eligibility is unresolved.")
    if source == "yanko_design":
        if _has_hint(text, _PHYSICAL_HINTS):
            return ConcreteProductResult("CONCRETE", "One product/design object is identifiable.")
        return ConcreteProductResult("AMBIGUOUS", "No single design object can be identified.")
    if title == "my" and "leather journal" in body and "backpocket" in body:
        return ConcreteProductResult("CONCRETE", "Body identifies one pocket journal cover.")
    if source in {"reddit", "reddit_arctic_shift"} and normalize_reddit_title(product.title):
        return ConcreteProductResult("CONCRETE", "Title identifies one supported product object.")
    physical_nouns = {
        hint for hint in _PHYSICAL_HINTS if re.search(rf"\b{re.escape(hint)}s?\b", text)
    }
    software_nouns = {
        hint for hint in _SOFTWARE_HINTS if re.search(rf"\b{re.escape(hint)}s?\b", text)
    }
    if source in {"reddit", "reddit_arctic_shift"}:
        if len(physical_nouns) == 1 or len(software_nouns) >= 1:
            return ConcreteProductResult("CONCRETE", "One product concept is identifiable in the post.")
        if len(physical_nouns) > 1:
            # Multiple related words can still describe one object (for example
            # a backpack with a holder), but the deterministic gate stays safe.
            title_nouns = {
                hint for hint in _PHYSICAL_HINTS
                if re.search(rf"\b{re.escape(hint)}s?\b", title)
            }
            if len(title_nouns) == 1:
                return ConcreteProductResult("CONCRETE", "Title identifies one primary product object.")
            return ConcreteProductResult("AMBIGUOUS", "Multiple possible product objects are present.")
        return ConcreteProductResult("AMBIGUOUS", "No concrete product noun is identifiable.")
    if source in {"kickstarter", "indiegogo"}:
        if physical_nouns or software_nouns:
            return ConcreteProductResult("CONCRETE", "Campaign describes a specific product object.")
        return ConcreteProductResult("AMBIGUOUS", "Campaign product object is not deterministic.")
    return ConcreteProductResult("AMBIGUOUS", "No source-specific concrete-product rule matched.")


def normalize_identity(
    product: Product,
    eligibility: EligibilityResult,
    existing_chinese_name: str | None = None,
    concrete: ConcreteProductResult | None = None,
) -> ProductIdentity:
    """Return a conservative, versioned identity without inventing facts."""
    if eligibility.eligibility_status == "INELIGIBLE":
        return ProductIdentity(product.title, None, None, "ineligible", "UNRESOLVED")
    title = " ".join(product.title.split()).strip()
    description = " ".join(product.description.split()).strip()
    if concrete and concrete.status != "CONCRETE":
        return ProductIdentity(
            title, None, existing_chinese_name,
            "non_concrete" if concrete.status == "NON_CONCRETE" else "unresolved",
            "UNRESOLVED",
        )
    if title.casefold() in {"my", "my edc", "this", "help", "question"}:
        match = re.search(
            r"\b((?:pocket\s+)?(?:leather\s+)?(?:journal|notebook)\s+cover)\b",
            description, re.I,
        )
        if match:
            name = match.group(1).title()
            zh = existing_chinese_name or (
                "口袋皮革笔记本套" if "leather" in name.casefold() else None
            )
            return ProductIdentity(title, name, zh, "description_pattern", "HIGH")
        if "leather journal" in description.casefold() and "backpocket" in description.casefold():
            return ProductIdentity(
                title, "Pocket Leather Journal Cover",
                existing_chinese_name or "口袋皮革笔记本套",
                "description_context_rule", "HIGH",
            )
        return ProductIdentity(title, None, existing_chinese_name, "vague_source_title", "UNRESOLVED")
    if product.source_platform.casefold() == "product_hunt":
        tagline = str(product.raw_data.get("tagline") or description).strip()
        tagline = re.sub(r"\s*(?:Discussion\s*\|\s*Link)\s*$", "", tagline, flags=re.I)
        if tagline:
            suffix_rules = (
                (r"sales agents?", "AI Sales Agent"),
                (r"file manager|finder should be", "macOS File Manager"),
                (r"usage limits?", "Usage Limit Monitor"),
                (r"meeting agents?", "Meeting Agent API"),
                (r"transcription", "Transcription App"),
                (r"observability", "Observability Platform"),
                (r"highlight and summarize", "Browser Research Extension"),
                (r"internal tools?", "Internal Tools Platform"),
                (r"ai models?", "On-Device AI Runtime"),
                (r"evals?|agent failures?", "AI Evaluation Tool"),
                (r"coding agent|codebase|dependencies", "Developer Tool"),
                (r"billing|processor", "Billing Platform"),
                (r"automations?", "Automation Tool"),
                (r"cms content", "CMS Tool"),
                (r"company data|signals api", "Company Data API"),
                (r"screen-sharing|onboarding", "User Onboarding Tool"),
                (r"photos?.*search|search photos", "Photo Search App"),
                (r"map", "Map App"),
                (r"agentic ide|designers and programmers", "Agentic IDE"),
                (r"agent team.*creation", "Creative AI Workspace"),
                (r"remote control.*agents?|agents?.*browser", "Agent Remote Control"),
                (r"shared workspace.*agents?|internal ai agents", "AI Agent Workspace"),
                (r"search and act.*work apps", "Workplace Search Tool"),
                (r"local project.*address", "Local Dev Routing Tool"),
                (r"dating|social.*network", "Social Networking App"),
                (r"composing.*sound", "Music Creation App"),
                (r"prototypes?.*feedback", "Prototype Feedback Tool"),
                (r"wardrobe", "Wardrobe App"),
                (r"whatsapp", "WhatsApp Assistant"),
                (r"family.*health|health.*one place", "Family Health App"),
            )
            suffix = next((label for pattern, label in suffix_rules if re.search(pattern, tagline, re.I)), None)
            if suffix:
                return ProductIdentity(
                    title, f"{title} — {suffix}", existing_chinese_name,
                    "product_hunt_product_type", "HIGH",
                )
            return ProductIdentity(
                title, f"{title} — {tagline}"[:100], existing_chinese_name,
                "product_hunt_title_tagline", "HIGH",
            )
    if product.source_platform.casefold() == "amazon":
        normalized = normalize_amazon_title(title)
        return ProductIdentity(
            title, normalized, existing_chinese_name,
            "amazon_catalog_parser", "HIGH" if normalized != title else "MEDIUM",
        )
    if "reddit" in product.source_platform.casefold():
        normalized = normalize_reddit_title(title, description)
        if normalized:
            return ProductIdentity(
                title, normalized, existing_chinese_name,
                "reddit_product_noun", "HIGH",
            )
    if product.source_platform.casefold() == "yanko_design":
        normalized = normalize_design_title(title)
        if normalized:
            return ProductIdentity(
                title, normalized, existing_chinese_name,
                "design_object_parser", "HIGH",
            )
    if len(title) >= 3 and not re.match(r"^(my|this|help)\b", title, re.I):
        return ProductIdentity(title, title, existing_chinese_name, "source_title", "MEDIUM")
    return ProductIdentity(title, None, existing_chinese_name, "unresolved", "UNRESOLVED")


_CORE_PRODUCT_PATTERNS = (
    (r"manual can opener", "Manual Can Opener"),
    (r"full length (?:floor )?mirror", "Full Length Mirror"),
    (r"metal platform bed frame", "Metal Platform Bed Frame"),
    (r"bathroom rugs?", "Bathroom Rug"),
    (r"air purifiers?", "Air Purifier"),
    (r"leaf blowers?", "Cordless Leaf Blower"),
    (r"(?:handheld )?vacuum cleaners?", "Handheld Vacuum Cleaner"),
    (r"milk frothers?", "Milk Frother"),
    (r"travel pillows?", "Travel Pillow"),
    (r"lunch box", "Insulated Lunch Box"),
    (r"tumblers?", "Insulated Tumbler"),
    (r"power ?banks?", "Power Bank"),
    (r"tea lights? candles?", "Tea Light Candles"),
    (r"fruit fly traps?", "Fruit Fly Trap"),
    (r"canopy tents?", "Canopy Tent"),
    (r"pillow inserts?", "Pillow Inserts"),
    (r"overnight oats containers?", "Overnight Oats Containers"),
)


def normalize_amazon_title(title: str) -> str:
    """Reduce catalog SEO titles to brand/model plus one core product noun."""
    for pattern, core in _CORE_PRODUCT_PATTERNS:
        match = re.search(pattern, title, re.I)
        if not match:
            continue
        prefix = title[:match.start()].strip(" -|,:/")
        words = prefix.split()
        brand_words = []
        generic_prefixes = {
            "electric", "portable", "flying", "fruit", "gaming", "pro",
            "refill", "upgraded", "cordless", "handheld",
        }
        for word in words[:4]:
            clean = re.sub(r"[^A-Za-z0-9]", "", word)
            if not clean or clean.casefold() in generic_prefixes or re.search(r"\d", clean):
                break
            if clean.isupper() or re.search(r"[a-z][A-Z]", clean) or not brand_words:
                brand_words.append(word)
            else:
                break
        brand = " ".join(brand_words).strip()
        return f"{brand} {core}".strip() if brand else core
    return re.split(r"\s*[|;]\s*|,\s*(?:Pack of|Black|White|Grey|Gray|Blue|Red)\b", title, maxsplit=1)[0][:100]


def normalize_reddit_title(title: str, description: str = "") -> str | None:
    text = title.casefold()
    rules = (
        (r"key organi[sz]er", "Key Organizer"),
        (r"(?:fanny|waist) (?:pack|pouch).*(?:without|no) zipper|without zipper.*(?:fanny|waist)", "Zipperless Fanny Pack / Waist Pack"),
        (r"(?:fanny|waist) (?:pack|pouch)", "Fanny Pack / Waist Pack"),
        (r"20\s*[–-]\s*25l.*(?:commuter|everyday|work)|(?:commuter|everyday|work).*20\s*[–-]\s*25l", "20–25L Commuter Backpack"),
        (r"40\s*[–-]\s*45l.*travel backpack", "40–45L Travel Backpack"),
        (r"toiletry kit", "Toiletry Kit"),
        (r"insulated water bottle", "Insulated Water Bottle"),
        (r"(?:backpacking|travel) pillows?", "Travel / Backpacking Pillow"),
        (r"wooden cutting board", "Wooden Cutting Board"),
        (r"travel wallets?", "Travel Wallet"),
        (r"travel adapter", "Travel Adapter"),
        (r"matador 24l adventure pack", "Matador 24L Adventure Pack"),
        (r"laptop/travel bag|laptop.*travel bag", "Laptop / Travel Bag"),
        (r"hiking.*travel.*(?:bag|backpack)", "Hiking / Travel Backpack"),
        (r"messenger/travel bag|messenger.*travel bag", "Expandable Messenger / Travel Bag"),
        (r"sling recommendations?", "Sling Bag"),
        (r"essentials pouch", "EDC Essentials Pouch"),
        (r"oakley spark max.*backpack", "Oakley Spark Max Backpack"),
        (r"osprey nebula 32l", "Osprey Nebula 32L Backpack"),
        (r"all around shoe", "All-Around Shoe"),
        (r"headphones?", "Travel Headphones"),
        (r"work backpack.*(?:hiking|tactical)|backpack.*doesn.t feel.*(?:hiking|tactical)", "Non-Tactical Work Backpack"),
        (r"dragonfly ultra|36l dragonfly", "Dragonfly Ultra 36L Backpack"),
    )
    return next((name for pattern, name in rules if re.search(pattern, text, re.I)), None)


def normalize_design_title(title: str) -> str | None:
    rules = (
        (r"desk lamp", "Desk Lamp"), (r"bedside lamp", "Bedside Lamp"),
        (r"turntable", "Turntable"), (r"coffee cups?", "Coffee Cups"),
        (r"serving tray", "Modular Serving Tray"), (r"tripod", "Camera Tripod"),
        (r"scissors", "Design Scissors"), (r"food recycler", "Food Recycler"),
        (r"litter box", "Self-Cleaning Litter Box"),
    )
    return next((name for pattern, name in rules if re.search(pattern, title, re.I)), None)


def _tokens(value: str) -> tuple[str, ...]:
    tokens = re.findall(r"[a-z0-9]+", value.casefold())
    normalized = []
    for token in tokens:
        if token in _STOPWORDS or token in _MATERIALS or token.isdigit():
            continue
        if token.endswith("ies") and len(token) > 4:
            token = token[:-3] + "y"
        elif token.endswith("s") and len(token) > 4:
            token = token[:-1]
        normalized.append(token)
    return tuple(dict.fromkeys(normalized))


def family_match(identity: ProductIdentity, content_type: str, category: str = "") -> FamilyMatch | None:
    """Create a conservative deterministic family key for an identity."""
    if not identity.normalized_product_name:
        return None
    tokens = _tokens(identity.normalized_product_name)
    token_set = set(tokens)
    # Carefully scoped concept aliases permit high-value fuzzy matches while
    # retaining distinct specialist products such as camera/hydration packs.
    if "backpack" in token_set:
        raw_name = identity.normalized_product_name.casefold()
        if "non-tactical" in raw_name or ({"non", "tactical"} <= token_set):
            return FamilyMatch(
                f"{content_type.casefold()}:work-backpack-non-tactical",
                "Non-Tactical Work Backpack", content_type,
                "protected_product_subtype", 0.95, tokens,
            )
        size_match = re.search(r"(\d+)\s*[–-]\s*(\d+)l", raw_name)
        if size_match:
            size_key = f"{size_match.group(1)}-{size_match.group(2)}l"
            use_case = "commuter" if "commuter" in token_set else "travel" if "travel" in token_set else "general"
            return FamilyMatch(
                f"{content_type.casefold()}:{use_case}-backpack-{size_key}",
                identity.normalized_product_name, content_type,
                "size_and_use_case", 0.96, tokens,
            )
        protected = next(
            (qualifier for qualifier in ("camera", "hydration", "tactical", "hiking") if qualifier in token_set),
            None,
        )
        if protected:
            return FamilyMatch(
                f"{content_type.casefold()}:backpack-{protected}",
                identity.normalized_product_name, content_type,
                "protected_product_subtype", 0.95, tokens,
            )
        if token_set & {"commuter", "work", "travel"}:
            return FamilyMatch(
                f"{content_type.casefold()}:commuter-travel-backpack",
                "Commuter / Travel Backpack", content_type,
                "use_case_alias", 0.88, tokens,
            )
    if token_set & {"fanny", "waist"} and token_set & {"pack", "pouch", "bag"}:
        return FamilyMatch(
            f"{content_type.casefold()}:fanny-waist-pack", "Fanny / Waist Pack",
            content_type, "product_synonym", 0.9, tokens,
        )
    if "pillow" in token_set and token_set & {"travel", "backpacking", "camping"}:
        return FamilyMatch(
            f"{content_type.casefold()}:travel-backpacking-pillow",
            "Travel / Backpacking Pillow", content_type,
            "use_case_alias", 0.9, tokens,
        )
    if "bottle" in token_set and token_set & {"insulated", "vacuum"}:
        return FamilyMatch(
            f"{content_type.casefold()}:insulated-water-bottle",
            "Insulated Water Bottle", content_type,
            "product_synonym", 0.92, tokens,
        )
    if "opener" in token_set and "manual" in token_set:
        return FamilyMatch(
            f"{content_type.casefold()}:manual-can-opener",
            "Manual Can Opener", content_type,
            "product_synonym", 0.95, tokens,
        )
    noun = next((token for token in tokens if token in _FAMILY_NOUNS), None)
    if not noun:
        # Unknown nouns stay isolated instead of being over-merged.
        key_tokens = tokens[:4]
        method = "normalized_identity_exact"
        score = 1.0
    else:
        qualifiers = tuple(token for token in tokens if token != noun)[:3]
        key_tokens = (noun,) + qualifiers
        method = "blocked_normalized_tokens"
        score = 0.9
    if not key_tokens:
        return None
    key = f"{content_type.casefold()}:{'-'.join(key_tokens)}"
    return FamilyMatch(
        key, identity.normalized_product_name, content_type,
        method, score, tokens,
    )


def extract_evidence(product: Product) -> list[EvidenceFact]:
    """Extract source-native facts from existing Product/raw_data only."""
    raw = product.raw_data or {}
    source = product.source_platform.casefold()
    aliases: dict[str, tuple[str, ...]]
    if "reddit" in source:
        aliases = {
            "score": ("score",), "comments": ("num_comments",),
            "subreddit": ("subreddit",), "post_date": ("created_utc", "published_at"),
        }
    elif "amazon" in source:
        aliases = {
            "price": ("price",), "rating": ("rating",),
            "review_count": ("review_count",), "rank": ("rank",),
            "rank_change": ("rank_change",),
        }
    elif "kickstarter" in source:
        aliases = {
            "backers": ("backers", "backers_count"), "pledged": ("pledged", "funding"),
            "goal": ("goal",), "funding_percentage": ("funding_percentage", "percent_funded"),
            "deadline": ("deadline",), "campaign_status": ("campaign_status", "state"),
        }
    elif "indiegogo" in source:
        aliases = {
            "backers": ("backer_count", "backerCount", "backers"),
            "funds_raised": ("funds_gathered", "fundsGathered", "funding"),
            "goal": ("campaign_goal", "campaignGoal", "goal"),
            "funding_percentage": ("funding_percentage",),
            "comment_count": ("comment_count", "commentCount"),
            "campaign_status": ("campaign_status", "status"),
        }
    elif source == "product_hunt":
        aliases = {
            "tagline": ("tagline",), "launch_date": ("published_at",),
            "topics": ("topics", "categories"), "description": ("description",),
        }
    elif source == "yanko_design":
        aliases = {
            "article_date": ("published_at",), "categories": ("categories",),
            "tags": ("tags",), "designer": ("designer", "company"),
        }
    else:
        aliases = {}
    facts: list[EvidenceFact] = []
    for metric, keys in aliases.items():
        value = next((raw[key] for key in keys if raw.get(key) not in (None, "", [])), None)
        if value is None:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            facts.append(EvidenceFact(metric, float(value)))
        else:
            text = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
            facts.append(EvidenceFact(metric, text_value=text[:1000]))
    return facts


def assess_evidence_strength(
    source_platform: str,
    facts: Iterable[EvidenceFact],
    *,
    independent_source_count: int = 1,
) -> EvidenceStrength:
    """Explain evidence strength with source-specific, non-commercial rules."""
    values = {fact.metric_name: fact.numeric_value for fact in facts if fact.numeric_value is not None}
    source = source_platform.casefold()
    strength = "WEAK"
    reasons: list[str] = []
    if "reddit" in source:
        comments, score = values.get("comments", 0), values.get("score", 0)
        reasons = [f"Reddit: {int(comments)} comments", f"Reddit: score {int(score)}"]
        strength = "STRONG" if comments >= 25 and score >= 25 else "MODERATE" if comments >= 5 or score >= 10 else "WEAK"
    elif "amazon" in source:
        reviews, rating = values.get("review_count", 0), values.get("rating", 0)
        reasons = [f"Amazon: {int(reviews)} reviews", f"Amazon: rating {rating:g}"]
        strength = "STRONG" if reviews >= 500 and rating >= 4 else "MODERATE" if reviews >= 50 else "WEAK"
    elif "kickstarter" in source or "indiegogo" in source:
        backers = values.get("backers", 0)
        funding = values.get("funding_percentage", 0)
        reasons = [f"Crowdfunding: {int(backers)} backers", f"Crowdfunding: {funding:g}% funded"]
        strength = "STRONG" if backers >= 500 and funding >= 100 else "MODERATE" if backers >= 50 or funding >= 100 else "WEAK"
    else:
        reasons = ["Only descriptive source metadata is currently available."]
    if independent_source_count >= 2:
        reasons.append(f"Observed across {independent_source_count} independent sources")
        strength = "STRONG" if strength == "MODERATE" else "MODERATE" if strength == "WEAK" else strength
    return EvidenceStrength(strength, reasons, sorted(values), EVIDENCE_VERSION)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
