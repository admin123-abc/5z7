#!/usr/bin/env python3
# ============================================================
#  main.py — 系统点火入口 + 依赖注入装配器
#
#  默认行为：直接弹出 Pygame GUI 主菜单（四按钮选模式）
#  也支持命令行参数直接指定模式跳过菜单
# ============================================================

from __future__ import annotations
import argparse
import sys
import io
import codecs
print(f"DEBUG: {sys.stdout.encoding}")  # 输出当前标准输出编码，调试用


if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="五子棋",
        description="五子棋对战系统 — 直接运行即可弹出 GUI 界面",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python main.py                        # 弹出 GUI 主菜单（推荐！）
  python main.py --mode pve             # 跳过菜单，直接人机对战
  python main.py --mode pvp             # 跳过菜单，直接双人对战
  python main.py --mode eve             # 跳过菜单，AI 自战
  python main.py --mode pvd             # 跳过菜单，挑战 DeepSeek R1
  python main.py --cli --mode pve       # CLI 终端模式
  python main.py --depth 4              # 设置 AI 搜索深度
  python main.py --no-sound             # 静音模式
        """,
    )
    parser.add_argument(
        "--mode", "-m",
        default=None,
        choices=["pvp", "pve", "evp", "eve", "rvp", "pvr", "pvd", "dvp"],
        help="直接指定对战模式（跳过菜单）",
    )
    parser.add_argument(
        "--depth", "-d",
        type=int,
        default=None,
        help="Minimax AI 搜索深度（默认 3，推荐 3-4）",
    )
    parser.add_argument(
        "--size", "-s",
        type=int,
        default=None,
        help="棋盘大小（默认 15，最小 5）",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="使用 CLI 终端模式（默认为 GUI）",
    )
    parser.add_argument(
        "--no-sound",
        action="store_true",
        help="禁用音效",
    )
    return parser


def make_players(mode: str, depth, use_gui: bool):
    from agents.minimax_ai import MinimaxAI
    from agents.rl_ai import RLPlayer
    from config import AI_SEARCH_DEPTH

    search_depth = depth if depth is not None else AI_SEARCH_DEPTH

    def ai(name="Minimax AI"):
        return MinimaxAI(name=name, depth=search_depth)

    def rl(name="RL AI"):
        return RLPlayer(name=name)

    def deepseek(name="DeepSeek R1"):
        from agents.deepseek_agent import DeepSeekAgent
        return DeepSeekAgent(name=name)

    def human(name="玩家"):
        if use_gui:
            from agents.gui_human import GUIHumanPlayer
            return GUIHumanPlayer(name=name)
        else:
            from agents.human import HumanPlayer
            return HumanPlayer(name=name)

    mode_map = {
        "pvp": (human("玩家 1"),         human("玩家 2")),
        "pve": (human("玩家"),           ai("Minimax AI")),
        "evp": (ai("Minimax AI"),        human("玩家")),
        "eve": (ai("AI (黑)"),           ai("AI (白)")),
        "rvp": (rl("RL AI"),             human("玩家")),
        "pvr": (human("玩家"),           rl("RL AI")),
        # DeepSeek R1 模式
        "pvd": (human("玩家"),           deepseek("DeepSeek R1")),
        "dvp": (deepseek("DeepSeek R1"), human("玩家")),
    }
    return mode_map[mode]


def run_gui(mode, depth, board_size, no_sound):
    """GUI 模式启动。"""
    import config as C
    if no_sound:
        C.GUI_SOUND_ENABLED = False

    from ui.gui_view import GUIView
    view = GUIView()

    # 如果没有指定 mode，先显示主菜单让用户选择
    if mode is None:
        mode = view.show_menu()
        if mode is None:
            # 用户在菜单按了 ESC
            return

    player_black, player_white = make_players(mode, depth, True)

    from core.engine import GameEngine
    engine = GameEngine(
        player_black=player_black,
        player_white=player_white,
        view=view,
        board_size=board_size,
    )

    view.set_engine(engine)
    view.main_loop()


def run_cli(mode, depth, board_size):
    """CLI 模式启动。"""
    if mode is None:
        mode = "pve"

    player_black, player_white = make_players(mode, depth, False)
    from ui.cli_view import CLIView
    view = CLIView()

    from core.engine import GameEngine
    engine = GameEngine(
        player_black=player_black,
        player_white=player_white,
        view=view,
        board_size=board_size,
    )
    engine.run()


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    board_size = args.size
    if board_size is not None and board_size < 5:
        print("⚠  棋盘至少为 5，已自动修正。")
        board_size = 5

    try:
        if args.cli:
            run_cli(args.mode, args.depth, board_size)
        else:
            run_gui(args.mode, args.depth, board_size,
                    getattr(args, "no_sound", False))
    except KeyboardInterrupt:
        print("\n  再见！")
        sys.exit(0)
    except SystemExit:
        pass


if __name__ == "__main__":
    main()
