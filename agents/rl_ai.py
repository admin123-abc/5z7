# ============================================================
#  agents/rl_ai.py — 强化学习 AI 占位符
#  这是系统的"开放扩展点"。
#
#  未来接入路线（不需要修改其他任何文件）：
#  1. 训练：用 self-play 生成对局数据 → PPO/AlphaZero 等算法训练策略网络
#  2. 推理：将训练好的模型权重加载进来
#  3. 实现：重写 get_move，让网络输出落子概率分布，取 argmax
#
#  现阶段行为：随机在合法位置落子（保证接口正常）
# ============================================================

import random
from agents.base_player import BasePlayer


class RLPlayer(BasePlayer):
    """
    强化学习玩家（占位符实现）。

    当前版本：随机落子（纯合法随机策略）。
    未来版本：加载神经网络权重，通过前向推理决策。

    接口契约（永远不变）：
        get_move(board, piece) -> (row, col)
    """

    def __init__(
        self,
        name: str = "RL AI（占位）",
        model_path: str = None,   # 预留：神经网络权重路径
    ):
        super().__init__(name)
        self.model_path = model_path
        self._model = None

        if model_path:
            self._load_model(model_path)

    # ── 公开接口 ─────────────────────────────────────────────

    def get_move(self, board, piece: int) -> tuple[int, int]:
        """
        当前：随机选取一个合法落子位。
        未来：调用 self._model 进行前向推理。
        """
        if self._model is not None:
            return self._neural_move(board, piece)
        else:
            return self._random_move(board)

    # ── 内部实现 ─────────────────────────────────────────────

    def _random_move(self, board) -> tuple[int, int]:
        """随机策略（占位用）"""
        empty = board.get_empty_positions()
        if not empty:
            raise RuntimeError("棋盘已满，无法落子")
        return random.choice(empty)

    def _neural_move(self, board, piece: int) -> tuple[int, int]:
        """
        神经网络推理（待实现）。
        接入时：
            1. 将 board._grid 转为 tensor（形状 [2, size, size] 双通道 one-hot）
            2. 送入 self._model 做前向传播
            3. 对输出概率分布 mask 掉非法位，取 argmax
        """
        raise NotImplementedError(
            "神经网络推理尚未实现，请先训练模型并加载权重。"
        )

    def _load_model(self, path: str) -> None:
        """
        加载神经网络权重（待实现）。
        示例（PyTorch）：
            import torch
            self._model = PolicyNetwork()
            self._model.load_state_dict(torch.load(path))
            self._model.eval()
        """
        print(f"  [RLPlayer] 模型路径已指定：{path}，但加载逻辑尚未实现。")
        self._model = None   # 保持 None 以触发随机回退
