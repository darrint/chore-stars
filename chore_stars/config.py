from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHORES_", extra="ignore")

    database_url: str = "sqlite:///./chores.db"
    photo_dir: str = "./photos"
    session_secret: str = "change-me"
    base_url: str = "http://127.0.0.1:8765"
    host: str = "127.0.0.1"
    port: int = 8765
    timezone: str = "America/Indiana/Indianapolis"
    star_budget: int = 100
    grab_minutes: int = 45
    dev_auth: bool = False
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    ntfy_url: str = ""
    ntfy_topic: str = "chores"
    parents_group: str = "parents"
    residents_group: str = "residents"


def load_settings() -> Settings:
    return Settings()
