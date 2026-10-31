"""Unit tests for sensitive data redaction in app.domain.privacy."""

from app.domain.privacy import redact_sensitive, RedactionResult


def test_redact_email_and_phone():
    """Emails and phone numbers should be masked with corresponding redaction tags."""
    raw = "Contact chef at alex.cooking@example.com or call 555-123-4567 for dinner reservations."
    res = redact_sensitive(raw)
    assert "[REDACTED_EMAIL]" in res.text
    assert "[REDACTED_PHONE]" in res.text
    assert "alex.cooking@example.com" not in res.text
    assert "555-123-4567" not in res.text
    assert "email" in res.redactions
    assert "phone" in res.redactions
    assert res.blocked is False


def test_redact_api_key_and_card_number():
    """API tokens and credit card numbers should be masked."""
    raw = "My OpenAI key is sk-abcdef12345678901234567890 and card is 4111 2222 3333 4444."
    res = redact_sensitive(raw)
    assert "[REDACTED_API_KEY]" in res.text
    assert "[REDACTED_CARD]" in res.text
    assert "sk-abcdef12345678901234567890" not in res.text
    assert "4111 2222 3333 4444" not in res.text
    assert res.blocked is False


def test_redact_password():
    """Password sequences following trigger words should be masked."""
    raw = "My wifi password is SuperSecretPassword! for the kitchen tablet."
    res = redact_sensitive(raw)
    assert "[REDACTED_PASSWORD]" in res.text
    assert "SuperSecretPassword!" not in res.text
    assert "password" in res.redactions
    assert res.blocked is False


def test_redact_gov_id():
    """SSN-like numbers should be masked."""
    raw = "User SSN 123-45-6789 provided for identification."
    res = redact_sensitive(raw)
    assert "[REDACTED_GOV_ID]" in res.text
    assert "123-45-6789" not in res.text
    assert res.blocked is False


def test_allergen_words_preserved():
    """Food allergy descriptions must not be redacted or blocked."""
    raw = "Severely allergic to peanuts, shellfish, and tree nuts. Contact: 415-555-2671."
    res = redact_sensitive(raw)
    assert "peanuts" in res.text
    assert "shellfish" in res.text
    assert "tree nuts" in res.text
    assert "[REDACTED_PHONE]" in res.text
    assert res.blocked is False


def test_mostly_secret_input_is_blocked():
    """Inputs that are predominantly secrets should be flagged as blocked."""
    only_token = "sk-1234567890abcdef1234567890abcdef"
    res1 = redact_sensitive(only_token)
    assert res1.blocked is True

    only_card = "Card: 4111-2222-3333-4444"
    res2 = redact_sensitive(only_card)
    assert res2.blocked is True


def test_clean_text_untouched():
    """Normal culinary preferences without secrets should remain intact."""
    raw = "Prefers spicy Thai curry with coconut milk, tofu, and jasmine rice."
    res = redact_sensitive(raw)
    assert res.text == raw
    assert len(res.redactions) == 0
    assert res.blocked is False
