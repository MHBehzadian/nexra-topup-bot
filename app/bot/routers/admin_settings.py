"""Superadmin-facing: configure the per-GB price, the card-to-card number, the
force-join channel, and the bulk-credentials-export PIN."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from aiogram import Bot

from .. import keyboards, texts
from ..backups import send_backup
from ..filters import SuperadminFilter
from ..nav import ALL_MENU_TEXTS
from ..states import (
    Broadcast,
    ExportCredentials,
    GrantTraffic,
    GrantWallet,
    SetBulkPin,
    SetCardNumber,
    SetForceJoinChannel,
    SetPricePerGb,
    ToggleWeekly,
)
from ... import db
from ...billing import apply_wallet_to_debts
from ...services.nexra_panel import NexraPanelError, nexra_panel
from ...units import bytes_to_gb

router = Router(name="admin_settings")
router.message.filter(SuperadminFilter())


@router.message(F.text == texts.BTN_SET_PRICE)
async def start_set_price(message: Message, state: FSMContext) -> None:
    await state.set_state(SetPricePerGb.value)
    await message.answer(texts.ASK_PRICE_PER_GB, reply_markup=keyboards.cancel_kb())


@router.message(SetPricePerGb.value, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_set_price(message: Message, state: FSMContext) -> None:
    await state.clear()
    raw = (message.text or "").strip().replace(",", "")
    try:
        price = float(raw)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.INVALID_PRICE, reply_markup=keyboards.superadmin_menu_kb())
        return
    db.set_setting("price_per_gb", str(price))
    await message.answer(
        texts.PRICE_SET_CONFIRM.format(price=int(price)), reply_markup=keyboards.superadmin_menu_kb()
    )


@router.message(F.text == texts.BTN_SET_CARD)
async def start_set_card(message: Message, state: FSMContext) -> None:
    await state.set_state(SetCardNumber.value)
    await message.answer(texts.ASK_CARD_NUMBER, reply_markup=keyboards.cancel_kb())


@router.message(SetCardNumber.value, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_set_card(message: Message, state: FSMContext) -> None:
    await state.clear()
    card_number = (message.text or "").strip()
    if not card_number:
        await message.answer(texts.INVALID_CARD_NUMBER, reply_markup=keyboards.superadmin_menu_kb())
        return
    db.set_setting("card_number", card_number)
    await message.answer(texts.CARD_SET_CONFIRM, reply_markup=keyboards.superadmin_menu_kb())


@router.message(F.text == texts.BTN_SET_FORCE_JOIN_CHANNEL)
async def start_set_channel(message: Message, state: FSMContext) -> None:
    await state.set_state(SetForceJoinChannel.value)
    await message.answer(texts.ASK_FORCE_JOIN_CHANNEL, reply_markup=keyboards.cancel_kb())


@router.message(SetForceJoinChannel.value, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_set_channel(message: Message, state: FSMContext) -> None:
    await state.clear()
    channel = (message.text or "").strip()
    if not channel.startswith("@"):
        await message.answer(texts.INVALID_CHANNEL, reply_markup=keyboards.superadmin_menu_kb())
        return
    db.set_setting("force_join_channel", channel)
    await message.answer(
        texts.FORCE_JOIN_CHANNEL_SET.format(channel=channel),
        reply_markup=keyboards.superadmin_menu_kb(),
    )


@router.message(F.text == texts.BTN_TOGGLE_FORCE_JOIN)
async def toggle_force_join(message: Message) -> None:
    channel = db.get_setting("force_join_channel")
    currently_on = db.get_setting("force_join_enabled") == "1"
    if not currently_on and not channel:
        await message.answer(texts.FORCE_JOIN_NO_CHANNEL_YET)
        return
    db.set_setting("force_join_enabled", "0" if currently_on else "1")
    await message.answer(
        texts.FORCE_JOIN_ENABLED_OFF if currently_on else texts.FORCE_JOIN_ENABLED_ON
    )


@router.message(F.text == texts.BTN_SET_BULK_PIN)
async def start_set_bulk_pin(message: Message, state: FSMContext) -> None:
    await state.set_state(SetBulkPin.value)
    await message.answer(texts.ASK_BULK_PIN_SET, reply_markup=keyboards.cancel_kb())


@router.message(SetBulkPin.value, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_set_bulk_pin(message: Message, state: FSMContext) -> None:
    await state.clear()
    pin = (message.text or "").strip()
    if not pin:
        await message.answer(texts.INVALID_BULK_PIN, reply_markup=keyboards.superadmin_menu_kb())
        return
    db.set_setting("bulk_password_pin", pin)
    await message.answer(texts.BULK_PIN_SET_CONFIRM, reply_markup=keyboards.superadmin_menu_kb())


@router.message(F.text == texts.BTN_EXPORT_ALL_PASSWORDS)
async def start_export_credentials(message: Message, state: FSMContext) -> None:
    if not db.get_setting("bulk_password_pin"):
        await message.answer(texts.BULK_PIN_NOT_SET)
        return
    await state.set_state(ExportCredentials.pin)
    await message.answer(texts.ASK_BULK_PIN_ENTER, reply_markup=keyboards.cancel_kb())


@router.message(ExportCredentials.pin, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_export_credentials(message: Message, state: FSMContext) -> None:
    await state.clear()
    entered_pin = (message.text or "").strip()
    correct_pin = db.get_setting("bulk_password_pin")
    if not correct_pin or entered_pin != correct_pin:
        await message.answer(texts.BULK_PIN_WRONG, reply_markup=keyboards.superadmin_menu_kb())
        return

    try:
        credentials = await nexra_panel.get_all_credentials()
    except NexraPanelError as exc:
        await message.answer(
            texts.SYNC_FAILED.format(error=exc), reply_markup=keyboards.superadmin_menu_kb()
        )
        return
    if not credentials:
        await message.answer(texts.NO_CREDENTIALS, reply_markup=keyboards.superadmin_menu_kb())
        return

    lines = [texts.CREDENTIALS_LIST_HEADER]
    chunks: list[str] = []
    current = lines[0]
    for admin in credentials:
        line = texts.CREDENTIALS_LINE.format(
            username=admin["username"],
            telegram_id=admin.get("telegram_id") or "—",
            password=admin["marzban_password"],
        )
        if len(current) + len(line) > 3500:
            chunks.append(current)
            current = ""
        current += line
    chunks.append(current)

    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        await message.answer(chunk, reply_markup=keyboards.superadmin_menu_kb() if is_last else None)


@router.message(F.text == texts.BTN_ALL_PANELS)
async def list_all_panels(message: Message) -> None:
    try:
        admins = await nexra_panel.list_all_admins()
    except NexraPanelError as exc:
        await message.answer(texts.SYNC_FAILED.format(error=exc))
        return
    if not admins:
        await message.answer(texts.NO_PANELS)
        return

    header = texts.ALL_PANELS_HEADER.format(count=len(admins))
    chunks: list[str] = []
    current = header
    for a in admins:
        line = texts.ADMIN_PANEL_LINE.format(
            username=a["username"],
            status="" if a.get("is_active") else texts.PANEL_INACTIVE_MARK,
            remaining_gb=bytes_to_gb(a.get("traffic")),
            initial_gb=bytes_to_gb(a.get("initial_traffic")),
            telegram_id=a.get("telegram_id") or "—",
        )
        if len(current) + len(line) > 3500:
            chunks.append(current)
            current = ""
        current += line
    chunks.append(current)

    for chunk in chunks:
        await message.answer(chunk)


@router.message(F.text == texts.BTN_GRANT_TRAFFIC)
async def start_grant(message: Message, state: FSMContext) -> None:
    await state.set_state(GrantTraffic.username)
    await message.answer(texts.ASK_GRANT_USERNAME, reply_markup=keyboards.cancel_kb())


@router.message(GrantTraffic.username, ~F.text.in_(ALL_MENU_TEXTS))
async def get_grant_username(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip()
    if not username:
        await message.answer(texts.ASK_GRANT_USERNAME, reply_markup=keyboards.cancel_kb())
        return
    await state.update_data(grant_username=username)
    await state.set_state(GrantTraffic.amount)
    await message.answer(
        texts.ASK_GRANT_AMOUNT.format(username=username), reply_markup=keyboards.cancel_kb()
    )


@router.message(GrantTraffic.amount, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_grant(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip().replace(",", ".")
    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.INVALID_AMOUNT_GB)
        return

    data = await state.get_data()
    await state.clear()
    username = data["grant_username"]

    try:
        result = await nexra_panel.grant(username, amount)
    except NexraPanelError as exc:
        await message.answer(
            texts.GRANT_FAILED.format(error=exc), reply_markup=keyboards.superadmin_menu_kb()
        )
        return

    new_gb = bytes_to_gb(result.get("new_traffic_bytes"))
    db.clear_warning_bucket(username)
    await message.answer(
        texts.GRANT_SUCCESS.format(added_gb=amount, username=username, new_gb=new_gb),
        reply_markup=keyboards.superadmin_menu_kb(),
    )

    target_telegram_id = result.get("telegram_id")
    if target_telegram_id:
        try:
            await bot.send_message(
                target_telegram_id,
                texts.GRANT_NOTIFY_ADMIN.format(
                    username=username, added_gb=amount, new_gb=new_gb
                ),
            )
        except Exception:
            pass


@router.message(F.text == texts.BTN_BACKUP)
async def manual_backup(message: Message, bot: Bot) -> None:
    await message.answer(texts.BACKUP_RUNNING)
    if not await send_backup(bot, targets=[message.from_user.id]):
        await message.answer(texts.BACKUP_FAILED, reply_markup=keyboards.superadmin_menu_kb())


@router.message(F.text == texts.BTN_DEBTS)
async def show_debts(message: Message) -> None:
    debts = db.list_outstanding_debts()
    if not debts:
        await message.answer(texts.NO_DEBTS_AT_ALL)
        return
    lines = []
    for d in debts:
        user = db.get_user(d["telegram_id"]) if d["telegram_id"] else None
        mention = "—"
        if user:
            mention = f"@{user['username']}" if user.get("username") else (user.get("full_name") or "—")
        lines.append(
            texts.DEBT_LINE.format(
                username=d["username"],
                amount=d["amount"],
                mention=mention,
                telegram_id=d["telegram_id"] or "—",
            )
        )
    await message.answer(texts.DEBTS_HEADER + "".join(lines))


@router.message(F.text == texts.BTN_TOGGLE_WEEKLY)
async def start_toggle_weekly(message: Message, state: FSMContext) -> None:
    await state.set_state(ToggleWeekly.username)
    enabled = db.list_weekly_enabled()
    current = ("\n\nفعال‌ها: " + "، ".join(enabled)) if enabled else ""
    await message.answer(texts.ASK_WEEKLY_USERNAME + current, reply_markup=keyboards.cancel_kb())


@router.message(ToggleWeekly.username, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_toggle_weekly(message: Message, state: FSMContext) -> None:
    await state.clear()
    username = (message.text or "").strip()
    if not username:
        await message.answer(texts.ASK_WEEKLY_USERNAME, reply_markup=keyboards.superadmin_menu_kb())
        return
    now_on = not db.is_weekly_enabled(username)
    db.set_weekly_enabled(username, now_on)
    template = texts.WEEKLY_ENABLED_ON if now_on else texts.WEEKLY_ENABLED_OFF
    await message.answer(
        template.format(username=username), reply_markup=keyboards.superadmin_menu_kb()
    )


@router.message(F.text == texts.BTN_GRANT_WALLET)
async def start_grant_wallet(message: Message, state: FSMContext) -> None:
    await state.set_state(GrantWallet.telegram_id)
    await message.answer(texts.ASK_GRANT_WALLET_ID, reply_markup=keyboards.cancel_kb())


@router.message(GrantWallet.telegram_id, ~F.text.in_(ALL_MENU_TEXTS))
async def get_grant_wallet_id(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer(texts.INVALID_WALLET_AMOUNT)
        return
    await state.update_data(target_telegram_id=int(raw))
    await state.set_state(GrantWallet.amount)
    await message.answer(texts.ASK_GRANT_WALLET_AMOUNT, reply_markup=keyboards.cancel_kb())


@router.message(GrantWallet.amount, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_grant_wallet(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip().replace(",", "")
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer(texts.INVALID_WALLET_AMOUNT)
        return

    data = await state.get_data()
    await state.clear()
    target_id, amount = data["target_telegram_id"], int(raw)

    db.add_wallet_balance(target_id, amount)
    apply_wallet_to_debts(target_id)
    balance = db.get_wallet_balance(target_id)

    await message.answer(
        texts.GRANT_WALLET_SUCCESS.format(telegram_id=target_id, balance=balance),
        reply_markup=keyboards.superadmin_menu_kb(),
    )
    try:
        await bot.send_message(
            target_id, texts.WALLET_CHARGED_ADMIN.format(amount=amount, balance=balance)
        )
    except Exception:
        pass


@router.message(F.text == texts.BTN_BROADCAST)
async def start_broadcast(message: Message, state: FSMContext) -> None:
    await state.set_state(Broadcast.text)
    await message.answer(texts.ASK_BROADCAST_TEXT, reply_markup=keyboards.cancel_kb())


@router.message(Broadcast.text, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_broadcast(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    body = message.text or ""
    if not body.strip():
        await message.answer(texts.INVALID_PASSWORD, reply_markup=keyboards.superadmin_menu_kb())
        return

    sent = failed = 0
    for telegram_id in db.list_known_users():
        try:
            await bot.send_message(telegram_id, texts.BROADCAST_PREFIX + body)
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        texts.BROADCAST_RESULT.format(sent=sent, failed=failed),
        reply_markup=keyboards.superadmin_menu_kb(),
    )


@router.message(F.text == texts.BTN_SYNC_TELEGRAM_IDS)
async def sync_telegram_ids(message: Message) -> None:
    await message.answer(texts.SYNC_RUNNING)
    try:
        result = await nexra_panel.sync_telegram_ids()
    except NexraPanelError as exc:
        await message.answer(
            texts.SYNC_FAILED.format(error=exc), reply_markup=keyboards.superadmin_menu_kb()
        )
        return

    updated = result.get("updated") or []
    if not updated:
        await message.answer(texts.SYNC_RESULT_NONE, reply_markup=keyboards.superadmin_menu_kb())
        return

    text = texts.SYNC_RESULT_HEADER.format(count=len(updated))
    for a in updated:
        text += texts.SYNC_RESULT_LINE.format(username=a["username"], telegram_id=a["telegram_id"])
    await message.answer(text, reply_markup=keyboards.superadmin_menu_kb())
