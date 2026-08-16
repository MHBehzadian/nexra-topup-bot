"""FSM state groups for multi-step bot flows."""

from aiogram.fsm.state import State, StatesGroup


class TopUp(StatesGroup):
    amount_gb = State()
    awaiting_payment = State()
    receipt = State()


class RejectReason(StatesGroup):
    reason = State()


class MessageUser(StatesGroup):
    text = State()


class ChangePassword(StatesGroup):
    new_password = State()


class SetPricePerGb(StatesGroup):
    value = State()


class SetCardNumber(StatesGroup):
    value = State()


class SetForceJoinChannel(StatesGroup):
    value = State()


class AddTutorial(StatesGroup):
    title = State()
    content = State()


class SetBulkPin(StatesGroup):
    value = State()


class ExportCredentials(StatesGroup):
    pin = State()
