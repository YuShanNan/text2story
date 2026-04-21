import re
import chardet

from utils.logger import get_logger

logger = get_logger(__name__)


def detect_encoding(file_path: str) -> str:
    """自动检测文件编码"""
    with open(file_path, "rb") as f:
        raw = f.read()
    result = chardet.detect(raw)
    encoding = result.get("encoding") or "utf-8"
    confidence = result.get("confidence", 0)
    logger.debug(f"检测到编码: {encoding} (置信度: {confidence:.2%})")
    return encoding


def convert_srt_to_txt(srt_path: str) -> str:
    """
    将 SRT 字幕文件转为纯文本。
    仅做格式转换（去除序号、时间轴、HTML 标签），不做语义处理。
    """
    encoding = detect_encoding(srt_path)
    with open(srt_path, "r", encoding=encoding, errors="replace") as f:
        content = f.read()

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
        # 跳过序号行
        if index_pattern.match(line):
            continue
        # 跳过时间轴行
        if time_pattern.match(line):
            continue
        # 去除 HTML 标签
        clean_line = html_pattern.sub("", line).strip()
        if clean_line:
            text_lines.append(clean_line)

    result = "\n".join(text_lines)
    logger.info(f"SRT 转换完成: 提取 {len(text_lines)} 行文本")
    return result
