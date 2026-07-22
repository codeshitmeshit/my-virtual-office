"""Backward-compatible standard-chat projection over the canonical timeline."""

from __future__ import annotations

import base64
import copy
import json
import os
import re
import threading
from collections import OrderedDict
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

from .conversation_timeline import ConversationTimelineService, TimelineScope


SOURCE_CACHE_ENTRY_LIMIT = 32
SOURCE_CACHE_BYTE_LIMIT = 64 * 1024 * 1024
SOURCE_RECORD_LIMIT = 1_000
KEY_SEPARATOR = "\x1f"


def history_hash(value: Any) -> str:
    result = 0x811C9DC5
    for byte in str(value or "").encode("utf-8"):
        result ^= byte
        result = (result * 0x01000193) & 0xFFFFFFFF
    return f"{result:08x}"


def encode_cursor(epoch_ms: Any, message_id: Any) -> str:
    payload = json.dumps(
        {"v": 1, "ts": int(epoch_ms or 0), "id": str(message_id or "")},
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(cursor: Any) -> tuple[int, str]:
    raw = str(cursor or "").strip()
    if not raw or len(raw) > 1_024:
        raise ValueError("invalid chat history cursor")
    try:
        padding = "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode((raw + padding).encode("ascii")).decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("v") != 1:
            raise ValueError
        epoch_ms = int(payload.get("ts"))
        message_id = str(payload.get("id") or "")
        if epoch_ms < 0 or not message_id or len(message_id) > 512:
            raise ValueError
        return epoch_ms, message_id
    except Exception as exc:
        raise ValueError("invalid chat history cursor") from exc


def _parse_epoch_ms(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        return int(value * 1000) if value < 10_000_000_000 else int(value)
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
    except (TypeError, ValueError):
        return 0


def extract_content(row: Mapping[str, Any]) -> tuple[str, list[Any], list[dict[str, Any]]]:
    message = row.get("message") if isinstance(row.get("message"), Mapping) else row
    content = message.get("content")
    text = str(row.get("text") or message.get("text") or "")
    media = copy.deepcopy(list(row.get("media") or []))
    tools = [copy.deepcopy(dict(item)) for item in (row.get("tools") or []) if isinstance(item, Mapping)]
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text_parts = []
        indexed_tools = {str(item.get("id") or item.get("toolCallId") or ""): item for item in tools}
        for block in content:
            if not isinstance(block, Mapping):
                continue
            block_type = str(block.get("type") or "")
            if block_type == "text":
                text_parts.append(str(block.get("text") or ""))
            elif block_type in ("image", "image_url", "input_image", "file", "media", "attachment", "video", "audio"):
                url = block.get("url") or block.get("path") or block.get("filePath") or block.get("mediaUrl")
                if not url and isinstance(block.get("image_url"), Mapping):
                    url = block["image_url"].get("url")
                if not url and isinstance(block.get("source"), Mapping):
                    url = block["source"].get("url") or block["source"].get("path")
                if url:
                    media.append(
                        {
                            "url": url,
                            "mimeType": block.get("mimeType") or block.get("media_type") or block.get("contentType") or "",
                            "name": block.get("name") or block.get("filename") or "",
                        }
                    )
            elif block_type in ("toolCall", "tool_call"):
                function = block.get("function") if isinstance(block.get("function"), Mapping) else {}
                tool = {
                    "id": block.get("id") or block.get("toolCallId") or block.get("callId") or "",
                    "name": block.get("name") or block.get("toolName") or function.get("name") or "tool",
                    "arguments": block.get("arguments") or block.get("args") or block.get("input") or function.get("arguments") or {},
                    "status": "done",
                }
                tools.append(tool)
                if tool["id"]:
                    indexed_tools[str(tool["id"])] = tool
            elif block_type in ("toolResult", "tool_result"):
                tool_id = str(block.get("toolCallId") or block.get("id") or "")
                tool = indexed_tools.get(tool_id)
                result = block.get("result", block.get("output", block.get("content", block.get("text", block.get("error", "")))))
                if tool is None:
                    tool = {"id": tool_id, "name": block.get("name") or "tool result", "arguments": {}}
                    tools.append(tool)
                    if tool_id:
                        indexed_tools[tool_id] = tool
                tool["result"] = copy.deepcopy(result)
                tool["error"] = copy.deepcopy(block.get("error") or "")
                tool["status"] = "error" if block.get("error") else "done"
        text = "".join(text_parts)
    return text, media, tools


def clean_feishu_image_text(row: Mapping[str, Any], metadata: Mapping[str, Any], text: Any) -> str:
    if str(metadata.get("sourceApp") or "").lower() != "feishu" or str(metadata.get("messageType") or "").lower() != "image":
        return str(text or "")
    attachments = row.get("attachments") if isinstance(row.get("attachments"), list) else []
    file_keys = {str(item.get("fileKey") or "").strip() for item in attachments if isinstance(item, Mapping)}
    names = {str(item.get("name") or "").strip() for item in attachments if isinstance(item, Mapping)}
    paths = {str(item.get("path") or "").strip() for item in attachments if isinstance(item, Mapping)}
    urls = {str(item.get("url") or "").strip() for item in attachments if isinstance(item, Mapping)}
    visible = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        image_match = re.fullmatch(r"!\[[^\]]*\]\(\s*([^\s)]+)\s*\)", stripped, re.IGNORECASE)
        if image_match and image_match.group(1) in file_keys:
            continue
        if stripped == "图片附件已同步到 VO。":
            continue
        if stripped.startswith("文件名：") and stripped.removeprefix("文件名：").strip() in names:
            continue
        if stripped.startswith("本地路径：") and stripped.removeprefix("本地路径：").strip() in paths:
            continue
        if stripped.startswith("预览 URL：") and stripped.removeprefix("预览 URL：").strip() in urls:
            continue
        visible.append(line)
    return "\n".join(visible).strip()


class BoundedJsonlHistoryCache:
    def __init__(self, *, entry_limit: int = SOURCE_CACHE_ENTRY_LIMIT, byte_limit: int = SOURCE_CACHE_BYTE_LIMIT) -> None:
        self._entry_limit = entry_limit
        self._byte_limit = byte_limit
        self._entries: OrderedDict[tuple[str, str, int], dict[str, Any]] = OrderedDict()
        self._bytes = 0
        self._hits = 0
        self._misses = 0
        self._lock = threading.RLock()

    @staticmethod
    def _signature(path: str) -> tuple[int, int, int] | None:
        try:
            stat = os.stat(path)
            return stat.st_ino, stat.st_size, stat.st_mtime_ns
        except (FileNotFoundError, OSError):
            return None

    @staticmethod
    def _iter_reverse(path: str, chunk_size: int = 64 * 1024):
        try:
            with open(path, "rb") as stream:
                stream.seek(0, os.SEEK_END)
                position = stream.tell()
                remainder = b""
                while position > 0:
                    read_size = min(chunk_size, position)
                    position -= read_size
                    stream.seek(position)
                    data = stream.read(read_size) + remainder
                    lines = data.split(b"\n")
                    remainder = lines[0]
                    for line in reversed(lines[1:]):
                        if line.strip():
                            yield line.decode("utf-8", errors="replace")
                if remainder.strip():
                    yield remainder.decode("utf-8", errors="replace")
        except (FileNotFoundError, OSError):
            return

    def load(
        self,
        path: str,
        cache_key: str,
        max_records: int = SOURCE_RECORD_LIMIT,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(max_records or SOURCE_RECORD_LIMIT), SOURCE_RECORD_LIMIT))
        signature = self._signature(path)
        key = (os.path.abspath(path or ""), str(cache_key or ""), limit)
        with self._lock:
            cached = self._entries.get(key)
            if cached and cached["signature"] == signature:
                self._hits += 1
                self._entries.move_to_end(key)
                return copy.deepcopy(cached["rows"])
            self._misses += 1

        newest_first = []
        if signature:
            for line in self._iter_reverse(path):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict) or (predicate and not predicate(row)):
                    continue
                newest_first.append(row)
                if len(newest_first) >= limit:
                    break
        rows = list(reversed(newest_first))
        estimated_bytes = len(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        with self._lock:
            previous = self._entries.pop(key, None)
            if previous:
                self._bytes -= previous["bytes"]
            self._entries[key] = {"signature": signature, "rows": copy.deepcopy(rows), "bytes": estimated_bytes}
            self._bytes += estimated_bytes
            while len(self._entries) > self._entry_limit or self._bytes > self._byte_limit:
                _, evicted = self._entries.popitem(last=False)
                self._bytes -= evicted["bytes"]
        return copy.deepcopy(rows)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"hits": self._hits, "misses": self._misses, "entries": len(self._entries), "bytes": self._bytes}


class ChatHistoryTimelineService:
    def __init__(self, timeline: ConversationTimelineService, cache: BoundedJsonlHistoryCache | None = None) -> None:
        self._timeline = timeline
        self._cache = cache or BoundedJsonlHistoryCache()

    def load_jsonl(
        self,
        path: str,
        cache_key: str,
        max_records: int = SOURCE_RECORD_LIMIT,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
    ) -> list[dict[str, Any]]:
        return self._cache.load(path, cache_key, max_records, predicate)

    def cache_stats(self) -> dict[str, int]:
        return self._cache.stats()

    @staticmethod
    def scope(request: Any) -> TimelineScope:
        return TimelineScope.create(
            request.provider_kind,
            request.agent_id,
            "",
            request.conversation_id,
            request.session_key,
        )

    def normalize_message(self, request: Any, row: Any, source: str = "", ordinal: int = 0) -> dict[str, Any]:
        row = row if isinstance(row, Mapping) else {}
        message = row.get("message") if isinstance(row.get("message"), Mapping) else row
        metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
        from_ref = row.get("from") if isinstance(row.get("from"), Mapping) else {}
        to_ref = row.get("to") if isinstance(row.get("to"), Mapping) else {}
        from_id = str(row.get("fromAgentId") or from_ref.get("id") or "")
        to_id = str(row.get("toAgentId") or to_ref.get("id") or "")
        explicit_role = str(row.get("role") or message.get("role") or "").strip().lower()
        direction = str(row.get("direction") or "").strip().lower()
        from_kind = str(from_ref.get("providerKind") or "").strip().lower()
        role = explicit_role or ("user" if direction == "request" or from_id == "user" or from_kind == "human" else "assistant")
        text, media, tools = extract_content(row)
        text = clean_feishu_image_text(row, metadata, text)
        epoch_ms = _parse_epoch_ms(row.get("epochMs") or row.get("ts") or row.get("timestamp") or message.get("timestamp"))
        if not epoch_ms:
            try:
                epoch_ms = int(row.get("epochMs") or row.get("ts") or 0)
            except (TypeError, ValueError):
                epoch_ms = 0
        normalized_source = str(source or row.get("source") or request.provider_kind)
        canonical_identity = KEY_SEPARATOR.join(
            (
                request.provider_kind,
                request.conversation_id or request.session_key,
                role,
                str(epoch_ms),
                from_id,
                to_id,
                normalized_source,
                history_hash(text),
            )
        )
        source_id = row.get("commEventId") or row.get("messageId") or row.get("id") or message.get("id")
        message_id = str(source_id or f"fallback-{history_hash(canonical_identity)}-{int(ordinal or 0)}")
        normalized = {
            "id": message_id,
            "providerKind": request.provider_kind,
            "conversationId": request.conversation_id or request.session_key,
            "role": role,
            "text": text,
            "epochMs": epoch_ms,
            "from": row.get("from") if not isinstance(row.get("from"), Mapping) else row["from"].get("name") or from_id,
            "fromAgentId": from_id,
            "to": row.get("to") if not isinstance(row.get("to"), Mapping) else row["to"].get("name") or to_id,
            "toAgentId": to_id,
            "media": media,
            "attachments": copy.deepcopy(list(row.get("attachments") or [])),
            "tools": tools,
            "thinking": str(row.get("thinking") or ""),
            "reasoningTokens": int(row.get("reasoningTokens") or 0),
            "approval": copy.deepcopy(row.get("approval")) if isinstance(row.get("approval"), Mapping) else None,
            "status": str(row.get("status") or "done"),
            "source": normalized_source,
            "identityFields": canonical_identity,
            "idempotencyKey": str(row.get("idempotencyKey") or metadata.get("idempotencyKey") or ""),
        }
        version_fields = {
            key: normalized[key]
            for key in (
                "role", "text", "from", "fromAgentId", "to", "toAgentId", "media", "attachments",
                "tools", "thinking", "reasoningTokens", "approval", "status", "source", "idempotencyKey",
            )
        }
        normalized["version"] = history_hash(json.dumps(version_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return normalized

    @staticmethod
    def page_messages(messages: Iterable[Mapping[str, Any]], before: tuple[int, str] | None, limit_plus_one: int) -> dict[str, Any]:
        ordered = sorted(
            (copy.deepcopy(dict(item)) for item in messages if isinstance(item, Mapping)),
            key=lambda item: (int(item.get("epochMs") or 0), str(item.get("id") or "")),
        )
        if before:
            ordered = [item for item in ordered if (int(item.get("epochMs") or 0), str(item.get("id") or "")) < before]
        selected = ordered[-max(1, int(limit_plus_one or 1)) :]
        return {"messages": selected, "hasMore": len(ordered) > len(selected)}

    def page_provider(self, request: Any, rows: Iterable[Mapping[str, Any]], source: str, limit_plus_one: int) -> dict[str, Any]:
        normalized = [
            self.normalize_message(request, row, source=source, ordinal=index)
            for index, row in enumerate(rows or ())
            if isinstance(row, Mapping)
        ]
        return self.page_messages(normalized, request.before, limit_plus_one)

    def merge_pages(self, request: Any, source_pages: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], str, bool]:
        before = request.before
        source_has_more = False
        groups = []
        for page in source_pages or ():
            source_has_more = source_has_more or bool(page.get("hasMore"))
            group = []
            for message in page.get("messages") or ():
                if not isinstance(message, Mapping):
                    continue
                item = copy.deepcopy(dict(message))
                if before and (int(item.get("epochMs") or 0), str(item.get("id") or "")) >= before:
                    continue
                if item.get("source") == "agent-platform-communications":
                    item["sourcePriority"] = 10
                group.append(item)
            groups.append(group)
        ordered = list(self._timeline.merge_compatibility_records(self.scope(request), groups))
        messages = ordered[-max(1, min(int(request.limit or 50), 50)) :]
        has_more = source_has_more or len(ordered) > len(messages)
        next_cursor = encode_cursor(messages[0].get("epochMs"), messages[0].get("id")) if messages and has_more else ""
        for message in messages:
            message.pop("sourcePriority", None)
        return messages, next_cursor, has_more
