from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Resolve relative to server/, not the process working directory. This lets
    # `uvicorn main:app` and `uvicorn server.main:app` load the same settings.
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Providers
    openai_api_key: str = ""
    gmi_api_key: str = ""
    elevenlabs_api_key: str = ""
    stability_api_key: str = ""

    # Backblaze B2
    b2_key_id: str = ""
    b2_app_key: str = ""
    b2_bucket: str = "reelproof-assets"
    b2_region: str = "us-west-004"
    b2_public_url_base: str = ""  # set to Cloudflare CNAME for public buckets
    b2_object_lock_enabled: bool = False
    b2_object_lock_retention_days: int = 365
    parquet_enabled: bool = False  # Phase 3 lineage analytics; requires pyarrow
    gmi_image_model: str = "reve-create-20250915"
    gmi_image_unit_cost_usd: float = 0.007
    gmi_product_image_model: str = "reve-edit-fast-20251030"
    gmi_product_image_unit_cost_usd: float = 0.007

    # Engine
    beat_count: int = 5
    max_agent_iterations: int = 2
    judge_pass_threshold: float = 0.7
    slideshow_beat_duration_sec: float = 3.5  # seconds per still in the final MP4
    slideshow_width: int = 1080
    slideshow_height: int = 1920
    slideshow_fps: int = 25
    slideshow_transition_sec: float = 0.35

    # API and operational limits
    cors_origins: str = "http://localhost:5173,http://localhost:4173"
    max_upload_bytes: int = 10 * 1024 * 1024
    max_upload_pixels: int = 40_000_000

    # Paths. Paths are resolved relative to server/, never the invoking shell.
    database_path: str = "jobs.db"
    data_dir: str = "data"  # ParquetSink local output
    output_dir: str = "output"  # local ffmpeg scratch

    @property
    def server_dir(self) -> Path:
        return Path(__file__).resolve().parents[1]

    @property
    def database_file(self) -> Path:
        return self.server_dir / self.database_path

    @property
    def data_path(self) -> Path:
        return self.server_dir / self.data_dir

    @property
    def output_path(self) -> Path:
        return self.server_dir / self.output_dir

    @property
    def allowed_cors_origins(self) -> list[str]:
        """Return a de-duplicated list of explicitly configured browser origins."""
        return list(
            dict.fromkeys(
                origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
            )
        )

    def missing_phase1_settings(self) -> list[str]:
        """Return the credentials required by the paid Phase 1 smoke run."""
        required = {
            "OPENAI_API_KEY": self.openai_api_key,
            "GMI_API_KEY": self.gmi_api_key,
            "B2_KEY_ID": self.b2_key_id,
            "B2_APP_KEY": self.b2_app_key,
        }
        return [name for name, value in required.items() if not value]


settings = Settings()
