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

    # App
    jwt_secret: str
    block_size: int = 4 * 1024 * 1024  # 4 MiB


settings = Settings()
