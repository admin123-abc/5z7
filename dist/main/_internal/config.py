# ============================================================
#  config.py — 全局参数总线
#  所有模块统一从此处读取配置，禁止硬编码魔法数字
# ============================================================

# ── 棋盘 ────────────────────────────────────────────────────
BOARD_SIZE: int = 30          # 标准五子棋棋盘 30×30
WIN_COUNT:  int = 5           # 连子数（五子棋）

# ── 棋子代号 ─────────────────────────────────────────────────
EMPTY: int = 0
BLACK: int = 1                # 先手
WHITE: int = 2

# ── AI 参数 ──────────────────────────────────────────────────
AI_SEARCH_DEPTH:   int = 3    # Minimax 默认搜索深度
AI_CANDIDATE_DIST: int = 2    # 只考虑距已有棋子此曼哈顿距离内的空位

# ── 棋子显示符号（CLI）─────────────────────────────────────────
PIECE_SYMBOLS: dict = {
    EMPTY: "·",
    BLACK: "●",
    WHITE: "○",
}

# ── 棋子名称 ─────────────────────────────────────────────────
PIECE_NAMES: dict = {
    BLACK: "黑子",
    WHITE: "白子",
}

# ============================================================
#  GUI 配置（仅 Pygame 视图使用）
# ============================================================

# ── 窗口 ────────────────────────────────────────────────────
GUI_WINDOW_TITLE: str  = "五子棋  Gobang"
GUI_WINDOW_W:     int  = 980          # 窗口总宽度（含侧边栏）
GUI_WINDOW_H:     int  = 800          # 窗口高度
GUI_FPS:          int  = 60           # 渲染帧率

# ── 棋盘布局 ─────────────────────────────────────────────────
GUI_BOARD_MARGIN: int  = 40           # 棋盘边距（像素），留给行列号
GUI_SIDE_PANEL_W: int  = 220          # 右侧信息面板宽度

# ── 配色方案（木纹暖色系）────────────────────────────────────
GUI_COLOR_BG           = (30,  25,  20)    # 窗口背景（深炭黑）
GUI_COLOR_BOARD_LIGHT  = (205, 160, 80)    # 棋盘浅木色
GUI_COLOR_BOARD_DARK   = (170, 115, 45)    # 棋盘深木色
GUI_COLOR_GRID_LINE    = (100,  65, 20)    # 格线颜色
GUI_COLOR_STAR_DOT     = (80,   45, 10)    # 星位实心点
GUI_COLOR_COORD        = (90,   55, 15)    # 坐标标注颜色
GUI_COLOR_PANEL_BG     = (22,   18, 14)    # 侧边栏背景
GUI_COLOR_PANEL_BORDER = (60,   45, 25)    # 侧边栏边框
GUI_COLOR_ACCENT       = (220, 160, 50)    # 强调色（金色）
GUI_COLOR_TEXT_MAIN    = (235, 220, 195)   # 主文字颜色
GUI_COLOR_TEXT_DIM     = (130, 110, 80)    # 次要文字颜色
GUI_COLOR_WIN_LINE     = (255, 215, 0)     # 胜利连线（金色）
GUI_COLOR_LAST_MOVE    = (255,  80, 80)    # 最后落子标记（红色）
GUI_COLOR_HOVER        = (255, 255, 255)   # 鼠标悬停预览色

# ── 棋子颜色 ─────────────────────────────────────────────────
# 黑子
GUI_BLACK_BASE         = (28,  28,  28)
GUI_BLACK_SHINE        = (90,  90,  90)
GUI_BLACK_SHADOW       = (8,    8,   8)
# 白子
GUI_WHITE_BASE         = (240, 240, 235)
GUI_WHITE_SHINE        = (255, 255, 255)
GUI_WHITE_SHADOW       = (170, 165, 150)

# ── 音效开关 ─────────────────────────────────────────────────
GUI_SOUND_ENABLED: bool = True

# ── 外部资源路径（src/ 目录）──────────────────────────────────
import os as _os
SRC_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "src")

# 棋子图片（JPG/PNG，会自动缩放到棋子大小并做圆形裁剪）
import os
from pathlib import Path

# 获取当前 config.py 所在的绝对路径
BASE_DIR = Path(__file__).resolve().parent

# ── 资源路径（强制转换为绝对路径） ───────────────────────────
# 这样无论你在哪执行程序，都会自动指向 5z7/src/ 目录
SRC_PLAYER_PIECE = str(BASE_DIR / "src" / "player.jpg")
SRC_AI_PIECE     = str(BASE_DIR / "src" / "ai.jpg")
SRC_PLAYER_SOUND = str(BASE_DIR / "src" / "player_do.wav")
SRC_AI_SOUND     = str(BASE_DIR / "src" / "ai_do.wav")
