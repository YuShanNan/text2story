"""API 客户端工厂：创建一个统一的 OpenAI 兼容客户端。"""
from config import Config
from api.openai_client import OpenAICompatClient
from utils.logger import get_logger

logger = get_logger(__name__)


class ClientBundle:
    """封装统一模型客户端及其模型配置"""

    def __init__(self, client: OpenAICompatClient, model: str):
        self.client = client
        self.model = model


def create_clients() -> ClientBundle:
    """创建统一模型客户端。"""
    if not Config.MODEL_API_KEY:
        raise ValueError(
            "未配置 MODEL_API_KEY\n"
            "请在 .env 中填写统一模型 API Key"
        )
    if not Config.MODEL_NAME:
        raise ValueError(
            "未配置 MODEL_NAME\n"
            "请在 .env 中填写统一模型名称"
        )

    client = OpenAICompatClient(
        base_url=Config.MODEL_BASE_URL,
        api_key=Config.MODEL_API_KEY,
        max_retry=Config.MAX_RETRY,
        timeout=Config.REQUEST_TIMEOUT,
    )

    logger.info("API 客户端已创建: %s (%s)", Config.MODEL_NAME, Config.MODEL_BASE_URL)
    return ClientBundle(client=client, model=Config.MODEL_NAME)
