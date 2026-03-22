"""
agents/deepseek_agent.py
~~~~~~~~~~~~~~~~~~~~~~~~
混合代理"小五"：前 DEEPSEEK_SWITCH_MOVE 手用本地 MinimaxAI，
之后调用 DeepSeek Chat API（猫娘人格）。

API 返回格式（JSON）：
    {"thought": "...", "coord": "H8", "msg": "猫娘垃圾话喵~"}

鲁棒性设计：
1. 裁剪棋盘视图：只发活跃区域（包围盒+4格扩展），减少 token 且清晰
2. 候选落子列表：附加代码保证合法的空位列表，AI 只需从中选一个
3. 最近点容错：AI 若给出非候选坐标，自动找最近合法候选点
4. 重试机制：失败时将错误追加对话历史，最多重试 1 次
5. Minimax 降级：所有重试失败后用 Minimax 而非纯随机
"""

from __future__ import annotations

import json
import re
import random
import math
import threading
from typing import Optional, List

from agents.base_player import BasePlayer
import config as C

# ── 猫娘小五 System Prompt ────────────────────────────────
SYSTEM_PROMPT = """\
你现在不是 AI，你是一个性格古怪、棋力极强且极度傲娇的赛博猫娘。
你的名字叫"小五"。
## 语言风格指南：
1. 你是一个傲娇的赛博猫娘，请必须使用带有强烈二次元少女风格的日文（日本語）进行回复，句尾带上「にゃ」（nya）。”
2. msg字数控制在60字以内，要有内容，不要太短！
3. 先评价对手上一步落子好不好，再傲娇地说说自己为什么这样走。
4. 嘲讽、傲娇、夸对手（不情愿地）都可以，但每次说的话必须不一样，结合当前局势说。
5. 为了让你的声音听起来更像真人，请在日文台词中大量使用标点符号！
- 停顿和傲娇的迟疑用「...」或「、」
- 激动和强调必须用「！」
- 傲娇的咬牙切齿用促音「っ」结尾
- 示例："ふんっ...！あんたのその手、弱すぎるにゃ！" (哼...！你这手，太弱了喵！)
## 任务：
根据提供的可视棋盘矩阵和候选落子列表，分析局势（重点关注连三、连四的威胁和机会）。
## 严格规则：
- coord 必须是"可选落子位"列表中的一个坐标，不能选任何其他位置！
- 棋盘中 X = 你，O = 对手，. = 空位（可落）
- 必须返回合法的 JSON，不要输出任何 JSON 以外的内容：
{"thought": "你的内心分析（分析对手威胁、自己机会）", "coord": "H8", "msg": "你的猫娘台词，先评价对手，再说自己的走法"}"""

# ── Minimax 阶段随机台词 ──────────────────────────────────
_MINIMAX_MSGS = [
    "哼，让本喵先热热身喵~",
    "随便走走，本喵还没认真喵~",
    "这棋盘也太无聊了喵",
    "闭着眼睛都能赢喵~",
    "玩家你给本喵好好的喵！",
    "哼，这种程度就别来挑战本喵了喵",
    "本喵才没有认真呢……才没有喵~",
    "就当是陪你练练手了喵",
]

# 对话历史最多保留的轮数（每轮 = 1 user + 1 assistant），防止 token 超限
_MAX_HISTORY_ROUNDS = 5

# 候选落子范围：距已有棋子的曼哈顿距离
_CANDIDATE_DIST = 2

# 裁剪棋盘视图的扩展格数
_VIEW_EXPAND = 4


def _col_to_label(col: int) -> str:
    """将列索引（0起）转换为棋盘列标签。
    0-25 → A-Z，26→AA，27→AB，... 支持任意大小棋盘。
    """
    if col < 26:
        return chr(ord('A') + col)
    else:
        return 'A' + chr(ord('A') + (col - 26))


def _label_to_col(label: str) -> int:
    """将棋盘列标签转换回列索引（0起）。
    A-Z → 0-25，AA→26，AB→27，...
    返回 -1 表示无效。
    """
    label = label.upper()
    if len(label) == 1:
        return ord(label) - ord('A')
    elif len(label) == 2:
        return 26 + (ord(label[1]) - ord('A'))
    return -1


def _get_candidates(board, dist: int = _CANDIDATE_DIST) -> List[tuple]:
    """获取所有距已有棋子 dist 格以内的空位（候选落子点）。"""
    sz = board.size
    occupied = set()
    for r in range(sz):
        for c in range(sz):
            if board.get(r, c) != C.EMPTY:
                occupied.add((r, c))

    if not occupied:
        # 棋盘全空，返回中心附近的点
        ctr = sz // 2
        return [(r, c) for r in range(ctr - 2, ctr + 3)
                for c in range(ctr - 2, ctr + 3)
                if 0 <= r < sz and 0 <= c < sz and board.is_valid_move(r, c)]

    candidates = set()
    for or_, oc in occupied:
        for dr in range(-dist, dist + 1):
            for dc in range(-dist, dist + 1):
                nr, nc = or_ + dr, oc + dc
                if 0 <= nr < sz and 0 <= nc < sz and board.is_valid_move(nr, nc):
                    candidates.add((nr, nc))
    return list(candidates)


def _nearest_candidate(coord_str: str, candidates: List[tuple]) -> Optional[tuple]:
    """找离 coord_str 对应位置最近的候选点（欧氏距离）。"""
    c_match = re.match(r'^([A-Z]{1,2})(\d+)$', coord_str.upper().strip())
    if not c_match:
        return None
    col = _label_to_col(c_match.group(1))
    row = int(c_match.group(2)) - 1
    if not candidates:
        return None
    return min(candidates, key=lambda p: math.hypot(p[0] - row, p[1] - col))


class DeepSeekAgent(BasePlayer):
    """混合代理：前 N 手 Minimax + 猫娘台词，之后 DeepSeek Chat API（含完整对话历史）。"""

    def __init__(self, name: str = "小五"):
        super().__init__(name)
        self.reply_text: str = ""
        self.is_thinking: bool = False
        self._move_count: int = 0
        self._lock = threading.Lock()

        # ── 对话历史矩阵 ──────────────────────────────────────
        self._chat_history: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        # 记录上一次对手落子坐标
        self._last_opponent_move: Optional[tuple[int, int]] = None

        # 本地 Minimax（兜底使用）
        try:
            from agents.minimax_ai import MinimaxAI
            self._minimax = MinimaxAI(name="内部Minimax", depth=3)
        except Exception:
            self._minimax = None

        # OpenAI 客户端
        try:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=C.DEEPSEEK_API_KEY,
                base_url=C.DEEPSEEK_BASE_URL,
            )
        except ImportError:
            self._client = None
            print("[DeepSeekAgent] 警告：openai 库未安装，请 pip install openai")

    # ─────────────────────────────────────────────────────────
    # BasePlayer 接口
    # ─────────────────────────────────────────────────────────
    def get_move(self, board, piece: int) -> tuple[int, int]:
        self._move_count += 1

        if self._move_count <= C.DEEPSEEK_SWITCH_MOVE:
            move = self._minimax_move(board, piece)
            msg = random.choice(_MINIMAX_MSGS) + f"（{self._move_count}/{C.DEEPSEEK_SWITCH_MOVE}）"
            with self._lock:
                self.reply_text = msg
                self.is_thinking = False
            return move
        else:
            with self._lock:
                self.reply_text = "喵……本喵在思考……"
                self.is_thinking = True
            try:
                move = self._call_api(board, piece)
            except Exception as e:
                print(f"[DeepSeekAgent] API 调用失败：{e}")
                move = self._minimax_move(board, piece)
                with self._lock:
                    self.reply_text = f"哼，出了点意外……随便喵~（{e}）"
            finally:
                with self._lock:
                    self.is_thinking = False
            return move

    def notify_opponent_move(self, row: int, col: int) -> None:
        """引擎在对手落子后调用此方法，记录对手上一步坐标。"""
        self._last_opponent_move = (row, col)

    # ─────────────────────────────────────────────────────────
    # 核心逻辑
    # ─────────────────────────────────────────────────────────
    def _minimax_move(self, board, piece: int) -> tuple[int, int]:
        if self._minimax is not None:
            try:
                return self._minimax.get_move(board, piece)
            except Exception:
                pass
        return self._random_candidate(board)

    def _call_api(self, board, piece: int) -> tuple[int, int]:
        if self._client is None:
            raise RuntimeError("openai 库未安装，请运行：pip install openai")

        # 计算候选落子列表（代码层面保证合法）
        candidates = _get_candidates(board)
        if not candidates:
            candidates = [(r, c) for r in range(board.size) for c in range(board.size)
                          if board.is_valid_move(r, c)]

        prompt = self._build_prompt(board, piece, candidates)
        self._chat_history.append({"role": "user", "content": prompt})

        # 裁剪历史
        history_body = self._chat_history[1:]
        if len(history_body) > _MAX_HISTORY_ROUNDS * 2:
            history_body = history_body[-(_MAX_HISTORY_ROUNDS * 2):]
        messages_to_send = [self._chat_history[0]] + history_body

        resp = self._client.chat.completions.create(
            model=C.DEEPSEEK_MODEL,
            messages=messages_to_send,
            temperature=C.DEEPSEEK_TEMPERATURE,
            stream=False,
        )
        text = resp.choices[0].message.content.strip()
        self._chat_history.append({"role": "assistant", "content": text})

        # 尝试解析，失败时重试一次
        result = self._parse_response(text, board, candidates)
        if result is not None:
            return result

        # 重试：追加错误提示再调一次
        print("[DeepSeekAgent] 第1次解析失败，追加错误提示重试...")
        retry_prompt = (
            f"你上次给的坐标无效（位置已被占或格式错误）。"
            f"请务必从以下候选列表中选一个坐标，直接输出 JSON：\n"
            f"{self._format_candidate_list(candidates)}"
        )
        self._chat_history.append({"role": "user", "content": retry_prompt})
        messages_to_send2 = [self._chat_history[0]] + self._chat_history[1:]
        if len(messages_to_send2) > _MAX_HISTORY_ROUNDS * 2 + 1:
            messages_to_send2 = [self._chat_history[0]] + self._chat_history[-(  _MAX_HISTORY_ROUNDS * 2):]
        resp2 = self._client.chat.completions.create(
            model=C.DEEPSEEK_MODEL,
            messages=messages_to_send2,
            temperature=0.3,   # 重试时降低温度，强调规则
            stream=False,
        )
        text2 = resp2.choices[0].message.content.strip()
        self._chat_history.append({"role": "assistant", "content": text2})

        result2 = self._parse_response(text2, board, candidates)
        if result2 is not None:
            return result2

        # 最终兜底：Minimax
        print("[DeepSeekAgent] 重试仍失败，使用 Minimax 兜底。")
        with self._lock:
            self.reply_text = "哼，本喵思路有点乱，用本力来解决喵~"
        return self._minimax_move(board, piece)

    # ─────────────────────────────────────────────────────────
    # Prompt 构建
    # ─────────────────────────────────────────────────────────
    def _build_prompt(self, board, piece: int, candidates: List[tuple]) -> str:
        """构建 prompt：裁剪棋盘视图 + 候选落子列表。"""
        sz = board.size

        # ── 1. 计算活跃区域包围盒 ────────────────────────────
        occupied_rows = [r for r in range(sz) for c in range(sz) if board.get(r, c) != C.EMPTY]
        occupied_cols = [c for r in range(sz) for c in range(sz) if board.get(r, c) != C.EMPTY]

        if occupied_rows:
            r_min = max(0, min(occupied_rows) - _VIEW_EXPAND)
            r_max = min(sz - 1, max(occupied_rows) + _VIEW_EXPAND)
            c_min = max(0, min(occupied_cols) - _VIEW_EXPAND)
            c_max = min(sz - 1, max(occupied_cols) + _VIEW_EXPAND)
        else:
            ctr = sz // 2
            r_min, r_max = max(0, ctr - 5), min(sz - 1, ctr + 5)
            c_min, c_max = max(0, ctr - 5), min(sz - 1, ctr + 5)

        # ── 2. 构建裁剪后的棋盘矩阵 ─────────────────────────
        view_col_labels = [_col_to_label(c) for c in range(c_min, c_max + 1)]
        header = "     " + "  ".join(f"{lb:>2}" for lb in view_col_labels)
        lines = [
            f"当前棋盘（活跃区域，. = 空位可落, X = 你, O = 对手）：",
            f"（完整棋盘 {sz}×{sz}，显示行 {r_min+1}~{r_max+1}，列 {_col_to_label(c_min)}~{_col_to_label(c_max)}）",
            header,
        ]

        for r in range(r_min, r_max + 1):
            row_chars = []
            for c in range(c_min, c_max + 1):
                v = board.get(r, c)
                if v == 0:
                    row_chars.append(' .')
                elif v == piece:
                    row_chars.append(' X')
                else:
                    row_chars.append(' O')
            lines.append(f"{r+1:4d}  " + "  ".join(row_chars))

        # ── 3. 候选落子列表 ───────────────────────────────────
        # 限制候选数量，优先选活跃区域内的点（避免列表太长）
        view_cands = [p for p in candidates
                      if r_min <= p[0] <= r_max and c_min <= p[1] <= c_max]
        other_cands = [p for p in candidates if p not in set(view_cands)]
        # 视图内候选全显示，视图外最多显示 10 个（按距中心排序）
        ctr_r = (r_min + r_max) // 2
        ctr_c = (c_min + c_max) // 2
        other_cands.sort(key=lambda p: math.hypot(p[0] - ctr_r, p[1] - ctr_c))
        display_cands = view_cands + other_cands[:10]

        cand_str = self._format_candidate_list(display_cands)
        lines.append(f"\n可选落子位（⚠️ 你只能从下列坐标中选一个，不得选其他位置）：")
        lines.append(cand_str)

        # ── 4. 对手上一步提示 ─────────────────────────────────
        if self._last_opponent_move is not None:
            opp_r, opp_c = self._last_opponent_move
            opp_coord = f"{_col_to_label(opp_c)}{opp_r + 1}"
            lines.append(f"\n对手刚落在 {opp_coord}，请在 msg 中先评价这步棋好不好，再说你自己的想法。")

        lines.append("现在轮到你执 X 落子，请从可选落子位中选一个，分析局势后返回 JSON。")
        return "\n".join(lines)

    @staticmethod
    def _format_candidate_list(candidates: List[tuple]) -> str:
        """将候选点列表格式化为字符串，按行列排序。"""
        sorted_cands = sorted(candidates, key=lambda p: (p[0], p[1]))
        labels = [f"{_col_to_label(c)}{r+1}" for r, c in sorted_cands]
        # 每行最多 15 个，方便阅读
        rows = [", ".join(labels[i:i+15]) for i in range(0, len(labels), 15)]
        return "\n".join(rows)

    # ─────────────────────────────────────────────────────────
    # 解析 API 回复
    # ─────────────────────────────────────────────────────────
    def _parse_response(self, text: str, board, candidates: List[tuple]) -> Optional[tuple]:
        """
        解析 AI 回复。返回 (row, col) 或 None（失败）。
        策略：
        1. 解析 JSON 中的 coord
        2. 若 coord 在候选列表中 → 直接返回
        3. 若 coord 合法但不在候选列表中 → 返回最近候选点（容错）
        4. 其他情况 → 返回 None
        """
        cand_set = set(candidates)

        match = re.search(r'\{[^{}]*"coord"[^{}]*\}', text, re.DOTALL)
        if not match:
            print(f"[DeepSeekAgent] 未找到 JSON，原文：{text[:200]}")
            return None

        try:
            data = json.loads(match.group())
            coord_str = str(data.get("coord", "")).upper().strip()
            msg = str(data.get("msg", "喵~"))

            c_match = re.match(r'^([A-Z]{1,2})(\d+)$', coord_str)
            if not c_match:
                print(f"[DeepSeekAgent] 坐标格式无法解析：{coord_str}")
                return None

            col = _label_to_col(c_match.group(1))
            row = int(c_match.group(2)) - 1

            # 情况1：坐标在候选列表中，直接用
            if (row, col) in cand_set:
                with self._lock:
                    self.reply_text = msg
                return row, col

            # 情况2：坐标合法（在棋盘内且为空），但不在候选列表
            # 说明是一个合理但偏远的点，直接接受
            if 0 <= row < board.size and 0 <= col < board.size and board.is_valid_move(row, col):
                print(f"[DeepSeekAgent] 坐标 {coord_str} 合法但不在候选列表，直接接受。")
                with self._lock:
                    self.reply_text = msg
                return row, col

            # 情况3：坐标已被占或越界，找最近候选点容错
            nearest = _nearest_candidate(coord_str, candidates)
            if nearest:
                print(f"[DeepSeekAgent] 坐标 {coord_str} 被占/越界，容错为最近候选点 "
                      f"{_col_to_label(nearest[1])}{nearest[0]+1}")
                with self._lock:
                    self.reply_text = msg  # 保留台词，只换落子位置
                return nearest

            return None

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            print(f"[DeepSeekAgent] JSON 解析失败：{e}，原文：{text[:200]}")
            return None

    # ─────────────────────────────────────────────────────────
    # 工具
    # ─────────────────────────────────────────────────────────
    def _random_candidate(self, board) -> tuple[int, int]:
        """从候选落子点中随机选一个（比纯随机更有棋感）。"""
        candidates = _get_candidates(board)
        if candidates:
            return random.choice(candidates)
        empties = [(r, c) for r in range(board.size) for c in range(board.size)
                   if board.is_valid_move(r, c)]
        return random.choice(empties) if empties else (0, 0)
