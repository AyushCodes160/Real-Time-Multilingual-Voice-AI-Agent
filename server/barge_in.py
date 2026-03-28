import asyncio

class BargeInController:
    def __init__(self):
        self._is_speaking = False
        self._barge_in_event = asyncio.Event()

    def set_speaking(self, talking: bool) -> None:
        self._is_speaking = talking
        if not talking:
            self._barge_in_event.clear()

    def register_user_speech(self) -> None:
        if self._is_speaking:
            self._barge_in_event.set()

    def check_interrupted(self) -> bool:
        return self._barge_in_event.is_set()

    def reset(self) -> None:
        self._barge_in_event.clear()
        self._is_speaking = False
