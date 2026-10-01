from ai.openai_advisor import OpenAIAdvisor


def test_advisor_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    advice = OpenAIAdvisor(api_key=None).explain_signal({"direction": "BUY"})
    assert "disabled" in advice.summary.lower()


def test_advisor_is_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert OpenAIAdvisor(api_key=None).enabled is False
