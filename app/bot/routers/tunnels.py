"""🛰 Tunnels: TunnelManager and the Backhaul monitor, from this bot.

TunnelManager keeps running where it is (it watches the tunnels and switches
DNS); this bot is its Telegram side. Connecting it hands TunnelManager this
bot's token and the superadmins' ids, so alerts and backups arrive here, and
TunnelManager stops reading the bot's messages itself (two readers of one
token would steal each other's updates). Commands go through its API key.

The Backhaul monitor is a script on the servers; it is read over SSH.
"""

from __future__ import annotations

import html
import re

import httpx
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .. import customize, keyboards, texts
from ..filters import Label, SuperadminFilter
from ..nav import ALL_MENU_TEXTS, superadmin_kb
from ..servers import action, choose, clean, label, target
from ..states import ConnectTunnelManager
from ... import db, remote
from ...config import settings
from ...remote import RemoteError

router = Router(name="tunnels")
router.message.filter(SuperadminFilter())
router.callback_query.filter(SuperadminFilter())

URL_KEY, API_KEY = "tm_url", "tm_api_key"
URL_RE = re.compile(r"^https?://[A-Za-z0-9.\-\[\]:]+(:\d+)?(/[A-Za-z0-9._~/-]*)?$")


class TMError(Exception):
    pass


def _conf() -> tuple[str, str]:
    return (db.get_setting(URL_KEY) or "").rstrip("/"), db.get_setting(API_KEY) or ""


async def _tm(method: str, path: str, url: str | None = None, key: str | None = None, **body) -> dict:
    base, k = _conf()
    base, k = (url or base), (key or k)
    if not base or not k:
        raise TMError(f"TunnelManager هنوز وصل نشده؛ «{texts.BTN_TM_CONNECT}» را بزنید.")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15)) as c:
            r = await c.request(method, base + path, headers={"X-API-Key": k}, json=body or None)
    except httpx.HTTPError as e:
        raise TMError(f"TunnelManager در {base} جواب نداد: {e or type(e).__name__}") from None
    if r.status_code == 401:
        raise TMError("کلید API رد شد. کلید تازه را با «" + texts.BTN_TM_CONNECT + "» وارد کنید.")
    if r.status_code == 404:
        raise TMError("این نسخه‌ی TunnelManager API ربات ندارد؛ آن را بروز کنید (git pull && bash deploy/install.sh).")
    try:
        data = r.json()
    except ValueError:
        raise TMError(f"جواب نامعتبر از TunnelManager (HTTP {r.status_code})") from None
    if r.status_code >= 300:
        raise TMError(str(data.get("detail") or f"HTTP {r.status_code}"))
    return data


async def _command(message: Message, cmd: str, *args: str) -> None:
    wait = await message.answer("⏳ ...")
    try:
        data = await _tm("POST", "/api/bot/command", cmd=cmd, args=list(args))
    except TMError as e:
        await wait.edit_text(f"❌ {html.escape(str(e))}")
        return
    text = data.get("text") or "—"
    try:
        await wait.edit_text(text[:4000])
    except Exception:  # TunnelManager's HTML did not parse here: send it plain
        await wait.edit_text(html.escape(re.sub(r"<[^>]+>", "", text))[:4000])


_COMMANDS = {
    "BTN_TM_STATUS": "/status",
    "BTN_TM_DOMAINS": "/domains",
    "BTN_TM_LINKS": "/links",
    "BTN_TM_CHECK": "/check",
    "BTN_TM_SCAN": "/scan",
    "BTN_TM_BACKUP": "/backup",
}


@router.message(Label(*_COMMANDS))
async def tm_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    name = next(n for n in _COMMANDS if message.text in customize.labels_for(n))
    await _command(message, _COMMANDS[name])


def _observe_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="👁 روشن (فقط گزارش)", callback_data="tmobs:on")
    kb.button(text="⚙️ خاموش (جابه‌جایی خودکار)", callback_data="tmobs:off")
    kb.adjust(1)
    return kb.as_markup()


@router.message(Label("BTN_TM_OBSERVE"))
async def tm_observe(message: Message, state: FSMContext) -> None:
    await state.clear()
    try:
        data = await _tm("POST", "/api/bot/command", cmd="/observe", args=[])
    except TMError as e:
        await message.answer(f"❌ {html.escape(str(e))}")
        return
    await message.answer(
        data.get("text", "") + "\n\nدر حالت نظارت، TunnelManager فقط می‌بیند و گزارش می‌دهد و "
        "خودش DNS را عوض نمی‌کند و تانلی را بازسازی نمی‌کند.",
        reply_markup=_observe_kb(),
    )


@router.callback_query(F.data.startswith("tmobs:"))
async def tm_observe_set(call: CallbackQuery) -> None:
    want = call.data.split(":")[1]
    try:
        data = await _tm("POST", "/api/bot/command", cmd="/observe", args=[want])
    except TMError as e:
        await call.answer(str(e)[:190], show_alert=True)
        return
    await call.answer("انجام شد")
    await call.message.edit_text(data.get("text", ""), reply_markup=_observe_kb())


# ------------------------------------------------------------------ connect


@router.message(Label("BTN_TM_CONNECT"))
async def tm_connect(message: Message, state: FSMContext) -> None:
    await state.set_state(ConnectTunnelManager.url)
    url, _ = _conf()
    now = f"\nالان وصل است به: <code>{html.escape(url)}</code>\n" if url else ""
    await message.answer(
        f"🔌 <b>اتصال TunnelManager</b>{now}\n"
        "آدرس پنل TunnelManager را بفرستید، مثلاً <code>http://1.2.3.4:8080</code>",
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(ConnectTunnelManager.url, F.text, ~F.text.in_(ALL_MENU_TEXTS))
async def tm_connect_url(message: Message, state: FSMContext) -> None:
    url = message.text.strip().rstrip("/")
    if "://" not in url:
        url = "http://" + url
    if not URL_RE.match(url):
        await message.answer("❌ آدرس درست نیست. مثل <code>http://1.2.3.4:8080</code> بفرستید:")
        return
    await state.update_data(url=url)
    await state.set_state(ConnectTunnelManager.key)
    await message.answer(
        "🔑 کلید API را بفرستید. روی سرور TunnelManager با این دستور چاپ می‌شود:\n"
        "<code>/opt/tunnelmanager/venv/bin/python -m tunnelmanager --data /var/lib/tunnelmanager apikey</code>"
    )


@router.message(ConnectTunnelManager.key, F.text, ~F.text.in_(ALL_MENU_TEXTS))
async def tm_connect_key(message: Message, state: FSMContext) -> None:
    key = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass
    url = (await state.get_data()).get("url", "")
    try:
        info = await _tm("GET", "/api/bot/info", url=url, key=key)
        link = await _tm(
            "POST", "/api/bot/link", url=url, key=key,
            bot_token=settings.bot_token, chat_ids=[str(i) for i in settings.superadmin_id_list],
        )
    except TMError as e:
        await message.answer(f"❌ {html.escape(str(e))}\nکلید را دوباره بفرستید یا لغو کنید.")
        return
    db.set_setting(URL_KEY, url)
    db.set_setting(API_KEY, key)
    await state.clear()
    await message.answer(
        f"✅ TunnelManager {html.escape(str(info.get('version', '')))} وصل شد: "
        f"{info.get('servers', 0)} سرور، {info.get('links', 0)} تانل، {info.get('domains', 0)} دامنه.\n"
        "از این به بعد هشدارها و بکاپ‌های تانل از همین ربات برای سوپرادمین‌ها می‌آید."
        + (f"\n⚠️ {html.escape(link['warning'])}" if link.get("warning") else ""),
        reply_markup=superadmin_kb(message.chat.id),
    )


# ------------------------------------------------------------------ Backhaul


@router.message(Label("BTN_BACKHAUL"))
async def backhaul(message: Message, state: FSMContext) -> None:
    await state.clear()
    await choose(message, state, "backhaul")


_NOT_INSTALLED = "__NOT_INSTALLED__"


@action("backhaul")
async def backhaul_on(message: Message, row, state: FSMContext) -> None:
    await _backhaul(message, row, "status")


async def _backhaul(message: Message, row, what: str) -> None:
    cmd = (
        f"command -v backhaul-monitor >/dev/null || {{ echo {_NOT_INSTALLED}; exit 0; }}; "
        f"backhaul-monitor {what}"
    )
    try:
        _, out = await remote.run(target(row), cmd, timeout=120)
    except RemoteError as e:
        await message.answer(f"❌ {html.escape(str(e))}")
        return
    if _NOT_INSTALLED in out:
        await message.answer(
            f"📡 روی {html.escape(label(row))} مانیتور Backhaul نصب نیست.\n"
            "نصب: <code>git clone https://github.com/MHBehzadian/backhaul-tunnel-monitor.git && "
            "cd backhaul-tunnel-monitor && sudo ./install.sh</code>"
        )
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="📄 گزارش کامل", callback_data=f"bhrep:{row['id']}")
    kb.button(text="💾 بکاپ کانفیگ", callback_data=f"bhbak:{row['id']}")
    title = {"status": "وضعیت پورت‌ها", "report": "گزارش کامل", "backup": "بکاپ"}[what]
    await message.answer(
        f"📡 <b>Backhaul — {title}</b> ({html.escape(label(row))})\n<pre>{clean(out)}</pre>",
        reply_markup=kb.as_markup() if what == "status" else None,
    )


@router.callback_query(F.data.startswith(("bhrep:", "bhbak:")))
async def backhaul_more(call: CallbackQuery) -> None:
    kind, sid = call.data.split(":")
    row = db.get_server(int(sid))
    await call.answer()
    if row:
        await _backhaul(call.message, row, "report" if kind == "bhrep" else "backup")
