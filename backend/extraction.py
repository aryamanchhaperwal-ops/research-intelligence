import hashlib
import re

"""Deterministic entity extraction and normalization.

Heuristics only - no external models. Every accepted entity is a capitalized
phrase observed verbatim in source text, classified into a research type and
graded by signal strength. Ordinary words, months, generic document/navigation
terms, numbers, dates, and common adjectives are rejected rather than emitted
as entities.
"""


MONTHS = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
    "nov", "dec",
}
DAYS = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}
DEMONYMS = {
    "american", "british", "german", "french", "indian", "pakistani", "chinese",
    "japanese", "russian", "canadian", "australian", "european", "asian",
    "african", "arab", "italian", "spanish", "korean", "turkish", "mexican",
    "brazilian", "dutch", "swiss", "irish", "scottish", "welsh", "polish",
    "swedish", "norwegian", "danish", "finnish", "portuguese", "greek",
    "israeli", "belgian", "austrian", "hungarian", "czech", "ukrainian",
    "soviet", "romanian", "bulgarian", "serbian", "croatian", "slovenian",
    "vietnamese", "thai", "indonesian", "malaysian", "filipino", "egyptian",
    "nigerian", "kenyan", "argentine",
}
# Generic document / navigation / boilerplate vocabulary that is not research.
GENERIC_DOC_WORDS = {
    "contents", "references", "external", "further", "retrieved", "archived",
    "navigation", "categories", "category", "jump", "main", "sample", "demo",
    "text", "url", "http", "https", "webarchive", "wikidata", "wikimedia",
    "wikipedia", "articles", "article", "pages", "page", "module", "short",
    "avoid", "learn", "editing", "edit", "figure", "figures", "table", "tables",
    "caption", "download", "general", "unsorted", "notes", "bibliography",
    "commons", "thumbnail", "toolbox", "views", "find", "go", "search",
    "donate", "create", "account", "contributions", "policy", "disclaimer",
    "privacy", "developers", "statistics", "foundation", "gallery", "read",
    "later", "first", "last", "next", "previous", "loading", "need", "your",
    "user", "users", "contact", "help", "party", "here", "all", "use", "about",
}
# Standalone words that are adjectives or adjective-like leading tokens of
# compounds ("General", "Artificial", "Deep", "Neural") and are meaningless
# without a noun head.
ADJECTIVAL_WORDS = {
    "general", "artificial", "deep", "machine", "neural", "natural", "applied",
    "modern", "digital", "intelligent", "early", "late", "living", "social",
    "computational", "clinical", "environmental", "financial", "industrial",
    "legal", "medical", "theoretical", "statistical", "urban", "cultural",
    "political", "economic", "global", "national", "regional", "local",
    "virtual", "augmented", "reinforcement", "supervised", "unsupervised",
    "generative", "predictive", "symbolic", "classical", "cognitive",
}
# High-frequency capitalized ordinary nouns/verbs/common words that appear
# mid-text (headings, prose) but are not research entities.
COMMON_CAPITALIZED_WORDS = {
    "research", "result", "results", "data", "study", "studies", "development",
    "approach", "approaches", "performance", "task", "tasks", "system",
    "systems", "network", "networks", "method", "methods", "model", "models",
    "algorithm", "algorithms", "technology", "technologies", "application",
    "applications", "chapter", "section", "sections", "part", "parts",
    "volume", "series", "report", "reports", "paper", "papers", "type",
    "types", "group", "groups", "committee", "university", "institute",
    "company", "companies", "government", "ministry", "council",
    "organization", "organizations", "example", "examples", "using", "used",
    "learning", "training", "work", "works", "based", "related", "known",
    "including", "such", "those", "these", "they", "their", "most", "many",
    "some", "with", "from", "into", "after", "during", "before", "between",
    "among", "under", "over", "through", "while", "where", "when", "what",
    "which", "who", "how", "why", "the", "and", "or", "but", "for", "nor",
    "not", "very", "more", "less", "field", "areas", "area", "topic", "topics",
    "name", "names", "source", "sources", "evidence", "finding", "findings",
    "key", "role", "roles", "number", "several", "within", "across",
}
# Multi-word boilerplate that must never be emitted as an entity.
GENERIC_PHRASES = {
    "external links", "further reading", "see also", "jump to", "retrieved",
    "retrieved from", "archived from", "original from", "webarchive template",
    "main article", "main page", "table of contents", "categories navigation",
    "page history", "recent changes", "create account", "log in", "edit this",
    "this article", "article text", "plain text", "references section",
    "notes section", "external sources", "further information", "related topics",
    "list of", "part of", "example of", "types of", "kind of", "form of",
    "sample content", "sample text", "sample organization", "sample community",
    "sample topic", "sample event", "the article", "the paper",
}
# Bare suffix words that are meaningless on their own.
BARE_SUFFIX_WORDS = {
    "university", "institute", "company", "corporation", "corp", "inc", "ltd",
    "llc", "committee", "council", "agency", "organization", "group",
    "foundation", "association", "commission", "ministry", "government",
    "systems", "software", "platform", "database", "algorithm", "model",
    "machine", "laboratory", "device", "network", "application", "journal",
    "press", "times", "monthly", "review", "observer", "post", "chronicle",
    "daily", "weekly", "bulletin", "gazette", "era", "movement", "reform",
    "rebellion", "campaign", "agreement", "conference", "summit", "treaty",
    "famine", "migration", "war", "revolution", "independence", "protest",
    "exhibition",
}
ORGANIZATION_TERMS = re.compile(
    r"\b(Inc|Corp|Corporation|Company|Institute|University|Agency|Group|"
    r"Organization|Ltd|LLC|Foundation|Council|Committee|Laboratories|Lab|"
    r"Institution|Consortium|Association|Authority|Bureau|Office|Ministry|"
    r"Commission|Society|Center|Centre)\b", re.I
)
PERSON_VERBS = re.compile(
    r"\b(said|wrote|argued|noted|states|reported|explains|explained|"
    r"added|claimed|described|observed|asserted|recalled|remembered|"
    r"announced|warns|noted that|believed|found)\b", re.I
)
EVENT_TERMS = re.compile(
    r"\b(War|Partition|Revolution|Era|Movement|Conference|Treaty|Famine|"
    r"Campaign|Protest|Exhibition|Reform|Rebellion|Independence|Migration|"
    r"Agreement|Summit|Opening|Launch|Crisis|Disaster|Battle|Massacre|"
    r"Genocide|Invasion|Breakthrough|Pandemic|Collapse|Crackdown)\b", re.I
)
TECHNOLOGY_TERMS = re.compile(
    r"\b(System|Software|Application|Platform|Database|Algorithm|Model|"
    r"Machine|Laboratory|Device|Network|Framework|Engine|Compiler|"
    r"Processor|Language|Toolkit|API|Runtime|Standard|Simulator)\b", re.I
)
PUBLICATION_TERMS = re.compile(
    r"\b(Journal|Press|Times|Gazette|Bulletin|Monthly|Review|Observer|"
    r"Post|Chronicle|Daily|Weekly|Magazine|Newspaper)\b", re.I
)
NAME_PREFIXES = re.compile(r"^(Mrs|Ms|Mr|Dr|Prof|Professor|Sir|Sri|Begum|Janab)\.?\s")
GEO_GAZETTEER = {
    "India", "Pakistan", "Bangladesh", "Kashmir", "Bengal", "Punjab", "Sindh",
    "Delhi", "Lahore", "Dhaka", "Calcutta", "Kolkata", "Amritsar", "New Delhi",
    "London", "New York", "Bombay", "Madras", "Lucknow", "Hyderabad", "Karachi",
    "Europe", "Asia", "America", "Africa", "China", "Japan", "Nepal", "Assam",
    "Sialkot", "Gujranwala", "Faisalabad", "Jalandhar", "Haryana", "Himachal",
    "Cambridge", "Oxford", "Silicon Valley", "Boston", "Chicago", "San Francisco",
    "Los Angeles", "Washington", "Berlin", "Paris", "Rome", "Madrid", "Tokyo",
    "Beijing", "Shanghai", "Seoul", "Moscow", "Geneva", "Vienna", "Ottawa",
    "Toronto", "Sydney", "Melbourne", "Seattle", "Austin", "Houston", "Denver",
    "Stanford", "California", "Texas", "Massachusetts", "Germany", "France",
    "Canada", "Australia", "United States", "United Kingdom", "Soviet Union",
}
KNOWN_LOCATIONS = {item.lower() for item in GEO_GAZETTEER}
KNOWN_ORGANIZATIONS = {
    "openai", "deepmind", "google", "microsoft", "apple", "amazon", "meta",
    "intel", "nvidia", "samsung", "sony", "oracle", "netflix", "salesforce",
    "ibm", "nasa", "cern", "mit", "harvard", "stanford", "oxford", "cambridge",
    "berkeley", "carnegie mellon", "united nations", "world bank",
    "world health organization", "international monetary fund",
    "disney", "bbc", "cnn", "reuters", "tesla", "spacex", "uber", "airbnb",
    "pfizer", "moderna", "bell labs", "dartmouth college",
}
KNOWN_TECHNOLOGIES = {
    "openai", "gpt", "gpt-3", "gpt-4", "chatgpt", "bert", "t5", "roberta",
    "lstm", "cnn", "rnn", "gan", "transformer", "pytorch", "tensorflow",
    "keras", "jax", "scikit-learn", "neo4j", "dall-e", "midjourney",
    "stable diffusion", "python", "java", "javascript", "c++", "kubernetes",
    "docker", "linux", "windows", "android", "ios", "react", "node.js",
    "numpy", "pandas", "hugging face", "opencv", "tiktok", "arduino",
    "raspberry pi", "ai", "ml", "dl", "nlp", "llm",
}
KNOWN_PUBLICATIONS = {
    "nature", "science", "pnas", "lancet", "wired", "economist",
    "financial times", "wall street journal", "new york times", "guardian",
    "the times", "times of india", "hindu", "arxiv",
}
KNOWN_EVENTS = {
    "rennaissance", "industrial revolution", "cold war", "world war",
    "world war i", "world war ii", "partition of india", "partition era",
    "bengal famine", "great depression", "space race", "information age",
    "digital revolution", "ai winter", "covid pandemic",
}
# Variants that must resolve to one canonical name.
ENTITY_ALIASES = {
    "open ai": "OpenAI",
    "open a.i.": "OpenAI",
    "a.i.": "AI",
    "google deepmind": "DeepMind",
    "deep mind": "DeepMind",
    "machine-learning": "machine learning",
    "deep-learning": "deep learning",
    "artificial-intelligence": "artificial intelligence",
    "gpt-3": "GPT-3",
    "gpt-4": "GPT-4",
    "chat gpt": "ChatGPT",
    "dall-e": "DALL-E",
    "stable-diffusion": "Stable Diffusion",
}
_PREFIX_CUE = re.compile(
    r"\b(by|at|of|with|from|into|in|on|for|alongside|under|led|founded|"
    r"launched|announced|published|reported|said|study)\s*\Z", re.I
)
SENTENCE_CUE = re.compile(
    r"\b(according to|said|found that|showed that|reported|stated that|argued|"
    r"noted that|suggests? that|indicates?|evidence|documented|described|"
    r"explains?|because|reveals?|concluded|confirmed|estimated|announced)\b", re.I
)
ENTITY_PHRASE = re.compile(r"\b[A-Z][\w&'-]*(?:\s+[A-Z][\w&'-]*){0,2}\b")


def _split_sentences(content):
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", content) if sentence.strip()]


KNOWN_SETS = KNOWN_ORGANIZATIONS | KNOWN_TECHNOLOGIES | KNOWN_PUBLICATIONS | KNOWN_EVENTS


def canonicalize_name(name):
    """Return (display name, canonical key). Variants collapse via aliases."""
    display = " ".join(name.split())
    key = display.lower().strip(".,;:()[]{}\"'")
    if key in ENTITY_ALIASES:
        display = ENTITY_ALIASES[key]
        key = display.lower()
    return display, key


def classify_entity(name):
    key = name.lower()
    if key in KNOWN_ORGANIZATIONS:
        return "Organization"
    if ORGANIZATION_TERMS.search(name):
        return "Organization"
    if key in KNOWN_EVENTS or EVENT_TERMS.search(name):
        return "Event"
    if NAME_PREFIXES.match(name) or PERSON_VERBS.search(name):
        return "Person"
    if key in KNOWN_PUBLICATIONS or (PUBLICATION_TERMS.search(name) and len(name.split()) >= 2):
        return "Publication"
    if key in KNOWN_TECHNOLOGIES or TECHNOLOGY_TERMS.search(name):
        return "Technology"
    if re.match(r"^[A-Z]{2,}$", name) or re.search(r"[a-z]+[A-Z]", name):
        return "Technology"
    if key in KNOWN_LOCATIONS:
        return "Location"
    return "Topic"


def _is_meaningless(name, entity_type):
    key = name.lower()
    if key in IGNORED or key in MONTHS or key in DAYS or key in DEMONYMS:
        return True
    if key in GENERIC_DOC_WORDS or key in ADJECTIVAL_WORDS:
        return True
    if key in BARE_SUFFIX_WORDS:
        return True
    if " ".join(name.split()).lower() in GENERIC_PHRASES:
        return True
    if len(name) < 2:
        return True
    if len(name) < 3 and not name.isupper():
        return True
    if entity_type == "Topic" and len(name.split()) == 1:
        return key in COMMON_CAPITALIZED_WORDS
    return False


IGNORED = {item.lower() for item in (
    "The", "This", "That", "These", "Those", "Research", "According",
    "Contents", "References", "External Links", "Retrieved", "Jump To",
    "Sample", "Demo", "Text", "URL", "Http", "Example", "Sciences",
    "Part", "Part I", "Part II", "See", "Very", "Most", "Many", "Those",
    "These", "They", "Some", "Several", "Such", "All", "Use", "More",
)}


def is_meaningless_entity(name, entity_type):
    return _is_meaningless(name, entity_type)


def _entity_confidence(name, entity_type, is_multi, has_cue, mentions):
    score = 0.5
    bonuses = {
        "Organization": 0.14, "Person": 0.14, "Location": 0.10,
        "Publication": 0.08, "Technology": 0.08, "Event": 0.06, "Topic": 0.02,
    }
    score += bonuses.get(entity_type, 0.02)
    if is_multi:
        score += 0.06
    if has_cue:
        score += 0.08
    if mentions > 1:
        score += min(0.03 * (mentions - 1), 0.15)
    score = max(0.4, min(1.0, score))
    label = "high" if score >= 0.72 else "medium" if score >= 0.58 else "low"
    return round(score, 2), label


def extract_entities(content, limit=80):
    """Extract research entities from plain text deterministically.

    Returns a list of dicts with: id, name, type, confidence, confidenceScore,
    description, mentions, sentenceIndex. IDs are stable per canonical entity
    so "Open AI" and "OpenAI" normalize to one node.
    """
    sentences = _split_sentences(content)[:600]
    found = {}
    order = []
    for sentence_index, sentence in enumerate(sentences, start=1):
        for match in ENTITY_PHRASE.finditer(sentence):
            name = re.sub(r"'?s\b.*$", "", match.group(0), flags=re.I).strip(" .")
            if not name:
                continue
            is_sentence_initial = match.start() <= 1
            prefix = sentence[max(0, match.start() - 40):match.start()]
            has_cue = bool(_PREFIX_CUE.search(prefix))
            entity_type = classify_entity(name)
            if _is_meaningless(name, entity_type):
                continue
            if len(name.split()) == 1 and is_sentence_initial:
                if entity_type not in ("Organization", "Person", "Publication",
                                       "Location", "Technology", "Event"):
                    continue
                if entity_type == "Location" and name.lower() not in KNOWN_LOCATIONS:
                    continue
                if entity_type == "Technology" and not (
                    name.lower() in KNOWN_TECHNOLOGIES
                    or re.match(r"^[A-Z]{2,}$", name)
                    or re.search(r"[a-z]+[A-Z]", name)
                ):
                    continue
            display, key = canonicalize_name(name)
            if not key or len(key) < 3:
                continue
            keyed = f"{entity_type}:{key}"
            if keyed in found:
                found[keyed]["mentions"] += 1
                continue
            entity_id = hashlib.sha256(keyed.encode("utf-8")).hexdigest()[:32]
            confidence_score, confidence_label = _entity_confidence(
                display, entity_type, len(display.split()) > 1,
                has_cue or bool(SENTENCE_CUE.search(sentence)), mentions=1,
            )
            found[keyed] = {
                "id": entity_id,
                "name": display,
                "type": entity_type,
                "confidence": confidence_label,
                "confidenceScore": confidence_score,
                "description": sentence[:220],
                "mentions": 1,
                "sentenceIndex": sentence_index,
            }
            order.append(keyed)
            if len(order) >= limit:
                return [found[keyed] for keyed in order]
    return [found[keyed] for keyed in order]