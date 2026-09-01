import os


class Settings:
    """Central, lazily-read env config for provider selection and Bedrock settings.

    Read from `os.environ` on access (not frozen at import time) so tests can
    override provider selection per-run via `monkeypatch.setenv`, matching the
    pattern already used by `verify_api_key()` in `app/core/security.py`.
    """

    @property
    def AI_PROVIDER(self) -> str:
        return os.environ.get("AI_PROVIDER", "bedrock")

    @property
    def AWS_REGION(self) -> str:
        return os.environ.get("AWS_REGION", "eu-west-1")

    @property
    def BEDROCK_LLM_MODEL_ID(self) -> str:
        return os.environ.get("BEDROCK_LLM_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0")

    @property
    def BEDROCK_EMBEDDING_MODEL_ID(self) -> str:
        return os.environ.get("BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")


settings = Settings()
