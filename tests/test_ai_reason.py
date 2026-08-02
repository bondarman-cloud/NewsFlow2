from app.ai import GeminiEditor


def test_ai_rejection_reason_is_parsed() -> None:
    result = GeminiEditor._parse(
        '{"publish": false, "title": "", "summary": "", "tags": [], '
        '"reason": "Это финансовый отчёт"}'
    )

    assert result.publish is False
    assert result.reason == "Это финансовый отчёт"


def test_ai_reason_is_optional_for_legacy_responses() -> None:
    result = GeminiEditor._parse(
        '{"publish": true, "title": "Новость", "summary": "Текст", "tags": ["AI"]}'
    )

    assert result.publish is True
    assert result.reason == ""
