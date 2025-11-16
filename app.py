import random
import threading
import time

import gradio as gr

from AIGN import AIGN, StoryEnded
from LLM import chatLLM

STREAM_INTERVAL = 0.

UI_STRINGS = {
    "zh": {
        "title": "## 小说创作工作台",
        "tab_start": "开始",
        "tab_outline": "大纲",
        "tab_status": "状态",
        "idea_label": "想法",
        "idea_placeholder": "简要描述你的小说灵感，例如世界观、人物或冲突。",
        "requirements_label": "写作要求",
        "requirements_placeholder": "指定视角、语气、风格等特殊需求（可选）。",
        "embellishment_label": "润色提示",
        "embellishment_placeholder": "告诉润色助手需要加强的氛围或细节（可选）。",
        "create_outline": "创建大纲",
        "polish_beginning": "打磨开篇",
        "next_paragraph": "续写下一段",
        "reset": "重置流程",
        "language_toggle": "切换到英文",
        "outline_label": "故事大纲",
        "memory_label": "剧情记忆",
        "plan_label": "写作蓝图",
        "temp_label": "即时设定",
        "chat_label": "创作对话",
        "novel_label": "当前正文",
        "story_ended_message": "🎉 恭喜！故事已经完成，所有章节都已写完。",
    },
    "en": {
        "title": "## Novel Writing Studio",
        "tab_start": "Start",
        "tab_outline": "Outline",
        "tab_status": "Status",
        "idea_label": "Idea",
        "idea_placeholder": "Describe the spark of your story (world, protagonist, conflict).",
        "requirements_label": "Writing Requests",
        "requirements_placeholder": "Share tone, POV, pacing, or other preferences (optional).",
        "embellishment_label": "Polish Notes",
        "embellishment_placeholder": "Tell the stylist what mood or detail to heighten (optional).",
        "create_outline": "Create Outline",
        "polish_beginning": "Polish Opening",
        "next_paragraph": "Write Next Segment",
        "reset": "Reset Workflow",
        "language_toggle": "Switch to Chinese",
        "outline_label": "Story Outline",
        "memory_label": "Story Memory",
        "plan_label": "Writing Plan",
        "temp_label": "Temporary Setting",
        "chat_label": "Creative Dialogue",
        "novel_label": "Current Manuscript",
        "story_ended_message": "🎉 Congratulations! The story is complete. All chapters have been written.",
    },
}

def make_middle_chat():
    carrier = threading.Event()
    carrier.history = []

    # 在 make_middle_chat 函数中
    def middle_chat(messages, temperature=None, top_p=None):
        nonlocal carrier
        carrier.history.append([None, ""])
        if len(carrier.history) > 20:
            carrier.history = carrier.history[-16:]
        try:
            total_tokens = None
            for resp in chatLLM(
                messages, temperature=temperature, top_p=top_p, stream=True
            ):
                output_text = resp["content"]
                # 流式生成时只显示内容
                carrier.history[-1][1] = output_text
                # 更新token值（如果有的话）
                if resp["total_tokens"] is not None:
                    total_tokens = resp["total_tokens"]
            
            # 生成完成后，如果有token信息，再添加到内容后面
            if total_tokens is not None:
                carrier.history[-1][1] = f"{output_text}\n\n---\n*total_tokens: {total_tokens}*"
            
            return {
                "content": output_text,
                "total_tokens": total_tokens,
            }
        except Exception as e:
            carrier.history[-1][1] = f"Error: {e}"
        raise e

    return carrier, middle_chat


def on_generate_outline_clicked(aign, user_idea, history):
    if getattr(aign, "language", None) is None:
        aign._apply_language("zh")
    aign._reset_story_state()
    aign.user_idea = user_idea

    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.novel_outline_writer.chat_llm = middle_chat

    gen_outline_thread = threading.Thread(target=aign.generate_outline)
    gen_outline_thread.start()

    while gen_outline_thread.is_alive():
        yield [
            aign,  # state
            carrier.history,  # chatbot
            aign.novel_outline,  # textbox
            gr.Button(visible=False),  # button - 这个应该是第4个值
        ]
        time.sleep(STREAM_INTERVAL)
    yield [
        aign,
        carrier.history,
        aign.novel_outline,
        gr.Button(visible=False),
    ]


def on_generate_beginning_clicked(
    aign, history, novel_outline, user_requirements, embellishment_idea
):
    aign.novel_outline = novel_outline
    aign.user_requirements = user_requirements
    aign.embellishment_idea = embellishment_idea

    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.novel_beginning_writer.chat_llm = middle_chat
    aign.novel_embellisher.chat_llm = middle_chat

    gen_beginning_thread = threading.Thread(target=aign.generate_beginning)
    gen_beginning_thread.start()

    while gen_beginning_thread.is_alive():
        yield [
            aign,  # state
            carrier.history,  # chatbot
            aign.writing_plan,  # textbox
            aign.temporary_setting,  # textbox
            aign.novel_content,  # textbox
            gr.Button(visible=False),  # button - 这个应该是第6个值
        ]
        time.sleep(STREAM_INTERVAL)
    yield [
        aign,
        carrier.history,
        aign.writing_plan,
        aign.temporary_setting,
        aign.novel_content,
        gr.Button(visible=False),
    ]

def on_generate_next_paragraph_clicked(
    aign,
    history,
    user_idea,
    novel_outline,
    writing_memory,
    temporary_setting,
    writing_plan,
    user_requirements,
    embellishment_idea,
):
    if getattr(aign, "language", None) is None:
        aign._apply_language("zh")
    aign.user_idea = user_idea
    aign.novel_outline = novel_outline
    aign.writing_memory = writing_memory
    aign.temporary_setting = temporary_setting
    aign.writing_plan = writing_plan
    aign.user_requirements = user_requirements
    aign.embellishment_idea = embellishment_idea

    # 获取当前语言设置
    current_language = getattr(aign, "language", "zh")
    ui = UI_STRINGS[current_language]

    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.novel_writer.chat_llm = middle_chat
    aign.novel_embellisher.chat_llm = middle_chat
    aign.memory_maker.chat_llm = middle_chat

    # 用于存储异常信息
    exception_occurred = [None]

    def generate_with_exception_handling():
        try:
            aign.generate_next_paragraph()
        except StoryEnded as e:
            exception_occurred[0] = e
        except Exception as e:
            exception_occurred[0] = e

    gen_next_paragraph_thread = threading.Thread(
        target=generate_with_exception_handling
    )
    gen_next_paragraph_thread.start()

    while gen_next_paragraph_thread.is_alive():
        yield [
            aign,  # state
            carrier.history,  # chatbot
            aign.writing_plan,  # textbox
            aign.temporary_setting,  # textbox
            aign.writing_memory,  # textbox
            aign.novel_content,  # textbox
            # 移除 gr.Button(visible=False) - 这是第7个值，造成不匹配
        ]
        time.sleep(STREAM_INTERVAL)
    
    # 检查是否有异常发生
    if exception_occurred[0] is not None:
        if isinstance(exception_occurred[0], StoryEnded):
            # 故事已结束，在聊天框中显示提示信息
            updated_history = list(carrier.history)
            updated_history.append([None, ui["story_ended_message"]])
            yield [
                aign,
                updated_history,
                aign.writing_plan,
                aign.temporary_setting,
                aign.writing_memory,
                aign.novel_content,
            ]
            return
        else:
            # 其他异常，显示错误信息
            updated_history = list(carrier.history)
            updated_history.append([None, f"错误: {str(exception_occurred[0])}"])
            yield [
                aign,
                updated_history,
                aign.writing_plan,
                aign.temporary_setting,
                aign.writing_memory,
                aign.novel_content,
            ]
            return
    
    # 最终返回也要匹配
    yield [
        aign,
        carrier.history,
        aign.writing_plan,
        aign.temporary_setting,
        aign.writing_memory,
        aign.novel_content,
    ]

def reset_workflow(current_aign, language):
    ui = UI_STRINGS[language]
    if current_aign is not None and hasattr(current_aign, "request_abort"):
        current_aign.request_abort()
    refreshed_aign = AIGN(chatLLM, language=language)
    return (
        refreshed_aign,
        gr.update(value=""),
        gr.update(value=""),
        gr.update(value=""),
        gr.update(value=[]),
        gr.update(value=""),
        gr.update(value=""),
        gr.update(value=""),
        gr.update(value=""),
        gr.update(value=""),
        gr.update(
            value=ui["create_outline"], visible=True, interactive=True
        ),
        gr.update(
            value=ui["polish_beginning"], visible=True, interactive=True
        ),
    )


def toggle_language(current_aign, current_language):
    if current_aign is not None and hasattr(current_aign, "request_abort"):
        current_aign.request_abort()
    new_language = "en" if current_language == "zh" else "zh"
    ui = UI_STRINGS[new_language]
    refreshed_aign = AIGN(chatLLM, language=new_language)
    return (
        refreshed_aign,
        new_language,
        gr.update(value=ui["title"]),
        gr.update(
            value="",
            label=ui["idea_label"],
            placeholder=ui["idea_placeholder"],
        ),
        gr.update(
            value="",
            label=ui["requirements_label"],
            placeholder=ui["requirements_placeholder"],
        ),
        gr.update(
            value="",
            label=ui["embellishment_label"],
            placeholder=ui["embellishment_placeholder"],
        ),
        gr.update(value=[], label=ui["chat_label"]),
        gr.update(value="", label=ui["outline_label"]),
        gr.update(value="", label=ui["memory_label"]),
        gr.update(value="", label=ui["plan_label"]),
        gr.update(value="", label=ui["temp_label"]),
        gr.update(value="", label=ui["novel_label"]),
        gr.update(
            value=ui["create_outline"], visible=True, interactive=True
        ),
        gr.update(
            value=ui["polish_beginning"], visible=True, interactive=True
        ),
        gr.update(value=ui["next_paragraph"], visible=True, interactive=True),
        gr.update(value=ui["reset"], visible=True, interactive=True),
        gr.update(value=ui["language_toggle"], visible=True, interactive=True),
        gr.update(label=ui["tab_start"]),
        gr.update(label=ui["tab_outline"]),
        gr.update(label=ui["tab_status"]),
    )


css = """
/* ========== 全局样式 ========== */
body {
    background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
    color: #2d3748;
    min-height: 100vh;
}

.gradio-container {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
    max-width: 100%;
    padding: 24px;
    background: transparent;
}

/* ========== 主布局 ========== */
.main-layout {
    gap: 20px;
    margin-top: 20px;
}

/* ========== 左侧功能区 - 创作对话 ========== */
#row2 {
    flex: 1;
    min-width: 0;
    max-height: 88vh;
    overflow: auto;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 28px;
    margin-right: 20px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 3px rgba(0, 0, 0, 0.04);
    transition: box-shadow 0.3s ease;
}

#row2:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08), 0 2px 6px rgba(0, 0, 0, 0.06);
}

.chatbot-wrapper {
    height: 100%;
    display: flex;
    flex-direction: column;
}

/* 聊天消息气泡样式 */
.chatbot-wrapper .chatbot {
    padding-bottom: 20px;
    flex: 1;
    overflow-y: auto;
}

/* 聊天消息容器 */
.chatbot-wrapper .chatbot > div {
    margin: 8px 0;
}

/* 用户消息 - 通过消息结构判断 */
.chatbot-wrapper .chatbot > div > div:first-child,
.chatbot-wrapper .chatbot [class*="user"],
.chatbot-wrapper .chatbot [class*="User"] {
    background: linear-gradient(135deg, #e6f7ff 0%, #d4edff 100%) !important;
    border-radius: 12px 12px 4px 12px !important;
    padding: 14px 18px !important;
    margin: 10px 0 !important;
    box-shadow: 0 2px 8px rgba(66, 153, 225, 0.15) !important;
    border-left: 3px solid #4299e1 !important;
    transition: all 0.2s ease !important;
}

.chatbot-wrapper .chatbot > div > div:first-child:hover,
.chatbot-wrapper .chatbot [class*="user"]:hover,
.chatbot-wrapper .chatbot [class*="User"]:hover {
    box-shadow: 0 4px 12px rgba(66, 153, 225, 0.2) !important;
    transform: translateX(-2px);
}

/* AI消息 */
.chatbot-wrapper .chatbot > div > div:not(:first-child),
.chatbot-wrapper .chatbot [class*="assistant"],
.chatbot-wrapper .chatbot [class*="Assistant"],
.chatbot-wrapper .chatbot [class*="bot"] {
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%) !important;
    border-radius: 12px 12px 12px 4px !important;
    padding: 14px 18px !important;
    margin: 10px 0 !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08) !important;
    border-left: 3px solid #94a3b8 !important;
    transition: all 0.2s ease !important;
}

.chatbot-wrapper .chatbot > div > div:not(:first-child):hover,
.chatbot-wrapper .chatbot [class*="assistant"]:hover,
.chatbot-wrapper .chatbot [class*="Assistant"]:hover,
.chatbot-wrapper .chatbot [class*="bot"]:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12) !important;
    transform: translateX(2px);
}

/* 通用消息样式 */
.chatbot-wrapper .chatbot div[class*="message"] {
    border-radius: 4px !important;
    padding: 12px 16px !important;
    margin: 8px 0 !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important;
}

/* ========== 中间编辑区 - 小说内容 ========== */
#row3 {
    flex: 1;
    min-width: 0;
    max-height: 88vh;
    overflow: auto;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 28px;
    margin: 0 20px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 3px rgba(0, 0, 0, 0.04);
    transition: box-shadow 0.3s ease;
}

#row3:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08), 0 2px 6px rgba(0, 0, 0, 0.06);
}

.novel-textbox {
    position: relative;
}

.novel-textbox label {
    font-size: 16px;
    font-weight: 600;
    color: #2d3748;
    margin-bottom: 12px;
    display: block;
}

.novel-textbox textarea {
    font-size: 16px !important;
    line-height: 1.8 !important;
    color: #2d3748 !important;
    padding: 20px !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 10px !important;
    background: #fafbfc !important;
    min-height: 600px !important;
    max-height: calc(88vh - 100px) !important;
    overflow-y: auto !important;
    resize: vertical !important;
    transition: all 0.3s ease !important;
}

.novel-textbox textarea::-webkit-scrollbar {
    width: 6px;
}

.novel-textbox textarea::-webkit-scrollbar-track {
    background: #f8fafc;
    border-radius: 3px;
}

.novel-textbox textarea::-webkit-scrollbar-thumb {
    background: #cbd5e0;
    border-radius: 3px;
}

.novel-textbox textarea::-webkit-scrollbar-thumb:hover {
    background: #a0aec0;
}

.novel-textbox textarea:focus {
    border-color: #4299e1 !important;
    outline: none !important;
    box-shadow: 0 0 0 4px rgba(66, 153, 225, 0.12), 0 2px 8px rgba(66, 153, 225, 0.15) !important;
    background: #ffffff !important;
}

/* 复制按钮样式 */
.novel-textbox button[title*="copy" i],
.novel-textbox button[aria-label*="copy" i] {
    position: absolute;
    top: 24px;
    right: 24px;
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 14px;
    color: #64748b;
    transition: all 0.2s;
    z-index: 10;
}

.novel-textbox button[title*="copy" i]:hover,
.novel-textbox button[aria-label*="copy" i]:hover {
    background: #e2e8f0;
    color: #4299e1;
}

/* 自动保存提示 */
.novel-textbox::after {
    content: "自动保存中";
    position: absolute;
    bottom: 16px;
    right: 16px;
    font-size: 12px;
    color: #94a3b8;
    pointer-events: none;
}

/* ========== 右侧状态区 - 标签页 ========== */
#row1 {
    width: 350px !important;
    min-width: 350px !important;
    max-width: 350px !important;
    max-height: 88vh;
    overflow: hidden;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 24px;
    margin-left: 20px;
    display: flex;
    flex-direction: column;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 3px rgba(0, 0, 0, 0.04);
    transition: box-shadow 0.3s ease;
}

#row1:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08), 0 2px 6px rgba(0, 0, 0, 0.06);
}

/* 标签页样式 */
.gr-tabs {
    border-bottom: 2px solid #e2e8f0;
    margin-bottom: 24px;
    padding-bottom: 0;
    background: linear-gradient(to bottom, #f8fafc, #ffffff);
    border-radius: 8px 8px 0 0;
    padding: 4px 4px 0 4px;
}

.gr-tabs button {
    padding: 12px 24px;
    font-weight: 600;
    color: #64748b;
    border: none;
    background: transparent;
    border-bottom: 3px solid transparent;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    margin-right: 4px;
    border-radius: 8px 8px 0 0;
    position: relative;
}

.gr-tabs button::before {
    content: '';
    position: absolute;
    bottom: -2px;
    left: 0;
    right: 0;
    height: 3px;
    background: #4299e1;
    transform: scaleX(0);
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.gr-tabs button:hover {
    background: rgba(66, 153, 225, 0.08);
    color: #4299e1;
}

.gr-tabs button:hover::before {
    transform: scaleX(0.5);
}

.gr-tabs button.selected {
    color: #4299e1;
    background: rgba(66, 153, 225, 0.1);
    border-bottom-color: #4299e1;
}

.gr-tabs button.selected::before {
    transform: scaleX(1);
}

/* 标签页内容区 */
.tab {
    overflow-y: auto;
    max-height: calc(88vh - 120px);
    padding: 8px 0;
    animation: fadeIn 0.3s ease-in-out;
    display: flex;
    flex-direction: column;
}

/* 确保开始标签页的按钮始终在底部可见 */
#row1 .tab:first-child {
    justify-content: space-between;
}

@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(4px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.tab::-webkit-scrollbar {
    width: 6px;
}

.tab::-webkit-scrollbar-track {
    background: #f8fafc;
    border-radius: 3px;
}

.tab::-webkit-scrollbar-thumb {
    background: #cbd5e0;
    border-radius: 3px;
}

.tab::-webkit-scrollbar-thumb:hover {
    background: #a0aec0;
}

/* 流程提示 */
.flow-hint {
    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
    border-left: 4px solid #4299e1;
    padding: 16px 20px;
    border-radius: 10px;
    margin-bottom: 24px;
    color: #475569;
    font-size: 13px;
    line-height: 1.7;
    box-shadow: 0 2px 6px rgba(66, 153, 225, 0.1);
    position: relative;
    overflow: hidden;
}

.flow-hint::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 4px;
    height: 100%;
    background: linear-gradient(180deg, #4299e1, #3182ce);
}

/* 输入框样式 */
.input-field {
    margin-bottom: 15px;
    max-height: 140px;
    overflow: hidden;
    background: transparent !important;
}

.input-field > div,
.input-field > div > div {
    background: transparent !important;
    border: none !important;
}

.input-field .wrap {
    background: transparent !important;
    border: none !important;
}

.input-field label {
    font-size: 13px;
    font-weight: 600;
    color: #2d3748;
    margin-bottom: 8px;
    display: block;
}

.input-field textarea,
.input-field input[type="text"] {
    border: 1.5px solid #e2e8f0 !important;
    border-radius: 8px !important;
    padding: 14px 16px !important;
    font-size: 14px !important;
    color: #2d3748 !important;
    background: #ffffff !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    max-height: 120px !important;
    overflow-y: auto !important;
    resize: vertical !important;
}

.input-field textarea::-webkit-scrollbar {
    width: 6px;
}

.input-field textarea::-webkit-scrollbar-track {
    background: #f8fafc;
    border-radius: 3px;
}

.input-field textarea::-webkit-scrollbar-thumb {
    background: #cbd5e0;
    border-radius: 3px;
}

.input-field textarea::-webkit-scrollbar-thumb:hover {
    background: #a0aec0;
}

.input-field textarea:focus,
.input-field input[type="text"]:focus {
    border-color: #4299e1 !important;
    outline: none !important;
    box-shadow: 0 0 0 4px rgba(66, 153, 225, 0.12), 0 2px 6px rgba(66, 153, 225, 0.1) !important;
    background: #ffffff !important;
    transform: translateY(-1px);
}

.input-field textarea::placeholder,
.input-field input[type="text"]::placeholder {
    color: #94a3b8 !important;
}

/* 移除Gradio默认的输入框容器样式 */
.input-field .form,
.input-field .form-group,
.input-field .gr-textbox,
.input-field [class*="textbox"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
}

/* 移除输入框容器底部的灰色边框 */
.input-field [class*="wrap"],
.input-field [class*="container"] {
    background: transparent !important;
    border: none !important;
    border-bottom: none !important;
}

/* 大纲文本框 */
.outline-textbox {
    margin-bottom: 16px;
    background: transparent !important;
}

.outline-textbox > div,
.outline-textbox > div > div {
    background: transparent !important;
    border: none !important;
}

.outline-textbox .wrap {
    background: transparent !important;
    border: none !important;
}

.outline-textbox label {
    font-size: 13px;
    font-weight: 600;
    color: #2d3748;
    margin-bottom: 8px;
}

.outline-textbox textarea {
    border: 1px solid #e2e8f0 !important;
    border-radius: 6px !important;
    padding: 12px 14px !important;
    font-size: 14px !important;
    color: #333333 !important;
    background: #ffffff !important;
    min-height: 300px !important;
    max-height: calc(88vh - 200px) !important;
    overflow-y: auto !important;
    resize: vertical !important;
}

.outline-textbox textarea::-webkit-scrollbar {
    width: 6px;
}

.outline-textbox textarea::-webkit-scrollbar-track {
    background: #f8fafc;
    border-radius: 3px;
}

.outline-textbox textarea::-webkit-scrollbar-thumb {
    background: #cbd5e0;
    border-radius: 3px;
}

.outline-textbox textarea::-webkit-scrollbar-thumb:hover {
    background: #a0aec0;
}

.outline-textbox textarea:focus {
    border-color: #4299e1 !important;
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.1) !important;
}

/* 移除大纲文本框容器的默认样式 */
.outline-textbox .form,
.outline-textbox .form-group,
.outline-textbox .gr-textbox,
.outline-textbox [class*="textbox"],
.outline-textbox [class*="wrap"],
.outline-textbox [class*="container"] {
    background: transparent !important;
    border: none !important;
    border-bottom: none !important;
    padding: 0 !important;
    margin: 0 !important;
}

/* 状态字段 */
.status-field {
    margin-bottom: 20px;
    background: transparent !important;
}

.status-field > div,
.status-field > div > div {
    background: transparent !important;
    border: none !important;
}

.status-field .wrap {
    background: transparent !important;
    border: none !important;
}

.status-field label {
    font-size: 15px;
    font-weight: 700;
    color: #2d3748;
    margin-bottom: 10px;
    display: block;
}

.status-field textarea {
    border: 1px solid #e2e8f0 !important;
    border-radius: 6px !important;
    padding: 12px 14px !important;
    font-size: 14px !important;
    color: #333333 !important;
    background: #ffffff !important;
    overflow-y: auto !important;
    resize: none !important;
    height: auto !important;
    min-height: auto !important;
    max-height: 180px !important;
    line-height: 1.5 !important;
}

.status-field textarea::-webkit-scrollbar {
    width: 6px;
}

.status-field textarea::-webkit-scrollbar-track {
    background: #f8fafc;
    border-radius: 3px;
}

.status-field textarea::-webkit-scrollbar-thumb {
    background: #cbd5e0;
    border-radius: 3px;
}

.status-field textarea::-webkit-scrollbar-thumb:hover {
    background: #a0aec0;
}

.status-field textarea:focus {
    border-color: #4299e1 !important;
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.1) !important;
}

/* 移除状态字段容器的默认样式 */
.status-field .form,
.status-field .form-group,
.status-field .gr-textbox,
.status-field [class*="textbox"],
.status-field [class*="wrap"],
.status-field [class*="container"] {
    background: transparent !important;
    border: none !important;
    border-bottom: none !important;
    padding: 0 !important;
    margin: 0 !important;
}

/* 状态标签页按钮底部间距 - 确保按钮始终可见 */
.tab .primary-button:last-child {
    margin-top: 20px;
    margin-bottom: 20px;
}

/* ========== 标题行样式 ========== */
.title-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
}

.title-row .secondary-button {
    margin-left: auto;
    padding: 8px 16px !important;
    font-size: 13px !important;
    height: auto !important;
    width: auto !important;
    min-width: auto !important;
    max-width: fit-content !important;
    flex-shrink: 0 !important;
    border-radius: 8px !important;
}

/* ========== 按钮样式 ========== */
.button-row {
    gap: 12px;
    margin-top: 16px;
    flex-shrink: 0;
}

.button-row button {
    flex: 1;
}

/* 主要按钮 */
.primary-button {
    background: linear-gradient(135deg, #4299e1 0%, #3182ce 100%) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 14px 28px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    cursor: pointer !important;
    box-shadow: 0 2px 6px rgba(66, 153, 225, 0.25), 0 1px 3px rgba(66, 153, 225, 0.15) !important;
    position: relative;
    overflow: hidden;
}

.primary-button::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
    transition: left 0.5s;
}

.primary-button:hover {
    background: linear-gradient(135deg, #3182ce 0%, #2c5aa0 100%) !important;
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(66, 153, 225, 0.35), 0 3px 8px rgba(66, 153, 225, 0.2) !important;
}

.primary-button:hover::before {
    left: 100%;
}

.primary-button:active {
    transform: translateY(0);
    box-shadow: 0 2px 4px rgba(66, 153, 225, 0.3) !important;
}

/* 次要按钮 */
.secondary-button {
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%) !important;
    color: #475569 !important;
    border: 1.5px solid #e2e8f0 !important;
    border-radius: 8px !important;
    padding: 12px 24px !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    cursor: pointer !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05) !important;
}

.secondary-button:hover {
    background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%) !important;
    border-color: #cbd5e0 !important;
    color: #2d3748 !important;
    transform: translateY(-1px);
    box-shadow: 0 3px 8px rgba(0, 0, 0, 0.1) !important;
}

.secondary-button:active {
    transform: translateY(0);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1) !important;
}

/* ========== 标题样式 ========== */
h2 {
    color: #2d3748;
    font-weight: 700;
    font-size: 24px;
    margin-bottom: 8px;
}

/* ========== 全局文本样式 ========== */
label {
    color: #2d3748;
}

/* ========== 隐藏元素 ========== */
button[aria-label="Use via API"] {
    display: none !important;
}

footer {
    display: none !important;
}

/* ========== 响应式设计 ========== */
@media (max-width: 1400px) {
    #row1 {
        width: 320px !important;
        min-width: 320px !important;
        max-width: 320px !important;
    }
}

@media (max-width: 1200px) {
    .main-layout {
        flex-direction: column;
    }
    
    #row2, #row1 {
        width: 100% !important;
        min-width: 100% !important;
        max-width: 100% !important;
        margin: 0 0 16px 0;
    }
    
    #row3 {
        margin: 0;
    }
}
"""

with gr.Blocks(css=css) as demo:
    initial_language = "zh"
    ui = UI_STRINGS[initial_language]

    language_state = gr.State(initial_language)
    aign = gr.State(AIGN(chatLLM, language=initial_language))

    with gr.Row(elem_classes=["title-row"]):
        title_md = gr.Markdown(ui["title"])
        language_button = gr.Button(
            ui["language_toggle"], variant="secondary", elem_classes=["secondary-button"]
        )
    with gr.Row(elem_classes=["main-layout"]):
        with gr.Column(scale=5, elem_id="row2"):
            chatBox = gr.Chatbot(height=f"85vh", elem_classes=["chatbot-wrapper"])
        with gr.Column(scale=5, elem_id="row3"):
            novel_content_text = gr.Textbox(
                label=ui["novel_label"],
                lines=32,
                interactive=True,
                show_copy_button=True,
                elem_classes=["novel-textbox"],
            )
            # TODO
            # download_novel_button = gr.Button("下载小说")
        with gr.Column(scale=0, elem_id="row1", min_width=350):
            with gr.Tab(ui["tab_start"]) as start_tab:
                user_idea_text = gr.Textbox(
                    "",
                    label=ui["idea_label"],
                    placeholder=ui["idea_placeholder"],
                    lines=4,
                    interactive=True,
                    elem_classes=["input-field"],
                )
                user_requirements_text = gr.Textbox(
                    "",
                    label=ui["requirements_label"],
                    placeholder=ui["requirements_placeholder"],
                    lines=4,
                    interactive=True,
                    elem_classes=["input-field"],
                )
                embellishment_idea_text = gr.Textbox(
                    "",
                    label=ui["embellishment_label"],
                    placeholder=ui["embellishment_placeholder"],
                    lines=4,
                    interactive=True,
                    elem_classes=["input-field"],
                )
                with gr.Row(elem_classes=["button-row"]):
                    gen_ouline_button = gr.Button(ui["create_outline"], elem_classes=["primary-button"])
                with gr.Row(elem_classes=["button-row"]):
                    reset_button = gr.Button(ui["reset"], variant="secondary", elem_classes=["secondary-button"])
            with gr.Tab(ui["tab_outline"]) as outline_tab:
                novel_outline_text = gr.Textbox(
                    label=ui["outline_label"], lines=15, interactive=True, elem_classes=["outline-textbox"]
                )
                gen_beginning_button = gr.Button(ui["polish_beginning"], elem_classes=["primary-button"])
            with gr.Tab(ui["tab_status"]) as status_tab:
                writing_memory_text = gr.Textbox(
                    label=ui["memory_label"],
                    lines=6,
                    interactive=True,
                    max_lines=8,
                    elem_classes=["status-field"],
                )
                writing_plan_text = gr.Textbox(
                    label=ui["plan_label"], lines=6, interactive=True, elem_classes=["status-field"]
                )
                temporary_setting_text = gr.Textbox(
                    label=ui["temp_label"], lines=5, interactive=True, elem_classes=["status-field"]
                )
                # TODO
                # gen_next_paragraph_button = gr.Button("撤销生成")
                gen_next_paragraph_button = gr.Button(ui["next_paragraph"], elem_classes=["primary-button"])
                # TODO
                # auto_gen_next_checkbox = gr.Checkbox(
                #     label="自动生成下一段", checked=False, interactive=True
                # )

    reset_button.click(
        reset_workflow,
        [aign, language_state],
        [
            aign,
            user_idea_text,
            user_requirements_text,
            embellishment_idea_text,
            chatBox,
            novel_outline_text,
            writing_memory_text,
            writing_plan_text,
            temporary_setting_text,
            novel_content_text,
            gen_ouline_button,
            gen_beginning_button,
        ],
    )

    language_button.click(
        toggle_language,
        [aign, language_state],
        [
            aign,
            language_state,
            title_md,
            user_idea_text,
            user_requirements_text,
            embellishment_idea_text,
            chatBox,
            novel_outline_text,
            writing_memory_text,
            writing_plan_text,
            temporary_setting_text,
            novel_content_text,
            gen_ouline_button,
            gen_beginning_button,
            gen_next_paragraph_button,
            reset_button,
            language_button,
            start_tab,
            outline_tab,
            status_tab,
        ],
    )

    gen_ouline_button.click(
        on_generate_outline_clicked,
        [aign, user_idea_text, chatBox],
        [aign, chatBox, novel_outline_text, gen_ouline_button],
    )
    gen_beginning_button.click(
        on_generate_beginning_clicked,
        [
            aign,
            chatBox,
            novel_outline_text,
            user_requirements_text,
            embellishment_idea_text,
        ],
        [
            aign,
            chatBox,
            writing_plan_text,
            temporary_setting_text,
            novel_content_text,
            gen_beginning_button,
        ],
    )
    gen_next_paragraph_button.click(
        on_generate_next_paragraph_clicked,
        [
            aign,
            chatBox,
            user_idea_text,
            novel_outline_text,
            writing_memory_text,
            temporary_setting_text,
            writing_plan_text,
            user_requirements_text,
            embellishment_idea_text,
        ],
        [
            aign,
            chatBox,
            writing_plan_text,
            temporary_setting_text,
            writing_memory_text,
            novel_content_text,
        ],
    )


demo.queue()
demo.launch(show_api=False, show_error=True)