from struct import pack
import re
import base64
import logging

from pyrogram.file_id import FileId
from pymongo.errors import (
    DuplicateKeyError,
    OperationFailure,
    AutoReconnect,
    ServerSelectionTimeoutError,
)
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
from info import (
    FILES_DATABASE,
    DATABASE_URI,
    DATABASE_NAME,
    COLLECTION_NAME,
    MAX_BTN,
)

logger = logging.getLogger(__name__)

# Movie/file records normally live in FILES_DATABASE.  DATABASE_URI is the
# application's user/premium/config database, but it is also used as a
# failover movie store when the dedicated files cluster is full/unavailable.
primary_client = AsyncIOMotorClient(FILES_DATABASE)
primary_db = primary_client[DATABASE_NAME]
primary_instance = Instance.from_db(primary_db)

fallback_client = AsyncIOMotorClient(DATABASE_URI)
fallback_db = fallback_client[DATABASE_NAME]
fallback_instance = Instance.from_db(fallback_db)


@primary_instance.register
class PrimaryMedia(Document):
    file_id = fields.StrField(attribute="_id")
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)
    file_type = fields.StrField(allow_none=True)

    class Meta:
        indexes = ("$file_name",)
        collection_name = COLLECTION_NAME


@fallback_instance.register
class FallbackMedia(Document):
    file_id = fields.StrField(attribute="_id")
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)
    file_type = fields.StrField(allow_none=True)

    class Meta:
        indexes = ("$file_name",)
        collection_name = COLLECTION_NAME


def _is_write_capacity_error(exc):
    """True for errors where the primary files store cannot accept writes."""
    if isinstance(exc, (AutoReconnect, ServerSelectionTimeoutError)):
        return True
    if isinstance(exc, OperationFailure):
        msg = str(exc).lower()
        return (
            "space quota" in msg
            or "writes are blocked" in msg
            or "quota" in msg
            or "storage" in msg
        )
    return False


async def _safe_ensure_indexes(model, label):
    try:
        await model.ensure_indexes()
        logger.info("%s movie indexes are ready", label)
        return True
    except Exception as exc:
        # Index creation must never prevent the bot from starting. Reads can
        # still work without the index, and save_file() can fail over.
        logger.warning(
            "%s movie index creation skipped: %s. Bot will continue in read/failover mode.",
            label,
            exc,
        )
        return False


class _MediaCollection:
    """Compatibility wrapper for old code using Media.collection.*."""

    async def delete_one(self, query):
        results = []
        for model in (PrimaryMedia, FallbackMedia):
            try:
                results.append(await model.collection.delete_one(query))
            except Exception as exc:
                logger.warning("Movie delete_one failed on %s store: %s", model.__name__, exc)
        # Return an object with the usual deleted_count attribute.
        class Result:
            deleted_count = sum(getattr(r, "deleted_count", 0) for r in results)
        return Result()

    async def delete_many(self, query):
        results = []
        for model in (PrimaryMedia, FallbackMedia):
            try:
                results.append(await model.collection.delete_many(query))
            except Exception as exc:
                logger.warning("Movie delete_many failed on %s store: %s", model.__name__, exc)
        class Result:
            deleted_count = sum(getattr(r, "deleted_count", 0) for r in results)
        return Result()

    async def drop(self):
        for model in (PrimaryMedia, FallbackMedia):
            try:
                await model.collection.drop()
            except Exception as exc:
                logger.warning("Movie collection drop failed on %s store: %s", model.__name__, exc)


class Media:
    """Dual-store facade.

    Existing plugins can continue using Media.count_documents(),
    Media.find_one(), Media.collection.delete_*(), etc.  Searches read both
    MongoDB clusters and writes fail over to DATABASE_URI when FILES_DATABASE
    is full.
    """

    collection = _MediaCollection()

    @classmethod
    async def ensure_indexes(cls):
        await _safe_ensure_indexes(PrimaryMedia, "FILES_DATABASE")
        await _safe_ensure_indexes(FallbackMedia, "DATABASE_URI")

    @classmethod
    async def count_documents(cls, filter=None):
        filter = filter or {}
        total = 0
        for model in (PrimaryMedia, FallbackMedia):
            try:
                total += await model.count_documents(filter)
            except Exception as exc:
                logger.warning("Movie count failed on %s store: %s", model.__name__, exc)
        return total

    @classmethod
    async def find_one(cls, filter):
        for model in (PrimaryMedia, FallbackMedia):
            try:
                result = await model.find_one(filter)
                if result:
                    return result
            except Exception as exc:
                logger.warning("Movie find_one failed on %s store: %s", model.__name__, exc)
        return None


async def get_files_db_size():
    """Return combined movie-store data size from both configured DBs."""
    total = 0
    for db, label in ((primary_db, "FILES_DATABASE"), (fallback_db, "DATABASE_URI")):
        try:
            total += (await db.command("dbstats")).get("dataSize", 0)
        except Exception as exc:
            logger.warning("Could not read %s movie DB size: %s", label, exc)
    return total


def _make_media(model, media, file_id, file_ref, file_name):
    return model(
        file_id=file_id,
        file_ref=file_ref,
        file_name=file_name,
        file_size=media.file_size,
        mime_type=media.mime_type,
        caption=media.caption.html if media.caption else None,
        file_type=media.mime_type.split("/")[0],
    )


async def save_file(media):
    """Save a Telegram file.

    Primary: FILES_DATABASE.
    Failover: DATABASE_URI, in the same database/collection namespace as the
    application's other data. If both stores are unavailable/full, return
    'err' instead of crashing the bot.
    """
    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))

    for model, label in (
        (PrimaryMedia, "FILES_DATABASE"),
        (FallbackMedia, "DATABASE_URI"),
    ):
        try:
            file = _make_media(model, media, file_id, file_ref, file_name)
        except ValidationError:
            print("Error occurred while saving file in database")
            return "err"

        try:
            await file.commit()
        except DuplicateKeyError:
            print(
                f'{getattr(media, "file_name", "NO_FILE")} is already saved in database'
            )
            return "dup"
        except Exception as exc:
            if model is PrimaryMedia and _is_write_capacity_error(exc):
                logger.warning(
                    "FILES_DATABASE cannot accept movie writes (%s). "
                    "Switching this file to DATABASE_URI.",
                    exc,
                )
                continue
            if model is PrimaryMedia:
                logger.warning(
                    "FILES_DATABASE movie write failed (%s). Trying DATABASE_URI fallback.",
                    exc,
                )
                continue
            logger.error(
                "DATABASE_URI movie fallback write failed: %s. Existing files remain readable.",
                exc,
            )
            return "err"
        else:
            print(
                f'{getattr(media, "file_name", "NO_FILE")} is saved to {label}'
            )
            return "suc"

    return "err"


async def _search_model(model, filter, limit):
    cursor = model.find(filter)
    cursor.sort("$natural", -1)
    if limit is None:
        return [file async for file in cursor]
    return await cursor.to_list(length=limit)


async def get_search_results(query, max_results=MAX_BTN, offset=0, lang=None):
    query = query.strip()
    if not query:
        raw_pattern = "."
    elif " " not in query:
        raw_pattern = r"(\b|[\.\+\-_])" + query + r"(\b|[\.\+\-_])"
    else:
        raw_pattern = query.replace(" ", r".*[\s\.\+\-_]")
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except Exception:
        regex = query

    filter = {"file_name": regex}

    # Fetch enough rows from each store to construct the requested combined
    # page. Duplicate file_ids are removed so failover does not double results.
    fetch_count = None if lang else max(1, offset + max_results)
    rows = []
    seen = set()
    for model in (PrimaryMedia, FallbackMedia):
        try:
            model_rows = await _search_model(model, filter, fetch_count)
            for file in model_rows:
                key = getattr(file, "file_id", None) or getattr(file, "_id", None)
                if key in seen:
                    continue
                if lang and lang not in file.file_name.lower():
                    continue
                seen.add(key)
                rows.append(file)
        except Exception as exc:
            logger.warning("Movie search failed on %s store: %s", model.__name__, exc)

    # Keep primary-store results first, then failover-store results.
    if lang:
        total_results = len(rows)
    else:
        total_results = 0
        for model in (PrimaryMedia, FallbackMedia):
            try:
                total_results += await model.count_documents(filter)
            except Exception as exc:
                logger.warning("Movie count failed on %s store: %s", model.__name__, exc)
        # The same file can temporarily exist in both stores during failover.
        # The displayed result list is de-duplicated, while the count remains
        # a safe upper bound in that uncommon case.
    files = rows[offset : offset + max_results]
    next_offset = offset + max_results
    if next_offset >= total_results:
        next_offset = ""
    return files, next_offset, total_results


async def get_bad_files(query, file_type=None, offset=0, filter=False):
    query = query.strip()
    if not query:
        raw_pattern = "."
    elif " " not in query:
        raw_pattern = r"(\b|[\.\+\-_])" + query + r"(\b|[\.\+\-_])"
    else:
        raw_pattern = query.replace(" ", r".*[\s\.\+\-_]")
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except Exception:
        return []

    db_filter = {"file_name": regex}
    if file_type:
        db_filter["file_type"] = file_type

    files = []
    seen = set()
    for model in (PrimaryMedia, FallbackMedia):
        try:
            cursor = model.find(db_filter)
            cursor.sort("$natural", -1)
            model_files = await cursor.to_list(length=None)
            for file in model_files:
                key = getattr(file, "file_id", None) or getattr(file, "_id", None)
                if key in seen:
                    continue
                seen.add(key)
                files.append(file)
        except Exception as exc:
            logger.warning("Movie bad-file lookup failed on %s store: %s", model.__name__, exc)

    total_results = len(files)
    return files, total_results


async def get_file_details(query):
    filter = {"file_id": query}
    return [file] if (file := await Media.find_one(filter)) else []


def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0
    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0
            r += bytes([i])
    return base64.urlsafe_b64encode(r).decode().rstrip("=")


def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")


def unpack_new_file_id(new_file_id):
    """Return file_id, file_ref"""
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash,
        )
    )
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref
