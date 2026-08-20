from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from . import texts


def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=texts.BTN_TOPUP)
    kb.button(text=texts.BTN_MY_PANELS)
    kb.button(text=texts.BTN_WALLET)
    kb.button(text=texts.BTN_CHANGE_PASSWORD)
    kb.button(text=texts.BTN_TUTORIALS)
    kb.button(text=texts.BTN_CREATE_PANEL)
    kb.adjust(2, 2, 2)
    return kb.as_markup(resize_keyboard=True)


def unlinked_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=texts.BTN_CREATE_PANEL)
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)


def superadmin_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=texts.BTN_PENDING_REQUESTS)
    kb.button(text=texts.BTN_SET_PRICE)
    kb.button(text=texts.BTN_SET_CARD)
    kb.button(text=texts.BTN_TOGGLE_FORCE_JOIN)
    kb.button(text=texts.BTN_SET_FORCE_JOIN_CHANNEL)
    kb.button(text=texts.BTN_TUTORIALS)
    kb.button(text=texts.BTN_ADD_TUTORIAL)
    kb.button(text=texts.BTN_ALL_PANELS)
    kb.button(text=texts.BTN_GRANT_TRAFFIC)
    kb.button(text=texts.BTN_BROADCAST)
    kb.button(text=texts.BTN_DEBTS)
    kb.button(text=texts.BTN_TOGGLE_WEEKLY)
    kb.button(text=texts.BTN_GRANT_WALLET)
    kb.button(text=texts.BTN_SET_BULK_PIN)
    kb.button(text=texts.BTN_EXPORT_ALL_PASSWORDS)
    kb.button(text=texts.BTN_SYNC_TELEGRAM_IDS)
    kb.adjust(1, 2, 2, 2, 2, 2, 2, 2, 1)
    return kb.as_markup(resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=texts.BTN_CANCEL)
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)


def force_join_kb(channel: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    handle = channel.lstrip("@")
    kb.button(text="📢 عضویت در کانال", url=f"https://t.me/{handle}")
    kb.button(text="✅ عضو شدم", callback_data="fj_check")
    kb.adjust(1)
    return kb.as_markup()


def invoice_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_PAY, callback_data="topup_pay")
    return kb.as_markup()


def payment_methods_kb() -> InlineKeyboardMarkup:
    """Weekly credit is only usable by panels the superadmin enabled it for, but
    the button is shown to everyone so those without it get a clear explanation
    rather than silently missing an option."""
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_PAY_CARD, callback_data="pay_method:card")
    kb.button(text=texts.BTN_PAY_WALLET, callback_data="pay_method:wallet")
    kb.button(text=texts.BTN_PAY_WEEKLY, callback_data="pay_method:weekly")
    kb.adjust(1)
    return kb.as_markup()


def pay_debt_kb(username: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_PAY_DEBT, callback_data=f"pay_debt:{username}")
    return kb.as_markup()


def wallet_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_CHARGE_WALLET, callback_data="wallet_charge")
    return kb.as_markup()


def approval_kb(request_id: int, admin_telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ تأیید", callback_data=f"topup_approve:{request_id}")
    kb.button(text="❌ رد", callback_data=f"topup_reject:{request_id}")
    kb.button(text=texts.BTN_MESSAGE_USER, callback_data=f"msg_user:{admin_telegram_id}")
    kb.adjust(2, 1)
    return kb.as_markup()


def message_user_kb(telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_MESSAGE_USER, callback_data=f"msg_user:{telegram_id}")
    kb.adjust(1)
    return kb.as_markup()


def panel_picker_kb(admins, action: str) -> InlineKeyboardMarkup:
    """One button per panel. `action` routes the choice (e.g. 'topup', 'pwd')."""
    kb = InlineKeyboardBuilder()
    for a in admins:
        kb.button(text=f"▪️ {a['username']}", callback_data=f"pick:{action}:{a['username']}")
    kb.adjust(1)
    return kb.as_markup()


def topup_panel_kb(username: str) -> InlineKeyboardMarkup:
    """Attached to low-traffic warnings so the admin can jump straight to topping
    up the panel the warning is about."""
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_TOPUP_THIS_PANEL, callback_data=f"pick:topup:{username}")
    return kb.as_markup()


def tutorials_list_kb(tutorials) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in tutorials:
        kb.button(text=t.title, callback_data=f"tutorial:{t.id}")
    kb.adjust(1)
    return kb.as_markup()
