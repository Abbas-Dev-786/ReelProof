from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Resolve relative to server/, not the process working directory. This lets
    # `uvicorn main:app` and `uvicorn server.main:app` load the same settings.
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM providers. Groq is the default campaign path: its OpenAI-compatible
    # API supports a structured text planner and a separate vision judge.
    # Set LLM_PROVIDER=nvidia to retain the former NIM implementation.
    llm_provider: Literal["groq", "nvidia"] = "groq"
    groq_api_key: str = ""
    groq_chat_base_url: str = ""
    groq_chat_timeout_sec: float = 30.0
    groq_chat_max_attempts: int = 2
    groq_chat_retry_backoff_sec: float = 1.0
    groq_chat_max_retry_delay_sec: float = 5.0
    groq_planner_max_tokens: int = 2048
    # Both GPT-OSS models support Groq's strict JSON-schema mode. The smaller
    # model is the normal planner; the larger model is a same-contract
    # failover for transient provider failures.
    groq_planner_model: str = "openai/gpt-oss-20b"
    groq_planner_fallback_model: str = "openai/gpt-oss-120b"
    # Qwen 3.6 accepts rendered image URLs and supports JSON Object mode. Its
    # responses are validated locally by the vision judge.
    groq_vision_model: str = "qwen/qwen3.6-27b"
    groq_vision_max_tokens: int = 512

    # NVIDIA NIM remains available as an explicit fallback through GenBlaze.
    nvidia_api_key: str = ""
    nvidia_chat_base_url: str = ""
    # Keep an unavailable NIM endpoint from consuming the whole campaign
    # deadline. The planner retries only transient failures within this budget.
    nvidia_chat_timeout_sec: float = 30.0
    nvidia_chat_max_attempts: int = 2
    nvidia_chat_retry_backoff_sec: float = 1.0
    nvidia_chat_max_retry_delay_sec: float = 5.0
    nvidia_planner_max_tokens: int = 2048
    # Specialist NIM models: text planning and multimodal visual evaluation.
    nvidia_planner_model: str = "z-ai/glm-5.2"
    nvidia_vision_model: str = "qwen/qwen3.5-397b-a17b"
    gmi_api_key: str = ""
    elevenlabs_api_key: str = ""
    stability_api_key: str = ""
    voiceover_enabled: bool = False
    elevenlabs_voice_model: str = "eleven_v3"
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"

    # LangSmith is opt-in. Its traces intentionally contain prompts and asset
    # URLs, so only enable it for workspaces approved for that data.
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "reelproof"
    langsmith_workspace_id: str = ""

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
    gmi_image_fallback_models: str = "gemini-2.5-flash-image,seedream-5.0-lite"
    gmi_product_image_model: str = "reve-edit-fast-20251030"
    gmi_product_image_unit_cost_usd: float = 0.007
    gmi_product_image_fallback_models: str = "reve-edit-20250915,reve-remix-fast-20251030"

    # Engine
    beat_count: int = 5
    max_agent_iterations: int = 2
    judge_pass_threshold: float = 0.7
    slideshow_beat_duration_sec: float = 3.5  # seconds per still in the final MP4
    slideshow_width: int = 1080
    slideshow_height: int = 1920
    slideshow_fps: int = 25
    slideshow_transition_sec: float = 0.35
    pov_video_model: str = "pixverse-v5.6-i2v"
    pov_video_fallback_models: str = "seedance-1-0-pro-fast,wan2.6-i2v"
    pov_video_unit_cost_usd: float = 0.03
    pov_clip_duration_sec: int = 5
    pov_max_concurrency: int = 2
    pov_pipeline_timeout_sec: int = 900
    image_step_retries: int = 1
    audio_step_retries: int = 1
    voiceover_step_retries: int = 1
    video_step_retries: int = 1
    job_lease_seconds: int = 1_800

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

    @property
    def pov_video_fallback_model_list(self) -> list[str]:
        """Return de-duplicated, configured fallbacks for image-to-video renders."""
        return self._model_list(self.pov_video_fallback_models, self.pov_video_model)

    @staticmethod
    def _model_list(raw_models: str, primary_model: str) -> list[str]:
        return list(
            dict.fromkeys(
                model.strip()
                for model in raw_models.split(",")
                if model.strip() and model.strip() != primary_model
            )
        )

    @property
    def gmi_image_fallback_model_list(self) -> list[str]:
        return self._model_list(self.gmi_image_fallback_models, self.gmi_image_model)

    @property
    def gmi_product_image_fallback_model_list(self) -> list[str]:
        return self._model_list(
            self.gmi_product_image_fallback_models, self.gmi_product_image_model
        )

    @property
    def active_llm_api_key(self) -> str:
        return self.groq_api_key if self.llm_provider == "groq" else self.nvidia_api_key

    @property
    def active_planner_model(self) -> str:
        return self.groq_planner_model if self.llm_provider == "groq" else self.nvidia_planner_model

    @property
    def active_vision_model(self) -> str:
        return self.groq_vision_model if self.llm_provider == "groq" else self.nvidia_vision_model

    @property
    def active_llm_key_env_name(self) -> str:
        return "GROQ_API_KEY" if self.llm_provider == "groq" else "NVIDIA_API_KEY"

    def missing_phase1_settings(self) -> list[str]:
        """Return the credentials required by the paid Phase 1 smoke run."""
        required = {
            "GMI_API_KEY": self.gmi_api_key,
            "STABILITY_API_KEY": self.stability_api_key,
            "B2_KEY_ID": self.b2_key_id,
            "B2_APP_KEY": self.b2_app_key,
        }
        return [name for name, value in required.items() if not value]

    def missing_campaign_settings(self) -> list[str]:
        """Return settings required before a browser-playable campaign starts."""
        required = {
            self.active_llm_key_env_name: self.active_llm_api_key,
            "GMI_API_KEY": self.gmi_api_key,
            "STABILITY_API_KEY": self.stability_api_key,
            "B2_KEY_ID": self.b2_key_id,
            "B2_APP_KEY": self.b2_app_key,
            # The API returns stored asset URLs to the browser. Without a public
            # base (or a future presigning implementation), private B2 URLs 403.
            "B2_PUBLIC_URL_BASE": self.b2_public_url_base,
        }
        if self.voiceover_enabled:
            required["ELEVENLABS_API_KEY"] = self.elevenlabs_api_key
        return [name for name, value in required.items() if not value]


settings = Settings()
