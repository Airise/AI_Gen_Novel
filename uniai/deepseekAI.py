import os

from openai import OpenAI


def deepseekChatLLM(model_name="deepseek-chat", api_key=None):
    """
    model_name 取值
    - deepseek-chat
    """
    api_key = os.environ.get("DEEPSEEK_AI_API_KEY", api_key)
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    def chatLLM(
        messages: list,
        temperature=None,
        top_p=None,
        max_tokens=None,
        stream=False,
    ) -> dict:
        if not stream:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            )
            return {
                "content": response.choices[0].message.content,
                "total_tokens": response.usage.total_tokens,
            }
        else:
            responses = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                stream=True,
            )

            def respGenerator():
                content = ""
                total_tokens = None
                for response in responses:
                    delta = response.choices[0].delta.content or ""
                    content += delta

                    usage = getattr(response, "usage", None)
                    if usage and getattr(usage, "total_tokens", None) is not None:
                        total_tokens = usage.total_tokens

                    yield {
                        "content": content,
                        "total_tokens": total_tokens,
                    }

            return respGenerator()

    return chatLLM
