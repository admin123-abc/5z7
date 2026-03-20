# ============================================================
#  agents/base_player.py — 玩家纯虚基类
#  所有玩家（人类 / AI）必须继承此类并实现 get_move 接口
# ============================================================

from abc import ABC, abstractmethod


class BasePlayer(ABC):
    """
    玩家抽象基类。

    子类必须实现：
        get_move(board, piece) -> (row, col)

    属性：
        name (str): 玩家名称，用于界面显示
    """

    def __init__(self, name: str = "玩家"):
        self.name: str = name

    @abstractmethod
    def get_move(self, board, piece: int) -> tuple[int, int]:
        """
        根据当前棋盘状态，返回落子坐标 (row, col)。

        参数:
            board  : core.board.Board  当前棋盘（只读，请勿直接修改）
            piece  : int               本方棋子代号（BLACK 或 WHITE）

        返回:
            (row, col): 合法的落子坐标（从 0 开始）
        """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
