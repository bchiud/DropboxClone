from pymongo import UpdateOne
from pymongo.collection import Collection

from app.ports.block_index import BlockIndex


class MongoBlockIndex(BlockIndex):
    def __init__(self, collection: Collection):
        self._collection = collection
        self._collection.create_index([("owner", 1), ("hash", 1)], unique=True)

    def present_subset(self, owner: str, hashes: list[str]) -> set[str]:
        docs = self._collection.find({"owner": owner, "hash": {"$in": hashes}}, {"_id": 0, "hash": 1})
        return {doc["hash"] for doc in docs}

    def add_many(self, owner: str, hashes: list[str]) -> None:
        # insert_many(ordered=False) + swallow BulkWriteError:
        # - works but need to handle duplicate-key errors
        # - messier than upsert
        # update_many:
        # - can't create many distinct docs
        if not hashes:
            return
        ops = [
            UpdateOne(
                filter={"owner": owner, "hash": h},
                update={"$setOnInsert": {"owner": owner, "hash": h}},  # write only if it's a new row
                upsert=True,
            )
            for h in hashes
        ]
        self._collection.bulk_write(ops, ordered=False)
