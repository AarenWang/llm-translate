"""
ChatGPT Plus 订阅 API 认证和使用示例

按照 liteLLM 文档：https://docs.litellm.ai/docs/providers/chatgpt
使用 OAuth 设备代码流程进行认证
"""

import litellm
import os

# 可选：设置自定义token存储目录（默认会在当前目录创建 .auth 文件夹）
# os.environ['CHATGPT_TOKEN_DIR'] = './my_auth_tokens'

def chatgpt_auth_example():
    """
    ChatGPT 订阅认证示例
    首次运行时会引导你完成OAuth设备代码认证流程
    """

    print("=" * 60)
    print("ChatGPT Plus 订阅 API 认证和使用")
    print("=" * 60)

    # 设置litellm日志级别（可选，用于调试）
    litellm.set_verbose = True

    try:
        # 方式1：使用 Responses API (推荐用于 Codex 模型)
        print("\n📝 方式1：使用 Responses API (Codex 模型)")
        print("-" * 40)

        response = litellm.responses(
            model="chatgpt/gpt-5.3-codex",
            input="用Python写一个Hello World程序"
        )

        print("✅ 响应成功！")
        print(f"响应内容：\n{response}")

    except Exception as e:
        print(f"❌ Responses API 调用失败: {e}")
        print("\n💡 提示：首次使用需要完成OAuth认证")
        print("   1. 运行程序后会显示设备代码和验证URL")
        print("   2. 打开URL，登录ChatGPT账号并输入代码")
        print("   3. 认证成功后token会保存在本地，后续可直接使用")

    try:
        # 方式2：使用 Chat Completions API (会桥接到 Responses)
        print("\n💬 方式2：使用 Chat Completions API (推荐用于聊天)")
        print("-" * 40)

        response = litellm.completion(
            model="chatgpt/gpt-5.4",
            messages=[
                {"role": "user", "content": "你好，请用一句话介绍Python"}
            ]
        )

        print("✅ 响应成功！")
        print(f"响应内容：\n{response}")

    except Exception as e:
        print(f"❌ Chat Completions API 调用失败: {e}")


def chatgpt_streaming_example():
    """
    流式响应示例
    """
    print("\n🌊 流式响应示例")
    print("-" * 40)

    try:
        response = litellm.completion(
            model="chatgpt/gpt-5.4",
            messages=[
                {"role": "user", "content": "请用3个要点介绍量子计算"}
            ],
            stream=True  # 启用流式响应
        )

        print("流式输出：")
        for chunk in response:
            if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content:
                    print(delta.content, end='', flush=True)
        print()  # 换行

    except Exception as e:
        print(f"❌ 流式响应失败: {e}")


def list_available_models():
    """
    列出可用的 ChatGPT 订阅模型
    """
    print("\n📋 可用的 ChatGPT 订阅模型：")
    print("-" * 40)

    models = [
        "chatgpt/gpt-5.4",           # GPT-5.4
        "chatgpt/gpt-5.4-pro",       # GPT-5.4 Pro
        "chatgpt/gpt-5.3-codex",     # GPT-5.3 Codex (代码生成)
        "chatgpt/gpt-5.3-codex-spark", # GPT-5.3 Codex Spark
        "chatgpt/gpt-5.3-instant",   # GPT-5.3 Instant (快速响应)
        "chatgpt/gpt-5.3-chat-latest" # GPT-5.3 Chat Latest
    ]

    for model in models:
        print(f"  • {model}")

def list_auth_way()：
    print("\n" + "=" * 60)
    print("📖 认证说明：")
    print("=" * 60)
    print("""
首次运行时，liteLLM 会启动 OAuth 设备代码流程：

1. 🖥️  程序会显示一个设备代码（如：ABCD-1234）和验证URL
2. 🌐  打开浏览器访问该URL
3. 🔑  使用你的 ChatGPT 账号登录
4. ✏️  输入显示的设备代码
5. ✅  确认授权
6. 💾  Token 会自动保存到本地 .auth 文件夹
7. 🎉  后续调用无需重新认证

注意事项：
• 需要 ChatGPT Pro/Max 订阅
• Token 会保存在本地，请妥善保管
• 如果认证失败，请检查订阅状态
• 不支持 max_tokens、max_output_tokens 等参数
""")

if __name__ == "__main__":
    # 列出可用模型
    list_available_models()
    # 列出认证方式
    #list_auth_way()

    # 认证和基本使用示例
    # chatgpt_auth_example()

    # 流式响应示例
    chatgpt_streaming_example()

    