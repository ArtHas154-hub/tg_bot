from aiogram.fsm.state import StatesGroup, State


class DealCreation(StatesGroup):
    choose_type = State()
    choose_currency = State()
    enter_amount = State()
    enter_description = State()


class ProfileUpdate(StatesGroup):
    set_card = State()
    set_wallet = State()
    set_stars = State()


class WithdrawRequestStates(StatesGroup):
    choose_currency = State()
    enter_amount = State()
    confirm_withdrawal = State()


class BroadcastStates(StatesGroup):
    enter_text = State()
    confirm = State()
