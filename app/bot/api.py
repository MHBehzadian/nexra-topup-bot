"""Management API for the Nexra panel: run this bot from the panel instead of
from its Telegram menu.

Same shape as the Nexra sales bots' API, so the panel talks to both alike:
everything lives under /api/v1, the panel sends `Authorization: Bearer <key>`,
and every answer is {"ok": true, "data": ...} or {"ok": false, "error": "..."}.

Served from the bot's own process, so a change made here (a text, a button's
colour) is live on the very next message — there is no second copy to sync.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
from datetime import datetime, timezone

from aiogram import Bot
from aiohttp import web

from . import auto_approve, bills, customize, sales
from .. import db
from ..config import settings

logger = logging.getLogger(__name__)

EMOJI_ID = re.compile(r"^\d{5,30}$")
PACK_NAME = re.compile(r"^[A-Za-z0-9_]{1,64}$")
# Previews are tiny and asked for again on every page load, so they're kept.
_EMOJI_CACHE: dict[str, tuple[bytes, str]] = {}
_EMOJI_CACHE_MAX = 2000


def _ok(data=None) -> web.Response:
    return web.json_response({"ok": True, "data": data}, dumps=lambda o: json.dumps(o, ensure_ascii=False))


def _fail(status: int, error: str) -> web.Response:
    return web.json_response({"ok": False, "error": error}, status=status)


@web.middleware
async def _auth(request: web.Request, handler):
    key = settings.management_key
    given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    # No key configured means nobody gets in, never that everybody does.
    if not key or not hmac.compare_digest(given.encode(), key.encode()):
        return _fail(401, "invalid key")
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception as exc:  # one bad call must not take the API down
        logger.exception(f"management API {request.method} {request.path} failed")
        return _fail(500, f"{type(exc).__name__}: {exc}")


async def _body(request: web.Request) -> dict:
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


# ------------------------------------------------------------------ info


async def info(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]
    me = await bot.me()
    return _ok({
        "role": "owner",
        "kind": "topup",
        "bot_username": me.username,
        "bot_name": me.full_name,
    })


async def stats(request: web.Request) -> web.Response:
    now = datetime.now(bills.TEHRAN)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = [
        s
        for s in db.list_sales_since(midnight.astimezone(timezone.utc).isoformat())
        if s.method not in sales.NOT_SALES
    ]
    pending = db.list_pending_requests()
    open_bills = bills.open_bills(now=now)
    overdue = [b for b in open_bills if b.days_overdue(now) is not None]
    users = db.list_known_users()
    return _ok({
        "users": len(users),
        "linked_users": sum(1 for u in users if db.is_user_linked(u)),
        "pending_requests": len(pending),
        "pending_amount": sum(p.toman_amount for p in pending),
        "open_bills": len(open_bills),
        "open_bills_amount": sum(b.amount for b in open_bills),
        "overdue_bills": len(overdue),
        "overdue_amount": sum(b.amount for b in overdue),
        "locked_panels": len(db.list_suspensions()),
        "sales_today": len(today),
        "sales_today_amount": sum(s.amount for s in today),
        "sales_today_gb": round(sum(s.gb for s in today), 2),
    })


# ------------------------------------------------------------------ settings


def _settings_view() -> dict:
    price = db.get_setting("price_per_gb")
    return {
        "price_per_gb": float(price) if price else None,
        "card_number": db.get_setting("card_number") or "",
        "force_join_enabled": db.get_setting("force_join_enabled") == "1",
        "force_join_channel": db.get_setting("force_join_channel") or "",
        "auto_approve_enabled": auto_approve.is_enabled(),
        # Never handed out: it guards the export of every panel's password.
        "has_bulk_pin": bool(db.get_setting("bulk_password_pin")),
        "min_gb": settings.min_gb,
        "max_gb": settings.max_gb,
    }


async def get_settings(request: web.Request) -> web.Response:
    return _ok(_settings_view())


async def put_settings(request: web.Request) -> web.Response:
    body = await _body(request)

    if "price_per_gb" in body:
        try:
            price = float(str(body["price_per_gb"]).replace(",", ""))
        except ValueError:
            return _fail(400, "price_per_gb must be a number")
        if price <= 0:
            return _fail(400, "price_per_gb must be above zero")
    if "force_join_channel" in body:
        channel = str(body["force_join_channel"] or "").strip()
        if channel and not channel.startswith("@"):
            return _fail(400, "the channel must start with @")
    if body.get("force_join_enabled") and not (
        str(body.get("force_join_channel", "")).strip() or db.get_setting("force_join_channel")
    ):
        return _fail(400, "set the channel before turning force-join on")

    # Everything checked first, so a bad field never leaves half a save behind.
    if "price_per_gb" in body:
        db.set_setting("price_per_gb", str(price))
    if "card_number" in body:
        db.set_setting("card_number", str(body["card_number"] or "").strip())
    if "force_join_channel" in body:
        db.set_setting("force_join_channel", channel)
    if "force_join_enabled" in body:
        db.set_setting("force_join_enabled", "1" if body["force_join_enabled"] else "0")
    if "auto_approve_enabled" in body and bool(body["auto_approve_enabled"]) != auto_approve.is_enabled():
        auto_approve.set_enabled(bool(body["auto_approve_enabled"]))
    if body.get("bulk_password_pin"):
        db.set_setting("bulk_password_pin", str(body["bulk_password_pin"]).strip())
    return _ok(_settings_view())


# ------------------------------------------------------------------ texts


def _texts_view() -> list[dict]:
    stored = customize.overrides()
    out = []
    for name, default in customize.DEFAULTS.items():
        try:
            fields = sorted(customize.fields(default))
        except ValueError:
            fields = []
        out.append({
            "id": name,
            "text": stored.get(name, default),
            "default": default,
            "changed": name in stored,
            "button": customize.is_button(name),
            "plain": name in customize.PLAIN,
            "fields": fields,
        })
    return out


async def get_texts(request: web.Request) -> web.Response:
    return _ok(_texts_view())


async def put_texts(request: web.Request) -> web.Response:
    body = await _body(request)
    errors = customize.set_texts({str(k): v for k, v in body.items()})
    if errors:
        return _fail(400, "; ".join(f"{k}: {v}" for k, v in errors.items()))
    return _ok(_texts_view())


# ------------------------------------------------------------------ buttons


def _buttons_view() -> dict:
    return {
        "buttons": customize.buttons(),
        "labels": {name: getattr(customize.texts, name) for name in customize.buttons()},
        "defaults": {name: customize.DEFAULT_STYLES.get(name, "") for name in customize.buttons()},
        "styles": list(customize.STYLES),
    }


async def get_buttons(request: web.Request) -> web.Response:
    return _ok(_buttons_view())


async def put_buttons(request: web.Request) -> web.Response:
    body = await _body(request)
    changes = body.get("buttons")
    if not isinstance(changes, dict):
        return _fail(400, "expected {buttons: {...}}")
    errors = customize.set_buttons(changes)
    if errors:
        return _fail(400, "; ".join(f"{k}: {v}" for k, v in errors.items()))
    return _ok(_buttons_view())


# ------------------------------------------------------------------ premium emoji


def _image_type(data: bytes) -> str:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "application/octet-stream"


async def emoji_preview(request: web.Request) -> web.Response:
    """A still picture of one custom emoji. Telegram only serves them to bots."""
    emoji_id = request.match_info["id"]
    if not EMOJI_ID.match(emoji_id):
        return _fail(400, "bad emoji id")
    cached = _EMOJI_CACHE.get(emoji_id)
    if not cached:
        bot: Bot = request.app["bot"]
        stickers = await bot.get_custom_emoji_stickers(custom_emoji_ids=[emoji_id])
        if not stickers:
            return _fail(404, "unknown emoji")
        sticker = stickers[0]
        if sticker.thumbnail:
            file_id = sticker.thumbnail.file_id
        elif not sticker.is_animated and not sticker.is_video:
            file_id = sticker.file_id
        else:
            return _fail(404, "this emoji has no still picture")
        data = (await bot.download(file_id)).read()
        cached = (data, _image_type(data))
        if len(_EMOJI_CACHE) >= _EMOJI_CACHE_MAX:
            _EMOJI_CACHE.clear()
        _EMOJI_CACHE[emoji_id] = cached
    data, ctype = cached
    return web.Response(body=data, content_type=ctype, headers={"Cache-Control": "private, max-age=86400"})


async def emoji_pack(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    if not PACK_NAME.match(name):
        return _fail(400, "bad pack name")
    bot: Bot = request.app["bot"]
    try:
        pack = await bot.get_sticker_set(name=name)
    except Exception as exc:
        return _fail(404, f"pack not found: {exc}")
    emojis = [
        {"id": s.custom_emoji_id, "emoji": s.emoji or ""}
        for s in pack.stickers
        if s.custom_emoji_id
    ]
    if not emojis:
        return _fail(400, "this is a sticker pack, not an emoji pack")
    return _ok({"name": pack.name, "title": pack.title, "emojis": emojis})


async def emoji_sets(request: web.Request) -> web.Response:
    """Which pack each custom emoji id comes from."""
    ids = [i for i in request.query.get("ids", "").split(",") if EMOJI_ID.match(i)][:200]
    if not ids:
        return _fail(400, "no emoji ids")
    bot: Bot = request.app["bot"]
    stickers = await bot.get_custom_emoji_stickers(custom_emoji_ids=ids)
    return _ok({"sets": {s.custom_emoji_id: s.set_name for s in stickers if s.set_name}})


async def get_emoji_allow(request: web.Request) -> web.Response:
    raw = db.get_setting("emoji_allow")
    return _ok({"ids": json.loads(raw) if raw else []})


async def put_emoji_allow(request: web.Request) -> web.Response:
    """The panel pushes its allowed packs here, as it does to the sales bots.
    Kept for the record; the panel's own pickers already offer only these."""
    ids = [str(i) for i in (await _body(request)).get("ids", []) if EMOJI_ID.match(str(i))]
    db.set_setting("emoji_allow", json.dumps(ids))
    return _ok({"ids": ids})


def build_app(bot: Bot) -> web.Application:
    app = web.Application(middlewares=[_auth], client_max_size=2 * 1024 * 1024)
    app["bot"] = bot
    app.add_routes([
        web.get("/api/v1/info", info),
        web.get("/api/v1/stats", stats),
        web.get("/api/v1/settings", get_settings),
        web.put("/api/v1/settings", put_settings),
        web.get("/api/v1/texts", get_texts),
        web.put("/api/v1/texts", put_texts),
        web.get("/api/v1/buttons", get_buttons),
        web.put("/api/v1/buttons", put_buttons),
        web.get("/api/v1/emoji/{id}", emoji_preview),
        web.get("/api/v1/emoji-pack/{name}", emoji_pack),
        web.get("/api/v1/emoji-sets", emoji_sets),
        web.get("/api/v1/emoji-allow", get_emoji_allow),
        web.put("/api/v1/emoji-allow", put_emoji_allow),
    ])
    return app


async def start(bot: Bot) -> web.AppRunner | None:
    """Serve the API next to polling. Off when no port or no key is set."""
    if not settings.management_port:
        return None
    if not settings.management_key:
        logger.warning("management API off: no MANAGEMENT_API_KEY or NEXRA_PANEL_BOT_API_KEY")
        return None
    runner = web.AppRunner(build_app(bot), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, settings.management_host, settings.management_port).start()
    logger.info(f"management API on {settings.management_host}:{settings.management_port}")
    return runner
