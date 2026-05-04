from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata


CANCELLATION_RE = re.compile(r"\b(?:cancelled|canceled)\b", re.IGNORECASE)
JOINT_SEMINAR_PREFIX_RE = re.compile(r"^\s*joint\b.+?\bseminar\b\s*", re.IGNORECASE)
GENERIC_SEMINAR_PREFIX_RE = re.compile(
    r"^\s*(?:aee|crc\s*tr\s*224|department|zew|applied)\b[ /&-]*(?:seminar|meeting)\b\s*",
    re.IGNORECASE,
)
INSTITUTION_KEYWORDS = {
    "bank",
    "business",
    "college",
    "department",
    "economics",
    "institute",
    "institution",
    "school",
    "sciences",
    "universitaet",
    "universitat",
    "universität",
    "university",
}
KNOWN_SHORT_INSTITUTIONS = {
    "bse",
    "bocconi",
    "ceu",
    "eth",
    "idei",
    "ifo",
    "ku",
    "lmu",
    "lse",
    "mit",
    "nber",
    "pse",
    "smu",
    "tse",
    "ucl",
    "ucla",
    "usi",
    "uzh",
    "vu",
    "zew",
}
KNOWN_INSTITUTION_PHRASES = {
    "colorado boulder",
    "ku leuven",
    "queen mary",
    "smu singapore",
    "universita bocconi",
    "universite libre de bruxelles",
    "usi lugano",
    "vu amsterdam",
}
NAME_SUFFIX_RE = re.compile(r",\s*(?:jr|sr|junior|senior)\.?\s*$", re.IGNORECASE)


@dataclass(slots=True)
class NormalizedSpeaker:
    speaker_name: str
    affiliation: str | None
    flags: list[str] = field(default_factory=list)


def contains_cancellation(value: str | None) -> bool:
    return bool(value and CANCELLATION_RE.search(value))


def normalize_speaker_identity(speaker_name: str, affiliation: str | None = None) -> NormalizedSpeaker:
    flags: list[str] = []
    raw_name = _collapse(speaker_name)
    raw_affiliation = _clean_affiliation(affiliation)

    if contains_cancellation(raw_name):
        flags.append("cancellation_marker_removed")
        raw_name = _strip_cancellation_marker(raw_name)
    if contains_cancellation(raw_affiliation):
        flags.append("cancellation_marker_removed")
        raw_affiliation = _strip_cancellation_marker(raw_affiliation)

    stripped_prefix = JOINT_SEMINAR_PREFIX_RE.sub("", raw_name)
    if stripped_prefix != raw_name:
        flags.append("meeting_prefix_removed")
        raw_name = stripped_prefix
    stripped_prefix = GENERIC_SEMINAR_PREFIX_RE.sub("", raw_name)
    if stripped_prefix != raw_name:
        flags.append("meeting_prefix_removed")
        raw_name = stripped_prefix

    raw_name, raw_affiliation, parenthetical_flags = _extract_parenthetical_affiliation(raw_name, raw_affiliation)
    flags.extend(parenthetical_flags)

    raw_name, raw_affiliation, suffix_flags = _extract_trailing_institution(raw_name, raw_affiliation)
    flags.extend(suffix_flags)

    if raw_affiliation and raw_affiliation.lower() in raw_name.lower():
        raw_name = re.sub(re.escape(raw_affiliation), " ", raw_name, flags=re.IGNORECASE)
        flags.append("duplicated_affiliation_removed")

    comma_affiliation = _extract_comma_affiliation(raw_name)
    if comma_affiliation:
        raw_name, comma_affiliation_value = comma_affiliation
        raw_affiliation = _join_affiliation(comma_affiliation_value, raw_affiliation)
        flags.append("comma_affiliation_split")

    cleaned_name = _clean_name(raw_name)
    cleaned_affiliation = _clean_affiliation(raw_affiliation)
    if "(" in cleaned_name or ")" in cleaned_name:
        flags.append("parenthesis_removed_from_name")
        cleaned_name = _clean_name(re.sub(r"\([^)]*\)", " ", cleaned_name).replace("(", " ").replace(")", " "))
    if contains_cancellation(cleaned_name):
        flags.append("cancellation_marker_removed")
        cleaned_name = _clean_name(_strip_cancellation_marker(cleaned_name))

    return NormalizedSpeaker(
        speaker_name=cleaned_name,
        affiliation=cleaned_affiliation,
        flags=list(dict.fromkeys(flags)),
    )


def speaker_name_quality_flags(value: str | None) -> list[str]:
    if not value:
        return ["missing_name"]
    flags: list[str] = []
    if "(" in value or ")" in value:
        flags.append("parenthesis_in_name")
    if "," in value:
        flags.append("comma_in_name")
    if contains_cancellation(value):
        flags.append("cancellation_marker_in_name")
    if split_speaker_names(value, None):
        flags.append("multiple_speakers_in_name")
    if JOINT_SEMINAR_PREFIX_RE.match(value) or GENERIC_SEMINAR_PREFIX_RE.match(value):
        flags.append("meeting_prefix_in_name")
    if len(value.split()) > 8:
        flags.append("too_many_name_tokens")
    return flags


def clean_person_display_name(value: str) -> str:
    cleaned = _strip_cancellation_marker(_collapse(value))
    cleaned = JOINT_SEMINAR_PREFIX_RE.sub("", cleaned)
    cleaned = GENERIC_SEMINAR_PREFIX_RE.sub("", cleaned)
    cleaned = NAME_SUFFIX_RE.sub("", cleaned)
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    cleaned = cleaned.replace("(", " ").replace(")", " ")
    if "," in cleaned:
        possible_people = split_speaker_names(cleaned, None)
        cleaned = possible_people[0] if possible_people else cleaned.split(",", 1)[0]
    return _clean_name(cleaned)


def split_speaker_names(speaker_name: str, affiliation: str | None = None) -> list[str]:
    cleaned = clean_person_display_name_without_split(speaker_name)
    if not cleaned:
        return []
    if "," in cleaned and not NAME_SUFFIX_RE.search(cleaned):
        if _extract_comma_affiliation(cleaned):
            return []
        parts = [_clean_name(part) for part in cleaned.split(",") if _clean_name(part)]
        if len(parts) > 1 and all(_looks_like_person_name(part) for part in parts):
            return parts
    if re.search(r"\s+and\s+", cleaned, re.IGNORECASE):
        parts = [_clean_name(part) for part in re.split(r"\s+and\s+", cleaned, flags=re.IGNORECASE) if _clean_name(part)]
        if len(parts) > 1 and all(_looks_like_person_name(part) for part in parts):
            return parts
    return []


def clean_person_display_name_without_split(value: str) -> str:
    cleaned = _strip_cancellation_marker(_collapse(value))
    cleaned = JOINT_SEMINAR_PREFIX_RE.sub("", cleaned)
    cleaned = GENERIC_SEMINAR_PREFIX_RE.sub("", cleaned)
    cleaned = NAME_SUFFIX_RE.sub("", cleaned)
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    cleaned = cleaned.replace("(", " ").replace(")", " ")
    return _clean_name(cleaned)


def person_identity_key(value: str) -> str:
    lowered = _collapse(value).lower()
    lowered = (
        lowered.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    ascii_value = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    ascii_value = re.sub(r"[^a-z0-9 ]+", " ", ascii_value)
    tokens = [
        token
        for token in re.sub(r"\s+", " ", ascii_value).strip().split(" ")
        if token and token not in {"dr", "ph", "phd", "prof", "professor"}
    ]
    return " ".join(tokens)


def looks_like_institution_name(value: str | None) -> bool:
    return bool(value and _looks_like_institution(value) and not _looks_like_person_name(value))


def _collapse(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _strip_cancellation_marker(value: str) -> str:
    value = re.sub(r"(?i)\s*[-–—:]?\s*\b(?:cancelled|canceled)\b\s*[-–—:]?\s*", " ", value)
    return _collapse(value).strip(" -–—:;,.")


def _extract_parenthetical_affiliation(name: str, affiliation: str | None) -> tuple[str, str | None, list[str]]:
    flags: list[str] = []
    if " (" not in name:
        return name, affiliation, flags

    before, after = name.rsplit(" (", 1)
    extracted_affiliation = after.strip().rstrip(")").strip()
    if not extracted_affiliation:
        return name, affiliation, flags

    flags.append("parenthetical_affiliation_split")
    return before.strip(), _join_affiliation(extracted_affiliation, affiliation), flags


def _extract_trailing_institution(name: str, affiliation: str | None) -> tuple[str, str | None, list[str]]:
    flags: list[str] = []
    stripped = name.rstrip(")").strip()
    if stripped == name and ")" not in name:
        return name, affiliation, flags

    tokens = stripped.split()
    if len(tokens) < 4:
        return stripped, affiliation, flags

    for index in range(2, len(tokens) - 1):
        tail = " ".join(tokens[index:])
        if _looks_like_institution(tail):
            flags.append("trailing_affiliation_split")
            return " ".join(tokens[:index]), _join_affiliation(tail, affiliation), flags
    return stripped, affiliation, flags


def _extract_comma_affiliation(name: str) -> tuple[str, str] | None:
    if "," not in name or NAME_SUFFIX_RE.search(name):
        return None

    parts = [_collapse(part) for part in name.split(",") if _collapse(part)]
    if len(parts) < 2:
        return None

    left = parts[0]
    right_parts = parts[1:]
    right = ", ".join(right_parts)
    if not _looks_like_person_name(left):
        return None

    if _looks_like_institution(right) or any(_looks_like_institution(part) for part in right_parts):
        return left, right
    if len(right_parts) == 1 and not _looks_like_person_name(right):
        return left, right
    return None


def _looks_like_institution(value: str | None) -> bool:
    if not value:
        return False
    cleaned = _clean_affiliation(value) or ""
    normalized = person_identity_key(cleaned)
    if normalized in KNOWN_INSTITUTION_PHRASES:
        return True
    tokens = {token.lower().strip(".,;:()") for token in normalized.split()}
    if tokens & KNOWN_SHORT_INSTITUTIONS:
        return True
    return bool(tokens & INSTITUTION_KEYWORDS)


def _looks_like_person_name(value: str) -> bool:
    cleaned = clean_person_display_name_without_split(value)
    if not cleaned or _looks_like_institution(cleaned):
        return False
    tokens = cleaned.split()
    if not 2 <= len(tokens) <= 5:
        return False
    lowercase_particles = {"da", "de", "del", "der", "di", "la", "le", "van", "von"}
    capitalized_tokens = [
        token
        for token in tokens
        if token.lower().strip(".") in lowercase_particles or token[:1].isupper() or token.isupper()
    ]
    return len(capitalized_tokens) == len(tokens)


def _join_affiliation(first: str | None, second: str | None) -> str | None:
    first_clean = _clean_affiliation(first)
    second_clean = _clean_affiliation(second)
    if first_clean and second_clean:
        if first_clean.lower() == second_clean.lower():
            return first_clean
        if first_clean.lower() in second_clean.lower():
            return second_clean
        if second_clean.lower() in first_clean.lower():
            return first_clean
        return f"{first_clean}, {second_clean}"
    return first_clean or second_clean


def _clean_name(value: str | None) -> str:
    cleaned = _collapse(value).strip(" -–—:;,.")
    cleaned = re.sub(r"\s*/\s*", "/", cleaned)
    return cleaned


def _clean_affiliation(value: str | None) -> str | None:
    cleaned = _collapse(value).strip(" -–—:;,.()")
    return cleaned or None
