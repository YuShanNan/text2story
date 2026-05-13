from dotenv import load_dotenv
import os

load_dotenv(override=True)


class Config:
    # 通用模型配置（统一用于修正 / 分镜 / 提示词 / 优化）
    MODEL_API_KEY = os.getenv("MODEL_API_KEY", "")
    MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "https://api.deepseek.com")
    MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")

    # 通用配置
    MAX_RETRY = int(os.getenv("MAX_RETRY", "5"))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "120"))
    MAX_CHUNK_SIZE = int(os.getenv("MAX_CHUNK_SIZE", "15000"))
    SRT_MAX_CHUNK_SIZE = int(os.getenv("SRT_MAX_CHUNK_SIZE", "1000"))
    STORYBOARD_MAX_CHUNK_SIZE = int(os.getenv("STORYBOARD_MAX_CHUNK_SIZE", "500"))
    THINKING_ENABLED = os.getenv("THINKING_ENABLED", "false").lower() == "true"
    # 分步思考模式（仅适配 DeepSeek，默认继承全局 THINKING_ENABLED）
    SRT_THINKING = os.getenv("SRT_THINKING", str(THINKING_ENABLED)).lower() == "true"
    STORYBOARD_THINKING = os.getenv("STORYBOARD_THINKING", str(THINKING_ENABLED)).lower() == "true"
    OPTIMIZE_THINKING = os.getenv("OPTIMIZE_THINKING", str(THINKING_ENABLED)).lower() == "true"
    VIDEO_THINKING = os.getenv("VIDEO_THINKING", str(THINKING_ENABLED)).lower() == "true"
    # 思考强度控制（仅 DeepSeek 思考模式，high / max）
    REASONING_EFFORT = os.getenv("REASONING_EFFORT", "high")
    SRT_REASONING_EFFORT = os.getenv("SRT_REASONING_EFFORT", REASONING_EFFORT)
    STORYBOARD_REASONING_EFFORT = os.getenv("STORYBOARD_REASONING_EFFORT", REASONING_EFFORT)
    OPTIMIZE_REASONING_EFFORT = os.getenv("OPTIMIZE_REASONING_EFFORT", REASONING_EFFORT)
    VIDEO_REASONING_EFFORT = os.getenv("VIDEO_REASONING_EFFORT", REASONING_EFFORT)

    # 路径
    PROMPTS_DIR = "prompts"
    OUTPUT_DIR = "output"
    INPUT_DIR = "input"
