from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = "http://host.docker.internal:55321"
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    database_url: str = (
        "postgresql://postgres:postgres@host.docker.internal:55322/postgres"
    )
    api_cors_origins: str = "http://localhost:3000"

    # Qwen / vLLM (OpenAI-compatible API)
    ai_base_url: str = "http://host.docker.internal:8080/v1"
    ai_api_key: str = "local"
    ai_model: str = "Qwen3.8-27B-NVFP4"

    # Google Routes handles road modes; ODPT/OTP handles public transit.
    # Japan GSI geocodes addresses, with openrouteservice as its fallback.
    ors_api_key: str = ""
    ors_geocoding_api_url: str = "https://api.openrouteservice.org/geocode/search"
    ors_geocoding_min_confidence: float = 0.8
    gsi_geocoding_api_url: str = (
        "https://msearch.gsi.go.jp/address-search/AddressSearch"
    )
    google_maps_api_key: str = ""
    google_routes_matrix_api_url: str = (
        "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
    )
    otp_api_url: str = "http://otp:8080/otp/gtfs/v1"
    route_transit_candidate_limit: int = 8
    route_candidate_limit: int = 20
    route_portfolio_limit: int = 10
    route_search_radius_km: int = 30
    route_max_search_radius_km: int = 200
    route_solver_time_limit_sec: int = 5
    route_default_max_visits: int = 4
    route_default_turnaround_buffer_min: int = 20
    route_default_travel_time_buffer_percent: int = 20
    route_default_access_buffer_min: int = 10
    route_default_return_buffer_min: int = 30
    route_sales_weight: int = 20
    route_gross_profit_weight: int = 30
    route_affinity_weight: int = 15
    route_urgency_weight: int = 15
    route_phase_weight: int = 10
    route_target_gap_weight: int = 10

    # Week/month batch planning: near-term days are solved in full detail,
    # remaining days are geographically clustered and estimated cheaply.
    route_batch_detailed_days: int = 3
    route_batch_candidate_limit: int = 150
    route_batch_pool_multiplier: int = 4
    route_batch_assumed_speed_kmh: int = 25

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


settings = Settings()
