import re

from utils.file_utils import read_file
from utils.logger import get_logger

logger = get_logger(__name__)


def convert_srt_to_txt(srt_path: str) -> str:
    """
    将 SRT 字幕文件转为纯文本。
    仅做格式转换（去除序号、时间轴、HTML 标签），不做语义处理。
    """
    content = read_file(srt_path)

    lines = content.strip().split("\n")
    text_lines = []

    time_pattern = re.compile(
        r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}"
    )
    index_pattern = re.compile(r"^\d+$")
    html_pattern = re.compile(r"<[^>]+>")

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if index_pattern.match(line):
            continue
        if time_pattern.match(line):
            continue
        clean_line = html_pattern.sub("", line).strip()
        if clean_line:
            text_lines.append(clean_line)

    result = "\n".join(text_lines)
    logger.info(f"SRT 转换完成: 提取 {len(text_lines)} 行文本")
    return result
