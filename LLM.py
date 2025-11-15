from uniai import aliChatLLM, deepseekChatLLM, zhipuChatLLM

# Using default timeout of 300 seconds (5 minutes)
# You can increase this if needed: aliChatLLM("qwen-long", timeout=600) for 10 minutes
chatLLM = deepseekChatLLM("deepseek-chat")

if __name__ == "__main__":

    content = "请用一个成语介绍你自己"
    messages = [{"role": "user", "content": content}]

    resp = chatLLM(messages)
    print(resp)

    for resp in chatLLM(messages, stream=True):
        print(resp)
