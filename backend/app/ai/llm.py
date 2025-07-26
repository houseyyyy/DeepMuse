from openai import OpenAI
from typing import List, Optional, Dict
import os
import yaml

with open("app/ai/prompts.yml", "r", encoding="utf-8") as f:
    prompts = yaml.safe_load(f)
# print(prompts['system_roles']['Notes'])
# print(prompts['system_roles']['Quiz'])
# print(prompts['system_roles']['Q&A'])
# print(prompts['user_prompts']['Notes'])
# print(prompts['user_prompts']['Quiz'])
# print(prompts['user_prompts']['Q&A'])

def run_deepseek_and_yield_results(
        query: str, 
        full_transcript: str, 
        new_message: str,
        history: List[Dict[str, str]] = [], 
        extra_requirements: Optional[str] = None,
        deepseek_api_key: str = None, 
        final_notes_save_path: str = None,
        final_quiz_save_path: str = None,
):
    """
    调用 DeepSeek API 生成结果 (生成器)

    :param query: 查询类型，可以是 "Notes"、"Q&A" 或 "Quiz"
    :param full_transcript: 完整的音频转录结果
    :param new_message: 新的用户消息
    :param history: 对话历史, 用于Q&A
    :param extra_requirements: 额外的用户需求
    :param deepseek_api_key: DeepSeek API密钥
    :param final_notes_save_path: 最终笔记保存路径
    :param final_quiz_save_path: 测试题保存路径

    Yields:
        生成器产出元组：(事件类型, 值, [可选消息])
        事件类型可以是:
        - 'persistent_error', 错误代码, 错误信息
        - 'llm_chunk', 片段内容
        - 'save_path', 最终保存路径(Notes/Quiz)

    """
    try:
        # 创建 DeepSeek 客户端
        client = OpenAI(
            api_key=deepseek_api_key,
            base_url="https://api.deepseek.com/v1"  # DeepSeek API 端点
        )

        # 对话历史
        messages = [
            {"role": "system", "content": prompts['system_roles'][query]},
        ]  

        # 把history列表中的信息拼接到messages列表中
        messages.extend(history)
        # print("llm中拼接后的messages:",messages)

        # 根据查询类型构建提示
        prompt = prompts['user_prompts'][query]
        if query == "Notes":
            prompt += f"原始文本：\n{full_transcript}"
            if extra_requirements:  # 添加额外的用户需求
                prompt += f"\n\n额外的需求: {extra_requirements}"
        elif query == "Quiz":
            with open(final_notes_save_path, 'r', encoding='utf-8') as f:
                notes = f.read()  # 读取笔记
            prompt += f"原始文本：\n{full_transcript}\n\n笔记内容: \n{notes}"
        elif query == "Q&A":
            with open(final_notes_save_path, 'r', encoding='utf-8') as f:
                notes = f.read()  # 读取笔记
            extension = f"原始文本：\n{full_transcript}\n\n笔记内容: \n{notes}\n\n"
            # 如果存在文件final_quiz_save_path
            if os.path.exists(final_quiz_save_path):  
                with open(final_quiz_save_path, 'r', encoding='utf-8') as f:
                    quiz = f.read()  # 读取测试题
                extension += f"测试题：\n{quiz}\n\n"

            messages[0]["content"] += extension
            prompt = new_message
        else:
            print("无效的操作类型")
            yield "persistent_error", 0, f"**无效的操作类型**\n\n请求的操作 '{query}' 不是一个有效的选项 ('Notes', 'Q&A', 'Quiz')。"
            return

        messages.append({"role": "user", "content": prompt})
        print("llm中加入提示词后的messages:",messages)

        # 调用 DeepSeek API（流式响应）
        response = client.chat.completions.create(
            model="deepseek-chat",  # 使用 DeepSeek-V3 模型
            messages=messages,  # 对话历史
            stream=True,  # 启用流式响应
            max_tokens=4000,  # 控制结果长度
            temperature=0.7  # 创造性
        )

        # 处理流式响应
        collected_messages = []

        for chunk in response:
            if chunk.choices[0].delta.content is not None:
                message_text = chunk.choices[0].delta.content
                collected_messages.append(message_text)
                yield "llm_chunk", message_text

        # 保存完整响应
        full_response = ''.join(collected_messages)
        # print("llm中完整响应:",full_response)

        final_save_path = None
        if query == "Notes":
            final_save_path = final_notes_save_path
        elif query == "Quiz":
            final_save_path = final_quiz_save_path
        else: # 随便给Q&A一个地址, 用不上, 但是有地址才是有效AI回复
            final_save_path = "neccessary"

        if final_save_path: 
            try:
                if query != "Q&A":
                    with open(final_save_path, 'w', encoding='utf-8') as f:
                        f.write(full_response)
                yield "save_path", final_save_path
            except IOError as e:
                user_friendly_error = f"**保存{query}文件失败**\n\n无法将生成的{query}写入本地文件。\n\n**原始错误信息:**\n`{e}`"
                yield "persistent_error", 0, user_friendly_error

    except Exception as e:
        error_type = type(e).__name__
        if "Authentication" in error_type or "401" in str(e):
            user_friendly_error = "**认证失败**\n\nDeepSeek API密钥无效或过期。请检查您的API密钥配置。"
        elif "RateLimit" in error_type:
            user_friendly_error = "**请求限制**\n\n已达到DeepSeek API的速率限制。请稍后再试。"
        else:
            print(e)
            user_friendly_error = f"**API错误**\n\n调用DeepSeek API时发生错误：\n`{str(e)}`"
        yield "persistent_error", 0, user_friendly_error
