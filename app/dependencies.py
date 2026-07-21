from functools import lru_cache

import boto3
import certifi
from pymongo import MongoClient

from app.adapters.b2_block_store import B2BlockStore
from app.adapters.in_memory_change_bus import InMemoryChangeBus
from app.adapters.mongo_block_index import MongoBlockIndex
from app.adapters.mongo_file_repository import MongoFileRepository
from app.adapters.mongo_refresh_token_repository import MongoRefreshTokenRepository
from app.adapters.mongo_share_link_repository import MongoShareLinkRepository
from app.adapters.mongo_share_repository import MongoShareRepository
from app.adapters.mongo_user_repository import MongoUserRepository
from app.application.auth_service import AuthService
from app.application.file_service import FileService
from app.application.share_service import ShareService
from app.config import settings
from app.ports.block_index import BlockIndex
from app.ports.block_store import BlockStore
from app.ports.change_bus import ChangeBus
from app.ports.file_repository import FileRepository
from app.ports.refresh_token_repository import RefreshTokenRepository
from app.ports.share_link_repository import ShareLinkRepository
from app.ports.share_repository import ShareRepository
from app.ports.user_repository import UserRepository
from app.realtime import ConnectionManager, Notifier


# --- real-time ---

@lru_cache
def get_change_bus() -> ChangeBus:
    if settings.redis_url:
        from app.adapters.redis_change_bus import RedisChangeBus
        return RedisChangeBus(settings.redis_url)
    return InMemoryChangeBus()


@lru_cache
def get_connection_manager() -> ConnectionManager:
    return ConnectionManager()


@lru_cache
def get_notifier() -> Notifier:
    return Notifier(bus=get_change_bus(), manager=get_connection_manager())


# --- repositories ---

@lru_cache
def _get_database():
    client = MongoClient(host=settings.mongodb_uri, tlsCAFile=certifi.where())
    return client[settings.mongodb_db]


@lru_cache
def get_file_repository() -> FileRepository:
    return MongoFileRepository(_get_database()["files"])


@lru_cache
def get_refresh_token_repository() -> RefreshTokenRepository:
    return MongoRefreshTokenRepository(_get_database()["refresh_tokens"])


@lru_cache
def get_share_repository() -> ShareRepository:
    return MongoShareRepository(_get_database()["shares"])


@lru_cache
def get_share_link_repository() -> ShareLinkRepository:
    return MongoShareLinkRepository(_get_database()["share_links"])


@lru_cache
def get_user_repository() -> UserRepository:
    return MongoUserRepository(_get_database()["users"])


@lru_cache
def get_block_index() -> BlockIndex:
    return MongoBlockIndex(_get_database()["blocks"])


# --- services ---

def get_auth_service() -> AuthService:
    return AuthService(
        refresh_token_repository=get_refresh_token_repository(),
        user_repository=get_user_repository(),
    )


def get_file_service() -> FileService:
    return FileService(
        block_store=get_block_store(),
        file_repository=get_file_repository(),
        block_index=get_block_index(),
    )


def get_share_service() -> ShareService:
    return ShareService(
        share_repository=get_share_repository(),
        share_link_repository=get_share_link_repository(),
    )


# --- storage ---

@lru_cache
def get_block_store() -> BlockStore:
    s3 = boto3.client(
        "s3", endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )
    return B2BlockStore(s3, settings.s3_bucket, settings.s3_url_ttl_seconds)
