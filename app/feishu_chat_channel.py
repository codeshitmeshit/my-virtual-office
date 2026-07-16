"""Feishu chat channel adapter for representative-agent conversations."""
import hashlib
import json
import os
import random
import re
import uuid
from datetime import datetime

ACK_EMOJIS = ("LGTM",)
ACK_REACTION_EMOJI_TYPE = "LGTM"


def chat_source_metadata(body):
    body = body if isinstance(body, dict) else {}
    mapping = (
        ("sourceApp", "sourceApp"),
        ("sourceSurface", "sourceSurface"),
        ("sourceLabel", "sourceLabel"),
        ("channel", "channel"),
        ("sourceMessageId", "sourceMessageId"),
        ("feishuChatId", "feishuChatId"),
        ("representativeAgentId", "representativeAgentId"),
    )
    metadata = {}
    for source_key, target_key in mapping:
        value = str(body.get(source_key) or "").strip()
        if value:
            metadata[target_key] = value
    return metadata


def channel_record_path(status_dir):
    return os.path.join(status_dir, "feishu-channel-records.jsonl")


def group_record_dir(status_dir):
    return os.path.join(status_dir, "feishu-group-records")


def group_record_path(status_dir, chat_id):
    seed = f"feishu-group-record:{str(chat_id or 'unknown').strip() or 'unknown'}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return os.path.join(group_record_dir(status_dir), f"{digest}.jsonl")


def _is_group_record(record):
    record = record if isinstance(record, dict) else {}
    return (
        str(record.get("chatType") or "").strip().lower() == "group"
        or str(record.get("sourceSurface") or "").strip().lower() == "feishu-group"
    )


def _record_sort_key(record):
    record = record if isinstance(record, dict) else {}
    created_at = record.get("createdAt")
    if isinstance(created_at, (int, float)):
        timestamp = float(created_at)
    else:
        value = str(created_at or "").strip()
        try:
            timestamp = float(value)
        except ValueError:
            try:
                timestamp = datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000
            except (ValueError, OverflowError):
                timestamp = 0.0
    return timestamp, str(record.get("id") or "")


def source_index_dir(status_dir):
    return os.path.join(status_dir, "feishu-source-message-index")


def source_index_path(status_dir, source_message_id):
    digest = hashlib.sha256(str(source_message_id or "").encode("utf-8")).hexdigest()
    return os.path.join(source_index_dir(status_dir), f"{digest}.json")


def group_metrics_path(status_dir):
    return os.path.join(status_dir, "feishu-group-metrics.json")


def load_group_metrics(status_dir):
    try:
        with open(group_metrics_path(status_dir), "r", encoding="utf-8") as f:
            item = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        item = {}
    return item if isinstance(item, dict) else {}


def increment_group_metrics(status_dir, increments, *, now, lock):
    increments = increments if isinstance(increments, dict) else {}
    if not increments:
        return load_group_metrics(status_dir)
    path = group_metrics_path(status_dir)
    os.makedirs(status_dir, exist_ok=True)
    with lock:
        current = load_group_metrics(status_dir)
        counters = current.get("counters") if isinstance(current.get("counters"), dict) else {}
        for key, amount in increments.items():
            clean_key = str(key or "").strip()[:128]
            if clean_key:
                counters[clean_key] = max(0, int(counters.get(clean_key) or 0) + int(amount or 0))
        item = {
            "schema": "vo.feishu-group-metrics/v1",
            "updatedAt": now(),
            "counters": counters,
        }
        temp_path = f"{path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                os.chmod(temp_path, 0o600)
                f.write(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
            os.chmod(path, 0o600)
        finally:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
    return item


def load_source_index(status_dir, source_message_id):
    source_message_id = str(source_message_id or "").strip()
    if not source_message_id:
        return None
    try:
        with open(source_index_path(status_dir, source_message_id), "r", encoding="utf-8") as f:
            item = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(item, dict) or item.get("sourceMessageId") != source_message_id:
        return None
    return item


def save_source_index(status_dir, record, *, now, lock):
    record = record if isinstance(record, dict) else {}
    source_message_id = str(record.get("sourceMessageId") or "").strip()
    event = str(record.get("event") or "").strip()
    if not source_message_id or event not in {"user_message", "turn_completed"}:
        return None
    state = "completed" if event == "turn_completed" else "processing"
    item = {
        "schema": "vo.feishu-source-message-index/v1",
        "sourceMessageId": source_message_id,
        "state": state,
        "updatedAt": now(),
        "record": {
            key: record.get(key)
            for key in (
                "id", "event", "sourceMessageId", "conversationId", "feishuChatId",
                "representativeAgentId", "chatType", "messageType", "reply",
                "feishuReply", "deliveryStatus", "sendResult", "agentResult",
            )
            if record.get(key) not in (None, "", [], {})
        },
    }
    directory = source_index_dir(status_dir)
    path = source_index_path(status_dir, source_message_id)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    temp_path = f"{path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    encoded = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with lock:
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                os.chmod(temp_path, 0o600)
                f.write(encoded)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
            os.chmod(path, 0o600)
        finally:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
    return item


def record_channel_event(status_dir, record, *, now, lock):
    record = record if isinstance(record, dict) else {}
    item = {
        "id": record.get("id") or str(uuid.uuid4()),
        "createdAt": now(),
        **record,
    }
    path = (
        group_record_path(status_dir, record.get("feishuChatId"))
        if _is_group_record(record)
        else channel_record_path(status_dir)
    )
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with lock:
        with open(path, "a", encoding="utf-8") as f:
            os.chmod(path, 0o600)
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    return item


def load_channel_records(status_dir, *, limit=500):
    bounded_limit = max(1, min(int(limit or 500), 2000))
    rows = []
    paths = [channel_record_path(status_dir)]
    directory = group_record_dir(status_dir)
    try:
        paths.extend(
            os.path.join(directory, name)
            for name in sorted(os.listdir(directory))
            if name.endswith(".jsonl")
        )
    except FileNotFoundError:
        pass
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict):
                        rows.append(item)
                    if len(rows) > bounded_limit * 2:
                        rows.sort(key=_record_sort_key)
                        del rows[:-bounded_limit]
        except FileNotFoundError:
            continue
    rows.sort(key=_record_sort_key)
    deduped = {}
    anonymous = []
    for row in rows:
        record_id = str(row.get("id") or "").strip()
        if record_id:
            deduped[record_id] = row
        else:
            anonymous.append(row)
    merged = [*deduped.values(), *anonymous]
    merged.sort(key=_record_sort_key)
    return merged[-bounded_limit:]


def load_group_recovery_turns(status_dir, chat_id, *, exclude_source_message_id="", max_turns=80):
    """Load bounded, completed history from exactly one physical group shard."""
    clean_chat_id = str(chat_id or "").strip()
    if not clean_chat_id:
        return []
    excluded_id = str(exclude_source_message_id or "").strip()
    completed = []
    try:
        with open(group_record_path(status_dir, clean_chat_id), "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(item, dict):
                    continue
                source_id = str(item.get("sourceMessageId") or "").strip()
                if (
                    str(item.get("event") or "").strip() != "turn_completed"
                    or str(item.get("feishuChatId") or "").strip() != clean_chat_id
                    or not source_id
                    or source_id == excluded_id
                ):
                    continue
                text = str(item.get("text") or "").strip()
                reply = str(item.get("reply") or "").strip()
                if text or reply:
                    completed.append(item)
    except (FileNotFoundError, OSError):
        return []

    completed.sort(key=_record_sort_key)
    completed = completed[-max(1, min(int(max_turns or 80), 500)):]
    turns = []
    for item in completed:
        source_id = str(item.get("sourceMessageId") or "").strip()
        text = str(item.get("text") or "").strip()
        reply = str(item.get("reply") or "").strip()
        sender = item.get("sender") if isinstance(item.get("sender"), dict) else {}
        if text:
            turn = {"role": "user", "text": text, "sourceMessageId": source_id}
            sender_name = str(sender.get("name") or item.get("fromDisplayName") or "").strip()
            sender_id = str(
                sender.get("openId") or sender.get("userId") or sender.get("unionId")
                or item.get("voUserId") or ""
            ).strip()
            if sender_name:
                turn["name"] = sender_name
            if sender_id:
                turn["speakerId"] = sender_id
            turns.append(turn)
        if reply:
            turns.append({"role": "assistant", "text": reply, "sourceMessageId": source_id})
    return turns


def migrate_legacy_group_records(status_dir, *, lock):
    """Move legacy group rows out of the shared channel audit into per-group shards."""
    shared_path = channel_record_path(status_dir)
    with lock:
        try:
            with open(shared_path, "r", encoding="utf-8") as f:
                rows = [json.loads(line) for line in f if line.strip()]
        except FileNotFoundError:
            return {"migrated": 0, "shards": 0}
        except json.JSONDecodeError:
            return {"migrated": 0, "shards": 0, "status": "invalid_legacy_jsonl"}

        group_rows = [row for row in rows if isinstance(row, dict) and _is_group_record(row)]
        if not group_rows:
            return {"migrated": 0, "shards": 0}
        private_rows = [row for row in rows if not (isinstance(row, dict) and _is_group_record(row))]
        by_path = {}
        for row in group_rows:
            path = group_record_path(status_dir, row.get("feishuChatId"))
            by_path.setdefault(path, []).append(row)

        for path, pending in by_path.items():
            os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
            existing_ids = set()
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            existing = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(existing, dict) and existing.get("id"):
                            existing_ids.add(str(existing["id"]))
            except FileNotFoundError:
                pass
            with open(path, "a", encoding="utf-8") as f:
                os.chmod(path, 0o600)
                for row in pending:
                    record_id = str(row.get("id") or "")
                    if record_id and record_id in existing_ids:
                        continue
                    f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                    if record_id:
                        existing_ids.add(record_id)
                f.flush()
                os.fsync(f.fileno())

        temp_path = f"{shared_path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                os.chmod(temp_path, 0o600)
                for row in private_rows:
                    f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, shared_path)
            os.chmod(shared_path, 0o600)
        finally:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
    return {"migrated": len(group_rows), "shards": len(by_path)}


def channel_records_response(status_dir, *, limit=500):
    records = load_channel_records(status_dir, limit=limit)
    return {
        "ok": True,
        "records": [_public_channel_record(item) for item in records],
        "count": len(records),
    }


def _public_channel_record(record):
    record = record if isinstance(record, dict) else {}
    if str(record.get("chatType") or "").lower() != "group" and str(record.get("sourceSurface") or "").lower() != "feishu-group":
        return record
    sender = record.get("sender") if isinstance(record.get("sender"), dict) else {}
    sender_id = str(sender.get("openId") or sender.get("userId") or sender.get("unionId") or record.get("voUserId") or "feishu-user")
    agent_result = record.get("agentResult") if isinstance(record.get("agentResult"), dict) else {}
    send_result = record.get("sendResult") if isinstance(record.get("sendResult"), dict) else {}
    return {
        key: record.get(key)
        for key in (
            "id", "createdAt", "event", "reason", "channel", "sourceApp", "sourceSurface",
            "sourceLabel", "sourceMessageId", "conversationId", "representativeAgentId",
            "chatType", "messageType", "deliveryStatus", "replyInThread", "transport",
            "workerInstanceId", "requestId", "createTime",
        )
        if record.get(key) not in (None, "", [], {})
    } | {
        "redacted": True,
        "senderRef": f"feishu-member:{hashlib.sha256(sender_id.encode('utf-8')).hexdigest()[:16]}",
        "attachmentCount": len(record.get("attachments") or []),
        "agentOk": bool(agent_result.get("ok")) if agent_result else None,
        "deliveryOk": bool(send_result.get("ok")) if send_result else None,
    }


def channel_idempotency_hit(load_records, source_message_id):
    if not source_message_id:
        return None
    for row in reversed(load_records()):
        if row.get("sourceMessageId") == source_message_id and row.get("event") == "turn_completed":
            return row
    return None


def sender_identity(event):
    sender = ((event or {}).get("sender") or {})
    sender_id = sender.get("sender_id") if isinstance(sender.get("sender_id"), dict) else {}
    name = str(sender.get("sender_name") or sender.get("name") or "").strip()[:512]
    sender_type = str(sender.get("sender_type") or sender.get("type") or "").strip().lower()[:64]
    raw_is_bot = sender.get("sender_is_bot") if "sender_is_bot" in sender else sender.get("is_bot")
    return {
        "openId": str(sender_id.get("open_id") or sender.get("open_id") or "").strip(),
        "userId": str(sender_id.get("user_id") or sender.get("user_id") or "").strip(),
        "unionId": str(sender_id.get("union_id") or sender.get("union_id") or "").strip(),
        "name": name,
        "type": sender_type,
        **({"isBot": raw_is_bot} if isinstance(raw_is_bot, bool) else {}),
    }


def binding_key_candidates(identity, chat_id=""):
    keys = []
    for prefix, value in (
        ("open_id", identity.get("openId")),
        ("user_id", identity.get("userId")),
        ("union_id", identity.get("unionId")),
        ("chat_id", chat_id),
    ):
        if value:
            keys.append(f"{prefix}:{value}")
            keys.append(value)
    return keys


def find_bound_user(bindings, identity, chat_id=""):
    if not isinstance(bindings, dict):
        return ""
    for key in binding_key_candidates(identity, chat_id):
        value = bindings.get(key)
        if isinstance(value, dict):
            value = value.get("voUserId") or value.get("userId") or value.get("id")
        if str(value or "").strip():
            return str(value).strip()
    return ""


def channel_user_id(identity, chat_id=""):
    identity = identity if isinstance(identity, dict) else {}
    for prefix, key in (
        ("open_id", "openId"),
        ("user_id", "userId"),
        ("union_id", "unionId"),
    ):
        value = str(identity.get(key) or "").strip()
        if value:
            return f"feishu:{prefix}:{value}"
    if str(chat_id or "").strip():
        return f"feishu:chat_id:{str(chat_id).strip()}"
    return "feishu:unknown"


def representative_conversation_id(vo_user_id, chat_id):
    seed = f"{vo_user_id or 'unknown'}:{chat_id or 'unknown'}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"feishu-dm:{digest}"


def group_conversation_id(chat_id):
    seed = f"feishu-group:{chat_id or 'unknown'}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"feishu-group:{digest}"


def source_projection(chat_type):
    if str(chat_type or "").strip().lower() == "group":
        return {"sourceSurface": "feishu-group", "sourceLabel": "Feishu Group"}
    return {"sourceSurface": "feishu-dm", "sourceLabel": "Feishu DM"}


def bot_is_explicitly_mentioned(mentions):
    return any(
        isinstance(item, dict) and item.get("isBot") is True
        for item in (mentions or [])
    )


def group_admission_reason(cfg, identity, mentions):
    cfg = cfg if isinstance(cfg, dict) else {}
    if not cfg.get("groupChatEnabled", False):
        return "unsupported_chat_type"
    if str(cfg.get("transportImplementation") or "channel-sdk-node").strip().lower() != "channel-sdk-node":
        return "unsupported_group_transport"
    if str((identity or {}).get("type") or "").strip().lower() != "user" or (identity or {}).get("isBot") is not False:
        return "non_human_sender"
    if not bot_is_explicitly_mentioned(mentions):
        return "missing_bot_mention"
    return ""


def representative_display_reply(agent_id, reply, *, find_agent):
    text = str(reply or "").strip()
    return text


def random_ack_emoji():
    return random.choice(ACK_EMOJIS)


def ack_reaction_emoji_type():
    return ACK_REACTION_EMOJI_TYPE


def chat_app_configured(cfg):
    return bool((cfg or {}).get("appId") and (cfg or {}).get("appSecret"))


def _message_text(message):
    text = str(message.get("text") or "").strip()
    if not text and isinstance(message.get("content"), dict):
        text = str(message["content"].get("text") or "").strip()
    return text


def _message_content_dict(message):
    content = message.get("content")
    if isinstance(content, dict):
        return content
    if isinstance(content, str) and content.strip():
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _message_image_key(message):
    content = _message_content_dict(message)
    for key in ("image_key", "imageKey", "file_key", "fileKey"):
        value = str(content.get(key) or message.get(key) or "").strip()
        if value:
            return value
    return ""


def _normalize_attachment(result, *, fallback_name=""):
    result = result if isinstance(result, dict) else {}
    item = {
        "type": "image",
        "resourceType": result.get("resourceType") or "image",
        "name": result.get("name") or fallback_name or result.get("fileKey") or "feishu-image",
        "path": result.get("path") or "",
        "url": result.get("url") or "",
        "mimeType": result.get("mimeType") or result.get("contentType") or "image/*",
        "contentType": result.get("contentType") or result.get("mimeType") or "image/*",
        "size": result.get("size") or 0,
        "fileKey": result.get("fileKey") or "",
        "messageId": result.get("messageId") or "",
    }
    return {k: v for k, v in item.items() if v not in ("", None)}


def _image_prompt_text(text, attachment_result, image_key):
    attachment_result = attachment_result if isinstance(attachment_result, dict) else {}
    placeholder = re.compile(r"^\s*!\[[^\]]*\]\(\s*" + re.escape(str(image_key or "")) + r"\s*\)\s*$", re.IGNORECASE)
    visible_lines = [line for line in str(text or "").splitlines() if not placeholder.match(line)]
    base = "\n".join(visible_lines).strip() or "用户通过飞书发送了一张图片。"
    if attachment_result.get("ok"):
        return base
    reason = attachment_result.get("message") or attachment_result.get("error") or attachment_result.get("status") or "unknown_error"
    return base + f"\n\n图片附件暂时无法下载，飞书 image_key：{image_key}，错误：{reason}"


def _safe_channel_call(func, *args):
    if not func:
        return {}
    try:
        result = func(*args)
        return result if isinstance(result, dict) else {"ok": bool(result), "result": result}
    except TimeoutError as exc:
        return {"ok": False, "status": "timeout", "category": "send_timeout", "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "status": "exception", "error": str(exc)}


def _message_id_from_send_result(result):
    result = result if isinstance(result, dict) else {}
    return str(result.get("messageId") or result.get("message_id") or ((result.get("data") or {}) if isinstance(result.get("data"), dict) else {}).get("message_id") or "").strip()


def _reaction_id_from_result(result):
    result = result if isinstance(result, dict) else {}
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    return str(result.get("reactionId") or result.get("reaction_id") or data.get("reaction_id") or "").strip()


def _delivery_classification(result):
    result = result if isinstance(result, dict) else {}
    if result.get("ok"):
        return "sent"
    return str(result.get("category") or result.get("status") or "delivery_failed").strip()[:128] or "delivery_failed"


def handle_message_event(
    body,
    *,
    cfg,
    bindings,
    load_records,
    idempotency_hit,
    record_event,
    lock_for,
    dispatch_agent,
    send_text,
    reply_text,
    find_agent,
    send_receipt=None,
    recall_message=None,
    add_reaction=None,
    delete_reaction=None,
    choose_receipt=random_ack_emoji,
    choose_reaction=ack_reaction_emoji_type,
    download_image=None,
):
    event = (body or {}).get("event") if isinstance((body or {}).get("event"), dict) else {}
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    chat_id = str(message.get("chat_id") or "").strip()
    chat_type = str(message.get("chat_type") or "").strip().lower()
    message_type = str(message.get("message_type") or "").strip().lower()
    source_message_id = str(message.get("message_id") or "").strip()
    text = _message_text(message)
    identity = sender_identity(event)
    projection = source_projection(chat_type)
    mentions = message.get("mentions") if isinstance(message.get("mentions"), list) else []
    base_record = {
        "channel": "feishu",
        "sourceApp": "feishu",
        **projection,
        "sourceMessageId": source_message_id,
        "feishuChatId": chat_id,
        "chatType": chat_type,
        "messageType": message_type,
        "sender": identity,
    }
    reply_in_thread = bool(message.get("rootId") or message.get("threadId") or message.get("root_id") or message.get("thread_id"))

    def deliver(text_to_send):
        if chat_type == "group":
            if not reply_text:
                return {"ok": False, "status": "reply_unavailable", "category": "reply_unavailable"}
            return _safe_channel_call(reply_text, chat_id, source_message_id, text_to_send, reply_in_thread)
        return _safe_channel_call(send_text, chat_id, text_to_send)
    for key in ("transport", "workerInstanceId", "requestId", "createTime", "rootId", "threadId", "replyToMessageId", "mentions", "resources"):
        value = message.get(key) if key in {"createTime", "rootId", "threadId", "replyToMessageId", "mentions", "resources"} else (body or {}).get(key)
        if value not in (None, "", [], {}):
            base_record[key] = value
    if not cfg.get("enabled", False):
        record = record_event({**base_record, "event": "rejected", "reason": "chat_app_disabled"})
        return {"ok": False, "status": "disabled", "record": record, "_status": 503}
    if not chat_app_configured(cfg):
        record = record_event({**base_record, "event": "rejected", "reason": "missing_chat_app_credentials"})
        return {"ok": False, "status": "missing_chat_app_credentials", "record": record, "_status": 503}
    if chat_type == "group":
        group_reason = group_admission_reason(cfg, identity, mentions)
        if group_reason:
            record = record_event({**base_record, "event": "ignored", "reason": group_reason})
            return {"ok": True, "status": f"ignored_{group_reason}", "record": record}
    elif chat_type != "p2p":
        record = record_event({**base_record, "event": "ignored", "reason": "unsupported_chat_type"})
        return {"ok": True, "status": "ignored_unsupported_chat_type", "record": record}
    if not source_message_id:
        record = record_event({**base_record, "event": "rejected", "reason": "missing_message_id"})
        return {"ok": False, "status": "missing_message_id", "record": record, "_status": 400}
    if message_type and message_type not in {"text", "image"}:
        record = record_event({**base_record, "event": "ignored", "reason": "unsupported_message_type"})
        return {"ok": True, "status": "ignored_unsupported_message_type", "record": record}
    attachments = []
    attachment_result = {}
    image_key = ""
    if message_type == "image":
        image_key = _message_image_key(message)
        if not image_key:
            record = record_event({**base_record, "event": "rejected", "reason": "missing_image_key"})
            return {"ok": False, "status": "missing_image_key", "record": record, "_status": 400}
        attachment_result = _safe_channel_call(download_image, source_message_id, image_key) if download_image else {
            "ok": False,
            "status": "image_download_unavailable",
            "fileKey": image_key,
            "messageId": source_message_id,
            "resourceType": "image",
        }
        if attachment_result.get("ok"):
            attachments = [_normalize_attachment(attachment_result, fallback_name=image_key)]
        text = _image_prompt_text(text, attachment_result, image_key)
    if not text:
        record = record_event({**base_record, "event": "ignored", "reason": "empty_text"})
        return {"ok": True, "status": "ignored_empty_text", "record": record}
    hit = idempotency_hit(source_message_id) if idempotency_hit else channel_idempotency_hit(load_records, source_message_id)
    if hit:
        return {"ok": True, "status": "duplicate", "idempotent": True, "record": hit, "reply": hit.get("reply") or ""}
    vo_user_id = find_bound_user(bindings, identity, chat_id) or channel_user_id(identity, chat_id)
    representative_agent_id = str(cfg.get("representativeAgentId") or "").strip()
    if not representative_agent_id:
        reply = "VO 尚未配置当前 CEO Agent，请先在 VO 设置中选择一个代表 Agent。"
        send_result = deliver(reply)
        record = record_event({
            **base_record,
            "event": "rejected",
            "reason": "missing_representative_agent",
            "voUserId": vo_user_id,
            "reply": reply,
            "sendResult": send_result,
            "deliveryStatus": _delivery_classification(send_result),
            "replyInThread": reply_in_thread if chat_type == "group" else False,
        })
        return {"ok": False, "status": "missing_representative_agent", "record": record, "sendResult": send_result, "_status": 400}
    conversation_id = group_conversation_id(chat_id) if chat_type == "group" else representative_conversation_id(vo_user_id, chat_id)
    lock = lock_for(conversation_id)
    with lock:
        hit = idempotency_hit(source_message_id) if idempotency_hit else channel_idempotency_hit(load_records, source_message_id)
        if hit:
            return {"ok": True, "status": "duplicate", "idempotent": True, "record": hit, "reply": hit.get("reply") or ""}
        inbound_record = record_event({
            **base_record,
            "event": "user_message",
            "voUserId": vo_user_id,
            "representativeAgentId": representative_agent_id,
            "conversationId": conversation_id,
            "text": text,
            "attachments": attachments,
            "attachmentResult": attachment_result if message_type == "image" else {},
            "imageKey": image_key,
        })
        receipt_text = ""
        receipt_result = {}
        receipt_message_id = ""
        reaction_type = str((choose_reaction or ack_reaction_emoji_type)() or "").strip() or ACK_REACTION_EMOJI_TYPE
        reaction_result = _safe_channel_call(add_reaction, source_message_id, reaction_type) if add_reaction else {}
        reaction_id = _reaction_id_from_result(reaction_result)
        if not reaction_result.get("ok") and send_receipt:
            receipt_text = str((choose_receipt or random_ack_emoji)() or "").strip() or ACK_EMOJIS[0]
            receipt_result = _safe_channel_call(send_receipt, chat_id, receipt_text)
            receipt_message_id = _message_id_from_send_result(receipt_result)
        try:
            result = dispatch_agent(
                representative_agent_id,
                text,
                conversation_id,
                {
                    "sourceMessageId": source_message_id,
                    "feishuChatId": chat_id,
                    "senderName": identity.get("name") or identity.get("openId") or identity.get("userId") or "Feishu User",
                    "sender": identity,
                    **projection,
                    "attachments": attachments,
                },
            )
        except Exception as exc:
            result = {"ok": False, "status": "agent_exception", "error": str(exc)}
        result = result if isinstance(result, dict) else {"ok": False, "status": "invalid_agent_result", "error": "Agent returned an invalid result"}
        reply = str(result.get("reply") or result.get("error") or "").strip() or "处理完成，但没有可发送的文本回复。"
        feishu_reply = representative_display_reply(representative_agent_id, reply, find_agent=find_agent)
        send_result = deliver(feishu_reply)
        reaction_delete_result = _safe_channel_call(delete_reaction, source_message_id, reaction_id) if reaction_id and delete_reaction else {}
        receipt_recall_result = _safe_channel_call(recall_message, receipt_message_id) if receipt_message_id and recall_message else {}
        completed_record = record_event({
            **base_record,
            "event": "turn_completed",
            "voUserId": vo_user_id,
            "representativeAgentId": representative_agent_id,
            "conversationId": conversation_id,
            "text": text,
            "reply": reply,
            "feishuReply": feishu_reply,
            "attachments": attachments,
            "attachmentResult": attachment_result if message_type == "image" else {},
            "imageKey": image_key,
            "agentResult": {k: v for k, v in result.items() if k not in {"tools", "thinking"}},
            "sendResult": send_result,
            "deliveryStatus": _delivery_classification(send_result),
            "replyInThread": reply_in_thread if chat_type == "group" else False,
            "reactionType": reaction_type,
            "reactionResult": reaction_result,
            "reactionDeleteResult": reaction_delete_result,
            "receiptText": receipt_text if receipt_result else "",
            "receiptResult": receipt_result,
            "receiptRecallResult": receipt_recall_result,
            "inboundRecordId": inbound_record.get("id"),
        })
        return {
            "ok": bool(result.get("ok")) and bool(send_result.get("ok")),
            "status": (
                "agent_failed" if not result.get("ok")
                else ("delivery_failed" if chat_type == "group" and not send_result.get("ok") else "completed")
            ),
            "reply": reply,
            "agentResult": result,
            "sendResult": send_result,
            "reactionResult": reaction_result,
            "reactionDeleteResult": reaction_delete_result,
            "receiptResult": receipt_result,
            "receiptRecallResult": receipt_recall_result,
            "record": completed_record,
        }
