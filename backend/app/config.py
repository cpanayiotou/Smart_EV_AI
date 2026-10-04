from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    evcc_base_url: str = "http://evcc:7070"
    evcc_timeout_seconds: float = 5.0
    # Use simulator until the real evcc/hardware installation is available.
    simulation_enabled: bool = True
    # Phase 1 is intentionally read-only.
    evcc_write_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
