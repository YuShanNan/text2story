import requests
import time
import json

from utils.logger import get_logger
from utils.retry_utils import format_retry_limit, retry_wait_seconds, should_retry_attempt

logger = get_logger(__name__)


class OpenAICompatClient:
    """统一的 OpenAI 兼容 API 客户端"""

    def __init__(self, base_url: str, api_key: str, max_retry: int = 3,
                 timeout: int = 300, thinking_enabled: bool = False):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_retry = max_retry
        self.timeout = timeout
        self.thinking_enabled = thinking_enabled

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _parse_sse_stream(self, response) -> tuple[str, str]:
        """
        解析 SSE 流式响应，逐块读取并拼接内容。支持 Ctrl+C 即时中断。
        返回 (content, reasoning_content) 元组。
        """
        content_parts = []
        reasoning_parts = []
        raw_data_lines = []

        for line in response.iter_lines(decode_unicode=True):
            if line is None:
                continue
            line = line.strip()
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)

                if "error" in chunk and "choices" not in chunk:
                    err_msg = chunk["error"]
                    if isinstance(err_msg, dict):
                        err_msg = err_msg.get("message", str(err_msg))
                    raise RuntimeError(f"API 返回错误: {err_msg}")

                delta = chunk.get("choices", [{}])[0].get("delta", {})
                rc = delta.get("reasoning_content", "")
                if rc:
                    reasoning_parts.append(rc)
                text = delta.get("content", "")
                if text:
                    content_parts.append(text)
            except RuntimeError:
                raise
            except (json.JSONDecodeError, KeyError, IndexError):
                raw_data_lines.append(data_str[:200])
                continue

        content = "".join(content_parts)
        reasoning = "".join(reasoning_parts)

        if not content.strip() and not reasoning.strip() and raw_data_lines:
            logger.debug(
                f"SSE 流解析完毕但内容为空，"
                f"共收到 {len(raw_data_lines)} 条未解析的 data 行，"
                f"最后一条: {raw_data_lines[-1]}"
            )

        return content, reasoning

    def chat_multi_turn(self, model: str, messages: list[dict],
                        temperature: float = 0.7, max_tokens: int = 4096,
                        fallback_model: str = None,
                        thinking_enabled: bool = None) -> str:
        """
        多轮对话请求（流式模式）。
        messages 为完整的角色消息列表，如 [{"role": "system", ...}, {"role": "user", ...}, ...]。
        使用 SSE 流式传输，支持 Ctrl+C 即时中断。
        fallback_model: 备用模型，主模型全部重试失败后自动切换
        thinking_enabled: 是否启用深度思考模式（仅 DeepSeek V3.2+ 等支持）
        """
        if thinking_enabled is None:
            thinking_enabled = self.thinking_enabled

        models_to_try = [model]
        if fallback_model and fallback_model != model:
            models_to_try.append(fallback_model)

        last_error = None
        retry_limit_label = format_retry_limit(self.max_retry)
        for current_model in models_to_try:
            if current_model != model:
                logger.warning(f"主模型 {model} 不可用，切换到备用模型 {current_model}")

            attempt = 0
            while True:
                attempt += 1
                try:
                    logger.debug(
                        f"API 调用 (model={current_model}, "
                        f"attempt={attempt}/{retry_limit_label})"
                    )
                    payload = {
                        "model": current_model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "stream": True,
                    }
                    if thinking_enabled:
                        payload["thinking"] = {"type": "enabled"}

                    response = requests.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                        timeout=(30, self.timeout),
                        stream=True,
                    )
                    response.raise_for_status()
                    response.encoding = "utf-8"

                    content, reasoning = self._parse_sse_stream(response)

                    if reasoning.strip():
                        logger.info(
                            f"思考过程 ({current_model}): "
                            f"{reasoning[:200]}{'...' if len(reasoning) > 200 else ''}"
                        )
                        logger.debug(f"完整思考过程: {reasoning}")

                    if not content.strip():
                        raise ValueError(
                            f"API 返回空内容 (model={current_model}, "
                            f"attempt={attempt}/{retry_limit_label})"
                        )

                    if current_model != model:
                        logger.info(f"备用模型 {current_model} 调用成功")
                    return content
                except KeyboardInterrupt:
                    raise
                except requests.exceptions.Timeout:
                    last_error = "请求超时"
                    logger.warning(
                        f"API 调用超时 ({current_model}, "
                        f"attempt {attempt}/{retry_limit_label})"
                    )
                except requests.exceptions.ConnectionError:
                    last_error = "无法连接到 API 服务"
                    logger.warning(
                        f"连接失败 ({current_model}, "
                        f"attempt {attempt}/{retry_limit_label})"
                    )
                except requests.exceptions.HTTPError as e:
                    status = e.response.status_code
                    body = ""
                    try:
                        body = e.response.text
                    except Exception:
                        pass
                    last_error = f"HTTP {status}: {body[:200]}"
                    logger.warning(
                        f"HTTP 错误 {status} ({current_model}, "
                        f"attempt {attempt}/{retry_limit_label})"
                    )
                except (KeyError, IndexError) as e:
                    last_error = f"API 返回数据格式异常: {e}"
                    logger.warning(f"响应解析失败: {e}")
                except RuntimeError as e:
                    last_error = str(e)
                    logger.warning(f"远程服务错误: {e}")
                except ValueError as e:
                    last_error = str(e)
                    logger.warning(f"内容校验失败: {e}")
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"未知错误: {e}")

                if not should_retry_attempt(attempt, self.max_retry):
                    break

                wait = retry_wait_seconds(attempt)
                logger.info(f"等待 {wait} 秒后重试... ({attempt + 1}/{retry_limit_label})")
                time.sleep(wait)

        raise RuntimeError(f"API 调用失败（已重试所有模型）: {last_error}")

    def chat(self, model: str, system_prompt: str, user_content: str,
             temperature: float = 0.7, max_tokens: int = 4096,
             fallback_model: str = None, thinking_enabled: bool = None) -> str:
        """单轮对话请求，委托给 chat_multi_turn。"""
        return self.chat_multi_turn(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            fallback_model=fallback_model,
            thinking_enabled=thinking_enabled,
        )
