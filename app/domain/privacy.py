"""Privacy and sensitive data redaction domain logic.

Provides best-effort masking of API keys, credentials, credit cards, emails,
phone numbers, and government identification numbers.

Note:
    This redaction logic is best-effort heuristic pattern matching and does
    not guarantee 100% detection of all conceivable secret formats.
    Health-sensitive food information (such as allergen names) is explicitly
    preserved for user safety.
"""

from dataclasses import dataclass, field
import re
from typing import Pattern

# Common culinary allergens that must NEVER be redacted or blocked
PRESERVED_ALLERGENS: set[str] = {
    "peanut", "peanuts", "tree nut", "tree nuts", "almond", "almonds",
    "walnut", "walnuts", "cashew", "cashews", "pistachio", "pistachios",
    "shellfish", "crustacean", "shrimp", "prawn", "crab", "lobster",
    "fish", "salmon", "tuna", "cod", "egg", "eggs", "milk", "dairy",
    "cheese", "butter", "soy", "soya", "soybean", "wheat", "gluten",
    "sesame", "mustard", "celery", "lupin", "mollusc", "molluscs", "sulfite", "sulfites"
}


@dataclass
class RedactionResult:
    """Outcome of sensitive data redaction."""
    text: str
    redactions: list[str] = field(default_factory=list)
    blocked: bool = False


# Module-level dictionary of redaction pattern categories and their regexes
# Easily extensible with additional token or identification formats
REDACTION_PATTERNS: dict[str, tuple[Pattern[str], str]] = {
    "api_key": (
        re.compile(
            r"\b(?:sk-[a-zA-Z0-9_\-]{20,}|AIza[0-9A-Za-z\-_]{35}|ghp_[a-zA-Z0-9]{36}|[a-fA-F0-9]{32,64})\b",
            re.IGNORECASE,
        ),
        "[REDACTED_API_KEY]",
    ),
    "card_number": (
        re.compile(
            r"\b(?:\d[ -]*?){13,19}\b",
        ),
        "[REDACTED_CARD]",
    ),
    "email": (
        re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        ),
        "[REDACTED_EMAIL]",
    ),
    "phone": (
        re.compile(
            r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"
        ),
        "[REDACTED_PHONE]",
    ),
    "password": (
        re.compile(
            r"(?i)\b(?:password\s+is|pass(?:word)?\s*[:=]|pwd\s*[:=])\s*([^\s,;]+)"
        ),
        "[REDACTED_PASSWORD]",
    ),
    "gov_id": (
        re.compile(
            r"\b\d{3}-\d{2}-\d{4}\b"
        ),
        "[REDACTED_GOV_ID]",
    ),
}


def redact_sensitive(text: str) -> RedactionResult:
    """Detect and mask obvious secrets and personal identifiers.

    Args:
        text: Raw text string to redact.

    Returns:
        RedactionResult containing the sanitized text, a list of redaction tag
        names applied, and a boolean indicating whether the memory is blocked.
    """
    if not text or not text.strip():
        return RedactionResult(text=text, redactions=[], blocked=False)

    original_length = len(re.sub(r"\s+", "", text))
    redacted_text = text
    applied_redactions: list[str] = []

    # 1. Redact passwords with lookbehind context capture
    pw_pattern, pw_tag = REDACTION_PATTERNS["password"]
    def _pw_sub(match: re.Match[str]) -> str:
        applied_redactions.append("password")
        full_match = match.group(0)
        secret_part = match.group(1)
        prefix = full_match[: match.start(1) - match.start(0)]
        return f"{prefix}{pw_tag}"

    redacted_text = pw_pattern.sub(_pw_sub, redacted_text)

    # 2. Redact other sensitive patterns
    for tag_name, (pattern, tag) in REDACTION_PATTERNS.items():
        if tag_name == "password":
            continue

        matches = list(pattern.finditer(redacted_text))
        if not matches:
            continue

        # Check each match
        sub_occurred = False
        for m in reversed(matches):
            matched_str = m.group(0)
            # Avoid re-redacting already redacted tags
            if matched_str.startswith("[REDACTED_"):
                continue

            # Additional validation for card numbers to prevent matching simple short numbers
            if tag_name == "card_number":
                digits_only = re.sub(r"\D", "", matched_str)
                if not (13 <= len(digits_only) <= 19):
                    continue

            # Additional validation for phone numbers
            if tag_name == "phone":
                digits_only = re.sub(r"\D", "", matched_str)
                if len(digits_only) < 10 or len(digits_only) > 15:
                    continue

            start, end = m.span()
            redacted_text = redacted_text[:start] + tag + redacted_text[end:]
            sub_occurred = True

        if sub_occurred:
            applied_redactions.append(tag_name)

    # 3. Compute blocked state: blocked when the text is essentially a secret
    # (i.e. more than 50% of the content was redacted or only trivial/label words remain)
    stripped_residual = re.sub(r"\[REDACTED_[A-Z_]+\]", "", redacted_text)
    residual_non_space = len(re.sub(r"\s+", "", stripped_residual))

    blocked = False
    if len(applied_redactions) > 0 and original_length > 0:
        redacted_ratio = (original_length - residual_non_space) / original_length
        # Trivial residual words (labels, articles, pronouns)
        words = re.findall(r"\b\w+\b", stripped_residual.lower())
        trivial_words = {
            "card", "credit", "debit", "number", "key", "token", "api", "secret",
            "password", "pass", "pwd", "pin", "ssn", "id", "email", "phone",
            "my", "the", "is", "a", "an", "here", "to", "and", "for", "in", "it"
        }
        meaningful_residual = [w for w in words if w not in trivial_words]

        if residual_non_space <= 3 or len(meaningful_residual) == 0:
            blocked = True
        elif redacted_ratio >= 0.7:
            blocked = True

    return RedactionResult(
        text=redacted_text,
        redactions=list(dict.fromkeys(applied_redactions)),
        blocked=blocked,
    )
