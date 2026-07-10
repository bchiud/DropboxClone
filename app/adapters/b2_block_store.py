from botocore.exceptions import ClientError

from app.ports.block_store import BlockStore


class B2BlockStore(BlockStore):
    def __init__(self, s3_client, bucket: str, url_ttl_seconds: int):
        self._s3 = s3_client
        self._bucket = bucket
        self._url_ttl_seconds = url_ttl_seconds

    def has_block(self, block_hash: str) -> bool:
        try:
            self._s3.head_object(Bucket=self._bucket, Key=block_hash)
            return True
        except ClientError as ce:
            if ce.response["Error"]["Code"] == "404":
                return False
            raise

    def presigned_put_url(self, block_hash: str) -> str:
        return self._s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": block_hash},
            ExpiresIn=self._url_ttl_seconds,
        )

    def presigned_get_url(self, block_hash: str) -> str:
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": block_hash},
            ExpiresIn=self._url_ttl_seconds,
        )
