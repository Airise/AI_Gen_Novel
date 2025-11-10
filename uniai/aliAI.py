import os

from openai import OpenAI


BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def aliChatLLM(model_name, api_key=None, timeout=300):
    """
    model_name 取值
    - qwen1.5-7b-chat
    - qwen1.5-14b-chat
    - qwen1.5-72b-chat
    - qwen-turbo
    - qwen-max
    - qwen-long

    timeout: Request timeout in seconds (default: 300 = 5 minutes)
    """
    api_key = os.environ.get("ALI_AI_API_KEY", api_key)

    # Validate API key
    if not api_key:
        raise ValueError(
            "ALI_AI_API_KEY environment variable is not set. "
            "Please set it using: export ALI_AI_API_KEY='your-api-key'"
        )

    client = OpenAI(api_key=api_key, base_url=BASE_URL, timeout=timeout)

    def chatLLM(
        messages: list,
        temperature=0.85,
        top_p=0.8,
        stream=False,
        max_tokens=None,
    ) -> dict:
        common_args = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }

        if not stream:
            try:
                response = client.chat.completions.create(**common_args)
                if response and response.choices:
                    return {
                        "content": response.choices[0].message.content,
                        "total_tokens": response.usage.total_tokens
                        if response.usage
                        else None,
                    }
                raise ValueError("Empty response from DashScope compatible API.")
            except Exception as e:
                error_msg = str(e)
                if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                    raise TimeoutError(
                        f"Request timed out after {timeout} seconds. "
                        f"This might be due to: 1) The model is generating a very long response, "
                        f"2) Network connectivity issues, 3) API service is slow. "
                        f"Consider using streaming mode (stream=True) for long responses, "
                        f"or increase the timeout value."
                    ) from e
                raise ConnectionError(
                    f"Connection error: {error_msg}. "
                    f"This might be due to: 1) Missing/invalid API key, "
                    f"2) Network connectivity issues, 3) API service unavailable. "
                    f"Please check your ALI_AI_API_KEY and network connection."
                ) from e
        else:
            try:
                responses = client.chat.completions.create(stream=True, **common_args)
            except Exception as e:
                error_msg = str(e)
                if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                    raise TimeoutError(
                        f"Request timed out after {timeout} seconds during streaming setup. "
                        f"This might be due to: 1) Network connectivity issues, "
                        f"2) API service is slow. Please check your network connection."
                    ) from e
                raise ConnectionError(
                    f"Connection error during streaming setup: {error_msg}. "
                    f"This might be due to: 1) Missing/invalid API key, "
                    f"2) Network connectivity issues, 3) API service unavailable. "
                    f"Please check your ALI_AI_API_KEY and network connection."
                ) from e

            def respGenerator():
                content = ""
                try:
                    for response in responses:
                        if not response or not response.choices:
                            continue
                        delta = response.choices[0].delta.content or ""
                        content += delta
                        total_tokens = (
                            response.usage.total_tokens
                            if getattr(response, "usage", None)
                            else None
                        )
                        yield {
                            "content": content,
                            "total_tokens": total_tokens,
                        }
                except Exception as e:
                    error_msg = str(e)
                    if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                        raise TimeoutError(
                            f"Request timed out during streaming after {timeout} seconds. "
                            f"This might be due to: 1) Network connectivity issues, "
                            f"2) API service is slow. Please check your network connection."
                        ) from e
                    raise ConnectionError(
                        f"Connection error during streaming: {error_msg}. "
                        f"This might be due to: 1) Missing/invalid API key, "
                        f"2) Network connectivity issues, 3) API service unavailable. "
                        f"Please check your ALI_AI_API_KEY and network connection."
                    ) from e

            return respGenerator()

    return chatLLM
