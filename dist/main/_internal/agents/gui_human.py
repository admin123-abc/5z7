from __future__ import annotations

import threading
from agents.base_player import BasePlayer


class GUIHumanPlayer(BasePlayer):
    """
    Pygame GUI 人类玩家。

    get_move() 阻塞等待主线程投递坐标或特殊指令。
    特殊指令：字符串 "undo" 表示玩家请求悔棋。
    """

    def __init__(self, name: str = "玩家"):
        super().__init__(name)
        self._pending: object = None   # (row,col) 或 "undo"
        self._move_event = threading.Event()

    def get_move(self, board, piece: int):
        """阻塞等待 GUI 投递坐标或指令。"""
        self._pending = None
        self._move_event.clear()
        self._move_event.wait()
        return self._pending

    def submit_move(self, row: int, col: int) -> None:
        """投递落子坐标（主线程调用）。"""
        self._pending = (row, col)
        self._move_event.set()

    def submit_undo(self) -> None:
        """投递悔棋指令（主线程调用）。"""
        self._pending = "undo"
        self._move_event.set()

    def is_waiting(self) -> bool:
        """是否正在等待玩家输入。"""
        return not self._move_event.is_set()
