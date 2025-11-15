import time

from AIGN_Prompt import PROMPTS


class ProcessAborted(Exception):
    """Raised when the generation workflow is aborted."""
    pass


def retry_operation(func, max_retries=10):
    def wrapper(*args, **kwargs):
        for _ in range(max_retries):
            try:
                return func(*args, **kwargs)
            except ProcessAborted:
                raise
            except Exception as e:
                print("-" * 30 + f"\n失败：\n{e}\n" + "-" * 30)
                time.sleep(2.333)
        raise ValueError("失败")

    return wrapper


class MarkdownAgent:
    """专门应对输入输出都是md格式的情况，例如小说生成"""

    def __init__(
        self,
        chat_llm,
        system_prompt: str,
        name: str,
        temperature=0.8,
        top_p=0.8,
        use_memory=False,
        initial_reply="明白了。",
        is_speak=True,
        abort_checker=None,
    ) -> None:

        self.chat_llm = chat_llm
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.top_p = top_p
        self.use_memory = use_memory
        self.is_speak = is_speak
        self.name = name
        self.abort_checker = abort_checker

        self.history = [{"role": "user", "content": self.system_prompt}]

        if initial_reply:
            self.history.append({"role": "assistant", "content": initial_reply})
        else:
            resp = chat_llm(messages=self.history)
            self.history.append({"role": "assistant", "content": resp["content"]})
            # if self.is_speak:
            #     self.speak(Msg(self.name, resp["content"]))

    def query(self, user_input: str) -> str:
        if self.abort_checker and self.abort_checker():
            raise ProcessAborted()
        resp = self.chat_llm(
            messages=self.history + [{"role": "user", "content": user_input}],
            temperature=self.temperature,
            top_p=self.top_p,
        )
        if self.use_memory:
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": resp["content"]})

        return resp

    def extract_sections(self, input_content: str, output_keys: list) -> dict:
        """解析类md格式中 # key 的内容，未解析全部output_keys中的key会报错"""
        if self.abort_checker and self.abort_checker():
            raise ProcessAborted()
        resp = self.query(input_content)
        output = resp["content"]

        lines = output.split("\n")
        sections = {}
        current_section = ""
        for line in lines:
            if line.startswith("# ") or line.startswith(" # "):
                # new key
                current_section = line[2:].strip()
                sections[current_section] = []
            else:
                # add content to current key
                if current_section:
                    sections[current_section].append(line.strip())
        for key in sections.keys():
            sections[key] = "\n".join(sections[key]).strip()

        for key in output_keys:
            if (key not in sections) or (len(sections[key]) == 0):
                raise ValueError(f"fail to parse {key} in output:\n{output}\n\n")

        # if self.is_speak:
        #     self.speak(
        #         Msg(
        #             self.name,
        #             f"total_tokens: {resp['total_tokens']}\n{resp['content']}\n",
        #         )
        #     )
        return sections

    def invoke_with_parsed_output(self, inputs: dict, output_keys: list) -> dict:
        input_content = ""
        for key, value in inputs.items():
            if isinstance(value, str) and len(value) > 0:
                input_content += f"# {key}\n{value}\n\n"

        if self.abort_checker and self.abort_checker():
            raise ProcessAborted()
        result = retry_operation(self.extract_sections)(input_content, output_keys)

        return result

    def clear_memory(self):
        if self.use_memory:
            self.history = self.history[:2]


class AIGN:
    def __init__(self, chat_llm, language="zh"):
        self.chat_llm = chat_llm
        self.language = None
        self.config = None
        self.keys = None
        self.record_headers = None
        self.inputs = None
        self._abort_flag = False

        self._reset_story_state()
        self._apply_language(language)

    def _reset_story_state(self):
        self._abort_flag = False
        self.novel_title = ""
        self.novel_outline = ""
        self.paragraphs = []
        self.novel_content = ""
        self.writing_plan = ""
        self.temporary_setting = ""
        self.writing_memory = ""
        self.pending_memory_text = ""
        self.user_idea = ""
        self.user_requirements = ""
        self.embellishment_idea = ""

    def _apply_language(self, language):
        if language not in PROMPTS:
            raise ValueError(f"Unsupported language: {language}")
        self.language = language
        self.config = PROMPTS[language]
        self.keys = self.config["keys"]
        self.record_headers = self.config["record_headers"]
        self.inputs = self.config["inputs"]

        self.novel_outline_writer = MarkdownAgent(
            chat_llm=self.chat_llm,
            system_prompt=self.config["outline_prompt"],
            name="NovelOutlineWriter",
            temperature=0.98,
            initial_reply=self.config["initial_reply"],
            abort_checker=self.is_aborted,
        )
        self.novel_beginning_writer = MarkdownAgent(
            chat_llm=self.chat_llm,
            system_prompt=self.config["beginning_prompt"],
            name="NovelBeginningWriter",
            temperature=0.80,
            initial_reply=self.config["initial_reply"],
            abort_checker=self.is_aborted,
        )
        self.novel_writer = MarkdownAgent(
            chat_llm=self.chat_llm,
            system_prompt=self.config["writer_prompt"],
            name="NovelWriter",
            temperature=0.81,
            initial_reply=self.config["initial_reply"],
            abort_checker=self.is_aborted,
        )
        self.novel_embellisher = MarkdownAgent(
            chat_llm=self.chat_llm,
            system_prompt=self.config["embellisher_prompt"],
            name="NovelEmbellisher",
            temperature=0.92,
            initial_reply=self.config["initial_reply"],
            abort_checker=self.is_aborted,
        )
        self.memory_maker = MarkdownAgent(
            chat_llm=self.chat_llm,
            system_prompt=self.config["memory_prompt"],
            name="MemoryMaker",
            temperature=0.66,
            initial_reply=self.config["initial_reply"],
            abort_checker=self.is_aborted,
        )

    def update_novel_content(self):
        self.novel_content = ""
        for paragraph in self.paragraphs:
            self.novel_content += f"{paragraph}\n\n"
        return self.novel_content

    def generate_outline(self, user_idea=None):
        if user_idea:
            self.user_idea = user_idea
        resp = self.novel_outline_writer.invoke_with_parsed_output(
            inputs={self.inputs["idea"]: self.user_idea},
            output_keys=[self.keys["title"], self.keys["outline"]],
        )
        self.novel_title = resp[self.keys["title"]]
        self.novel_outline = resp[self.keys["outline"]]
        return self.novel_outline

    def generate_beginning(self, user_requirements=None, embellishment_idea=None):
        if user_requirements:
            self.user_requirements = user_requirements
        if embellishment_idea:
            self.embellishment_idea = embellishment_idea

        resp = self.novel_beginning_writer.invoke_with_parsed_output(
            inputs={
                self.inputs["idea"]: self.user_idea,
                self.inputs["outline"]: self.novel_outline,
                self.inputs["requirements"]: self.user_requirements,
            },
            output_keys=[
                self.keys["opening"],
                self.keys["plan"],
                self.keys["temporary"],
            ],
        )
        beginning = resp[self.keys["opening"]]
        self.writing_plan = resp[self.keys["plan"]]
        self.temporary_setting = resp[self.keys["temporary"]]

        resp = self.novel_embellisher.invoke_with_parsed_output(
            inputs={
                self.inputs["outline"]: self.novel_outline,
                self.inputs["temporary"]: self.temporary_setting,
                self.inputs["plan"]: self.writing_plan,
                self.inputs["polish"]: self.embellishment_idea,
                self.inputs["polish_target"]: beginning,
            },
            output_keys=[self.keys["polish"]],
        )
        beginning = resp[self.keys["polish"]]

        self.paragraphs.append(beginning)
        self.update_novel_content()

        return beginning

    def get_recent_context(self, max_length=2000):
        recent_context = ""

        for index in range(0, len(self.paragraphs)):
            candidate = self.paragraphs[-1 - index]
            if (len(recent_context) + len(candidate)) < max_length:
                recent_context = candidate + "\n" + recent_context
            else:
                break
        return recent_context

    def record_novel(self):
        record_content = ""
        record_content += (
            f"{self.record_headers['outline']}\n\n{self.novel_outline}\n\n"
        )
        record_content += f"{self.record_headers['content']}\n\n"
        record_content += self.novel_content
        record_content += (
            f"{self.record_headers['memory']}\n\n{self.writing_memory}\n\n"
        )
        record_content += f"{self.record_headers['plan']}\n\n{self.writing_plan}\n\n"
        record_content += (
            f"{self.record_headers['temporary']}\n\n{self.temporary_setting}\n\n"
        )

        with open("novel_record.md", "w", encoding="utf-8") as f:
            f.write(record_content)

    def update_memory(self):
        if len(self.pending_memory_text) > 2000:
            resp = self.memory_maker.invoke_with_parsed_output(
                inputs={
                    self.inputs["memory_prev"]: self.writing_memory,
                    self.inputs["memory_body"]: self.pending_memory_text,
                },
                output_keys=[self.keys["memory"]],
            )
            self.writing_memory = resp[self.keys["memory"]]
            self.pending_memory_text = ""

    def generate_next_paragraph(self, user_requirements=None, embellishment_idea=None):
        if user_requirements:
            self.user_requirements = user_requirements
        if embellishment_idea:
            self.embellishment_idea = embellishment_idea

        recent_context = self.get_recent_context()

        resp = self.novel_writer.invoke_with_parsed_output(
            inputs={
                self.inputs["idea"]: self.user_idea,
                self.inputs["outline"]: self.novel_outline,
                self.inputs["memory_prev"]: self.writing_memory,
                self.inputs["temporary"]: self.temporary_setting,
                self.inputs["plan"]: self.writing_plan,
                self.inputs["requirements"]: self.user_requirements,
                self.inputs["previous"]: recent_context,
            },
            output_keys=[
                self.keys["paragraph"],
                self.keys["plan"],
                self.keys["temporary"],
            ],
        )
        next_paragraph = resp[self.keys["paragraph"]]
        next_writing_plan = resp[self.keys["plan"]]
        next_temp_setting = resp[self.keys["temporary"]]

        resp = self.novel_embellisher.invoke_with_parsed_output(
            inputs={
                self.inputs["outline"]: self.novel_outline,
                self.inputs["temporary"]: next_temp_setting,
                self.inputs["plan"]: next_writing_plan,
                self.inputs["polish"]: embellishment_idea,
                self.inputs["context"]: recent_context,
                self.inputs["polish_target"]: next_paragraph,
            },
            output_keys=[self.keys["polish"]],
        )
        next_paragraph = resp[self.keys["polish"]]

        self.paragraphs.append(next_paragraph)
        self.writing_plan = next_writing_plan
        self.temporary_setting = next_temp_setting

        self.pending_memory_text += f"\n{next_paragraph}"

        self.update_memory()
        self.update_novel_content()
        self.record_novel()

        return next_paragraph

    def request_abort(self):
        self._abort_flag = True

    def is_aborted(self):
        return self._abort_flag
