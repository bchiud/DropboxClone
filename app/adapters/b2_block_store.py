from botocore.exceptions import ClientError

from app.ports.block_store import BlockStore


class B2BlockStore(BlockStore):
    def __init__(self, s3_client, bucket: str):
        self._s3 = s3_client
        self._bucket = bucket

    def has_block(self, block_hash: str) -> bool:
        try:
            self._s3.head_object(Bucket=self._bucket, Key=block_hash)
            return True
        except ClientError as ce:
            if ce.response["Error"]["Code"] == "404":
                return False
            raise

    def put_block(self, block_hash: str, data: bytes) -> None:
        if self.has_block(block_hash):
            return
        self._s3.put_object(Bucket=self._bucket, Key=block_hash, Body=data)

    def get_block(self, block_hash: str) -> bytes:
        response = self._s3.get_object(Bucket=self._bucket, Key=block_hash)
        return response["Body"].read()
