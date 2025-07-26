# splitter.py
import subprocess  # 用于调用外部程序(ffmpeg/ffprobe)
import os
import math
import concurrent.futures  # 用于线程池并发处理
from ..utils import retry  # 导入重试装饰器


def get_media_duration(media_path: str) -> float | None:
    """
    使用 ffprobe 获取媒体文件总时长（秒）, 适用于视频和音频.

    :param media_path: 媒体文件的路径.
    :return: 媒体文件的总时长（秒）, 或 None 如果无法获取.
    """

    # 构造 ffprobe 命令, 获取媒体文件的总时长
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        media_path,
    ]
    # 尝试执行命令, 并返回解析后的时长
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return float(result.stdout)
    except FileNotFoundError:
        print(
            "错误：找不到 'ffprobe' 命令。请确保 FFmpeg 已经完全安装，并且其 bin 目录已添加到了系统的 PATH 环境变量中。"
        )
        return None
    except subprocess.CalledProcessError as e:
        print(f"ffprobe 执行失败，可能是文件已损坏或格式不支持: {e.stderr}")
        return None
    except Exception as e:
        print(f"获取媒体时长时发生错误: {e}")
        return None


@retry(max_retries=3, delay=2, allowed_exceptions=(subprocess.CalledProcessError,))
def _process_chunk(args) -> str | None:
    """
    (工作函数) 处理单个音频块的生成.

    :param args: 包含参数的元组.
    :return: 处理完成的音频块路径，或 None 如果处理失败。
    """
    media_path, output_dir, chunk_duration, i, num_chunks = args
    start_time = i * chunk_duration
    output_filename = os.path.join(output_dir, f"chunk_{i+1:03d}.mp3")

    # 构造ffmpeg命令, 用于提取指定时间段的音频并转为MP3
    command = [
        "ffmpeg",
        "-i",
        media_path,
        "-ss",
        str(start_time),
        "-t",
        str(chunk_duration),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-q:a",
        "2",
        "-y",
        output_filename,
    ]

    try:
        print(f"开始生成第 {i+1}/{num_chunks} 个音频块: {output_filename}")
        # 捕获标准错误和标准输出, 以防止它们直接打印, 除非发生错误
        subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"完成生成第 {i+1}/{num_chunks} 个音频块。")
        return output_filename
    except subprocess.CalledProcessError as e:
        # 重试装饰器会处理这个异常, 但在重新抛出前, 我们会记录日志以便明确问题所在
        print(f"处理第 {i+1} 个音频块时失败: {e.stderr}")
        raise e  # 重新抛出异常来触发重试
    except FileNotFoundError:
        print(
            "错误：找不到 'ffmpeg' 命令。请确保 FFmpeg 已经完全安装，并且其 bin 目录已添加到了系统的 PATH 环境变量中。"
        )
        # 这是设置错误, 不需要重试
        return None


def split_media_to_audio_chunks_generator(
    media_path: str, output_dir: str, chunk_duration: int = 600
):
    """
    (生成器版本) 将媒体文件切分为音频块, 并实时产出进度.
    产出事件: ('progress', 已完成数量, 总数量)
              ('result', 输出文件列表)
              ('error', 错误信息)

    :param media_path: 媒体文件的路径.
    :param output_dir: 输出目录.
    :param chunk_duration: 每个音频块的持续时间（秒）.
    :return: 生成器, 产出进度和结果.
    """
    if not os.path.exists(media_path):
        yield "error", f"错误：媒体文件 '{media_path}' 不存在。", None
        return

    try:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
    except OSError as e:
        yield "error", f"错误：创建输出目录 '{output_dir}' 失败: {e}", None
        return

    duration = get_media_duration(media_path)
    if not duration:
        yield "error", "无法获取媒体文件时长。", None
        return

    # 计算音频块数量
    num_chunks = math.ceil(duration / chunk_duration)
    if num_chunks == 0:
        yield "result", []
        return

    print(f"媒体总时长: {duration:.2f}秒, 将被切分为 {num_chunks} 个音频块。")

    # 准备所有任务参数
    tasks_args = [
        (media_path, output_dir, chunk_duration, i, num_chunks)
        for i in range(num_chunks)
    ]

    output_files = []
    completed_count = 0

    # 使用线程池并发处理任务
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        # 提交所有任务
        future_to_args = {
            executor.submit(_process_chunk, args): args for args in tasks_args
        }
        for future in concurrent.futures.as_completed(future_to_args):
            try:
                result = future.result()
                if result:
                    output_files.append(result)
            except Exception as e:
                # 如果一个块在多次尝试后仍然无法处理, 则异常在这里被抛出.
                yield "error", f"一个音频块在多次尝试后仍然无法处理，已停止。错误: {e}", None
                # 停止线程池并取消未完成任务
                executor.shutdown(wait=False, cancel_futures=True)
                return

            # 每完成一个块, 输出进度
            completed_count += 1
            yield "progress", completed_count, num_chunks

    if not output_files or len(output_files) != num_chunks:
        yield "error", "未能成功生成所有音频块，可能部分块处理失败。", None
        return

    yield "result", sorted(output_files)
