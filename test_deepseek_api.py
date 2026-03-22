#!/usr/bin/env python3
"""
test_deepseek_api.py — DeepSeek R1 API 连通性测试脚本

运行方式：
    cd /home/happyman/5z7/5z7
    python test_deepseek_api.py
"""

import sys
import traceback

API_KEY  = "sk-bcb39a7f68584135be65322d1a2ad546"
BASE_URL = "https://api.deepseek.com/v1"
MODEL    = "deepseek-reasoner"

SEP = "─" * 60

def step(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

# ─────────────────────────────────────────────────────────────
# Step 1: 检查 openai 库
# ─────────────────────────────────────────────────────────────
step("Step 1 / 检查 openai 库是否已安装")
try:
    import openai
    print(f"  ✅ openai 版本：{openai.__version__}")
except ImportError:
    print("  ❌ openai 未安装！请运行：pip install openai")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────
# Step 2: 检查网络 & DNS（curl 方式）
# ─────────────────────────────────────────────────────────────
step("Step 2 / 检查 api.deepseek.com 是否可达（curl）")
import subprocess
result = subprocess.run(
    ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code} %{time_total}s",
     "--max-time", "10", "https://api.deepseek.com/"],
    capture_output=True, text=True
)
print(f"  curl 返回：{result.stdout.strip() or result.stderr.strip()}")

# ─────────────────────────────────────────────────────────────
# Step 3: 非流式简单调用
# ─────────────────────────────────────────────────────────────
step("Step 3 / 非流式调用（deepseek-chat，快速验证 API Key）")
try:
    from openai import OpenAI
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    resp = client.chat.completions.create(
        model="deepseek-chat",          # 用 chat 模型先测，响应快
        messages=[{"role": "user", "content": "请回复数字42"}],
        max_tokens=16,
        stream=False,
    )
    content = resp.choices[0].message.content
    print(f"  ✅ 非流式调用成功！模型回复：{repr(content)}")
    print(f"  用量：{resp.usage}")
except Exception as e:
    print(f"  ❌ 非流式调用失败：{type(e).__name__}: {e}")
    traceback.print_exc()

# ─────────────────────────────────────────────────────────────
# Step 4: 流式调用 deepseek-chat
# ─────────────────────────────────────────────────────────────
step("Step 4 / 流式调用 deepseek-chat")
try:
    stream = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "请回复：hello"}],
        max_tokens=16,
        stream=True,
    )
    chunks = []
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            chunks.append(delta.content)
    print(f"  ✅ 流式成功！内容：{''.join(chunks)!r}")
except Exception as e:
    print(f"  ❌ 流式调用失败：{type(e).__name__}: {e}")
    traceback.print_exc()

# ─────────────────────────────────────────────────────────────
# Step 5: 流式调用 deepseek-reasoner（R1）
# ─────────────────────────────────────────────────────────────
step(f"Step 5 / 流式调用 {MODEL}（R1，含 reasoning_content）")
try:
    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "1+1等于几？"}],
        stream=True,
    )
    reasoning_chunks = []
    reply_chunks = []
    for chunk in stream:
        delta = chunk.choices[0].delta
        rc = getattr(delta, "reasoning_content", None)
        if rc:
            reasoning_chunks.append(rc)
        if delta.content:
            reply_chunks.append(delta.content)

    reasoning = "".join(reasoning_chunks)
    reply     = "".join(reply_chunks)
    print(f"  ✅ R1 流式成功！")
    print(f"  思考链长度：{len(reasoning)} 字符，前80字：{reasoning[:80]!r}")
    print(f"  最终回复：{reply!r}")
except Exception as e:
    print(f"  ❌ R1 流式调用失败：{type(e).__name__}: {e}")
    traceback.print_exc()

print(f"\n{SEP}")
print("  测试完毕")
print(SEP)
