from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://latticelens:latticelens_dev@localhost:5432/latticelens"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    default_page_size: int = 50
    max_page_size: int = 200

    anthropic_api_key: str = ""
    extraction_model: str = "claude-sonnet-4-20250514"

    model_config = {"env_prefix": "LATTICELENS_"}


settings = Settings()
