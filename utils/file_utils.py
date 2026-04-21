import os
import chardet

from utils.logger import get_logger

logger = get_logger(__name__)

_PROMPT_ALIASES = {
    ("storyboard", "default"): "（默认）分镜提示词.txt",
    ("storyboard", "默认分镜提示词"): "（默认）分镜提示词.txt",
}


def ensure_dir(path: str) -> None:
    """确保目录存在，不存在则创建"""
    os.makedirs(path, exist_ok=True)


def read_file(path: str, encoding: str | None = None) -> str:
    """读取文件内容，自动检测编码"""
    if encoding is None:
        with open(path, "rb") as f:
            raw = f.read()
        detected = chardet.detect(raw)
        encoding = detected.get("encoding") or "utf-8"
    with open(path, "r", encoding=encoding, errors="replace") as f:
        return f.read()


def write_file(
    path: str,
    content: str,
    encoding: str = "utf-8-sig",
    log_saved: bool = True,
) -> None:
    """写入文件，自动创建父目录"""
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding=encoding) as f:
        f.write(content)
    if log_saved:
        logger.info(f"文件已保存: {path}")


def get_stem(path: str) -> str:
    """获取文件名（不含扩展名）"""
    return os.path.splitext(os.path.basename(path))[0]


def get_safe_stem(path: str, relative_to: str = "") -> str:
    """
    获取唯一的文件标识名，避免不同目录下同名文件冲突。
    如 input/ep1/story.srt → 'ep1_story'
    如 input/story.srt     → 'story'
    """
    if relative_to:
        rel = os.path.relpath(path, relative_to)
    else:
        rel = os.path.basename(path)
    stem = os.path.splitext(rel)[0]
    # 将路径分隔符替换为下划线
    stem = stem.replace(os.sep, "_").replace("/", "_")
    return stem


def get_output_dir_for_file(stem: str) -> str:
    """根据 stem 生成按文件归类的输出目录路径: output/{stem}/"""
    from config import Config
    return os.path.join(Config.OUTPUT_DIR, stem)


def load_prompt(prompts_dir: str, category: str,
                name: str = "default") -> str:
    """
    加载系统提示词。
    prompts_dir: 提示词根目录
    category: 子目录名（如 correction, storyboard, image_prompt, video_prompt）
    name: 提示词文件名（不含 .txt 后缀）
    """
    prompt_path = os.path.join(prompts_dir, category, f"{name}.txt")
    if not os.path.exists(prompt_path):
        alias_name = _PROMPT_ALIASES.get((category, name))
        if alias_name:
            prompt_path = os.path.join(prompts_dir, category, alias_name)
    if not os.path.exists(prompt_path):
        raise FileNotFoundError(
            f"提示词文件不存在: {prompt_path}\n"
            f"请在 {os.path.join(prompts_dir, category)}/ 目录下创建 {name}.txt"
        )
    content = read_file(prompt_path)
    logger.debug(f"已加载提示词: {prompt_path}")
    return content.strip()


def split_text(text: str, max_chars: int = 3000) -> list[str]:
    """
    将长文本按自然段落分割为多个块。
    每块不超过 max_chars 字符，避免在句子中间截断。
    """
    paragraphs = text.split("\n")
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current_chunk) + len(para) + 1 > max_chars and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = para
        else:
            current_chunk += "\n" + para if current_chunk else para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    # 如果没有分段成功（整段文本无换行），强制按字数切割
    if len(chunks) == 1 and len(chunks[0]) > max_chars:
        text = chunks[0]
        chunks = []
        for i in range(0, len(text), max_chars):
            chunks.append(text[i:i + max_chars])

    logger.debug(f"文本分段: {len(chunks)} 段")
    return chunks
