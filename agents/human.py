# ============================================================
#  agents/human.py — 人类终端输入玩家
#  通过标准输入接收坐标，带格式校验与友好提示
# ============================================================

from agents.base_player import BasePlayer


class HumanPlayer(BasePlayer):
    """
    人类玩家。

    输入格式：
        row col      （以空格分隔，从 0 开始）
        例如：  7 7   代表第 8 行第 8 列（棋盘中央）

    也支持逗号分隔：  7,7
    输入 'q' 或 'quit' 可退出游戏。
    """

    def __init__(self, name: str = "人类玩家"):
        super().__init__(name)

    def get_move(self, board, piece: int) -> tuple[int, int]:
        """等待并解析人类的终端输入，返回合法坐标。"""
        size = board.size
        while True:
            try:
                raw = input(f"  输入坐标 (行 列，范围 0-{size - 1})：").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  检测到退出指令，游戏终止。")
                raise SystemExit(0)

            if raw.lower() in ("q", "quit", "exit", "退出"):
                print("  游戏退出。")
                raise SystemExit(0)

            # 支持空格或逗号分隔
            raw = raw.replace(",", " ")
            parts = raw.split()

            if len(parts) != 2:
                print(f"  ⚠  请输入两个数字，例如：7 7")
                continue

            try:
                row, col = int(parts[0]), int(parts[1])
            except ValueError:
                print(f"  ⚠  坐标必须是整数，例如：7 7")
                continue

            if not (0 <= row < size and 0 <= col < size):
                print(f"  ⚠  坐标超出范围，行和列均需在 0 到 {size - 1} 之间。")
                continue

            if not board.is_valid_move(row, col):
                print(f"  ⚠  ({row}, {col}) 已被占用，请选择空位。")
                continue

            return row, col
