from functools import lru_cache

from supabase import Client, create_client

from app.config import settings


@lru_cache
def get_supabase_client() -> Client | None:
    """Service-role client for server-side Supabase access. Returns None if unset."""
    url = settings.supabase_url
    key = settings.supabase_service_role_key or settings.supabase_anon_key
    if not url or not key or key.startswith("your-"):
        return None
    return create_client(url, key)
