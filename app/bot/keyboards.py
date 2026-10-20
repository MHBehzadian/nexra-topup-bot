from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from . import customize, texts


def _b(kb, name: str, text: str | None = None, **kwargs) -> None:
    """One button by its name in texts: its label (or `text`, for a label that is
    formatted with something), plus the colour and premium icon set for it in
    the Nexra panel."""
    kb.button(
        text=getattr(texts, name) if text is None else text,
        **kwargs,
        **customize.button_opts(name),
    )


def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    _b(kb, "BTN_TOPUP")
    _b(kb, "BTN_MY_PANELS")
    _b(kb, "BTN_WALLET")
    _b(kb, "BTN_CHANGE_PASSWORD")
    _b(kb, "BTN_TUTORIALS")
    _b(kb, "BTN_FORECAST")
    _b(kb, "BTN_MY_INVOICES")
    _b(kb, "BTN_PANEL_LOGIN")
    _b(kb, "BTN_CREATE_PANEL")
    kb.adjust(2, 2, 2, 2, 2)
    return kb.as_markup(resize_keyboard=True)


def panel_login_kb() -> InlineKeyboardMarkup:
    """Two doors to the same panel: one domain routes from inside Iran, the
    other doesn't — so the choice is theirs to make, not ours to guess."""
    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_LOGIN_WITH_VPN", url=texts.PANEL_URL_WITH_VPN)
    _b(kb, "BTN_LOGIN_WITHOUT_VPN", url=texts.PANEL_URL_WITHOUT_VPN)
    kb.adjust(1)
    return kb.as_markup()


def unlinked_menu_kb() -> ReplyKeyboardMarkup:
    """No panel, but we have billed them, so the money side of the bot is theirs.
    The panel button is where activation and the requests live."""
    kb = ReplyKeyboardBuilder()
    _b(kb, "BTN_WALLET")
    _b(kb, "BTN_MY_INVOICES")
    _b(kb, "BTN_MY_PANELS")
    kb.adjust(2, 1)
    return kb.as_markup(resize_keyboard=True)


def prospect_menu_kb() -> ReplyKeyboardMarkup:
    """Someone we have no business with yet — no panel, never billed. Only the way
    in: no wallet, and so no card number, until there is something to pay."""
    kb = ReplyKeyboardBuilder()
    _b(kb, "BTN_MY_PANELS")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)


def panel_request_kb() -> ReplyKeyboardMarkup:
    """Shown alongside the activation notice, so the two ways of asking for a
    panel sit where someone actually looks for them."""
    kb = ReplyKeyboardBuilder()
    _b(kb, "BTN_PARTNERSHIP")
    _b(kb, "BTN_CREATE_PANEL")
    _b(kb, "BTN_BACK")
    kb.adjust(1, 1, 1)
    return kb.as_markup(resize_keyboard=True)


def _reply_kb(*names, layout=(2,)) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    for name in names:
        _b(kb, name)
    kb.adjust(*layout)
    return kb.as_markup(resize_keyboard=True)


def superadmin_menu_kb() -> ReplyKeyboardMarkup:
    """Root menu: sections, not the whole feature list.

    Twenty-odd buttons on one keyboard filled the screen and buried the one
    thing that is actually time-critical — the pending requests — so everything
    else moved a tap away, grouped by what it is for.
    """
    return _reply_kb(
        "BTN_PENDING_REQUESTS",
        "BTN_SEC_PANELS",
        "BTN_SEC_FINANCE",
        "BTN_SEC_USERS",
        "BTN_TUTORIALS",
        "BTN_SEC_SETTINGS",
        layout=(1, 2, 2, 1),
    )


def panels_section_kb() -> ReplyKeyboardMarkup:
    return _reply_kb(
        "BTN_ALL_PANELS",
        "BTN_GRANT_TRAFFIC",
        "BTN_PANEL_HISTORY",
        "BTN_CREATE_ADMIN",
        "BTN_SYNC_TELEGRAM_IDS",
        "BTN_EXPORT_ALL_PASSWORDS",
        "BTN_BACK",
        layout=(2, 2, 2, 1),
    )


def finance_section_kb() -> ReplyKeyboardMarkup:
    return _reply_kb(
        "BTN_DIGEST",
        "BTN_INVOICES",
        "BTN_NEW_INVOICE",
        "BTN_SALES_REPORT",
        "BTN_GRANT_WALLET",
        "BTN_TOGGLE_WEEKLY",
        "BTN_BACK",
        layout=(1, 2, 1, 2, 1),
    )


def users_section_kb() -> ReplyKeyboardMarkup:
    return _reply_kb(
        "BTN_SEARCH_USER",
        "BTN_BROADCAST",
        "BTN_BACK",
        layout=(2, 1),
    )


def tutorials_section_kb() -> ReplyKeyboardMarkup:
    return _reply_kb(
        "BTN_VIEW_TUTORIALS",
        "BTN_ADD_TUTORIAL",
        "BTN_DELETE_TUTORIAL",
        "BTN_BACK",
        layout=(1, 2, 1),
    )


def settings_section_kb() -> ReplyKeyboardMarkup:
    return _reply_kb(
        "BTN_TOGGLE_AUTO_APPROVE",
        "BTN_SET_PRICE",
        "BTN_SET_CARD",
        "BTN_TOGGLE_FORCE_JOIN",
        "BTN_SET_FORCE_JOIN_CHANNEL",
        "BTN_SET_BULK_PIN",
        "BTN_BACKUP",
        "BTN_BACK",
        layout=(1, 2, 2, 2, 1),
    )


SECTION_KEYBOARDS = {
    "panels": panels_section_kb,
    "finance": finance_section_kb,
    "users": users_section_kb,
    "tutorials": tutorials_section_kb,
    "settings": settings_section_kb,
}


def cancel_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    _b(kb, "BTN_CANCEL")
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)


def force_join_kb(channel: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    handle = channel.lstrip("@")
    _b(kb, "BTN_JOIN_CHANNEL", url=f"https://t.me/{handle}")
    _b(kb, "BTN_JOINED", callback_data="fj_check")
    kb.adjust(1)
    return kb.as_markup()


def invoice_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_PAY", callback_data="topup_pay")
    return kb.as_markup()


def payment_methods_kb() -> InlineKeyboardMarkup:
    """Weekly credit is only usable by panels the superadmin enabled it for, but
    the button is shown to everyone so those without it get a clear explanation
    rather than silently missing an option."""
    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_PAY_CARD", callback_data="pay_method:card")
    _b(kb, "BTN_PAY_WALLET", callback_data="pay_method:wallet")
    _b(kb, "BTN_PAY_WEEKLY", callback_data="pay_method:weekly")
    kb.adjust(1)
    return kb.as_markup()


def invoice_due_kb() -> InlineKeyboardMarkup:
    """Preset payment deadlines, so the superadmin picks instead of typing a date."""
    from .invoices import DUE_OPTIONS

    kb = InlineKeyboardBuilder()
    for key, (label_name, _) in DUE_OPTIONS.items():
        kb.button(text=getattr(texts, label_name), callback_data=f"invoice_due:{key}")
    kb.adjust(1)
    return kb.as_markup()


def pay_invoice_kb(invoice_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_PAY_INVOICE", callback_data=f"pay_invoice:{invoice_id}")
    _b(kb, "BTN_PAY_PART", callback_data=f"pay_invoice_part:{invoice_id}")
    kb.adjust(1)
    return kb.as_markup()


def user_actions_kb(telegram_id: int) -> InlineKeyboardMarkup:
    from .. import db  # here rather than at import time: keyboards is imported very early

    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_DEDUCT_WALLET", callback_data=f"usr_deduct:{telegram_id}")
    _b(kb, "BTN_INVOICE_FOR_USER", callback_data=f"usr_invoice:{telegram_id}")
    _b(kb, "BTN_MARK_PAID", callback_data=f"paidpick:{telegram_id}")
    _b(kb, "BTN_MARK_PART_PAID", callback_data=f"partpick:{telegram_id}")
    _b(kb, "BTN_DELETE_INVOICE", callback_data=f"usr_delinv:{telegram_id}")
    _b(kb, "BTN_MESSAGE_USER", callback_data=f"msg_user:{telegram_id}")
    # Whichever of the two makes sense right now, so there is nothing to read
    # off the card before deciding which button to press.
    if db.list_suspensions(telegram_id):
        _b(kb, "BTN_UNLOCK_PANELS", callback_data=f"usr_unlock:{telegram_id}")
    else:
        _b(kb, "BTN_LOCK_PANELS", callback_data=f"usr_lock:{telegram_id}")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()


def confirm_lock_kb(telegram_id: int, locking: bool) -> InlineKeyboardMarkup:
    """Changing someone's password is not undoable by them, so it takes a second tap."""
    kb = InlineKeyboardBuilder()
    action = "lockok" if locking else "unlockok"
    _b(
        kb,
        "BTN_CONFIRM_LOCK" if locking else "BTN_CONFIRM_UNLOCK",
        callback_data=f"{action}:{telegram_id}",
    )
    _b(kb, "BTN_KEEP", callback_data="lock_no")
    kb.adjust(1)
    return kb.as_markup()


def pay_debt_kb(username: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_PAY_DEBT", callback_data=f"pay_debt:{username}")
    _b(kb, "BTN_PAY_PART", callback_data=f"pay_debt_part:{username}")
    kb.adjust(1)
    return kb.as_markup()


def bill_actions_kb(customer) -> InlineKeyboardMarkup | None:
    """What you can do about a customer, however many debts they have: remind
    them, record a payment made outside the bot, write one off, or write to them.

    A button per debt meant five buttons for two debts, each labelled with a
    panel name or an invoice number you had to match against the lines above.
    """
    if customer.telegram_id is None:
        return None
    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_WARN_CUSTOMER", callback_data=f"warnall:{customer.telegram_id}")
    _b(kb, "BTN_MARK_PAID", callback_data=f"paidpick:{customer.telegram_id}")
    _b(kb, "BTN_MARK_PART_PAID", callback_data=f"partpick:{customer.telegram_id}")
    _b(kb, "BTN_DELETE_CUSTOMER_BILL", callback_data=f"delpick:{customer.telegram_id}")
    _b(kb, "BTN_MESSAGE_USER", callback_data=f"msg_user:{customer.telegram_id}")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def bill_pay_all_kb(items) -> InlineKeyboardMarkup:
    """Pay buttons for everything one notice covers."""
    if len(items) == 1:
        return bill_pay_kb(items[0])
    kb = InlineKeyboardBuilder()
    for bill in items:
        if bill.kind == "invoice":
            name = "BTN_PAY_BILL_INVOICE"
            label = texts.BTN_PAY_BILL_INVOICE.format(id=bill.invoice_id)
            data = f"pay_invoice:{bill.invoice_id}"
        else:
            name = "BTN_PAY_BILL_WEEKLY"
            label = texts.BTN_PAY_BILL_WEEKLY.format(username=bill.username)
            data = f"pay_debt:{bill.username}"
        _b(kb, name, text=label, callback_data=data)
    kb.adjust(1)
    return kb.as_markup()


def bills_delete_kb(items) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for bill in items:
        if bill.kind == "invoice":
            name, label = "BTN_DELETE_BILL_INVOICE", texts.BTN_DELETE_BILL_INVOICE.format(id=bill.invoice_id)
        else:
            name, label = "BTN_DELETE_BILL_WEEKLY", texts.BTN_DELETE_BILL_WEEKLY.format(username=bill.username)
        _b(kb, name, text=f"{label} — {bill.amount:,}", callback_data=f"billdel:{bill.key}")
    kb.adjust(1)
    return kb.as_markup()


def confirm_bill_delete_kb(bill) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_CONFIRM_DELETE_BILL", callback_data=f"billdelok:{bill.key}")
    _b(kb, "BTN_KEEP", callback_data="billdel_no")
    kb.adjust(1)
    return kb.as_markup()


def bills_mark_paid_kb(items, action: str = "billpaid") -> InlineKeyboardMarkup:
    """One button per open bill; `action` decides whether picking one records it
    paid in full ("billpaid") or asks how much came in ("billpart")."""
    kb = InlineKeyboardBuilder()
    for bill in items:
        if bill.kind == "invoice":
            name, label = "BTN_MARK_PAID_INVOICE", texts.BTN_MARK_PAID_INVOICE.format(id=bill.invoice_id)
        else:
            name, label = "BTN_MARK_PAID_WEEKLY", texts.BTN_MARK_PAID_WEEKLY.format(username=bill.username)
        _b(kb, name, text=f"{label} — {bill.amount:,}", callback_data=f"{action}:{bill.key}")
    kb.adjust(1)
    return kb.as_markup()


def confirm_bill_paid_kb(bill) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_CONFIRM_MARK_PAID", callback_data=f"billpaidok:{bill.key}")
    _b(kb, "BTN_KEEP", callback_data="billpaid_no")
    kb.adjust(1)
    return kb.as_markup()


def suspended_kb() -> InlineKeyboardMarkup:
    """Shown with the lock notice: see what is owed, or pay all of it at once."""
    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_SHOW_ALL_BILLS", callback_data="bills_all")
    _b(kb, "BTN_PAY_ALL_BILLS", callback_data="pay_all")
    kb.adjust(1)
    return kb.as_markup()


def bill_pay_kb(bill) -> InlineKeyboardMarkup:
    if bill.kind == "invoice":
        return pay_invoice_kb(bill.invoice_id)
    return pay_debt_kb(bill.username)


def wallet_amount_kb() -> InlineKeyboardMarkup:
    """Common top-up sizes, plus an escape hatch for anything else."""
    kb = InlineKeyboardBuilder()
    for amount in texts.WALLET_PRESETS:
        kb.button(text=f"{amount:,} تومان", callback_data=f"wallet_amt:{amount}")
    _b(kb, "BTN_WALLET_CUSTOM", callback_data="wallet_amt:custom")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def topup_amount_kb() -> InlineKeyboardMarkup:
    """Common purchase sizes, plus an escape hatch for anything else."""
    kb = InlineKeyboardBuilder()
    for gb in texts.TOPUP_PRESETS:
        kb.button(text=f"{gb:,} GB", callback_data=f"topup_gb:{gb}")
    _b(kb, "BTN_TOPUP_CUSTOM", callback_data="topup_gb:custom")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def partner_volume_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, label in [
        ("u1", texts.VOL_UNDER_1TB),
        ("1", texts.VOL_1TB),
        ("2", texts.VOL_2TB),
        ("3", texts.VOL_3TB),
        ("o3", texts.VOL_OVER_3TB),
    ]:
        kb.button(text=label, callback_data=f"pvol:{key}")
    kb.adjust(1)
    return kb.as_markup()


def wallet_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_CHARGE_WALLET", callback_data="wallet_charge")
    return kb.as_markup()


def approval_kb(request_id: int, admin_telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_APPROVE", callback_data=f"topup_approve:{request_id}")
    _b(kb, "BTN_REJECT", callback_data=f"topup_reject:{request_id}")
    _b(kb, "BTN_APPROVE_PARTIAL", callback_data=f"topup_partial:{request_id}")
    _b(kb, "BTN_MESSAGE_USER", callback_data=f"msg_user:{admin_telegram_id}")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def message_user_kb(telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_MESSAGE_USER", callback_data=f"msg_user:{telegram_id}")
    kb.adjust(1)
    return kb.as_markup()


def panel_history_kb(admins) -> InlineKeyboardMarkup:
    """A history button per panel, under the list of their panels."""
    kb = InlineKeyboardBuilder()
    for admin in admins:
        _b(
            kb,
            "BTN_HISTORY",
            text=f"{texts.BTN_HISTORY} · {admin['username']}",
            callback_data=f"hist:{admin['username']}",
        )
    kb.adjust(1)
    return kb.as_markup()


def panel_picker_kb(admins, action: str) -> InlineKeyboardMarkup:
    """One button per panel. `action` routes the choice (e.g. 'topup', 'pwd')."""
    kb = InlineKeyboardBuilder()
    for a in admins:
        kb.button(text=f"▪️ {a['username']}", callback_data=f"pick:{action}:{a['username']}")
    kb.adjust(1)
    return kb.as_markup()


def panel_name_picker_kb(panel_names) -> InlineKeyboardMarkup:
    """Choose which Marzban panel a newly provisioned reseller belongs to.

    The callback carries the panel's position, not its name: Telegram caps
    callback_data at 64 bytes and a Persian panel name would blow past that.
    """
    kb = InlineKeyboardBuilder()
    for index, name in enumerate(panel_names):
        kb.button(text=f"▪️ {name}", callback_data=f"newadmin_panel:{index}")
    kb.adjust(1)
    return kb.as_markup()


def tutorials_delete_kb(tutorials) -> InlineKeyboardMarkup:
    """Same list as browsing, but each row arms a deletion instead of opening."""
    kb = InlineKeyboardBuilder()
    for t in tutorials:
        kb.button(text=f"🗑 {t.title}", callback_data=f"tutorial_del:{t.id}")
    kb.adjust(1)
    return kb.as_markup()


def confirm_delete_tutorial_kb(tutorial_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_CONFIRM_DELETE", callback_data=f"tutorial_del_yes:{tutorial_id}")
    _b(kb, "BTN_KEEP", callback_data="tutorial_del_no")
    kb.adjust(1)
    return kb.as_markup()


def topup_panel_kb(username: str) -> InlineKeyboardMarkup:
    """Attached to low-traffic warnings so the admin can jump straight to topping
    up the panel the warning is about."""
    kb = InlineKeyboardBuilder()
    _b(kb, "BTN_TOPUP_THIS_PANEL", callback_data=f"pick:topup:{username}")
    return kb.as_markup()


def tutorials_list_kb(tutorials) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in tutorials:
        kb.button(text=t.title, callback_data=f"tutorial:{t.id}")
    kb.adjust(1)
    return kb.as_markup()
