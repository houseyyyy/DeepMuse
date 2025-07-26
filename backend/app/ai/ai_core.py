import os
import shutil
from .video_processor.splitter import split_media_to_audio_chunks_generator
from .video_processor.transcriber import transcribe_single_audio_chunk
from .llm import run_deepseek_and_yield_results
from typing import Optional, List, Dict
import uuid
from ..config import settings
import pdfplumber
import docx
import win32com.client
import pandas as pd
from bs4 import BeautifulSoup

TEMP_DIR = settings.UPLOAD_DIR

def main_process(
    input_path: str,
    username: str,
    doubao_app_id: str,
    doubao_token: str,
    deepseek_api_key: str,
    output_filename: str,
    query: str,
    new_message: str,
    extra_requirements: Optional[str] = None,
    history: List[Dict[str, str]] = [],
    conversation_id: Optional[str] = None
):
    """
    统一处理入口：支持音视频/文本转写, 生成Notes/Quiz/Q&A

    产出事件:


    :param input_path: 上传文件的本地路径
    :param username: 用户名
    :param doubao_app_id: 豆包APP ID
    :param doubao_token: 豆包TOKEN
    :param deepseek_api_key: DeepSeek API KEY
    :param output_filename: 输出文件名（不带后缀）
    :param query: ("Notes"/"Quiz"/"Q&A")
    :param new_message: 新消息
    :param extra_requirements: 用户额外需求
    :param history: 对话历史, 用于Q&A
    :param conversation_id: 对话ID, 用于创建用户专属目录

    Yields:
        生成器产出元组：(事件类型, 值, [可选消息])
        事件类型可以是:
        - "progress": 主进度更新 (值: 0-1 之间的进度, 消息, 步骤详情)
        - "sub_progress": 子进度更新 (值: 0-1 之间的进度)
        - "llm_chunk": LLM生成的文本片段 (值: 文本片段)
        - "persistent_error": 持久性错误 (值: 错误代码, 消息: 错误信息)
        - "error": 临时错误 (值: 错误代码, 消息: 错误信息)
        - "done": 处理完成 (值: 最终文件路径, 消息: 完成信息)
    """

    # 支持的文件格式
    video_exts = {'.mp4', '.mov', '.mpeg', '.webm'}
    audio_exts = {'.mp3', '.m4a', '.wav', '.amr', '.mpga'}
    text_exts = {'.txt', '.md', '.mdx', '.markdown', '.pdf', '.html', '.xlsx', '.xls', '.doc', '.docx', '.csv', '.pptx', '.ppt'}

    file_ext = os.path.splitext(input_path)[1].lower() # 获取文件扩展名
    current_progress = 0  # 用于跟踪整体进度


    # 使用用户名和对话ID创建用户专属目录
    user_temp_dir = os.path.join(TEMP_DIR, username, str(conversation_id or uuid.uuid4()))
    os.makedirs(user_temp_dir, exist_ok=True)

    transcript_save_path = os.path.join(user_temp_dir, f"{output_filename}_transcript.txt") # 转录文本保存路径
    final_notes_save_path = os.path.join(user_temp_dir, f"{output_filename}_notes.md") # 最终笔记保存路径
    final_quiz_save_path = os.path.join(user_temp_dir, f"{output_filename}_quiz.md") # 最终 quiz 保存路径
    full_transcript = ""  # 存储完整的转录文本（文本文件直接读取, 音视频转写后拼接）
    history = history or []

    # 若为Q&A或Quiz模式，则直接读取文件
    if query == "Q&A" or query == "Quiz":
        try:
            with open(transcript_save_path, 'r', encoding='utf-8') as f:
                full_transcript = f.read()
        except Exception as e:
            user_friendly_error = f"**读取文件失败**\n\n无法读取您上传的文本文档 '{os.path.basename(input_path)}'。\n\n**原始错误信息:**\n`{e}`"
            yield "persistent_error", 0, user_friendly_error
            return

    # Notes模式执行完整流程
    else:
        # 文本文件直接读取
        if file_ext in text_exts:
            total_steps = 3  # 总步骤数

            # 步骤 1/3: 读取文本文件
            yield "progress", current_progress / total_steps, f"步骤 {current_progress + 1}/{total_steps}: 正在读取文本文档..."
            try:
                if file_ext == '.pdf':
                    with pdfplumber.open(input_path) as pdf:
                        full_transcript = "\n".join([page.extract_text() for page in pdf.pages])
                elif file_ext == '.docx':
                    doc = docx.Document(input_path)
                    full_transcript = "\n".join([para.text for para in doc.paragraphs])
                elif file_ext == '.doc':
                    word = win32com.client.Dispatch("Word.Application")
                    doc = word.Documents.Open(input_path)
                    full_transcript = doc.Content.Text
                    doc.Close()
                    word.Quit()
                elif file_ext in {'.xlsx', '.xls'}:
                    df = pd.read_excel(input_path)
                    full_transcript = df.to_string()
                elif file_ext == '.csv':
                    df = pd.read_csv(input_path)
                    full_transcript = df.to_string()
                elif file_ext == '.html':
                    with open(input_path, 'r', encoding='utf-8') as f:
                        soup = BeautifulSoup(f.read(), 'html.parser')
                        full_transcript = soup.get_text()
                elif file_ext in {'.pptx', '.ppt'}:
                    powerpoint = win32com.client.Dispatch("PowerPoint.Application")
                    presentation = powerpoint.Presentations.Open(input_path)
                    for slide in presentation.Slides:
                        for shape in slide.Shapes:
                            if hasattr(shape, "TextFrame"):
                                full_transcript += shape.TextFrame.TextRange.Text + "\n"
                    presentation.Close()
                    powerpoint.Quit()
                else: # 纯文本文件 (.txt, .md, .mdx, .markdown)
                    with open(input_path, 'r', encoding='utf-8') as f:
                        full_transcript = f.read()
            except Exception as e:
                user_friendly_error = f"**读取文件失败**\n\n无法读取您上传的文本文档 '{os.path.basename(input_path)}'。\n\n**原始错误信息:**\n`{e}`"
                yield "persistent_error", 0, user_friendly_error
                return

            current_progress += 1

        # 音视频文件需切分+转写
        elif file_ext in video_exts or file_ext in audio_exts:
            is_video = file_ext in video_exts # 是否为视频
            total_steps = 4
            step_name = "视频" if is_video else "音频"

            # 步骤 1/4: 切分音频块
            yield "progress", current_progress / total_steps, f"步骤 {current_progress + 1}/{total_steps}: 正在切分{step_name}为音频块..."
            output_dir = os.path.join(user_temp_dir, f"chunks_{output_filename}") # 存储音频快
            splitter_generator = split_media_to_audio_chunks_generator(input_path, output_dir, 600)
            audio_chunks = []

            # 处理生成器结果
            for event_type, val1, *val2 in splitter_generator:
                if event_type == 'progress':
                    completed, total = val1, val2[0]
                    yield "sub_progress", completed / total, f"正在切分... ({completed}/{total})"
                elif event_type == 'result':
                    audio_chunks = val1
                elif event_type == 'error':
                    user_friendly_error = f"**媒体文件切分失败**\n\n无法处理您上传的媒体文件。\n\n**原始错误信息:**\n`{val1}`"
                    yield "persistent_error", 0, user_friendly_error
                    return

            if not audio_chunks:
                yield "persistent_error", 0, f"**{step_name}切分失败**\n\n未能从您的文件中提取出任何音频块。"
                return

            yield "sub_progess", 1.0, f"✅ {step_name}切分全部完成！"
            current_progress += 1
            yield "progress", current_progress / total_steps, f"✅ {step_name}切分完成，准备开始转录..."

            # 步骤 2/4: 转录
            yield "progress", current_progress / total_steps, f"步骤 {current_progress + 1}/{total_steps}: 正在转录 {len(audio_chunks)} 个音频块..."
            all_transcripts = []  # 存储所有转录结果
            num_transcribed = 0  # 已转录的块数

            for i, chunk in enumerate(audio_chunks):
                try:
                    yield "sub_progress", num_transcribed / len(audio_chunks), f"正在转录块 {i+1}/{len(audio_chunks)}..."

                    # 转录单个音频块
                    transcript = transcribe_single_audio_chunk(chunk, doubao_app_id, doubao_token)
                    if transcript:
                        all_transcripts.append(transcript)
                    else:
                        raise Exception(f"音频块转录失败 (块索引: {i})")

                    # 更新转录进度
                    num_transcribed += 1
                    yield "sub_progress", num_transcribed / len(audio_chunks), f"已完成 {num_transcribed}/{len(audio_chunks)} 个块"
                except Exception as e:
                    error_msg = f"**音频块转录失败**\n\n块 {i+1} 转录失败，跳过此块。\n\n**错误信息:**\n`{e}`"
                    yield "error", 0, error_msg
                    # 在结果中留空，但继续处理下一个块
                    all_transcripts.append("")
                    num_transcribed += 1 # 仍然计数为已处理
                    yield "sub_progress", num_transcribed / len(audio_chunks), f"已完成 {num_transcribed}/{len(audio_chunks)} 个块 (跳过错误块)"

            # 检查是否所有块都处理失败
            if all(not t for t in all_transcripts):
                yield "persistent_error", 0, "**所有音频块转录失败**\n\n所有音频块在转录过程中都失败了。"
                return

            yield "sub_progress", 1.0, "✅ 音频转录全部完成！"
            current_progress += 1
            yield "progress", current_progress / total_steps, "所有音频快转录完成！"
            shutil.rmtree(output_dir, ignore_errors=True) # 删除临时音频快目录

            # 保存文字稿
            full_transcript = "\n\n".join(filter(None, all_transcripts))

        else:
            user_friendly_error = f"**不支持的文件类型**\n\n您上传的文件类型 (`{file_ext}`) 当前不受支持。"
            yield "error", 0, user_friendly_error
            return

        # 步骤 3/4(2/3): 保存文字稿
        yield "progress", current_progress / total_steps, f"步骤 {current_progress + 1}/{total_steps}: 正在保存文字稿..."
        try:
            with open(transcript_save_path, "w", encoding="utf-8") as f:
                f.write(full_transcript)
        except IOError as e:
            yield "error", 0, f"无法保存文字稿文件: {e}"

        current_progress += 1
        yield "progress", current_progress / total_steps, "文字稿汇总完成。"

        # 步骤 4/4(3/3): 调用DeepSeek模型生成内容
        yield "progress", current_progress / total_steps, f"步骤 {current_progress + 1}/{total_steps}: 正在调用DeepSeek模型生成内容..."

    if (query == "Quiz"):
        yield "progress", 1.0, "正在生成测试题..."
    final_path = None  # 笔记保存路径
    deepseek_gen = run_deepseek_and_yield_results(
        query=query,
        full_transcript=full_transcript,
        new_message=new_message,
        history=history,
        extra_requirements=extra_requirements,
        deepseek_api_key=deepseek_api_key,
        final_notes_save_path=final_notes_save_path,
        final_quiz_save_path=final_quiz_save_path,
    )

    # 处理调用结果
    for event_type, value, *rest in deepseek_gen:
        if event_type == "persistent_error":
            yield event_type, value, rest[0] if rest else ""
            return
        elif event_type == "llm_chunk":
            yield event_type, value
        elif event_type == "save_path":
            final_path = value

    if final_path:
        print("final_path: ", final_path)
        if query == "Q&A":
            print("QA: ", final_path)
            yield "done", final_path, "问答已生成！"
        elif query == "Quiz":
            print("Quiz: ", final_path)
            yield "done", final_path, "测试题已生成！"
        else:
            print("Notes: ", final_path)
            current_progress += 1
            yield "progress", current_progress / total_steps, "处理完成！"
            yield "done", final_path, "智能笔记已生成！"
    return
