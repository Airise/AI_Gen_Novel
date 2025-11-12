import random
import threading
import time

import gradio as gr

from AIGN import AIGN
from LLM import chatLLM

STREAM_INTERVAL = 0.

UI_STRINGS = {
    "zh": {
        "title": "## 小说创作工作台",
        "flow_hint": "依次完成：梳理想法 → 标注大纲 → 生成开头 → 关注状态 → 续写下一段",
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
    },
    "en": {
        "title": "## Novel Writing Studio",
        "flow_hint": "Workflow: Capture idea → Shape outline → Polish opening → Review status → Continue drafting",
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
            aign,
            carrier.history,
            aign.novel_outline,
            gr.Button(visible=False),
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
            aign,
            carrier.history,
            aign.writing_plan,
            aign.temporary_setting,
            aign.novel_content,
            gr.Button(visible=False),
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

    carrier, middle_chat = make_middle_chat()
    carrier.history = history
    aign.novel_writer.chat_llm = middle_chat
    aign.novel_embellisher.chat_llm = middle_chat
    aign.memory_maker.chat_llm = middle_chat

    gen_next_paragraph_thread = threading.Thread(
        target=aign.generate_next_paragraph
    )
    gen_next_paragraph_thread.start()

    while gen_next_paragraph_thread.is_alive():
        yield [
            aign,
            carrier.history,
            aign.writing_plan,
            aign.temporary_setting,
            aign.writing_memory,
            aign.novel_content,
            gr.Button(visible=False),
        ]
        time.sleep(STREAM_INTERVAL)
    yield [
        aign,
        carrier.history,
        aign.writing_plan,
        aign.temporary_setting,
        aign.writing_memory,
        aign.novel_content,
        gr.Button(visible=False),
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
        gr.update(value=ui["flow_hint"]),
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
body {
    background: #f7f8fc;
}
.gradio-container {
    font-family: "Noto Sans", sans-serif;
}
#row1, #row2, #row3 {
    min-width: 220px;
    max-height: 720px;
    overflow: auto;
    background: #ffffff;
    border: 1px solid #e4e7f5;
    border-radius: 10px;
    padding: 12px;
}
#row2 {
    min-width: 340px;
}
button[aria-label="Use via API"] {
    display: none !important;
}
footer {
    display: none !important;
}
"""

with gr.Blocks(css=css) as demo:
    initial_language = "zh"
    ui = UI_STRINGS[initial_language]

    language_state = gr.State(initial_language)
    aign = gr.State(AIGN(chatLLM, language=initial_language))

    title_md = gr.Markdown(ui["title"])
    with gr.Row():
        with gr.Column(scale=0, elem_id="row1"):
            with gr.Tab(ui["tab_start"]) as start_tab:
                flow_md = gr.Markdown(ui["flow_hint"])
                user_idea_text = gr.Textbox(
                    "",
                    label=ui["idea_label"],
                    placeholder=ui["idea_placeholder"],
                    lines=4,
                    interactive=True,
                )
                user_requirements_text = gr.Textbox(
                    "",
                    label=ui["requirements_label"],
                    placeholder=ui["requirements_placeholder"],
                    lines=4,
                    interactive=True,
                )
                embellishment_idea_text = gr.Textbox(
                    "",
                    label=ui["embellishment_label"],
                    placeholder=ui["embellishment_placeholder"],
                    lines=4,
                    interactive=True,
                )
                with gr.Row():
                    gen_ouline_button = gr.Button(ui["create_outline"])
                    reset_button = gr.Button(ui["reset"], variant="secondary")
                    language_button = gr.Button(
                        ui["language_toggle"], variant="secondary"
                    )
            with gr.Tab(ui["tab_outline"]) as outline_tab:
                novel_outline_text = gr.Textbox(
                    label=ui["outline_label"], lines=24, interactive=True
                )
                gen_beginning_button = gr.Button(ui["polish_beginning"])
            with gr.Tab(ui["tab_status"]) as status_tab:
                writing_memory_text = gr.Textbox(
                    label=ui["memory_label"],
                    lines=6,
                    interactive=True,
                    max_lines=8,
                )
                writing_plan_text = gr.Textbox(
                    label=ui["plan_label"], lines=6, interactive=True
                )
                temporary_setting_text = gr.Textbox(
                    label=ui["temp_label"], lines=5, interactive=True
                )
                # TODO
                # gen_next_paragraph_button = gr.Button("撤销生成")
                gen_next_paragraph_button = gr.Button(ui["next_paragraph"])
                # TODO
                # auto_gen_next_checkbox = gr.Checkbox(
                #     label="自动生成下一段", checked=False, interactive=True
                # )
        with gr.Column(scale=3, elem_id="row2"):
            chatBox = gr.Chatbot(height=f"80vh", label=ui["chat_label"])
        with gr.Column(scale=0, elem_id="row3"):
            novel_content_text = gr.Textbox(
                label=ui["novel_label"],
                lines=32,
                interactive=True,
                show_copy_button=True,
            )
            # TODO
            # download_novel_button = gr.Button("下载小说")

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
            flow_md,
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