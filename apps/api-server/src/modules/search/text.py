from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable


TOKEN_PATTERN = re.compile(r"[0-9A-Za-z\uAC00-\uD7A3]+")
KOREAN_SPATIAL_PATTERN = re.compile(
    r"([0-9A-Za-z\uAC00-\uD7A3 ]{1,30})\s*(\uC704|\uC544\uB798|\uC606|\uADFC\uCC98|\uC548|\uC55E|\uB4A4)"
)

KOREAN_PARTICLE_SUFFIXES: tuple[str, ...] = (
    "\uC5D0\uC11C",
    "\uC5D0\uAC8C\uC11C",
    "\uD55C\uD14C\uC11C",
    "\uC73C\uB85C\uBD80\uD130",
    "\uC5D0\uAC8C",
    "\uD55C\uD14C",
    "\uC73C\uB85C",
    "\uB85C",
    "\uC740",
    "\uB294",
    "\uC774",
    "\uAC00",
    "\uC744",
    "\uB97C",
    "\uC5D0",
    "\uC640",
    "\uACFC",
    "\uB3C4",
    "\uB9CC",
    "\uC758",
)

SYNONYM_GROUPS: dict[str, set[str]] = {
    "wallet": {"wallet", "wallets", "purse", "\uC9C0\uAC11", "\uCE74\uB4DC\uC9C0\uAC11"},
    "key": {
        "key",
        "keys",
        "keyring",
        "\uC5F4\uC1E0",
        "\uD0A4",
        "\uCC28\uD0A4",
        "\uC790\uB3D9\uCC28\uD0A4",
        "\uD0A4\uB9C1",
    },
    "phone": {
        "phone",
        "phones",
        "cellphone",
        "cell",
        "smartphone",
        "\uD734\uB300\uD3F0",
        "\uD578\uB4DC\uD3F0",
        "\uD3F0",
        "\uC2A4\uB9C8\uD2B8\uD3F0",
        "\uC544\uC774\uD3F0",
        "iphone",
    },
    "glasses": {
        "glasses",
        "eyeglasses",
        "spectacles",
        "sunglasses",
        "\uC548\uACBD",
        "\uC120\uAE00\uB77C\uC2A4",
    },
    "bag": {
        "bag",
        "bags",
        "backpack",
        "handbag",
        "\uAC00\uBC29",
        "\uBC31\uD329",
        "\uC5D0\uCF54\uBC31",
        "\uD578\uB4DC\uBC31",
    },
    "card": {
        "card",
        "cards",
        "\uCE74\uB4DC",
        "\uC2E0\uC6A9\uCE74\uB4DC",
        "\uCCB4\uD06C\uCE74\uB4DC",
        "\uAD50\uD1B5\uCE74\uB4DC",
    },
    "charger": {
        "charger",
        "cable",
        "adapter",
        "powerbank",
        "\uCF00\uC774\uBE14",
        "\uCDA9\uC804\uAE30",
        "\uCDA9\uC804\uCF00\uC774\uBE14",
        "\uC5B4\uB311\uD130",
        "\uBCF4\uC870\uBC30\uD130\uB9AC",
    },
    "earbuds": {
        "earbuds",
        "earbud",
        "earphones",
        "earphone",
        "airpods",
        "airpod",
        "buds",
        "galaxybuds",
        "\uC774\uC5B4\uD3F0",
        "\uC5D0\uC5B4\uD31F",
        "\uBC84\uC988",
        "\uAC24\uB7ED\uC2DC\uBC84\uC988",
        "\uBB34\uC120\uC774\uC5B4\uD3F0",
        "\uBE14\uB8E8\uD22C\uC2A4\uC774\uC5B4\uD3F0",
    },
    "laptop": {"laptop", "notebook", "\uCEF4\uD4E8\uD130", "\uB178\uD2B8\uBD81"},
    "desk": {"desk", "table", "\uCC45\uC0C1", "\uD14C\uC774\uBE14"},
    "keyboard": {"keyboard", "\uD0A4\uBCF4\uB4DC"},
    "monitor": {"monitor", "screen", "\uBAA8\uB2C8\uD130"},
    "chair": {"chair", "\uC758\uC790"},
    "bed": {"bed", "\uCE68\uB300"},
    "sofa": {"sofa", "couch", "\uC18C\uD30C"},
    "umbrella": {"umbrella", "umbrellas", "\uC6B0\uC0B0"},
    "drawer": {"drawer", "\uC11C\uB78D"},
    "shelf": {"shelf", "\uC120\uBC18"},
    "floor": {"floor", "\uBC14\uB2E5"},
    "counter": {"counter", "countertop", "\uC870\uB9AC\uB300", "\uCE74\uC6B4\uD130"},
    "sink": {"sink", "\uC2F1\uD06C\uB300"},
    "bathroom": {"bathroom", "restroom", "\uD654\uC7A5\uC2E4"},
    "kitchen": {"kitchen", "\uC8FC\uBC29"},
    "bedroom": {"bedroom", "\uCE68\uC2E4"},
    "livingroom": {"livingroom", "living", "\uAC70\uC2E4"},
}

KOREAN_LABELS: dict[str, str] = {
    "wallet": "\uC9C0\uAC11",
    "key": "\uC5F4\uC1E0",
    "phone": "\uD734\uB300\uD3F0",
    "glasses": "\uC548\uACBD",
    "bag": "\uAC00\uBC29",
    "card": "\uCE74\uB4DC",
    "charger": "\uCDA9\uC804\uAE30",
    "earbuds": "\uC774\uC5B4\uD3F0",
    "laptop": "\uB178\uD2B8\uBD81",
    "desk": "\uCC45\uC0C1",
    "keyboard": "\uD0A4\uBCF4\uB4DC",
    "monitor": "\uBAA8\uB2C8\uD130",
    "chair": "\uC758\uC790",
    "bed": "\uCE68\uB300",
    "sofa": "\uC18C\uD30C",
    "umbrella": "\uC6B0\uC0B0",
    "drawer": "\uC11C\uB78D",
    "shelf": "\uC120\uBC18",
    "floor": "\uBC14\uB2E5",
    "counter": "\uCE74\uC6B4\uD130",
    "sink": "\uC2F1\uD06C\uB300",
    "bathroom": "\uD654\uC7A5\uC2E4",
    "kitchen": "\uC8FC\uBC29",
    "bedroom": "\uCE68\uC2E4",
    "livingroom": "\uAC70\uC2E4",
}

ALIAS_TO_CANONICAL: dict[str, str] = {}
for canonical, aliases in SYNONYM_GROUPS.items():
    for alias in aliases:
        ALIAS_TO_CANONICAL[alias.lower()] = canonical

SPATIAL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\bnext to\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} \uC606",
    ),
    (
        re.compile(
            r"\bbeside\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} \uC606",
    ),
    (
        re.compile(
            r"\bnear\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} \uADFC\uCC98",
    ),
    (
        re.compile(
            r"\bin front of\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} \uC55E",
    ),
    (
        re.compile(
            r"\bbehind\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} \uB4A4",
    ),
    (
        re.compile(
            r"\binside\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} \uC548",
    ),
    (
        re.compile(
            r"\bunder\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} \uC544\uB798",
    ),
    (
        re.compile(
            r"\bbelow\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} \uC544\uB798",
    ),
    (
        re.compile(
            r"\bon top of\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} \uC704",
    ),
    (
        re.compile(
            r"\bon\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} \uC704",
    ),
    (
        re.compile(
            r"\bin\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} \uC548",
    ),
)

SPATIAL_CONNECTOR_SPLIT = re.compile(
    r"\s+(?:next to|beside|near|in front of|behind|inside|under|below|on top of|on|in)\b",
    re.I,
)

NEGATION_CUES: tuple[str, ...] = (
    "\uB9D0\uACE0",
    "\uBE60\uC9C0\uACE0",
    "\uC81C\uC678\uD558\uACE0",
    "\uC81C\uC678",
    "\uB300\uC2E0",
    "instead of",
    "other than",
    "except",
    "without",
)

QUERY_STOP_TERMS: set[str] = {
    "a",
    "an",
    "and",
    "are",
    "around",
    "can",
    "did",
    "do",
    "find",
    "for",
    "give",
    "had",
    "have",
    "help",
    "i",
    "is",
    "it",
    "last",
    "latest",
    "look",
    "me",
    "mine",
    "my",
    "please",
    "put",
    "show",
    "that",
    "the",
    "there",
    "thing",
    "was",
    "were",
    "where",
    "\uAC70",
    "\uAC83",
    "\uAE30\uC5B5",
    "\uB098",
    "\uB098\uC758",
    "\uB0B4",
    "\uB193\uC740",
    "\uB450\uC5C8\uC5B4",
    "\uB454",
    "\uB480\uB358",
    "\uB480\uB354\uB77C",
    "\uB480\uC5B4",
    "\uB480\uC9C0",
    "\uB1A8\uB354\uB77C",
    "\uB1A8\uC5B4",
    "\uB1A8\uC9C0",
    "\uB9C8\uC9C0\uB9C9",
    "\uB9C8\uC9C0\uB9C9\uC73C\uB85C",
    "\uBB3C\uAC74",
    "\uBCF4\uC5EC\uC918",
    "\uC5B4\uB514",
    "\uC5B4\uB514\uB2E4",
    "\uC5B4\uB514\uC5D0",
    "\uC5B4\uB514\uC788\uC5B4",
    "\uC5B4\uB514\uC788\uC9C0",
    "\uC5B4\uB528\uC5B4",
    "\uC5B4\uB528\uC9C0",
    "\uC788\uB358",
    "\uC788\uC5B4",
    "\uC788\uC5C8\uC5B4",
    "\uC788\uC5C8\uC9C0",
    "\uC788\uC9C0",
    "\uC81C",
    "\uC880",
    "\uCD5C\uADFC",
    "\uCC3E\uC544",
    "\uCC3E\uC544\uBD10",
    "\uCC3E\uC544\uC918",
    "\uD639\uC2DC",
}


def normalize_whitespace(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).split())


def normalize_search_query(text: str | None) -> str:
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return ""

    lowered = cleaned.lower()
    last_cue_start = -1
    last_cue = ""
    for cue in NEGATION_CUES:
        cue_start = lowered.rfind(cue)
        if cue_start > last_cue_start:
            last_cue_start = cue_start
            last_cue = cue

    if last_cue_start >= 0:
        candidate = normalize_whitespace(cleaned[last_cue_start + len(last_cue) :])
        candidate = candidate.lstrip(" ,.!?;:\u3000")
        if candidate:
            return candidate

    return cleaned


def tokenize_text(text: str | None) -> list[str]:
    if not text:
        return []
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def dedupe_strings(values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = normalize_whitespace(value)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def strip_korean_particle(token: str) -> str:
    lowered = token.lower()
    if len(lowered) <= 1:
        return lowered

    for suffix in sorted(KOREAN_PARTICLE_SUFFIXES, key=len, reverse=True):
        if lowered.endswith(suffix) and len(lowered) > len(suffix) + 1:
            return lowered[: -len(suffix)]

    return lowered


def canonicalize_token(token: str) -> str:
    normalized = strip_korean_particle(token)
    return ALIAS_TO_CANONICAL.get(normalized, normalized)


def is_query_stop_token(token: str) -> bool:
    normalized = strip_korean_particle(token)
    canonical = canonicalize_token(normalized)
    return (
        token.lower() in QUERY_STOP_TERMS
        or normalized in QUERY_STOP_TERMS
        or canonical in QUERY_STOP_TERMS
    )


def expand_terms(values: Iterable[str]) -> list[str]:
    expanded: set[str] = set()
    for value in values:
        for token in tokenize_text(value):
            stem = strip_korean_particle(token)
            canonical = canonicalize_token(stem)
            expanded.add(token)
            expanded.add(stem)
            expanded.add(canonical)
            expanded.update(SYNONYM_GROUPS.get(canonical, set()))
    return sorted(expanded)


def search_terms_from_query(text: str | None) -> list[str]:
    normalized_query = normalize_search_query(text)
    tokens = tokenize_text(normalized_query)
    if not tokens:
        return []

    meaningful_tokens = [
        strip_korean_particle(token)
        for token in tokens
        if not is_query_stop_token(token)
    ]
    return expand_terms(meaningful_tokens or tokens)


def humanize_term(value: str) -> str:
    tokens = tokenize_text(value)
    if not tokens:
        return normalize_whitespace(value)

    words: list[str] = []
    for token in tokens[:4]:
        canonical = canonicalize_token(token)
        words.append(KOREAN_LABELS.get(canonical, token))
    return " ".join(words)


def _clean_spatial_object(value: str) -> str:
    cleaned = normalize_whitespace(value)
    if not cleaned:
        return ""

    cleaned = SPATIAL_CONNECTOR_SPLIT.split(cleaned, maxsplit=1)[0]
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.I)
    return normalize_whitespace(cleaned)


def extract_spatial_hint(*texts: str | None) -> str | None:
    for text in texts:
        cleaned = normalize_whitespace(text)
        if not cleaned:
            continue

        korean_match = KOREAN_SPATIAL_PATTERN.search(cleaned)
        if korean_match:
            return f"{humanize_term(korean_match.group(1))} {korean_match.group(2)}"

        for pattern, template in SPATIAL_RULES:
            match = pattern.search(cleaned)
            if match:
                spatial_object = _clean_spatial_object(match.group(1))
                if spatial_object:
                    return template.format(obj=humanize_term(spatial_object))

    return None


def format_timestamp(value: str | None) -> str | None:
    if not value:
        return None

    normalized = value.replace("Z", "+00:00")
    try:
        timestamp = datetime.fromisoformat(normalized)
        period = "\uC624\uC804" if timestamp.hour < 12 else "\uC624\uD6C4"
        display_hour = timestamp.hour % 12 or 12
        display_time = f"{period} {display_hour}\uC2DC"
        if timestamp.minute:
            display_time += f" {timestamp.minute}\uBD84"
        return f"{timestamp.strftime('%Y-%m-%d')} {display_time}"
    except ValueError:
        return value
