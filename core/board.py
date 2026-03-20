# ============================================================
#  core/board.py — 棋盘矩阵数据结构 + 输赢仲裁算法
#  职责：纯数据读写 + 规则引擎，零 UI，零 AI
# ============================================================

from __future__ import annotations

import copy
from config import BOARD_SIZE, EMPTY, WIN_COUNT


class BoardError(Exception):
    """棋盘操作异常基类"""


class OutOfBoundsError(BoardError):
    """落子越界"""


class CellOccupiedError(BoardError):
    """该格已有棋子"""


class Board:
    """
    棋盘矩阵。

    内部使用二维列表 _grid[row][col]：
        0  → EMPTY
        1  → BLACK
        2  → WHITE

    坐标约定：(row, col)，均从 0 开始，最大为 size-1。
    """

    # 四个方向向量（横、竖、主对角线、反对角线）
    _DIRECTIONS = [
        (0, 1),   # →
        (1, 0),   # ↓
        (1, 1),   # ↘
        (1, -1),  # ↙
    ]

    def __init__(self, size: int = BOARD_SIZE):
        self.size: int = size
        self._grid: list[list[int]] = [
            [EMPTY] * size for _ in range(size)
        ]
        self._move_count: int = 0   # 已落子数，便于平局判断

    # ── 公开 API ─────────────────────────────────────────────

    def place(self, row: int, col: int, piece: int) -> None:
        """
        在 (row, col) 放置 piece（BLACK 或 WHITE）。

        Raises:
            OutOfBoundsError: 坐标超出棋盘范围
            CellOccupiedError: 该格已被占用
        """
        self._validate(row, col)
        self._grid[row][col] = piece
        self._move_count += 1

    def is_valid_move(self, row: int, col: int) -> bool:
        """判断 (row, col) 是否是合法落子位（在界内且为空）"""
        if not (0 <= row < self.size and 0 <= col < self.size):
            return False
        return self._grid[row][col] == EMPTY

    def check_win(self, row: int, col: int) -> bool:
        """
        以最近落子点 (row, col) 为中心，检查该棋子是否使己方形成连五。
        只需检查四个方向。
        """
        piece = self._grid[row][col]
        if piece == EMPTY:
            return False

        for dr, dc in self._DIRECTIONS:
            count = 1  # 计入落子点本身
            # 正方向延伸
            count += self._count_line(row, col, dr, dc, piece)
            # 反方向延伸
            count += self._count_line(row, col, -dr, -dc, piece)
            if count >= WIN_COUNT:
                return True
        return False

    def is_full(self) -> bool:
        """棋盘满了 → 平局"""
        return self._move_count >= self.size * self.size

    def get_empty_positions(self) -> list[tuple[int, int]]:
        """返回所有空位坐标列表"""
        return [
            (r, c)
            for r in range(self.size)
            for c in range(self.size)
            if self._grid[r][c] == EMPTY
        ]

    def get(self, row: int, col: int) -> int:
        """读取 (row, col) 的棋子代号"""
        return self._grid[row][col]

    def copy(self) -> "Board":
        """返回当前棋盘的深拷贝（供 AI 搜索使用）"""
        new_board = Board(self.size)
        new_board._grid = copy.deepcopy(self._grid)
        new_board._move_count = self._move_count
        return new_board

    # ── 技能 / 悔棋 支持 API ────────────────────────────────

    def remove(self, row: int, col: int) -> int:
        """
        移除 (row, col) 上的棋子，返回被移除的棋子代号。
        若该格为空则什么都不做，返回 EMPTY。
        用于悔棋和技能。
        """
        piece = self._grid[row][col]
        if piece != EMPTY:
            self._grid[row][col] = EMPTY
            self._move_count = max(0, self._move_count - 1)
        return piece

    def set_piece(self, row: int, col: int, piece: int) -> None:
        """
        强制将 (row, col) 设为 piece（忽略原有内容）。
        用于"乾坤挪移"技能（翻转棋子归属）。
        """
        if not (0 <= row < self.size and 0 <= col < self.size):
            raise OutOfBoundsError(f"坐标 ({row}, {col}) 越界")
        old = self._grid[row][col]
        self._grid[row][col] = piece
        # 调整落子计数
        if old == EMPTY and piece != EMPTY:
            self._move_count += 1
        elif old != EMPTY and piece == EMPTY:
            self._move_count = max(0, self._move_count - 1)

    def clear_area(self, row: int, col: int, radius: int = 1) -> list:
        """
        清空以 (row, col) 为中心、半径 radius 格的矩形区域。
        返回被清除的 [(r, c, piece), ...] 列表（仅非空格）。
        用于"终归虚无"技能。
        """
        cleared = []
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                r, c = row + dr, col + dc
                if 0 <= r < self.size and 0 <= c < self.size:
                    piece = self._grid[r][c]
                    if piece != EMPTY:
                        cleared.append((r, c, piece))
                        self._grid[r][c] = EMPTY
                        self._move_count = max(0, self._move_count - 1)
        return cleared

    def check_win_full(self) -> int:
        """
        全局扫描检查是否有一方已经五连（技能操作后用）。
        返回获胜方棋子代号，或 EMPTY（未分胜负）。
        """
        from config import BLACK, WHITE
        for piece in (BLACK, WHITE):
            for r in range(self.size):
                for c in range(self.size):
                    if self._grid[r][c] == piece and self.check_win(r, c):
                        return piece
        return EMPTY

    # ── 内部工具 ─────────────────────────────────────────────

    def _validate(self, row: int, col: int) -> None:
        if not (0 <= row < self.size and 0 <= col < self.size):
            raise OutOfBoundsError(
                f"坐标 ({row}, {col}) 超出棋盘范围 [0, {self.size - 1}]"
            )
        if self._grid[row][col] != EMPTY:
            raise CellOccupiedError(
                f"坐标 ({row}, {col}) 已被占用"
            )

    def _count_line(
        self, row: int, col: int, dr: int, dc: int, piece: int
    ) -> int:
        """从 (row, col) 沿向量 (dr, dc) 延伸，统计连续同色棋子数"""
        count = 0
        r, c = row + dr, col + dc
        while 0 <= r < self.size and 0 <= c < self.size:
            if self._grid[r][c] == piece:
                count += 1
                r += dr
                c += dc
            else:
                break
        return count
