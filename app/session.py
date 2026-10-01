import json
import logging
from datetime import datetime, timezone

from redis.asyncio import Redis

from app.config import Settings

logger = logging.getLogger(__name__)
_local_history: dict[str, list[dict[str, str]]] = {}
_clients: dict[str, Redis] = {}


class ModalMonthlyQuotaExceeded(Exception):
    pass


class ModalQuotaStoreUnavailable(Exception):
    pass


def _redis(url: str) -> Redis:
    if url not in _clients:
        _clients[url] = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _clients[url]


def _session_key(chat_id: str) -> str:
    return f"cloud-bot:session:{chat_id}"


async def get_history(settings: Settings, chat_id: str) -> list[dict[str, str]]:
    try:
        values = await _redis(settings.valkey_url).lrange(
            _session_key(chat_id),
            -settings.session_max_turns * 2,
            -1,
        )
        return [json.loads(value) for value in values]
    except Exception as error:
        logger.warning("Valkey unavailable; using in-process history: %s", error)
        return list(_local_history.get(chat_id, []))


async def save_exchange(
    settings: Settings,
    chat_id: str,
    user_message: str,
    assistant_reply: str,
) -> None:
    exchange = [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": assistant_reply},
    ]
    try:
        client = _redis(settings.valkey_url)
        key = _session_key(chat_id)
        await client.rpush(
            key,
            *(json.dumps(item, ensure_ascii=False) for item in exchange),
        )
        await client.ltrim(key, -settings.session_max_turns * 2, -1)
        await client.expire(key, settings.session_ttl)
    except Exception as error:
        logger.warning("Valkey unavailable; saving history in process: %s", error)
        history = _local_history.setdefault(chat_id, [])
        history.extend(exchange)
        del history[:-settings.session_max_turns * 2]


async def clear_session(settings: Settings, chat_id: str) -> None:
    _local_history.pop(chat_id, None)
    try:
        await _redis(settings.valkey_url).delete(_session_key(chat_id))
    except Exception as error:
        logger.warning("Could not clear Valkey session: %s", error)


async def reserve_modal_request(settings: Settings) -> None:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    key = f"cloud-bot:modal-requests:{month}"
    script = (
        "local count = tonumber(redis.call('GET', KEYS[1]) or '0') "
        "if count >= tonumber(ARGV[1]) then return 0 end "
        "local next_count = redis.call('INCR', KEYS[1]) "
        "if next_count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end "
        "return 1"
    )
    try:
        allowed = await _redis(settings.valkey_url).eval(
            script,
            1,
            key,
            settings.modal_max_requests_per_month,
            40 * 24 * 60 * 60,
        )
    except Exception as error:
        raise ModalQuotaStoreUnavailable from error
    if not allowed:
        raise ModalMonthlyQuotaExceeded


async def close_session_store() -> None:
    for client in _clients.values():
        await client.aclose()
    _clients.clear()