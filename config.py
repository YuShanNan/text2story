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
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "300"))
    MAX_CHUNK_SIZE = int(os.getenv("MAX_CHUNK_SIZE", "3000"))

    # 路径
    PROMPTS_DIR = "prompts"
    OUTPUT_DIR = "output"
    INPUT_DIR = "input"
