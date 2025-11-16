import time

from AIGN_Prompt import PROMPTS


class ProcessAborted(Exception):
    """Raised when the generation workflow is aborted."""
    pass


class StoryEnded(Exception):
    """Raised when the story has reached its final chapter."""
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
        """解析类md格式中 # key 的内容"""
        if self.abort_checker and self.abort_checker():
            raise ProcessAborted()
        
        resp = self.query(input_content)
        output = resp["content"]
        
        print(f"=== 开始解析输出 ===")
        print(f"需要解析的键: {output_keys}")
        print(f"原始输出内容:\n{output}\n")

        lines = output.split("\n")
        sections = {}
        current_section = ""
        
        for line in lines:
            line = line.strip()
            if line.startswith("# "):
                # 新的部分
                current_section = line[2:].strip()
                sections[current_section] = []
                print(f"找到部分: '{current_section}'")
            elif current_section and line:
                # 添加到当前部分
                sections[current_section].append(line)
        
        # 清理每个部分的内容
        for key in list(sections.keys()):
            content = "\n".join(sections[key]).strip()
            sections[key] = content
            print(f"部分 '{key}' 的内容长度: {len(content)}")
            if not content:
                print(f"警告: 部分 '{key}' 内容为空")
                # 不删除空内容，保留以便后续智能匹配

        print(f"解析出的所有键: {list(sections.keys())}")

        # 智能匹配：尝试将找到的部分映射到期望的键
        matched_sections = {}
        unmatched_keys = []
        used_found_keys = set()  # 记录已使用的找到的键
        
        for expected_key in output_keys:
            if expected_key in sections:
                # 直接匹配
                matched_sections[expected_key] = sections[expected_key]
                used_found_keys.add(expected_key)
            else:
                # 尝试智能匹配
                matched = False
                # 对于标题类键，尝试匹配可能的标题格式
                if "标题" in expected_key or "title" in expected_key.lower():
                    # 优先查找包含"章"的键
                    for found_key, found_content in sections.items():
                        if found_key not in used_found_keys and not matched:
                            if "章" in found_key:
                                # 如果内容过长（>500字符），可能是段落内容被误放在标题下，只使用键名
                                if len(found_content) > 500:
                                    matched_sections[expected_key] = found_key
                                    # 不标记为已使用，因为内容可能还需要用于段落
                                    matched = True
                                    print(f"智能匹配: 将 '{found_key}' 的键名映射到期望键 '{expected_key}'（内容过长，可能是段落）")
                                else:
                                    # 如果内容为空或较短，使用内容或键名
                                    matched_sections[expected_key] = found_content if found_content else found_key
                                    used_found_keys.add(found_key)
                                    matched = True
                                    print(f"智能匹配: 将 '{found_key}' 映射到期望键 '{expected_key}'")
                                break
                    
                    # 如果还没匹配，查找第一个看起来像标题的部分（可能是小说标题或章节标题）
                    if not matched:
                        for found_key, found_content in sections.items():
                            if found_key not in used_found_keys and not matched:
                                # 如果这个键看起来像标题（不是常见的输出键如"开头"、"计划"等）
                                common_keys = {"开头", "计划", "临时设定", "END", "opening", "plan", "temporary", "end", "段落", "paragraph", "segment"}
                                if found_key not in common_keys:
                                    # 如果内容过长（>500字符），可能是段落内容被误放在标题下，只使用键名
                                    if len(found_content) > 500:
                                        matched_sections[expected_key] = found_key
                                        # 不标记为已使用，因为内容可能还需要用于段落
                                        matched = True
                                        print(f"智能匹配: 将 '{found_key}' 的键名映射到期望键 '{expected_key}'（内容过长，可能是段落）")
                                    else:
                                        # 如果内容为空或较短，使用内容或键名
                                        matched_sections[expected_key] = found_content if found_content else found_key
                                        used_found_keys.add(found_key)
                                        matched = True
                                        print(f"智能匹配: 将 '{found_key}' 映射到期望键 '{expected_key}'")
                                    break
                
                # 对于段落类键，如果找不到，检查是否有标题键包含大量内容（可能是段落内容被误放在标题下）
                elif "段落" in expected_key or "paragraph" in expected_key.lower() or "segment" in expected_key.lower():
                    for found_key, found_content in sections.items():
                        if not matched:
                            # 检查这个键是否看起来像标题，但包含大量内容（可能是段落内容）
                            common_keys = {"开头", "计划", "临时设定", "END", "opening", "plan", "temporary", "end", "段落", "paragraph", "segment"}
                            if found_key not in common_keys and len(found_content) > 500:  # 如果内容超过500字符，可能是段落内容
                                matched_sections[expected_key] = found_content
                                # 注意：这里不将 found_key 添加到 used_found_keys，因为它的键名可能还需要用于标题匹配
                                matched = True
                                print(f"智能匹配: 将 '{found_key}' 的内容（{len(found_content)}字符）映射到期望键 '{expected_key}'")
                                break
                
                if not matched:
                    unmatched_keys.append(expected_key)
                    print(f"错误: 缺少键 '{expected_key}'")
        
        # 特殊处理：如果标题键的内容被用作段落，需要确保标题键也能正确匹配
        # 检查是否有标题类键的内容被用作段落，但标题键本身还没有被匹配
        title_keys = [k for k in output_keys if "标题" in k or "title" in k.lower()]
        paragraph_keys = [k for k in output_keys if "段落" in k or "paragraph" in k.lower() or "segment" in k.lower()]
        
        for title_key in title_keys:
            if title_key not in matched_sections:
                # 查找是否有段落键使用了某个标题键的内容
                for para_key in paragraph_keys:
                    if para_key in matched_sections:
                        para_content = matched_sections[para_key]
                        # 查找是哪个 found_key 的内容被用作段落
                        for found_key, found_content in sections.items():
                            if found_content == para_content and len(found_content) > 500:
                                # 这个 found_key 的内容被用作段落，但键名应该是标题
                                matched_sections[title_key] = found_key  # 使用键名作为标题
                                used_found_keys.add(found_key)
                                print(f"智能匹配: 将 '{found_key}' 的键名映射到期望键 '{title_key}'（内容已用于段落）")
                                break
                        if title_key in matched_sections:
                            break
        
        if unmatched_keys:
            raise ValueError(f"解析失败，缺少以下键: {unmatched_keys}\n完整输出:\n{output}\n已找到的部分: {list(sections.keys())}")
        
        print("=== 解析成功 ===")
        return matched_sections

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
        self._story_completed = False

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
        self.dialogue_optimizer = MarkdownAgent(
            chat_llm=self.chat_llm,
            system_prompt=self.config["dialogue_optimizer_prompt"],
            name="DialogueOptimizer",
            temperature=0.75,
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
        
        # 使用新的输出键
        resp = self.novel_outline_writer.invoke_with_parsed_output(
            inputs={self.inputs["idea"]: self.user_idea},
            output_keys=[
                self.keys["title"],
                self.keys["estimated_chapters"],
                self.keys["chapter_plan"], 
                self.keys["outline"]
            ],
        )
        
        # 提取所有部分
        self.novel_title = resp[self.keys["title"]]
        estimated_chapters = resp[self.keys["estimated_chapters"]]
        chapter_plan = resp[self.keys["chapter_plan"]]
        detailed_outline = resp[self.keys["outline"]]
        
        # 组合成完整的大纲
        self.novel_outline = f"# {self.novel_title}\n\n{estimated_chapters}\n\n{chapter_plan}\n\n{detailed_outline}"
        
        return self.novel_outline

    def generate_beginning(self, user_requirements=None, embellishment_idea=None):
        if user_requirements:
            self.user_requirements = user_requirements
        if embellishment_idea:
            self.embellishment_idea = embellishment_idea

        # 使用新的输出键，包含标题信息
        resp = self.novel_beginning_writer.invoke_with_parsed_output(
            inputs={
                self.inputs["idea"]: self.user_idea,
                self.inputs["outline"]: self.novel_outline,
                self.inputs["requirements"]: self.user_requirements,
            },
            output_keys=[
                self.keys["chapter_title"],   # 第一章标题
                self.keys["opening"],         # 开头内容
                self.keys["plan"],            # 计划
                self.keys["temporary"],       # 临时设定
            ],
        )
        
        # 提取所有信息
        chapter_title = resp[self.keys["chapter_title"]]
        beginning = resp[self.keys["opening"]]
        self.writing_plan = resp[self.keys["plan"]]
        self.temporary_setting = resp[self.keys["temporary"]]

        # 清理标题，去除可能的描述性文字
        if chapter_title:
            chapter_title = self._clean_chapter_title(chapter_title)

        # 验证标题不为空
        if not chapter_title or not chapter_title.strip():
            raise ValueError(f"第一章标题为空，无法继续生成。解析结果: {resp}")

        # 润色
        polish_resp = self.novel_embellisher.invoke_with_parsed_output(
            inputs={
                self.inputs["outline"]: self.novel_outline,
                self.inputs["temporary"]: self.temporary_setting,
                self.inputs["plan"]: self.writing_plan,
                self.inputs["polish"]: self.embellishment_idea,
                self.inputs["polish_target"]: beginning,
            },
            output_keys=[self.keys["polish"]],
        )
        # 确保使用润色后的结果
        polished_beginning = polish_resp[self.keys["polish"]]
        if not polished_beginning or not polished_beginning.strip():
            # 如果润色结果为空，使用原始开头
            print("警告: 润色结果为空，使用原始开头")
            polished_beginning = beginning
        beginning = polished_beginning

        # 将标题和内容组合成完整的段落
        beginning_with_title = f"## {chapter_title.strip()}\n\n{beginning}"
        
        self.paragraphs.append(beginning_with_title)
        self.update_novel_content()

        return beginning_with_title

    def _extract_chapter_number_from_title(self, title: str) -> int:
        """从章节标题中提取章节号，例如'第1章：xxx'或'第一章：xxx'"""
        import re
        # 匹配"第X章"或"第一章"等格式
        match = re.search(r'第([一二三四五六七八九十\d]+)章', title)
        if match:
            num_str = match.group(1)
            # 处理中文数字
            chinese_nums = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, 
                          '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
            if num_str in chinese_nums:
                return chinese_nums[num_str]
            try:
                return int(num_str)
            except:
                pass
        return 0

    def _get_current_chapter_info(self):
        """获取当前已写的章节信息"""
        if not self.paragraphs:
            return 0, None
        
        # 从已有段落中提取章节标题
        chapter_titles = []
        for para in self.paragraphs:
            lines = para.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('## '):
                    title = line[3:].strip()
                    chapter_titles.append(title)
                    break
        
        if not chapter_titles:
            return 0, None
        
        # 获取最后一个章节标题
        last_title = chapter_titles[-1]
        last_chapter_num = self._extract_chapter_number_from_title(last_title)
        
        # 如果无法从标题中提取章节号，尝试从大纲中匹配标题来获取章节号
        if last_chapter_num <= 0 and self.novel_outline:
            last_chapter_num = self._match_title_to_chapter_number(last_title)
        
        return len(chapter_titles), last_chapter_num
    
    def _match_title_to_chapter_number(self, title):
        """通过匹配标题从大纲中获取章节号"""
        import re
        if not self.novel_outline or not title:
            return 0
        
        # 在大纲中查找包含该标题的章节
        # 尝试匹配格式：第X章：标题 或 第X章：标题 - 描述
        lines = self.novel_outline.split('\n')
        for line in lines:
            # 查找包含该标题的行
            if title in line:
                # 尝试从该行提取章节号
                match = re.search(r'第([一二三四五六七八九十\d]+)章', line)
                if match:
                    num_str = match.group(1)
                    chinese_nums = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, 
                                  '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
                    if num_str in chinese_nums:
                        return chinese_nums[num_str]
                    try:
                        return int(num_str)
                    except:
                        pass
        
        # 如果直接匹配失败，尝试模糊匹配（标题的一部分）
        title_keywords = title.split()[:2]  # 取标题的前两个词
        for keyword in title_keywords:
            if len(keyword) > 1:  # 只匹配长度大于1的关键词
                for line in lines:
                    if keyword in line:
                        match = re.search(r'第([一二三四五六七八九十\d]+)章', line)
                        if match:
                            num_str = match.group(1)
                            chinese_nums = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, 
                                          '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
                            if num_str in chinese_nums:
                                return chinese_nums[num_str]
                            try:
                                return int(num_str)
                            except:
                                pass
                            break
        
        return 0

    def _extract_max_chapter_number_from_outline(self):
        """从大纲中提取最大章节号"""
        import re
        if not self.novel_outline:
            return None
        
        # 查找所有章节号
        pattern = r'第([一二三四五六七八九十\d]+)章'
        matches = re.findall(pattern, self.novel_outline)
        
        if not matches:
            return None
        
        max_chapter_num = 0
        chinese_nums = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, 
                      '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        
        for num_str in matches:
            if num_str in chinese_nums:
                num = chinese_nums[num_str]
            else:
                try:
                    num = int(num_str)
                except:
                    continue
            max_chapter_num = max(max_chapter_num, num)
        
        return max_chapter_num if max_chapter_num > 0 else None

    def _is_last_chapter(self):
        """检查是否已经到达最后一章"""
        if self._story_completed:
            return True
        
        if not self.novel_outline:
            return False
        
        # 获取当前章节信息
        chapter_count, last_chapter_num = self._get_current_chapter_info()
        
        if last_chapter_num <= 0:
            return False
        
        # 从大纲中提取最大章节号
        max_chapter_num = self._extract_max_chapter_number_from_outline()
        
        if max_chapter_num is None:
            return False
        
        # 如果当前章节号等于或大于最大章节号，说明已经到达最后一章
        is_last = last_chapter_num >= max_chapter_num
        if is_last:
            print(f"检测到最后一章: 当前章节号={last_chapter_num}, 最大章节号={max_chapter_num}")
        return is_last
    
    def _will_exceed_max_chapter(self):
        """检查下一章是否会超过最大章节号"""
        if not self.novel_outline:
            return False
        
        # 获取当前章节信息
        chapter_count, last_chapter_num = self._get_current_chapter_info()
        
        # 确定下一章的章节号
        if last_chapter_num > 0:
            next_chapter_num = last_chapter_num + 1
        else:
            next_chapter_num = chapter_count + 1
        
        # 从大纲中提取最大章节号
        max_chapter_num = self._extract_max_chapter_number_from_outline()
        
        if max_chapter_num is None:
            return False
        
        # 如果下一章超过最大章节号，说明已经完成
        will_exceed = next_chapter_num > max_chapter_num
        if will_exceed:
            print(f"下一章将超过最大章节号: 下一章={next_chapter_num}, 最大章节号={max_chapter_num}")
        return will_exceed

    def _clean_chapter_title(self, title):
        """清理章节标题，去除描述性文字"""
        import re
        if not title:
            return title
        
        title = title.strip()
        
        # 去除"第X章："前缀（如果存在）
        title = re.sub(r'^第[一二三四五六七八九十\d]+章[：:]\s*', '', title)
        
        # 如果包含" - "或" -"，只保留"-"前面的部分
        if ' - ' in title:
            title = title.split(' - ')[0].strip()
        elif ' -' in title:
            title = title.split(' -')[0].strip()
        
        # 去除末尾可能的多余空格和标点
        title = title.rstrip('，。、；：')
        
        return title

    def _extract_next_chapter_title_from_outline(self):
        """从大纲中提取下一章的标题"""
        import re
        if not self.novel_outline:
            return None
        
        # 获取当前章节信息
        chapter_count, last_chapter_num = self._get_current_chapter_info()
        # 确定下一章的章节号
        if last_chapter_num > 0:
            next_chapter_num = last_chapter_num + 1
        else:
            # 如果没有找到章节号，使用章节数量+1
            next_chapter_num = chapter_count + 1
        
        # 检查是否超过最大章节号
        max_chapter_num = self._extract_max_chapter_number_from_outline()
        if max_chapter_num and next_chapter_num > max_chapter_num:
            return None
        
        # 在大纲中查找对应章节
        # 匹配格式：第X章：标题 - 描述
        pattern = rf'第{next_chapter_num}章[：:]\s*([^\n]+)'
        match = re.search(pattern, self.novel_outline)
        if match:
            title_with_desc = match.group(1).strip()
            # 清理标题，去除描述部分
            title = self._clean_chapter_title(title_with_desc)
            return title
        
        return None

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
        # 检查是否已经到达最后一章（检查当前章节）
        if self._is_last_chapter():
            self._story_completed = True
            raise StoryEnded("故事已经完成，所有章节都已写完。")
        
        # 检查下一章是否会超过最大章节号（更严格的检查）
        if self._will_exceed_max_chapter():
            self._story_completed = True
            raise StoryEnded("故事已经完成，所有章节都已写完。")
        
        if user_requirements:
            self.user_requirements = user_requirements
        if embellishment_idea:
            self.embellishment_idea = embellishment_idea

        recent_context = self.get_recent_context()
        
        # 从大纲中提取下一章的标题
        expected_chapter_title = self._extract_next_chapter_title_from_outline()
        
        # 如果无法提取下一章标题（可能已经完成），再次检查
        if expected_chapter_title is None:
            if self._will_exceed_max_chapter():
                self._story_completed = True
                raise StoryEnded("故事已经完成，所有章节都已写完。")
        chapter_count, last_chapter_num = self._get_current_chapter_info()
        next_chapter_num = last_chapter_num + 1 if last_chapter_num > 0 else chapter_count + 1
        
        # 如果找到了预期的章节标题，在用户要求中添加提示
        chapter_hint = ""
        if expected_chapter_title:
            chapter_hint = f"\n\n重要提示：当前应该写第{next_chapter_num}章，章节标题应该是：{expected_chapter_title}。请务必使用这个标题，不要使用之前的章节标题。"
        
        user_req_with_hint = (self.user_requirements or "") + chapter_hint

        resp = self.novel_writer.invoke_with_parsed_output(
            inputs={
                self.inputs["idea"]: self.user_idea,
                self.inputs["outline"]: self.novel_outline,
                self.inputs["memory_prev"]: self.writing_memory,
                self.inputs["temporary"]: self.temporary_setting,
                self.inputs["plan"]: self.writing_plan,
                self.inputs["requirements"]: user_req_with_hint,
                self.inputs["previous"]: recent_context,
            },
            output_keys=[
                self.keys["paragraph_title"],   # 当前章节标题
                self.keys["paragraph"],       # 段落内容
                self.keys["plan"],            # 计划
                self.keys["temporary"],       # 临时设定
            ],
        )
        
        paragraph_title = resp[self.keys["paragraph_title"]]
        next_paragraph = resp[self.keys["paragraph"]]
        next_writing_plan = resp[self.keys["plan"]]
        next_temp_setting = resp[self.keys["temporary"]]

        # 清理LLM返回的标题，去除可能的描述性文字
        if paragraph_title:
            paragraph_title = self._clean_chapter_title(paragraph_title)

        # 验证标题不为空
        if not paragraph_title or not paragraph_title.strip():
            # 如果标题为空，尝试使用从大纲中提取的标题
            if expected_chapter_title:
                print(f"警告: LLM返回的标题为空，使用从大纲中提取的标题: {expected_chapter_title}")
                paragraph_title = expected_chapter_title
            else:
                raise ValueError(f"章节标题为空，无法继续生成。解析结果: {resp}")
        # 如果找到了预期的章节标题，验证返回的标题是否正确
        elif expected_chapter_title:
            # 检查返回的标题是否与预期标题匹配（允许部分匹配，因为可能包含"第X章："前缀）
            returned_title_clean = paragraph_title.strip()
            expected_title_clean = expected_chapter_title.strip()
            
            # 如果返回的标题不包含预期的标题，使用预期的标题
            if expected_title_clean not in returned_title_clean and returned_title_clean not in expected_title_clean:
                # 检查是否是同一章节的不同表示方式
                returned_chapter_num = self._extract_chapter_number_from_title(returned_title_clean)
                if returned_chapter_num != next_chapter_num:
                    print(f"警告: LLM返回的标题 '{returned_title_clean}' 与预期标题 '{expected_chapter_title}' 不匹配，使用预期标题")
                    paragraph_title = expected_chapter_title
                # 如果章节号匹配，但标题不同，可能是LLM使用了不同的标题格式，保留LLM的标题但记录警告
                else:
                    print(f"提示: LLM返回的标题 '{returned_title_clean}' 与大纲中的标题 '{expected_chapter_title}' 不同，但章节号匹配，保留LLM的标题")

        # 润色
        polish_resp = self.novel_embellisher.invoke_with_parsed_output(
            inputs={
                self.inputs["outline"]: self.novel_outline,
                self.inputs["temporary"]: next_temp_setting,
                self.inputs["plan"]: next_writing_plan,
                self.inputs["polish"]: self.embellishment_idea,
                self.inputs["context"]: recent_context,
                self.inputs["polish_target"]: next_paragraph,
            },
            output_keys=[self.keys["polish"]],
        )
        # 确保使用润色后的结果
        polished_paragraph = polish_resp[self.keys["polish"]]
        if not polished_paragraph or not polished_paragraph.strip():
            # 如果润色结果为空，使用原始段落
            print("警告: 润色结果为空，使用原始段落")
            polished_paragraph = next_paragraph
        next_paragraph = polished_paragraph

        # 将章节标题和内容组合
        paragraph_with_title = f"## {paragraph_title.strip()}\n\n{next_paragraph}"
        
        self.paragraphs.append(paragraph_with_title)
        self.writing_plan = next_writing_plan
        self.temporary_setting = next_temp_setting

        # 使用润色后的内容更新记忆
        self.pending_memory_text += f"\n{next_paragraph}"
        self.update_memory()
        self.update_novel_content()
        self.record_novel()

        # 检查生成完这一章后是否到达最后一章
        if self._is_last_chapter() or self._will_exceed_max_chapter():
            self._story_completed = True
            print(f"故事已完成，已标记为完成状态")

        return paragraph_with_title

    def optimize_dialogue(self, dialogue_content, context=None, optimization_requirements=None):
        """
        优化小说中的对话内容
        
        Args:
            dialogue_content: 要优化的对话内容
            context: 对话发生的上下文（可选）
            optimization_requirements: 用户提出的特殊优化要求（可选）
        
        Returns:
            优化后的对话内容
        """
        if self.is_aborted():
            raise ProcessAborted()
        
        inputs = {
            self.inputs["outline"]: self.novel_outline,
            self.inputs["temporary"]: self.temporary_setting,
            self.inputs["plan"]: self.writing_plan,
            self.inputs["dialogue_target"]: dialogue_content,
        }
        
        if context:
            inputs[self.inputs["context"]] = context
        
        if optimization_requirements:
            inputs[self.inputs["dialogue_optimization"]] = optimization_requirements
        
        resp = self.dialogue_optimizer.invoke_with_parsed_output(
            inputs=inputs,
            output_keys=[self.keys["optimized_dialogue"]],
        )
        
        return resp[self.keys["optimized_dialogue"]]

    def request_abort(self):
        self._abort_flag = True

    def is_aborted(self):
        return self._abort_flag
