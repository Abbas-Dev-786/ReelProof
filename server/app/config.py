from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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

    # Engine
    beat_count: int = 5
    max_agent_iterations: int = 2
    judge_pass_threshold: float = 0.7
    slideshow_beat_duration_sec: float = 3.5  # seconds per still in the final MP4

    # Paths
    data_dir: str = "data"      # ParquetSink local output
    output_dir: str = "output"  # local ffmpeg scratch


settings = Settings()
