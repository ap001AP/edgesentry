# =============================================================================
# EdgeSentry - Service configuration
# =============================================================================
# All settings come from environment variables, with sensible defaults for
# local development. 
# =============================================================================

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Service settings, loaded from env vars (or a .env file locally).

    Pydantic validates and type-coerces these on startup, so a typo'd port
    number fails immediately and loudly rather than at first use.
    """

    # --- MQTT broker ---------------------------------------------------------
    # In k8s this becomes the in-cluster service name; locally it's the
    # Docker-published port on your Mac.
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883

    # Topics the service subscribes to. Must match what the bridge publishes.
    topic_events: str = "edgesentry/events"
    topic_readings: str = "edgesentry/readings"
    topic_health: str = "edgesentry/health"

    # --- Database ------------------------------------------------------------
    # Full connection string. Overridden in k8s to point at the in-cluster DB.
    database_url: str = (
        "postgresql+psycopg://edgesentry:edgesentry@localhost:5432/edgesentry"
    )

    # --- LLM backend ---------------------------------------------------------
    # "ollama" runs a local model 
    # "anthropic" calls the API (paid fallback)
    llm_backend: str = "ollama"          # "ollama" | "anthropic"

    # Ollama (local) settings.
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"

    # Anthropic (fallback) settings. Empty by default so local dev doesn't need one.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # --- Behaviour -----------------------------------------------------------
    # Only summarize significant events; routine readings are just stored.
    # Guards against burning inference on noise.
    summarize_significant_only: bool = True

    # --- Observability -------------------------------------------------------
    metrics_port: int = 8001    # where Prometheus scrapes from
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",           # load local overrides from a .env file
        env_prefix="EDGESENTRY_",  
        extra="ignore",
    )

# A single shared instance, imported by the rest of the app.
settings = Settings()