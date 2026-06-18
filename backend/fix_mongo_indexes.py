"""Drop djongo-orphaned unique indexes that block normal inserts on MongoDB.

Background: djongo cannot fully apply some SimpleJWT `token_blacklist` migrations
on MongoDB (field renames / BigAutoField retypes). That leaves a stale UNIQUE
index on `token_blacklist_outstandingtoken.jti_hex` — a column the running code
never populates — so every token insert after the first collides on `jti_hex: null`
(E11000 duplicate key) and the login/register endpoints 500.

This script drops any index on that collection whose key references `jti_hex`.
It is idempotent and safe to run on every boot (start-space.sh calls it): if the
index is already gone it does nothing. No documents are modified.

Reads MONGO_URI + DB_NAME from the environment (the same values the app uses),
falling back to DB_HOST/DB_PORT for local MongoDB.
"""

import os

from pymongo import MongoClient

DB_NAME = os.environ.get("DB_NAME", "medical_platform")
MONGO_URI = os.environ.get("MONGO_URI", "")
COLLECTION = "token_blacklist_outstandingtoken"
BAD_FIELD = "jti_hex"


def _client():
    if MONGO_URI:
        return MongoClient(MONGO_URI)
    host = os.environ.get("DB_HOST", "localhost")
    port = int(os.environ.get("DB_PORT", "27017"))
    return MongoClient(host=host, port=port)


def main():
    client = _client()
    db = client[DB_NAME]
    if COLLECTION not in db.list_collection_names():
        print(f"[fix_mongo_indexes] collection '{COLLECTION}' not present yet — nothing to do")
        return
    col = db[COLLECTION]
    dropped = []
    for idx in col.list_indexes():
        key = idx.get("key", {})
        if BAD_FIELD in key:
            name = idx["name"]
            col.drop_index(name)
            dropped.append(name)
    if dropped:
        print(f"[fix_mongo_indexes] dropped stale index(es): {dropped}")
    else:
        print("[fix_mongo_indexes] no stale jti_hex index found — OK")


if __name__ == "__main__":
    main()
