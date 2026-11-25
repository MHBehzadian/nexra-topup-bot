"""🤖 Sales bots: the servers they run on, and making / looking after them.

Everything the separate installer bot did, here instead: a new nexra-mirzabot
in one go (token + admin id, nothing else: it runs on the server's IP and
polls Telegram, so no domain, DNS or certificate), the list with each bot's
state, health check, backup, update, schema repair, the Nexra Panel address
and where products show. The work itself is install.sh / nexrabot on the
server, run over SSH.
"""

from __future__ import annotations

import html
import re
import secrets
import shlex
import time

import httpx
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .. import keyboards, texts
from ..filters import Label, SuperadminFilter
from ..nav import ALL_MENU_TEXTS, superadmin_kb
from ..servers import ACTIONS, ANSI, action, choose, clean, label, target
from ..states import AddServer, BotsNexraUrl, NewSalesBot
from ... import db, remote
from ...config import settings
from ...remote import RemoteError, Target

router = Router(name="sales_bots")
router.message.filter(SuperadminFilter())
router.callback_query.filter(SuperadminFilter())

ETC = "/etc/nexrabot"
BIN = "/usr/local/bin/nexrabot"
SCRIPT = "/root/nexrabot-install.sh"
TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,50}$")
URL_RE = re.compile(r"^https?://[A-Za-z0-9._~:/?#\[\]@!$&()*+,;=%-]+$")
ADDR_RE = re.compile(r"^(?:(?P<user>[a-z_][a-z0-9_-]{0,31})@)?(?P<host>[A-Za-z0-9.-]+|\[[0-9a-fA-F:]+\])(?::(?P<port>\d{1,5}))?$")
DEFAULT_NEXRA_URL = "https://weare.nexradns.site/dashboard"

# One line per Go bot: BOT n user url state health db updates token
LIST_SCRIPT = r"""
for f in /etc/nexrabot/bot*.env; do
  [ -f "$f" ] || continue
  n=${f##*/bot}; n=${n%.env}
  case "$n" in ''|*[!0-9]*) continue;; esac
  g() { sed -n "s/^$1=//p" "$f" | tail -1 | tr -d '"'; }
  url=$(g PUBLIC_URL); [ -n "$url" ] || url="https://$(g DOMAIN)"
  listen=$(g LISTEN); port=${listen##*:}
  st=$(systemctl is-active "nexrabot@$n" 2>/dev/null)
  hz=$(curl -fsS -m 4 "http://127.0.0.1:$port/healthz" 2>/dev/null | head -c 60)
  printf 'BOT\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$n" "$(g BOT_USERNAME)" "$url" "${st:-?}" "${hz:--}" "$(g DB_NAME)" "$(g UPDATES)" "$(g BOT_TOKEN)"
done
for c in /var/www/html/*/config.php; do
  [ -f "$c" ] || continue
  grep -q '^\$APIKEY' "$c" || continue
  grep -q '{BOT_TOKEN}' "$c" && continue
  d=$(dirname "$c")
  grep -qx "LEGACY_PHP_DIR=$d" /etc/nexrabot/bot*.env 2>/dev/null && continue
  printf 'PHP\t%s\n' "$d"
done
true
"""


def _menu(message: Message):
    # by the chat, not the sender: after an inline tap the message is the bot's own
    return superadmin_kb(message.chat.id)


async def _bots(t: Target) -> tuple[list[dict], list[str]]:
    code, out = await remote.run(t, LIST_SCRIPT, timeout=90)
    bots, php = [], []
    for line in out.splitlines():
        parts = line.split("\t")
        if parts[0] == "BOT" and len(parts) >= 9:
            bots.append(dict(zip(("n", "user", "url", "state", "health", "db", "updates", "token"), parts[1:9])))
        elif parts[0] == "PHP" and len(parts) >= 2:
            php.append(parts[1])
    return bots, php


async def _tg(token: str, method: str, **params) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"https://api.telegram.org/bot{token}/{method}", json=params or None)
        body = r.json()
    if not body.get("ok"):
        raise RuntimeError(body.get("description") or f"HTTP {r.status_code}")
    return body["result"]


async def _say_error(message: Message, e: Exception) -> None:
    await message.answer(f"❌ {html.escape(str(e))}", reply_markup=_menu(message))


# ================================================================== servers


@router.message(Label("BTN_SERVERS"))
async def servers_list(message: Message, state: FSMContext) -> None:
    await state.clear()
    servers = db.list_servers()
    kb = InlineKeyboardBuilder()
    lines = ["🖥 <b>سرورها</b>\n"]
    for row in servers:
        lines.append(f"• <b>{html.escape(row['name'])}</b> — <code>{html.escape(row['username'])}@{html.escape(row['host'])}:{row['port']}</code>")
        kb.button(text=f"📊 {row['name']}", callback_data=f"srvstat:{row['id']}")
        kb.button(text="🗑 حذف", callback_data=f"srvdel:{row['id']}")
    if not servers:
        lines.append("هنوز سروری اضافه نشده.")
    kb.button(text="➕ افزودن سرور", callback_data="srvadd")
    kb.adjust(*([2] * len(servers)), 1)
    await message.answer("\n".join(lines), reply_markup=kb.as_markup())


async def _ask_address(message: Message, state: FSMContext) -> None:
    await state.set_state(AddServer.address)
    await message.answer(
        "🖥 آدرس سرور را بفرستید:\n"
        "<code>1.2.3.4</code> یا با پورت SSH <code>1.2.3.4:2222</code> "
        "یا با کاربر دیگر <code>ubuntu@1.2.3.4</code>\n\n"
        "(همین سروری که ربات تاپ‌آپ رویش است هم با IP خودش اضافه می‌شود.)",
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(Label("BTN_ADD_SERVER"))
async def add_server_button(message: Message, state: FSMContext) -> None:
    await _ask_address(message, state)


@router.callback_query(F.data == "srvadd")
async def add_server_cb(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await _ask_address(call.message, state)


@router.message(AddServer.address, F.text, ~F.text.in_(ALL_MENU_TEXTS))
async def add_server_address(message: Message, state: FSMContext) -> None:
    m = ADDR_RE.match(message.text.strip())
    port = int(m.group("port") or 22) if m else 0
    if not m or not 0 < port < 65536:
        await message.answer("❌ آدرس درست نیست. مثل <code>1.2.3.4</code> یا <code>1.2.3.4:2222</code> بفرستید:")
        return
    await state.update_data(host=m.group("host").strip("[]"), port=port, username=m.group("user") or "root")
    await state.set_state(AddServer.secret)
    await message.answer(
        "🔑 رمز SSH این سرور را بفرستید (یا متن کامل کلید خصوصی).\n"
        "پیام شما بلافاصله بعد از خواندن پاک می‌شود."
    )


@router.message(AddServer.secret, F.text, ~F.text.in_(ALL_MENU_TEXTS))
async def add_server_secret(message: Message, state: FSMContext) -> None:
    secret = message.text.strip()
    try:
        await message.delete()  # it holds the password
    except Exception:
        pass
    data = await state.get_data()
    t = Target(host=data["host"], port=data["port"], username=data["username"], secret=secret)
    wait = await message.answer("⏳ در حال اتصال...")
    try:
        code, out = await remote.run(t, "hostname; id -u", timeout=30)
    except RemoteError as e:
        await wait.edit_text(f"❌ {html.escape(str(e))}\nدوباره رمز را بفرستید یا لغو کنید.")
        return
    lines = out.strip().splitlines()
    if code != 0 or not lines or lines[-1].strip() != "0":
        why = (
            "این کاربر sudo بدون رمز ندارد؛ با root وصل شوید یا sudo بدون رمز بدهید."
            if t.username != "root" else "دستور آزمایشی اجرا نشد."
        )
        await wait.edit_text(f"❌ {why}\n<pre>{clean(out, 500)}</pre>")
        return
    name = (lines[0].strip() if lines else "") or t.host
    sid = db.add_server(name[:40], t.host, t.port, t.username, secret)
    await state.clear()
    await wait.edit_text(f"✅ سرور <b>{html.escape(name)}</b> ({html.escape(t.host)}) اضافه شد (#{sid}).")
    await message.answer("حالا می‌توانید روی آن ربات بسازید.", reply_markup=_menu(message))


@router.callback_query(F.data.startswith("srvdel:"))
async def delete_server_ask(call: CallbackQuery) -> None:
    sid = int(call.data.split(":")[1])
    row = db.get_server(sid)
    if not row:
        await call.answer("این سرور دیگر نیست.", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 بله، حذف شود", callback_data=f"srvdelok:{sid}")
    await call.answer()
    await call.message.answer(
        f"سرور {html.escape(label(row))} از لیست حذف شود؟\nروی خود سرور و ربات‌هایش هیچ تغییری داده نمی‌شود.",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("srvdelok:"))
async def delete_server(call: CallbackQuery) -> None:
    db.delete_server(int(call.data.split(":")[1]))
    await call.answer("حذف شد")
    await call.message.edit_text("🗑 سرور از لیست حذف شد.")


@router.callback_query(F.data.startswith("srvstat:"))
async def server_status_cb(call: CallbackQuery, state: FSMContext) -> None:
    row = db.get_server(int(call.data.split(":")[1]))
    await call.answer()
    if row:
        await server_status(call.message, row, state)


@action("status")
async def server_status(message: Message, row, state: FSMContext) -> None:
    script = r"""
echo "⏱ $(uptime -p)"
echo "💽 $(df -h / | tail -1 | awk '{print $3" از "$2" ("$5")"}')"
echo "🧠 $(free -h | awk '/^Mem/{print $3" از "$2}')"
echo "⚙️ CPU: $(nproc) هسته، بار $(cut -d' ' -f1-3 /proc/loadavg)"
db=$(systemctl is-active mariadb 2>/dev/null || systemctl is-active mysql 2>/dev/null); echo "🗄 database: ${db:-نصب نیست}"
echo "🤖 ربات‌های Go در حال اجرا: $(systemctl list-units --type=service --state=running --plain --no-legend 'nexrabot@*' 2>/dev/null | wc -l)"
[ -x /usr/local/bin/nexrabot ] && echo "📦 nexrabot $(/usr/local/bin/nexrabot version 2>/dev/null)"
systemctl is-active --quiet nginx && echo "🌐 nginx: active"
true
"""
    try:
        _, out = await remote.run(target(row), script, timeout=60)
    except RemoteError as e:
        return await _say_error(message, e)
    await message.answer(f"🖥 <b>{html.escape(label(row))}</b>\n\n{clean(out)}")


# ================================================================== new bot


@router.message(Label("BTN_NEW_SALES_BOT"))
async def new_bot(message: Message, state: FSMContext) -> None:
    await state.clear()
    await choose(message, state, "newbot")


@action("newbot")
async def new_bot_on(message: Message, row, state: FSMContext) -> None:
    await state.set_state(NewSalesBot.token)
    await state.update_data(server_id=row["id"])
    await message.answer(
        f"🤖 ساخت ربات فروش روی <b>{html.escape(label(row))}</b>\n\n"
        "توکن ربات جدید را از @BotFather بفرستید:",
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(NewSalesBot.token, F.text, ~F.text.in_(ALL_MENU_TEXTS))
async def new_bot_token(message: Message, state: FSMContext) -> None:
    token = message.text.strip()
    if not TOKEN_RE.match(token):
        await message.answer("❌ این توکن ربات نیست. توکن را از @BotFather کپی کنید و بفرستید:")
        return
    if token == settings.bot_token:
        await message.answer("❌ این توکن همین ربات تاپ‌آپ است. توکن یک ربات تازه را بفرستید:")
        return
    try:
        me = await _tg(token, "getMe")
    except Exception as e:
        await message.answer(f"❌ تلگرام این توکن را قبول نکرد: {html.escape(str(e))}\nدوباره بفرستید:")
        return
    try:
        await message.delete()  # the token is a secret
    except Exception:
        pass
    await state.update_data(token=token, username=me.get("username", ""))
    await state.set_state(NewSalesBot.admin)
    await message.answer(
        f"✅ ربات @{html.escape(me.get('username', ''))}\n\n"
        f"👤 آیدی عددی ادمین این ربات را بفرستید (آیدی خودتان: <code>{message.from_user.id}</code>):"
    )


_MARKS = {">>> ": "▫️ ", "!!! ": "⚠️ ", "xxx ": "❌ ", "done": "✅ done", "database": "🗄 database"}


def _progress_text(head: str, lines: list[str]) -> str:
    """The install.sh step lines (>>> / !!! / xxx) so far, newest last."""
    steps = []
    for raw in lines:
        line = ANSI.sub("", raw).strip()
        for mark, icon in _MARKS.items():
            if line.startswith(mark):
                steps.append(icon + line[len(mark):][:200])
                break
    body = html.escape("\n".join(steps[-10:]))
    return f"{head}\n\n<pre>{body or '…'}</pre>"


@router.message(NewSalesBot.admin, F.text, ~F.text.in_(ALL_MENU_TEXTS))
async def new_bot_admin(message: Message, state: FSMContext) -> None:
    admin = message.text.strip()
    if not admin.isdigit():
        await message.answer("❌ آیدی عددی بفرستید (فقط عدد):")
        return
    data = await state.get_data()
    await state.clear()
    row = db.get_server(data.get("server_id", 0))
    if not row:
        await message.answer("سرور پیدا نشد.", reply_markup=_menu(message))
        return
    secret = settings.nexra_secret_code or secrets.token_hex(6)
    env = {
        "TOKEN": data["token"],
        "ADMIN": admin,
        "NEXRA_SECRET": secret,
        "RELEASE": settings.nexrabot_release or "latest",
        # the superadmins are admins everywhere: never used to find whose bot it is
        "NEXRA_OWNER_ID": ",".join(str(i) for i in settings.superadmin_id_list),
    }
    if settings.nexra_panel_owner_username and settings.nexra_panel_owner_password and settings.nexra_panel_api_url:
        env.update(
            NEXRA_PANEL_URL=settings.nexra_panel_api_url.rstrip("/"),
            NEXRA_PANEL_USER=settings.nexra_panel_owner_username,
            NEXRA_PANEL_PASS=settings.nexra_panel_owner_password,
        )
    assigns = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
    script = (
        "set -e\n"
        f"curl -fsSL --retry 3 {shlex.quote(settings.nexrabot_install_url)} -o {SCRIPT}\n"
        f"N=$(bash {SCRIPT} free-number)\n"
        'echo "NEXRA_BOT_NUMBER=$N"\n'
        f"N=$N DOMAIN= {assigns} bash {SCRIPT} new\n"
    )
    head = f"🔧 ساخت @{html.escape(data.get('username', ''))} روی {html.escape(label(row))} (۱ تا ۳ دقیقه)"
    status = await message.answer(head, reply_markup=_menu(message))
    last_text = ""

    async def progress(lines: list[str]) -> None:
        nonlocal last_text
        text = _progress_text(head, lines)
        if text != last_text:
            last_text = text
            await status.edit_text(text)

    started = time.monotonic()
    try:
        code, out = await remote.stream(target(row), script, progress, timeout=1200)
    except RemoteError as e:
        return await _say_error(message, e)
    m = re.search(r"NEXRA_BOT_NUMBER=(\d+)", out)
    if code != 0 or not m:
        await status.edit_text(_progress_text(head, out.splitlines()))
        await message.answer(f"❌ ساخت ربات کامل نشد. آخر خروجی:\n<pre>{clean(out, 1500)}</pre>")
        return
    n = m.group(1)
    _, cfg = await remote.run(
        target(row),
        f"grep -E '^(BOT_USERNAME|PUBLIC_URL|DOMAIN|API_OWNER_KEY|API_MANAGER_KEY|NEXRA_SECRET)=' {ETC}/bot{n}.env",
        timeout=30,
    )
    values = dict(line.split("=", 1) for line in cfg.splitlines() if "=" in line)
    url = values.get("PUBLIC_URL") or "https://" + values.get("DOMAIN", "?")
    panel = "⚠️ به Nexra Panel وصل نشد؛ با کلیدهای زیر در Panel ← Bot ← افزودن ربات اضافه کنید."
    if "connected to Nexra Panel and given to" in out:
        who = re.search(r"given to (\S+)", out)
        panel = f"✅ به Nexra Panel وصل شد و به ادمین <b>{html.escape(who.group(1) if who else '?')}</b> داده شد."
    elif "connected to Nexra Panel; NOT given" in out:
        panel = "✅ به Nexra Panel وصل شد، ولی به ادمینی داده نشد؛ در Panel ← Bot ← اتصال ربات‌ها به صاحبش بدهید."
    await status.edit_text(_progress_text(head, out.splitlines()))
    await message.answer(
        f"✅ <b>ربات ساخته شد</b> ({int(time.monotonic() - started)} ثانیه)\n\n"
        f"شماره: {n}\n"
        f"ربات: @{html.escape(values.get('BOT_USERNAME', data.get('username', '')))}\n"
        f"آدرس: <code>{html.escape(url)}</code>\n"
        f"ادمین: <code>{admin}</code>\n"
        f"کد مخفی مدیریت پنل: <code>{html.escape(values.get('NEXRA_SECRET', secret).strip(chr(34)))}</code>\n"
        "بکاپ دیتابیس: هر ساعت به تلگرام ادمین\n\n"
        f"{panel}\n"
        f"کلید مالک: <code>{html.escape(values.get('API_OWNER_KEY', ''))}</code>\n"
        f"کلید مدیر: <code>{html.escape(values.get('API_MANAGER_KEY', ''))}</code>\n\n"
        "ربات بدون دامنه کار می‌کند (پیام‌ها را خودش از تلگرام می‌گیرد). به ربات /start بدهید.",
        reply_markup=_menu(message),
    )


# ================================================================== list / health


@router.message(Label("BTN_SALES_BOTS"))
async def list_bots(message: Message, state: FSMContext) -> None:
    await state.clear()
    await choose(message, state, "list")


@action("list")
async def list_bots_on(message: Message, row, state: FSMContext) -> None:
    try:
        bots, php = await _bots(target(row))
    except RemoteError as e:
        return await _say_error(message, e)
    if not bots and not php:
        await message.answer(f"روی {html.escape(label(row))} هنوز رباتی نیست. «{texts.BTN_NEW_SALES_BOT}» را بزنید.")
        return
    lines = [f"📋 <b>ربات‌های {html.escape(label(row))}</b>\n"]
    kb = InlineKeyboardBuilder()
    for b in bots:
        ok = b["state"] == "active" and b["health"].startswith("ok")
        mode = "بدون دامنه" if b["updates"] == "polling" else "وبهوک"
        lines.append(
            f"{'✅' if ok else '❌'} <b>#{b['n']}</b> @{html.escape(b['user'])}\n"
            f"   🌐 <code>{html.escape(b['url'])}</code> ({mode})\n"
            f"   ⚙️ {html.escape(b['state'])} — {html.escape(b['health'])} — 🗄 {html.escape(b['db'])}"
        )
        kb.button(text=f"🔄 #{b['n']}", callback_data=f"botrs:{row['id']}:{b['n']}")
        kb.button(text=f"📜 لاگ #{b['n']}", callback_data=f"botlog:{row['id']}:{b['n']}")
    if php:
        lines.append("\n🐘 <b>هنوز روی PHP</b> (با «" + texts.BTN_BOTS_MIGRATE + "» به Go منتقل می‌شوند):")
        lines += [f"   • <code>{html.escape(p)}</code>" for p in php]
    kb.adjust(2)
    await message.answer("\n".join(lines), reply_markup=kb.as_markup() if bots else None)


def _bot_ref(data: str):
    _, sid, n = data.split(":")
    if not n.isdigit():
        return None, None
    return db.get_server(int(sid)), n


@router.callback_query(F.data.startswith("botrs:"))
async def restart_bot(call: CallbackQuery) -> None:
    row, n = _bot_ref(call.data)
    if not row:
        await call.answer("پیدا نشد", show_alert=True)
        return
    await call.answer(f"ری‌استارت #{n} ...")
    try:
        code, out = await remote.run(
            target(row),
            f"systemctl restart nexrabot@{n} && sleep 3 && systemctl is-active nexrabot@{n}",
            timeout=60,
        )
    except RemoteError as e:
        return await _say_error(call.message, e)
    await call.message.answer(("✅" if code == 0 else "❌") + f" ربات #{n}: <code>{clean(out, 300)}</code>")


@router.callback_query(F.data.startswith("botlog:"))
async def bot_log(call: CallbackQuery) -> None:
    row, n = _bot_ref(call.data)
    if not row:
        await call.answer("پیدا نشد", show_alert=True)
        return
    await call.answer()
    try:
        _, out = await remote.run(target(row), f"journalctl -u nexrabot@{n} -n 40 --no-pager -o cat", timeout=60)
    except RemoteError as e:
        return await _say_error(call.message, e)
    await call.message.answer(f"📜 <b>لاگ ربات #{n}</b>\n<pre>{clean(out)}</pre>")


@router.message(Label("BTN_BOTS_HEALTH"))
async def health(message: Message, state: FSMContext) -> None:
    await state.clear()
    await choose(message, state, "health")


@action("health")
async def health_on(message: Message, row, state: FSMContext) -> None:
    wait = await message.answer("🩺 در حال بررسی...")
    try:
        bots, _ = await _bots(target(row))
    except RemoteError as e:
        return await _say_error(message, e)
    if not bots:
        await wait.edit_text("رباتی روی این سرور نیست.")
        return
    lines = []
    for b in bots:
        problems = []
        if b["state"] != "active":
            problems.append(f"سرویس {b['state']}")
        if not b["health"].startswith("ok"):
            problems.append("جواب نمی‌دهد (healthz)")
        try:
            info = await _tg(b["token"], "getWebhookInfo")
            pending = info.get("pending_update_count", 0)
            if b["updates"] == "polling":
                if info.get("url"):
                    problems.append("وبهوک روی ربات بدون دامنه مانده")
                if pending > 20:
                    problems.append(f"{pending} پیام خوانده‌نشده")
            else:
                when = info.get("last_error_date") or 0
                if not info.get("url"):
                    problems.append("وبهوک تنظیم نیست")
                elif when and time.time() - when < 600:
                    problems.append(f"خطای وبهوک: {info.get('last_error_message', '')[:60]}")
                if pending > 20:
                    problems.append(f"{pending} آپدیت معطل")
        except Exception as e:
            problems.append(f"تلگرام: {str(e)[:60]}")
        state_text = "✅ سالم" if not problems else "❌ " + " | ".join(problems)
        lines.append(f"<b>#{b['n']}</b> @{html.escape(b['user'])}: {html.escape(state_text)}")
    await wait.edit_text(
        f"🩺 <b>نتیجه‌ی بررسی {html.escape(label(row))}</b>\n\n" + "\n".join(lines)
        + "\n\nبرای ربات خراب: «📋 لیست ربات‌ها» ← 🔄 ری‌استارت یا 📜 لاگ."
    )


# ================================================================== maintenance


@router.message(Label("BTN_BOTS_REPAIR"))
async def repair(message: Message, state: FSMContext) -> None:
    await state.clear()
    await choose(message, state, "repair")


@action("repair")
async def repair_on(message: Message, row, state: FSMContext) -> None:
    script = rf"""
for f in {ETC}/bot*.env; do
  [ -f "$f" ] || continue
  n=${{f##*/bot}}; n=${{n%.env}}
  if out=$({BIN} schema -c "$f" 2>&1); then echo "#$n ✅ $(echo "$out" | tail -1)"; else echo "#$n ❌ $(echo "$out" | tail -1)"; fi
done
true
"""
    wait = await message.answer("🔧 در حال تعمیر دیتابیس همه‌ی ربات‌ها...")
    try:
        _, out = await remote.run(target(row), script, timeout=300)
    except RemoteError as e:
        return await _say_error(message, e)
    await wait.edit_text(f"🔧 <b>تعمیر دیتابیس</b>\n\n{clean(out) or 'رباتی نیست.'}")


@router.message(Label("BTN_BOTS_UPDATE"))
async def update(message: Message, state: FSMContext) -> None:
    await state.clear()
    await choose(message, state, "update")


@action("update")
async def update_on(message: Message, row, state: FSMContext) -> None:
    head = f"♻️ بروزرسانی همه‌ی ربات‌های {html.escape(label(row))} به آخرین نسخه"
    status = await message.answer(head)
    script = (
        "set -e\n"
        f"curl -fsSL --retry 3 {shlex.quote(settings.nexrabot_install_url)} -o {SCRIPT}\n"
        f"RELEASE={shlex.quote(settings.nexrabot_release or 'latest')} bash {SCRIPT} update\n"
    )

    async def progress(lines: list[str]) -> None:
        await status.edit_text(_progress_text(head, lines))

    try:
        code, out = await remote.stream(target(row), script, progress, timeout=900)
    except RemoteError as e:
        return await _say_error(message, e)
    await status.edit_text(_progress_text(head, out.splitlines()))
    await message.answer(
        ("✅ همه‌ی ربات‌ها بروز شدند." if code == 0 else f"❌ بروزرسانی کامل نشد:\n<pre>{clean(out, 1500)}</pre>"),
        reply_markup=_menu(message),
    )


@router.message(Label("BTN_BOTS_MIGRATE"))
async def migrate(message: Message, state: FSMContext) -> None:
    await state.clear()
    await choose(message, state, "migrate")


@action("migrate")
async def migrate_ask(message: Message, row, state: FSMContext) -> None:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬆️ بله، منتقل شوند", callback_data=f"migrok:{row['id']}")
    await message.answer(
        f"همه‌ی ربات‌های PHP روی {html.escape(label(row))} به نسخه‌ی Go منتقل شوند؟\n\n"
        "همان دیتابیس و همان وبهوک می‌ماند، قبلش بکاپ گرفته می‌شود و هر رباتی که خطا بدهد خودش به PHP برمی‌گردد.",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("migrok:"))
async def migrate_run(call: CallbackQuery) -> None:
    row = db.get_server(int(call.data.split(":")[1]))
    await call.answer()
    if not row:
        return
    await call.message.edit_reply_markup()
    env = ""
    if settings.nexra_panel_owner_username and settings.nexra_panel_owner_password and settings.nexra_panel_api_url:
        env = (
            f"NEXRA_PANEL_URL={shlex.quote(settings.nexra_panel_api_url.rstrip('/'))} "
            f"NEXRA_PANEL_USER={shlex.quote(settings.nexra_panel_owner_username)} "
            f"NEXRA_PANEL_PASS={shlex.quote(settings.nexra_panel_owner_password)} "
        )
    script = (
        "set -e\n"
        f"curl -fsSL --retry 3 {shlex.quote(settings.nexrabot_install_url)} -o {SCRIPT}\n"
        f"{env}RELEASE={shlex.quote(settings.nexrabot_release or 'latest')} bash {SCRIPT} migrate-all\n"
    )
    head = "⬆️ انتقال ربات‌های PHP به Go"
    status = await call.message.answer(head)

    async def progress(lines: list[str]) -> None:
        await status.edit_text(_progress_text(head, lines))

    try:
        code, out = await remote.stream(target(row), script, progress, timeout=3600)
    except RemoteError as e:
        return await _say_error(call.message, e)
    await status.edit_text(_progress_text(head, out.splitlines()))
    await call.message.answer(
        "✅ انتقال تمام شد." if code == 0 else f"❌ انتقال کامل نشد:\n<pre>{clean(out, 1500)}</pre>"
    )


# ================================================================== backup


@router.message(Label("BTN_BOTS_BACKUP"))
async def backup(message: Message, state: FSMContext) -> None:
    await state.clear()
    await choose(message, state, "backup")


@action("backup")
async def backup_on(message: Message, row, state: FSMContext) -> None:
    t = target(row)
    try:
        bots, _ = await _bots(t)
    except RemoteError as e:
        return await _say_error(message, e)
    if not bots:
        await message.answer("رباتی روی این سرور نیست.")
        return
    wait = await message.answer(f"💾 بکاپ از {len(bots)} ربات...")
    sent = 0
    for b in bots:
        if not b["n"].isdigit():
            continue
        path = f"/tmp/nexrabot-backup-{b['n']}-{int(time.time())}.sql.gz"
        try:
            code, out = await remote.run(
                t, f"{BIN} db-dump -c {ETC}/bot{b['n']}.env --out {path} >/dev/null && chmod 644 {path}", timeout=600
            )
            if code != 0:
                await message.answer(f"#{b['n']}: ❌ بکاپ نشد\n<pre>{clean(out, 400)}</pre>")
                continue
            blob = await remote.fetch(t, path)
            name = f"{b['user'] or 'bot' + b['n']}_{time.strftime('%Y%m%d_%H%M')}.sql.gz"
            await message.answer_document(
                BufferedInputFile(blob, filename=name), caption=f"💾 بکاپ #{b['n']} @{b['user']} — {b['db']}"
            )
            sent += 1
        except RemoteError as e:
            await message.answer(f"#{b['n']}: ❌ {html.escape(str(e))}")
        finally:
            try:
                await remote.run(t, f"rm -f {path}", timeout=30)
            except RemoteError:
                pass
    await wait.edit_text(f"💾 بکاپ تمام شد: {sent} از {len(bots)} ربات.")


# ================================================================== Nexra URL / products


@router.message(Label("BTN_BOTS_NEXRA_URL"))
async def nexra_url(message: Message, state: FSMContext) -> None:
    await state.clear()
    await choose(message, state, "nexraurl")


@action("nexraurl")
async def nexra_url_ask(message: Message, row, state: FSMContext) -> None:
    await state.set_state(BotsNexraUrl.url)
    await state.update_data(server_id=row["id"])
    await message.answer(
        "🔁 آدرس جدید پنل Nexra را بفرستید؛ روی <b>همه‌ی</b> پنل‌های Nexra در همه‌ی ربات‌های این سرور اعمال می‌شود.\n\n"
        f"برای آدرس پیش‌فرض فقط <b>1</b> بفرستید:\n<code>{DEFAULT_NEXRA_URL}</code>",
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(BotsNexraUrl.url, F.text, ~F.text.in_(ALL_MENU_TEXTS))
async def nexra_url_apply(message: Message, state: FSMContext) -> None:
    url = DEFAULT_NEXRA_URL if message.text.strip() == "1" else message.text.strip().rstrip("/")
    if not URL_RE.match(url) or "'" in url or "\\" in url:
        await message.answer("❌ آدرس معتبر نیست؛ با https:// شروع شود. دوباره بفرستید:")
        return
    row = db.get_server((await state.get_data()).get("server_id", 0))
    await state.clear()
    if not row:
        return
    # the URL is checked above to hold no quote or backslash, so it can sit in the SQL
    sql = f"UPDATE marzban_panel SET url_panel='{url}', datelogin=NULL WHERE type='nexra'; SELECT ROW_COUNT();"
    script = rf"""
for f in {ETC}/bot*.env; do
  [ -f "$f" ] || continue
  n=${{f##*/bot}}; n=${{n%.env}}
  db=$(sed -n 's/^DB_NAME=//p' "$f" | tail -1)
  c=$(mysql --default-character-set=utf8mb4 -N "$db" -e {shlex.quote(sql)} 2>&1 | tail -1)
  echo "#$n: $c"
done
true
"""
    try:
        _, out = await remote.run(target(row), script, timeout=120)
    except RemoteError as e:
        return await _say_error(message, e)
    await message.answer(
        f"🔁 <b>آدرس پنل Nexra</b> ← <code>{html.escape(url)}</code>\n"
        f"(عدد = تعداد پنل‌های Nexra که عوض شد)\n\n<pre>{clean(out) or 'رباتی نیست.'}</pre>",
        reply_markup=_menu(message),
    )


@router.message(Label("BTN_BOTS_PRODUCTS"))
async def products(message: Message, state: FSMContext) -> None:
    await state.clear()
    await choose(message, state, "products")


@action("products")
async def products_on(message: Message, row, state: FSMContext) -> None:
    q = (
        "SELECT CONCAT('panels: ', IFNULL(GROUP_CONCAT(CONCAT(name_panel,' [',type,']') SEPARATOR ', '),'-')) FROM marzban_panel;"
        "SELECT CONCAT('products: ', IFNULL(GROUP_CONCAT(x SEPARATOR ' | '),'-')) FROM "
        "(SELECT CONCAT(IFNULL(Location,'-'),' = ',COUNT(*)) x FROM product GROUP BY Location) t;"
    )
    script = rf"""
for f in {ETC}/bot*.env; do
  [ -f "$f" ] || continue
  n=${{f##*/bot}}; n=${{n%.env}}
  db=$(sed -n 's/^DB_NAME=//p' "$f" | tail -1)
  echo "#$n $(sed -n 's/^BOT_USERNAME=//p' "$f" | tail -1)"
  mysql --default-character-set=utf8mb4 -N "$db" -e {shlex.quote(q)} 2>&1 | sed 's/^/   /'
done
true
"""
    try:
        _, out = await remote.run(target(row), script, timeout=120)
    except RemoteError as e:
        return await _say_error(message, e)
    kb = InlineKeyboardBuilder()
    kb.button(text="1️⃣ همه‌ی محصولات در همه‌ی پنل‌ها", callback_data=f"prod:{row['id']}:1")
    kb.button(text="2️⃣ همه‌ی محصولات به پنل Nexra", callback_data=f"prod:{row['id']}:2")
    kb.adjust(1)
    await message.answer(
        f"🛒 <b>محصولات ربات‌ها</b>\n<pre>{clean(out) or 'رباتی نیست.'}</pre>\n"
        "هر محصول فقط زیر پنلی دیده می‌شود که نامش در Location آن محصول است؛ بعد از اضافه‌کردن پنل Nexra، "
        "محصولات قدیمی هنوز به نام پنل قبلی‌اند. روی همه‌ی ربات‌های این سرور:",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("prod:"))
async def products_apply(call: CallbackQuery) -> None:
    _, sid, mode = call.data.split(":")
    row = db.get_server(int(sid))
    await call.answer()
    if not row or mode not in ("1", "2"):
        return
    await call.message.edit_reply_markup()
    if mode == "1":
        sql = "UPDATE product SET Location='/all'; SELECT ROW_COUNT();"
    else:
        # the name is copied inside SQL: through the shell an emoji in it broke
        sql = (
            "UPDATE product SET Location=(SELECT name_panel FROM marzban_panel WHERE type='nexra' LIMIT 1) "
            "WHERE EXISTS (SELECT 1 FROM marzban_panel WHERE type='nexra'); SELECT ROW_COUNT();"
        )
    script = rf"""
for f in {ETC}/bot*.env; do
  [ -f "$f" ] || continue
  n=${{f##*/bot}}; n=${{n%.env}}
  db=$(sed -n 's/^DB_NAME=//p' "$f" | tail -1)
  echo "#$n: $(mysql --default-character-set=utf8mb4 -N "$db" -e {shlex.quote(sql)} 2>&1 | tail -1) محصول"
done
true
"""
    try:
        _, out = await remote.run(target(row), script, timeout=120)
    except RemoteError as e:
        return await _say_error(call.message, e)
    await call.message.answer(
        "🛒 <b>محل نمایش محصولات</b>\n<pre>" + (clean(out) or "رباتی نیست.") + "</pre>\n"
        "دسته‌بندی‌ها هم خودشان برمی‌گردند، چون همان محصولات را دنبال می‌کنند."
    )


# ================================================================== server picker


@router.callback_query(F.data.startswith("srv:"))
async def picked_server(call: CallbackQuery, state: FSMContext) -> None:
    _, name, sid = call.data.split(":")
    row = db.get_server(int(sid))
    fn = ACTIONS.get(name)
    await call.answer()
    if not row or not fn:
        await call.message.answer("این سرور دیگر در لیست نیست.")
        return
    await call.message.edit_reply_markup()
    await fn(call.message, row, state)
