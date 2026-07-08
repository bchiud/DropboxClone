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

    # Auth (JWT)
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


settings = Settings()
