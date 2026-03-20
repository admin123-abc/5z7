# ============================================================
#  agents/minimax_ai.py — 带 Alpha-Beta 剪枝的 Minimax AI
#  棋力引擎：启发式评分 + 候选缩减 + Alpha-Beta 剪枝
# ============================================================

import math
from agents.base_player import BasePlayer
from config import (
    EMPTY, BLACK, WHITE,
    AI_SEARCH_DEPTH, AI_CANDIDATE_DIST,
    WIN_COUNT,
)


# ── 棋型评分表（连子数 → 分值，区分活型/死型）────────────────────
# 活型：两端均未被封堵；死型：至少一端被封堵
_SCORE_TABLE = {
    # (连子数, 活端数): 分值
    (5, 2): 10_000_000,   # 五连（必胜）
    (5, 1): 10_000_000,
    (5, 0): 10_000_000,
    (4, 2): 100_000,      # 活四
    (4, 1): 10_000,       # 冲四
    (4, 0): 10_000,
    (3, 2): 5_000,        # 活三
    (3, 1): 500,          # 眠三
    (3, 0): 100,
    (2, 2): 200,          # 活二
    (2, 1): 50,
    (2, 0): 10,
    (1, 2): 10,
    (1, 1): 5,
    (1, 0): 1,
}

_DIRECTIONS = [(0, 1), (1, 0), (1, 1), (1, -1)]


class MinimaxAI(BasePlayer):
    """
    带 Alpha-Beta 剪枝的 Minimax 博弈树 AI。

    参数：
        depth (int): 搜索深度，越大棋力越强但越慢。
                     推荐：3（秒级响应），4（数秒），5（较慢）
        candidate_dist (int): 候选落子位的邻域半径。
                              只搜索已有棋子周边此距离内的空位。
    """

    def __init__(
        self,
        name: str = "Minimax AI",
        depth: int = AI_SEARCH_DEPTH,
        candidate_dist: int = AI_CANDIDATE_DIST,
    ):
        super().__init__(name)
        self.depth = depth
        self.candidate_dist = candidate_dist

    # ── 公开接口 ─────────────────────────────────────────────

    def get_move(self, board, piece: int) -> tuple[int, int]:
        """返回 AI 认为最优的落子坐标。"""
        opponent = WHITE if piece == BLACK else BLACK

        candidates = self._get_candidates(board)
        if not candidates:
            # 棋盘为空，直接走中心
            center = board.size // 2
            return center, center

        best_score = -math.inf
        best_move = candidates[0]

        for row, col in candidates:
            board_copy = board.copy()
            board_copy.place(row, col, piece)

            # 检查是否立即获胜
            if board_copy.check_win(row, col):
                return row, col

            score = self._minimax(
                board_copy, self.depth - 1, -math.inf, math.inf,
                False, piece, opponent, last_move=(row, col)
            )
            if score > best_score:
                best_score = score
                best_move = (row, col)

        return best_move

    # ── Minimax + Alpha-Beta ─────────────────────────────────

    def _minimax(
        self,
        board,
        depth: int,
        alpha: float,
        beta: float,
        is_maximizing: bool,
        ai_piece: int,
        opp_piece: int,
        last_move: tuple[int, int],
    ) -> float:
        # 终止条件：棋局结束 / 搜索深度耗尽
        if last_move and board.check_win(*last_move):
            # 上一步落子已经赢了
            if is_maximizing:
                # 上一步是对手落的（最小化层）→ 对手赢
                return -1_000_000 * (depth + 1)
            else:
                # 上一步是自己落的（最大化层）→ 自己赢
                return 1_000_000 * (depth + 1)

        if depth == 0 or board.is_full():
            return self._evaluate(board, ai_piece, opp_piece)

        candidates = self._get_candidates(board)
        if not candidates:
            return self._evaluate(board, ai_piece, opp_piece)

        current_piece = ai_piece if is_maximizing else opp_piece

        if is_maximizing:
            max_score = -math.inf
            for row, col in candidates:
                board_copy = board.copy()
                board_copy.place(row, col, current_piece)
                score = self._minimax(
                    board_copy, depth - 1, alpha, beta,
                    False, ai_piece, opp_piece, last_move=(row, col)
                )
                max_score = max(max_score, score)
                alpha = max(alpha, score)
                if beta <= alpha:
                    break  # β 剪枝
            return max_score
        else:
            min_score = math.inf
            for row, col in candidates:
                board_copy = board.copy()
                board_copy.place(row, col, current_piece)
                score = self._minimax(
                    board_copy, depth - 1, alpha, beta,
                    True, ai_piece, opp_piece, last_move=(row, col)
                )
                min_score = min(min_score, score)
                beta = min(beta, score)
                if beta <= alpha:
                    break  # α 剪枝
            return min_score

    # ── 启发式评分 ────────────────────────────────────────────

    def _evaluate(self, board, ai_piece: int, opp_piece: int) -> float:
        """对当前棋盘局面打分（正值有利于 AI，负值有利于对手）。"""
        return (
            self._score_for(board, ai_piece)
            - self._score_for(board, opp_piece)
        )

    def _score_for(self, board, piece: int) -> float:
        """统计指定颜色所有棋型的总分。"""
        total = 0
        size = board.size
        opp = WHITE if piece == BLACK else BLACK

        for r in range(size):
            for c in range(size):
                if board.get(r, c) == piece:
                    for dr, dc in _DIRECTIONS:
                        total += self._line_score(board, r, c, dr, dc, piece, opp)
        return total

    def _line_score(
        self, board, row: int, col: int,
        dr: int, dc: int, piece: int, opp: int
    ) -> float:
        """
        从 (row, col) 沿 (dr, dc) 方向，统计该方向上的棋型分值。
        避免重复计数：只统计从该点"正向延伸"的线段。
        """
        size = board.size

        # 若该点不是线段的"起点"（反向有同色子），跳过
        prev_r, prev_c = row - dr, col - dc
        if (0 <= prev_r < size and 0 <= prev_c < size
                and board.get(prev_r, prev_c) == piece):
            return 0

        # 正向统计连子数
        count = 0
        r, c = row, col
        while 0 <= r < size and 0 <= c < size and board.get(r, c) == piece:
            count += 1
            r += dr
            c += dc

        if count == 0:
            return 0

        # 统计两端是否开放
        open_ends = 0
        # 正端（延伸末尾的下一格）
        if 0 <= r < size and 0 <= c < size and board.get(r, c) == EMPTY:
            open_ends += 1
        # 负端（起点的前一格）
        neg_r, neg_c = row - dr, col - dc
        if (0 <= neg_r < size and 0 <= neg_c < size
                and board.get(neg_r, neg_c) == EMPTY):
            open_ends += 1

        # 截断到合法范围再查表
        query_count = min(count, WIN_COUNT)
        return _SCORE_TABLE.get((query_count, open_ends), 0)

    # ── 候选落子优化 ──────────────────────────────────────────

    def _get_candidates(self, board) -> list[tuple[int, int]]:
        """
        只返回已有棋子邻域 candidate_dist 格内的空位，
        大幅减少搜索空间。若棋盘全空返回空列表。
        """
        size = board.size
        dist = self.candidate_dist
        occupied = set()
        candidates = set()

        for r in range(size):
            for c in range(size):
                if board.get(r, c) != EMPTY:
                    occupied.add((r, c))

        if not occupied:
            return []

        for (r, c) in occupied:
            for dr in range(-dist, dist + 1):
                for dc in range(-dist, dist + 1):
                    nr, nc = r + dr, c + dc
                    if (0 <= nr < size and 0 <= nc < size
                            and board.get(nr, nc) == EMPTY):
                        candidates.add((nr, nc))

        # 按启发分排序（优先搜索"看起来更好"的落点），加速剪枝
        return sorted(candidates, key=lambda pos: -self._quick_score(board, pos))

    def _quick_score(self, board, pos: tuple[int, int]) -> int:
        """快速估算某个空位的价值（用于候选排序）。"""
        row, col = pos
        score = 0
        size = board.size
        for dr, dc in _DIRECTIONS:
            for piece in (BLACK, WHITE):
                # 数正负方向连续同色子
                cnt = 0
                for sign in (1, -1):
                    r, c = row + sign * dr, col + sign * dc
                    while (0 <= r < size and 0 <= c < size
                           and board.get(r, c) == piece):
                        cnt += 1
                        r += sign * dr
                        c += sign * dc
                score += cnt * cnt  # 连子越多越重要
        return score
