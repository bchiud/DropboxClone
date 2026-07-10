from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MongoDB Atlas
    mongodb_uri: str
    mongodb_db: str = "dropbox_clone"

    # Backblaze B2 (S3-compatible)
    s3_endpoint_url: str
    s3_access_key_id: str
    s3_secret_access_key: str
    s3_region: str
    s3_bucket: str = "dropbox-clone"
    # 4 MB blocks @ 1 MB/s = ~4.2s
    # 300s @ 1 MB/s = ~300MB
    # 300s @ 10 MB/s = ~2.9 GB
    # to handle larger files, we'll need to increase this, OR better, mint URL batches as the client walks the recipe
    s3_url_ttl_seconds: int = 300

    # Auth (JWT)
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    share_link_expire_minutes: int = 10080

    # Realtime (pub/sub)
    redis_url: str | None = None  # None -> single-process in-memory bus


settings = Settings()
