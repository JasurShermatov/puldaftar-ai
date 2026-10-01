"""Bot FSM holatlari (handlerlar o'rtasida umumiy)."""
from aiogram.fsm.state import State, StatesGroup


class AiChat(StatesGroup):
    waiting = State()      # foydalanuvchi AI suhbat rejimida: matn/ovoz — savol sifatida qabul qilinadi
