# V5.1 Security Rules

- Never commit `TELEGRAM_TOKEN`, broker passwords, API keys, or access tokens.
- Runtime credentials must come from environment/deployment secrets.
- `ALLOWED_TELEGRAM_USER_IDS` is mandatory in production; an empty allow-list is a startup failure.
- AI credentials are not trading credentials. AI output cannot authorize an order or bypass risk gates.
- Logs and generated artifacts are not source: do not commit `.coverage`, `.pytest_cache`, `__pycache__`, `.pyc`, or runtime logs.
- Any credential that has previously appeared in source or committed history must be revoked/rotated before production use.
