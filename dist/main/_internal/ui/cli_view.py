# ============================================================
#  ui/cli_view.py — 终端字符棋盘视图
#  职责：把 Board 对象渲染成字符画；打印消息。
#        不含任何游戏逻辑，不含任何 AI 逻辑。
# ============================================================

from config import PIECE_SYMBOLS, EMPTY


class CLIView:
    """
    终端（黑框框）字符棋盘视图。

    示例输出（9×9 演示）：
        ┌─ 五子棋 ──────────────────────────┐
           0  1  2  3  4  5  6  7  8
         0 ·  ·  ·  ·  ·  ·  ·  ·  ·
         1 ·  ·  ·  ·  ·  ·  ·  ·  ·
         2 ·  ·  ·  ●  ·  ·  ·  ·  ·
         ...
        └───────────────────────────────────┘

    ● = 黑子   ○ = 白子   · = 空位
    """

    # ANSI 颜色（可选，若终端不支持请设 _USE_COLOR = False）
    _USE_COLOR: bool = True
    _BLACK_COLOR  = "\033[1;33m"   # 亮黄（黑子在黑色终端上更清晰）
    _WHITE_COLOR  = "\033[1;37m"   # 亮白
    _RESET        = "\033[0m"
    _HEADER_COLOR = "\033[1;36m"   # 青色标题
    _COORD_COLOR  = "\033[0;90m"   # 灰色坐标

    def render(self, board) -> None:
        """将 Board 渲染并打印到终端。"""
        size = board.size
        width = size * 3 + 4
        sep = "─" * width

        # 标题栏
        self._print(f"\n┌─{self._color('五子棋', self._HEADER_COLOR)}{sep}┐")

        # 列号行
        col_labels = "  ".join(f"{c:2d}" for c in range(size))
        self._print(
            f"    {self._color(col_labels, self._COORD_COLOR)}"
        )

        # 棋盘行
        for r in range(size):
            row_label = self._color(f"{r:2d}", self._COORD_COLOR)
            cells = []
            for c in range(size):
                piece = board.get(r, c)
                symbol = PIECE_SYMBOLS[piece]
                if self._USE_COLOR and piece != EMPTY:
                    color = (
                        self._BLACK_COLOR if piece == 1 else self._WHITE_COLOR
                    )
                    symbol = f"{color}{symbol}{self._RESET}"
                cells.append(symbol)
            row_str = "  ".join(cells)
            self._print(f" {row_label}  {row_str}")

        self._print(f"└{sep}─┘\n")

    def show_message(self, msg: str) -> None:
        """打印一条提示消息。"""
        print(msg)

    # ── 内部工具 ─────────────────────────────────────────────

    @staticmethod
    def _print(text: str) -> None:
        print(text)

    def _color(self, text: str, ansi_code: str) -> str:
        if self._USE_COLOR:
            return f"{ansi_code}{text}{self._RESET}"
        return text
