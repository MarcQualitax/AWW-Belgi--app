from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    kbo_api_base_url: str | None = None
    kbo_api_key: str | None = None
    nbb_api_base_url: str | None = None
    nbb_api_key: str | None = None
    graydon_api_base_url: str | None = None
    graydon_api_key: str | None = None
    google_custom_search_key: str | None = None
    google_custom_search_cx: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
