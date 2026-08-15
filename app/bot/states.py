"""FSM state groups for multi-step bot flows."""

from aiogram.fsm.state import State, StatesGroup


class TopUp(StatesGroup):
    amount_gb = State()
    toman_amount = State()
    receipt = State()


class RejectReason(StatesGroup):
    reason = State()


class MessageUser(StatesGroup):
    text = State()


class ChangePassword(StatesGroup):
    new_password = State()
