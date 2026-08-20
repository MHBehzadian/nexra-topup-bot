from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""
    # CSV of Telegram numeric IDs allowed to approve/reject top-up requests.
    superadmin_ids: str = ""

    # Must include the panel's URLPATH segment, e.g. https://panel.example.com/dashboard
    nexra_panel_api_url: str = ""
    # Must match nexra-panel's BOT_API_KEY setting.
    nexra_panel_bot_api_key: str = ""

    sqlite_path: str = "data/topup_bot.db"
    media_dir: str = "data/media"

    # Allowed range for a single top-up request.
    min_gb: float = 200.0
    max_gb: float = 10000.0

    # How often to check every panel's remaining traffic for warnings.
    warning_scan_interval_seconds: int = 1800

    @property
    def superadmin_id_list(self) -> list[int]:
        return [
            int(x) for x in self.superadmin_ids.split(",") if x.strip().lstrip("-").isdigit()
        ]


settings = Settings()
