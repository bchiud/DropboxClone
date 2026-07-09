from functools import lru_cache

import boto3
import certifi
from pymongo import MongoClient

from app.adapters.b2_block_store import B2BlockStore
from app.adapters.mongo_file_repository import MongoFileRepository
from app.adapters.mongo_share_repository import MongoShareRepository
from app.adapters.mongo_user_repository import MongoUserRepository
from app.application.auth_service import AuthService
from app.application.file_service import FileService
from app.application.share_service import ShareService
from app.config import settings
from app.ports.block_store import BlockStore
from app.ports.file_repository import FileRepository
from app.ports.share_repository import ShareRepository
from app.ports.user_repository import UserRepository
from app.realtime import ConnectionManager


@lru_cache
def _get_database():
    client = MongoClient(host=settings.mongodb_uri, tlsCAFile=certifi.where())
    return client[settings.mongodb_db]


@lru_cache
def get_block_store() -> BlockStore:
    s3 = boto3.client(
        "s3", endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )
    return B2BlockStore(s3, settings.s3_bucket)


@lru_cache
def get_file_repository() -> FileRepository:
    return MongoFileRepository(_get_database()["files"])


@lru_cache
def get_share_repository() -> ShareRepository:
    return MongoShareRepository(_get_database()["shares"])


@lru_cache
def get_user_repository() -> UserRepository:
    return MongoUserRepository(_get_database()["users"])


def get_auth_service() -> AuthService:
    return AuthService(
        user_repository=get_user_repository(),
    )


def get_file_service() -> FileService:
    return FileService(
        block_store=get_block_store(),
        file_repository=get_file_repository(),
    )


def get_share_service() -> ShareService:
    return ShareService(
        share_repository=get_share_repository(),
    )


@lru_cache
def get_connection_manager() -> ConnectionManager:
    return ConnectionManager()
