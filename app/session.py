import json
import logging

from redis.asyncio import Redis

from app.config import Settings

logger = logging.getLogger(__name__)
_local_history: dict[str, list[dict[str, str]]] = {}
_clients: dict[str, Redis] = {}


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


async def close_session_store() -> None:
    for client in _clients.values():
        await client.aclose()
    _clients.clear()