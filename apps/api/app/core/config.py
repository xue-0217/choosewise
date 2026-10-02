from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    demo_mode: bool = True
    database_url: str = 'sqlite:///./choosewise-demo.db'
    price_max_age_days: int = 7
    session_ttl_hours: int = 24
    run_timeout_seconds: int = 90
    max_concurrent_runs: int = 3
    llm_base_url: str = ''
    llm_api_key: str = ''
    llm_model: str = ''
    cookie_secure: bool = False
    curated_directory: Path = PROJECT_ROOT / 'data/curated/crawl-runs'

    @property
    def model_ready(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)
