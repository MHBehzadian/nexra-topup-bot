"""What the superadmin has changed about the bot from the Nexra panel: the
wording of any text, and each button's colour and premium-emoji icon.

texts.py stays the source of the defaults. An override is written onto the
texts module itself, so every `texts.X` read anywhere picks it up at once with
no restart. The few places that look a label up when the module loads (the
reply-button filters, nav.ALL_MENU_TEXTS) go through `Label` and
`refresh_menu_texts` instead, which also keep accepting the default wording —
a customer's keyboard only changes on their next menu, and the old button must
still work until then.
"""

from __future__ import annotations

import json
import re
import string

from . import texts
from .. import db

# Every editable text, as shipped. Taken before any override is applied.
DEFAULTS: dict[str, str] = {
    name: value
    for name, value in vars(texts).items()
    if name.isupper() and isinstance(value, str)
}

STYLES = ("primary", "success", "danger")

# The colour a button has until the superadmin picks another: the one action
# each screen is there for — pay, top up, get into the panel.
DEFAULT_STYLES: dict[str, str] = {
    "BTN_TOPUP": "primary",
    "BTN_LOGIN_WITH_VPN": "primary",
    "BTN_LOGIN_WITHOUT_VPN": "primary",
    "BTN_PARTNERSHIP": "primary",
    "BTN_CREATE_PANEL": "primary",
    "BTN_PENDING_REQUESTS": "primary",
    "BTN_JOIN_CHANNEL": "primary",
    "BTN_PAY": "primary",
    "BTN_PAY_CARD": "primary",
    "BTN_PAY_INVOICE": "primary",
    "BTN_PAY_DEBT": "primary",
    "BTN_PAY_BILL_INVOICE": "primary",
    "BTN_PAY_BILL_WEEKLY": "primary",
    "BTN_PAY_ALL_BILLS": "primary",
    "BTN_CHARGE_WALLET": "primary",
    "BTN_TOPUP_THIS_PANEL": "primary",
    "BTN_APPROVE": "primary",
}

# Shown where Telegram parses no HTML (a callback's toast or alert), so a tag
# or a premium emoji would appear as raw markup.
PLAIN = {
    "ALREADY_HANDLED", "BILL_DELETE_FAILED", "FORCE_JOIN_CONFIRMED",
    "INVOICE_ALREADY_PAID", "INVOICE_NOT_FOUND", "LOCKED_TOAST", "LOCK_NOT_LOCKED",
    "LOCK_NO_PANELS", "NOT_FOUND", "NOT_LINKED_RETRY", "NO_DEBT", "NO_INVOICES",
    "PANEL_CHOICE_EXPIRED", "PANEL_UNREACHABLE", "PAY_ALL_NOTHING",
    "TUTORIAL_NOT_FOUND", "UNLOCKED_TOAST", "WARNING_BILL_GONE",
    "WARNING_NOT_DELIVERED", "WARNING_SENT_TOAST", "WEEKLY_NOT_ENABLED",
}

_TEXTS_KEY = "custom_texts"
_BUTTONS_KEY = "button_styles"
_EMOJI_ID = re.compile(r"^\d{5,30}$")
_TAG = re.compile(r"<[^>]+>")


def is_button(name: str) -> bool:
    return name.startswith("BTN_")


def _load(key: str) -> dict:
    raw = db.get_setting(key)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _store(key: str, data: dict) -> None:
    db.set_setting(key, json.dumps(data, ensure_ascii=False))


# ------------------------------------------------------------------ texts


def overrides() -> dict[str, str]:
    return {k: v for k, v in _load(_TEXTS_KEY).items() if k in DEFAULTS and isinstance(v, str)}


def apply() -> None:
    """Write the stored wording onto the texts module; call after every change."""
    stored = overrides()
    for name, default in DEFAULTS.items():
        setattr(texts, name, stored.get(name, default))
    refresh_menu_texts()


def fields(text: str) -> set[str]:
    """The {placeholders} a text is formatted with. Raises ValueError on a stray
    brace, which would make every later .format() of it fail."""
    names = set()
    for _, field, _, _ in string.Formatter().parse(text):
        if field is not None:
            names.add(re.split(r"[.\[!:]", field, maxsplit=1)[0])
    return names


def validate(name: str, value: str) -> str | None:
    """Why this wording can't be used, or None if it can."""
    if name not in DEFAULTS:
        return "unknown text"
    if not value.strip():
        return "text is empty"
    try:
        allowed = fields(DEFAULTS[name])
        used = fields(value)
    except ValueError:
        return "a { or } is unbalanced; write {{ or }} for a literal brace"
    extra = used - allowed
    if extra:
        return "unknown placeholder: " + ", ".join(sorted("{" + f + "}" for f in extra))
    if is_button(name) or name in PLAIN:
        if _TAG.search(value):
            return (
                "a button label can't hold HTML or a premium emoji — set its icon instead"
                if is_button(name)
                else "this text is shown as a pop-up, which can't show HTML or a premium emoji"
            )
        if len(value) > (64 if is_button(name) else 200):
            return "too long"
    else:
        if len(value) > 4000:
            return "too long"
    return None


def set_texts(changes: dict[str, str]) -> dict[str, str]:
    """Store new wording; an empty value or the default puts the default back.
    Returns the errors per name — nothing is stored if there are any."""
    stored = overrides()
    errors: dict[str, str] = {}
    for name, value in changes.items():
        if not isinstance(value, str):
            errors[name] = "text must be a string"
            continue
        if value.strip() == "" or value == DEFAULTS.get(name):
            stored.pop(name, None)
            continue
        error = validate(name, value)
        if error:
            errors[name] = error
        else:
            stored[name] = value

    # Two buttons with one label would answer to the same tap.
    owners: dict[str, list[str]] = {}
    for name in DEFAULTS:
        if is_button(name):
            owners.setdefault(stored.get(name, DEFAULTS[name]), []).append(name)
    for name in changes:
        if name in stored and is_button(name):
            others = [n for n in owners.get(stored[name], []) if n != name]
            if others:
                errors[name] = f"same label as {others[0]}"

    if errors:
        return errors
    _store(_TEXTS_KEY, stored)
    apply()
    return {}


# ------------------------------------------------------------------ buttons


# Read on every keyboard drawn, so kept in memory; set_buttons resets it.
_buttons_cache: dict[str, dict] | None = None


def buttons() -> dict[str, dict]:
    """Each button's colour and icon, defaults filled in. An explicit empty
    style ("") is how a default colour is turned off."""
    global _buttons_cache
    if _buttons_cache is not None:
        return _buttons_cache
    stored = _load(_BUTTONS_KEY)
    out: dict[str, dict] = {}
    for name in DEFAULTS:
        if not is_button(name):
            continue
        entry = stored.get(name) or {}
        style = entry.get("style", DEFAULT_STYLES.get(name, ""))
        out[name] = {"style": style or "", "emoji": entry.get("emoji") or ""}
    _buttons_cache = out
    return out


def set_buttons(changes: dict[str, dict]) -> dict[str, str]:
    stored = _load(_BUTTONS_KEY)
    errors: dict[str, str] = {}
    for name, entry in changes.items():
        if not is_button(name) or name not in DEFAULTS:
            errors[name] = "unknown button"
            continue
        if not isinstance(entry, dict):
            errors[name] = "expected {style, emoji}"
            continue
        style = entry.get("style") or ""
        emoji = str(entry.get("emoji") or "").strip()
        if style and style not in STYLES:
            errors[name] = "style must be primary, success or danger"
            continue
        if emoji and not _EMOJI_ID.match(emoji):
            errors[name] = "icon must be a custom emoji id"
            continue
        clean = {"emoji": emoji} if emoji else {}
        if style != DEFAULT_STYLES.get(name, ""):
            clean["style"] = style
        if clean:
            stored[name] = clean
        else:
            stored.pop(name, None)
    if errors:
        return errors
    global _buttons_cache
    _store(_BUTTONS_KEY, stored)
    _buttons_cache = None
    return {}


def button_opts(name: str) -> dict:
    """Keyword arguments for a keyboard builder's .button() for this button."""
    entry = buttons().get(name) or {}
    return {
        "style": entry.get("style") or None,
        "icon_custom_emoji_id": entry.get("emoji") or None,
    }


# ------------------------------------------------------------------ menu labels


def labels_for(*names: str) -> set[str]:
    """What a tap on one of these buttons may say: its current label, or the
    default one a keyboard sent before the change still carries."""
    out = set()
    for name in names:
        out.add(getattr(texts, name))
        out.add(DEFAULTS[name])
    return out


def refresh_menu_texts() -> None:
    from . import nav  # nav imports keyboards, which imports this module

    nav.ALL_MENU_TEXTS.clear()
    nav.ALL_MENU_TEXTS.update(labels_for(*nav.MENU_KEYS))


# ------------------------------------------------------------------ taps on iconed buttons


def all_button_labels() -> set[str]:
    return labels_for(*(name for name in DEFAULTS if is_button(name)))


def _without_custom_emoji(text: str, entities) -> str:
    """The text with every custom-emoji span cut out. Entity offsets count
    UTF-16 code units, not Python characters, hence the round trip."""
    spans = sorted(
        (e.offset, e.offset + e.length) for e in entities or [] if e.type == "custom_emoji"
    )
    if not spans:
        return text
    raw = text.encode("utf-16-le")
    out, pos = bytearray(), 0
    for start, end in spans:
        out += raw[pos * 2 : start * 2]
        pos = max(pos, end)
    out += raw[pos * 2 :]
    return out.decode("utf-16-le", errors="ignore")


def tapped_label(text: str | None, entities=None) -> str | None:
    """The button label a tap was meant to send, when the text differs from it.

    A reply button with a premium icon (set from the panel) sends its icon along
    with its label — the icon's emoji in front, marked as a custom emoji — so the
    text no longer equals the label and the tap went unrecognised, landing in
    whatever flow was waiting for typed input. None when the text is already a
    label, or isn't a button at all.
    """
    if not text:
        return None
    labels = all_button_labels()
    if text in labels:
        return None
    stripped = _without_custom_emoji(text, entities).strip()
    if stripped in labels:
        return stripped
    # Some clients send the icon as a plain emoji with no entity: accept a
    # label preceded by a few characters of emoji and spacing, and nothing else.
    for label in sorted(labels, key=len, reverse=True):
        if text.endswith(label):
            prefix = text[: -len(label)]
            if len(prefix) <= 12 and not any(ch.isalnum() for ch in prefix):
                return label
    return None
