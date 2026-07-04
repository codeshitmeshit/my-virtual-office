"""Feishu chat channel adapter for representative-agent conversations."""
import hashlib
import json
import os
import random
import uuid

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


def record_channel_event(status_dir, record, *, now, lock):
    record = record if isinstance(record, dict) else {}
    item = {
        "id": record.get("id") or str(uuid.uuid4()),
        "createdAt": now(),
        **record,
    }
    path = channel_record_path(status_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    return item


def load_channel_records(status_dir, *, limit=500):
    path = channel_record_path(status_dir)
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    return rows[-max(1, min(int(limit or 500), 2000)):]


def channel_records_response(status_dir, *, limit=500):
    records = load_channel_records(status_dir, limit=limit)
    return {
        "ok": True,
        "records": records,
        "count": len(records),
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
    return {
        "openId": str(sender_id.get("open_id") or sender.get("open_id") or "").strip(),
        "userId": str(sender_id.get("user_id") or sender.get("user_id") or "").strip(),
        "unionId": str(sender_id.get("union_id") or sender.get("union_id") or "").strip(),
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


def _safe_channel_call(func, *args):
    if not func:
        return {}
    try:
        result = func(*args)
        return result if isinstance(result, dict) else {"ok": bool(result), "result": result}
    except Exception as exc:
        return {"ok": False, "status": "exception", "error": str(exc)}


def _message_id_from_send_result(result):
    result = result if isinstance(result, dict) else {}
    return str(result.get("messageId") or result.get("message_id") or ((result.get("data") or {}) if isinstance(result.get("data"), dict) else {}).get("message_id") or "").strip()


def _reaction_id_from_result(result):
    result = result if isinstance(result, dict) else {}
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    return str(result.get("reactionId") or result.get("reaction_id") or data.get("reaction_id") or "").strip()


def handle_message_event(
    body,
    *,
    cfg,
    bindings,
    load_records,
    record_event,
    lock_for,
    dispatch_agent,
    send_text,
    find_agent,
    send_receipt=None,
    recall_message=None,
    add_reaction=None,
    delete_reaction=None,
    choose_receipt=random_ack_emoji,
    choose_reaction=ack_reaction_emoji_type,
):
    event = (body or {}).get("event") if isinstance((body or {}).get("event"), dict) else {}
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    chat_id = str(message.get("chat_id") or "").strip()
    chat_type = str(message.get("chat_type") or "").strip().lower()
    message_type = str(message.get("message_type") or "").strip().lower()
    source_message_id = str(message.get("message_id") or "").strip()
    text = _message_text(message)
    identity = sender_identity(event)
    base_record = {
        "channel": "feishu",
        "sourceApp": "feishu",
        "sourceSurface": "feishu-dm",
        "sourceMessageId": source_message_id,
        "feishuChatId": chat_id,
        "chatType": chat_type,
        "messageType": message_type,
        "sender": identity,
    }
    if not cfg.get("enabled", False):
        record = record_event({**base_record, "event": "rejected", "reason": "chat_app_disabled"})
        return {"ok": False, "status": "disabled", "record": record, "_status": 503}
    if not chat_app_configured(cfg):
        record = record_event({**base_record, "event": "rejected", "reason": "missing_chat_app_credentials"})
        return {"ok": False, "status": "missing_chat_app_credentials", "record": record, "_status": 503}
    if chat_type != "p2p":
        record = record_event({**base_record, "event": "ignored", "reason": "unsupported_chat_type"})
        return {"ok": True, "status": "ignored_unsupported_chat_type", "record": record}
    if message_type and message_type != "text":
        record = record_event({**base_record, "event": "ignored", "reason": "unsupported_message_type"})
        return {"ok": True, "status": "ignored_unsupported_message_type", "record": record}
    if not source_message_id:
        record = record_event({**base_record, "event": "rejected", "reason": "missing_message_id"})
        return {"ok": False, "status": "missing_message_id", "record": record, "_status": 400}
    if not text:
        record = record_event({**base_record, "event": "ignored", "reason": "empty_text"})
        return {"ok": True, "status": "ignored_empty_text", "record": record}
    hit = channel_idempotency_hit(load_records, source_message_id)
    if hit:
        return {"ok": True, "status": "duplicate", "idempotent": True, "record": hit, "reply": hit.get("reply") or ""}
    vo_user_id = find_bound_user(bindings, identity, chat_id) or channel_user_id(identity, chat_id)
    representative_agent_id = str(cfg.get("representativeAgentId") or "").strip()
    if not representative_agent_id:
        reply = "VO 尚未配置当前 CEO Agent，请先在 VO 设置中选择一个代表 Agent。"
        send_result = send_text(chat_id, reply)
        record = record_event({
            **base_record,
            "event": "rejected",
            "reason": "missing_representative_agent",
            "voUserId": vo_user_id,
            "reply": reply,
            "sendResult": send_result,
        })
        return {"ok": False, "status": "missing_representative_agent", "record": record, "sendResult": send_result, "_status": 400}
    conversation_id = representative_conversation_id(vo_user_id, chat_id)
    lock = lock_for(conversation_id)
    with lock:
        hit = channel_idempotency_hit(load_records, source_message_id)
        if hit:
            return {"ok": True, "status": "duplicate", "idempotent": True, "record": hit, "reply": hit.get("reply") or ""}
        inbound_record = record_event({
            **base_record,
            "event": "user_message",
            "voUserId": vo_user_id,
            "representativeAgentId": representative_agent_id,
            "conversationId": conversation_id,
            "text": text,
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
        result = dispatch_agent(
            representative_agent_id,
            text,
            conversation_id,
            {
                "sourceMessageId": source_message_id,
                "feishuChatId": chat_id,
                "senderName": identity.get("openId") or identity.get("userId") or "Feishu User",
            },
        )
        reply = str(result.get("reply") or result.get("error") or "").strip() or "处理完成，但没有可发送的文本回复。"
        feishu_reply = representative_display_reply(representative_agent_id, reply, find_agent=find_agent)
        send_result = send_text(chat_id, feishu_reply)
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
            "agentResult": {k: v for k, v in result.items() if k not in {"tools", "thinking"}},
            "sendResult": send_result,
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
            "status": "completed" if result.get("ok") else "agent_failed",
            "reply": reply,
            "agentResult": result,
            "sendResult": send_result,
            "reactionResult": reaction_result,
            "reactionDeleteResult": reaction_delete_result,
            "receiptResult": receipt_result,
            "receiptRecallResult": receipt_recall_result,
            "record": completed_record,
        }
