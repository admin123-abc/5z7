"""
tts.py — 语音合成模块（Edge-TTS + pygame 播放）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
用微软 Neural TTS 把小五的台词用真人般的语音读出来。
在后台线程异步生成语音并播放，不阻塞游戏主循环。
"""

from __future__ import annotations

import os
import threading
import tempfile
import asyncio
from typing import Optional

import config as C


class TTSPlayer:
    """线程安全的 TTS 播放器。新文本来了自动打断旧的、播新的。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._current_text: str = ""
        self._enabled: bool = getattr(C, 'TTS_ENABLED', False)
        self._voice: str = getattr(C, 'TTS_VOICE', 'ja-JP-NanamiNeural')
        self._rate: str = getattr(C, 'TTS_RATE', '+10%')
        self._pitch: str = getattr(C, 'TTS_PITCH', '+5Hz')
        self._tmp_dir = tempfile.mkdtemp(prefix="5z7_tts_")

        # 检查 edge_tts 是否可用
        try:
            import edge_tts
            self._available = True
        except ImportError:
            self._available = False
            print("[TTS] edge-tts 未安装，语音功能已禁用")

    def speak(self, text: str) -> None:
        """异步播放文本语音。新调用会打断旧的播放。"""
        if not self._enabled or not self._available:
            return
        if not text or text == self._current_text:
            return

        # 过滤掉括号内的提示文字（如"（5/5）"）
        import re
        clean_text = re.sub(r'[（(][^）)]*[）)]', '', text).strip()
        if not clean_text:
            return

        with self._lock:
            self._current_text = text

        # 在后台线程中执行 TTS
        t = threading.Thread(target=self._worker, args=(clean_text,), daemon=True)
        self._thread = t
        t.start()

    def _worker(self, text: str):
        """后台线程：生成语音文件并用 pygame 播放。"""
        try:
            import edge_tts
            import pygame

            # 生成临时 MP3 文件
            tmp_path = os.path.join(self._tmp_dir, "tts_out.mp3")

            # 创建新的事件循环（因为在子线程里）
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    self._generate_audio(edge_tts, text, tmp_path)
                )
            finally:
                loop.close()

            if not os.path.isfile(tmp_path) or os.path.getsize(tmp_path) < 100:
                print("[TTS] 音频文件生成失败或太小")
                return

            # 用 pygame.mixer.music 播放（支持 MP3，可打断）
            try:
                pygame.mixer.music.load(tmp_path)
                pygame.mixer.music.play()
            except Exception as e:
                print(f"[TTS] pygame 播放失败：{e}")

        except Exception as e:
            print(f"[TTS] 语音生成失败：{e}")

    async def _generate_audio(self, edge_tts, text: str, output_path: str):
        """异步生成语音文件。"""
        communicate = edge_tts.Communicate(
            text,
            voice=self._voice,
            rate=self._rate,
            pitch=self._pitch,
        )
        await communicate.save(output_path)

    def stop(self):
        """停止当前播放。"""
        try:
            import pygame
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except Exception:
            pass

    def cleanup(self):
        """清理临时文件。"""
        self.stop()
        try:
            import shutil
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
        except Exception:
            pass
