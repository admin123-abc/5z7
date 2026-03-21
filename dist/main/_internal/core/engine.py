from __future__ import annotations

# ============================================================
#  core/engine.py — 全局状态机
#  职责：控制回合流转；向 Player 索要落子坐标；喂给 Board；
#        通过注入的 View 渲染棋盘。
#        引擎本身不含任何渲染代码，也不含任何 AI 逻辑。
#  新增：悔棋历史 + 技能接口（乾坤挪移/终归虚无/一马当先）
# ============================================================

import threading
from config import BLACK, WHITE, PIECE_NAMES, EMPTY
from core.board import Board, BoardError


class GameEngine:
    """
    五子棋状态机。

    依赖注入：
        player_black : BasePlayer  先手（黑子）
        player_white : BasePlayer  后手（白子）
        view         : 拥有 render(board) 和 show_message(msg) 方法的视图对象
        board_size   : 棋盘大小（可选，默认从 config 读取）
    """

    def __init__(self, player_black, player_white, view, board_size=None):
        from config import BOARD_SIZE
        size = board_size if board_size is not None else BOARD_SIZE

        self.board = Board(size)
        self.view = view

        self._players = {
            BLACK: player_black,
            WHITE: player_white,
        }
        self._current_piece: int = BLACK

        # ── 悔棋历史 ──────────────────────────────────────────
        # 每个元素: {"type": "place"/"skill", "snapshot": Board}
        # 最多保留 60 步历史
        self._history: list[dict] = []
        self._MAX_HISTORY = 60

        # ── 技能使用标志（每局各一次）────────────────────────
        # 玩家黑子技能次数
        self.skill_charges = {
            "horse": 1,   # 一马当先
            "swap":  1,   # 乾坤挪移
            "void":  1,   # 终归虚无
        }

        # ── 线程锁（技能和悔棋可能从 GUI 主线程调用）─────────
        self._lock = threading.Lock()

        # 游戏是否结束
        self._game_over = False

    # ── 公开入口 ─────────────────────────────────────────────

    def run(self) -> None:
        """
        点火！主游戏循环。
        CLI 模式：直接在主线程调用此方法。
        GUI 模式：由 GUIView.set_engine() 在后台线程调用此方法。
        """
        self.view.show_message("=== 五子棋开始！黑子先手 ===\n")

        while True:
            # 1. 渲染当前棋盘
            self.view.render(self.board)

            current_player = self._players[self._current_piece]
            piece_name = PIECE_NAMES[self._current_piece]

            self.view.show_message(
                f"【{piece_name}】{current_player.name} 请落子："
            )

            # 2. 向玩家索要落子坐标（带错误重试）
            result = self._request_move(current_player)

            # result 可能是 "undo" 特殊指令
            if result == "undo":
                continue

            row, col = result

            # 3. 记录历史快照
            self._push_history("place")

            # 4. 写入棋盘
            self.board.place(row, col, self._current_piece)

            # 5. 胜负判断
            if self._check_end_after_action(row, col):
                break

            # 6. 切换回合
            self._switch_turn()

    # ── 悔棋公开接口（GUI 主线程调用）───────────────────────

    def undo(self) -> bool:
        """
        悔棋：回退最多 2 步（玩家1步 + AI1步）。
        成功返回 True，无历史可悔返回 False。
        由 GUIView 在主线程调用，通过 GUIHumanPlayer 中断等待。
        """
        with self._lock:
            if len(self._history) < 1:
                return False
            # 最多回退 2 步
            steps = min(2, len(self._history))
            for _ in range(steps):
                snapshot = self._history.pop()["snapshot"]
            # 恢复到该快照
            self.board = snapshot.copy()
            # 回退后回合也倒退对应步数
            # 奇数步不变，偶数步不变（因为每步都切换了）
            if steps % 2 == 1:
                self._switch_turn()
            return True

    # ── 技能公开接口（GUI 主线程调用）──────────────────────

    def skill_horse(self, row: int, col: int, dr: int, dc: int) -> bool:
        """
        一马当先：在 (row,col) 和 (row+dr, col+dc) 各落一子（斜方向）。
        返回是否成功，并检测胜负。
        """
        if self.skill_charges.get("horse", 0) <= 0:
            return False
        piece = self._current_piece
        pos2 = (row + dr, col + dc)
        # 两格都必须合法
        if not self.board.is_valid_move(row, col):
            return False
        if not (0 <= pos2[0] < self.board.size and 0 <= pos2[1] < self.board.size):
            return False
        if not self.board.is_valid_move(*pos2):
            return False

        with self._lock:
            self._push_history("skill_horse")
            self.board.place(row, col, piece)
            self.board.place(*pos2, piece)
            self.skill_charges["horse"] -= 1
        return True

    def skill_swap(self, row: int, col: int) -> bool:
        """
        乾坤挪移：将 (row,col) 上的对手棋子翻转为己方。
        """
        if self.skill_charges.get("swap", 0) <= 0:
            return False
        opp = WHITE if self._current_piece == BLACK else BLACK
        if self.board.get(row, col) != opp:
            return False

        with self._lock:
            self._push_history("skill_swap")
            self.board.set_piece(row, col, self._current_piece)
            self.skill_charges["swap"] -= 1
        return True

    def skill_void(self, row: int, col: int) -> bool:
        """
        终归虚无：清空 (row,col) 周围 3×3 区域。
        """
        if self.skill_charges.get("void", 0) <= 0:
            return False
        if not (0 <= row < self.board.size and 0 <= col < self.board.size):
            return False

        with self._lock:
            self._push_history("skill_void")
            self.board.clear_area(row, col, radius=1)
            self.skill_charges["void"] -= 1
        return True

    # ── 内部工具 ─────────────────────────────────────────────

    def _push_history(self, action_type: str) -> None:
        """保存当前棋盘快照到历史栈。"""
        self._history.append({
            "type": action_type,
            "snapshot": self.board.copy(),
            "piece": self._current_piece,
        })
        if len(self._history) > self._MAX_HISTORY:
            self._history.pop(0)

    def _request_move(self, player):
        """
        向 player 请求一个合法落子坐标。
        返回 (row, col) 或 "undo" 字符串（表示玩家请求悔棋）。
        """
        while True:
            try:
                result = player.get_move(self.board, self._current_piece)

                # GUIHumanPlayer 可能返回特殊指令字符串
                if result == "undo":
                    success = self.undo()
                    if success:
                        self.view.render(self.board)
                        self.view.show_message("  ↩  已悔棋，请重新落子")
                        return "undo"
                    else:
                        self.view.show_message("  ⚠  无法悔棋（没有历史记录）")
                        continue

                row, col = result
                if not self.board.is_valid_move(row, col):
                    self.view.show_message(
                        f"  ⚠  坐标 ({row}, {col}) 不合法（越界或已占用），请重新输入。"
                    )
                    continue
                return row, col
            except BoardError as e:
                self.view.show_message(f"  ⚠  落子失败：{e}，请重新输入。")
            except (ValueError, TypeError) as e:
                self.view.show_message(f"  ⚠  输入格式错误：{e}，请重新输入。")

    def _check_end_after_action(self, row: int = None, col: int = None) -> bool:
        """
        检查游戏是否结束。
        若指定了 (row, col) 则只检查该点周围；否则全局扫描。
        返回 True 表示游戏结束。
        """
        from config import PIECE_NAMES
        winner = EMPTY

        if row is not None and col is not None:
            if self.board.check_win(row, col):
                winner = self._current_piece
        else:
            winner = self.board.check_win_full()

        if winner != EMPTY:
            pname = PIECE_NAMES[winner]
            pplayer = self._players[winner]
            self.view.render(self.board)
            self.view.show_message(
                f"\n🎉 【{pname}】{pplayer.name} 获胜！游戏结束。"
            )
            self._game_over = True
            return True

        if self.board.is_full():
            self.view.render(self.board)
            self.view.show_message("\n🤝 棋盘已满，平局！游戏结束。")
            self._game_over = True
            return True

        return False

    def _switch_turn(self) -> None:
        """黑白交替"""
        self._current_piece = WHITE if self._current_piece == BLACK else BLACK
