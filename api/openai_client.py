import requests
import time
import json

from utils.logger import get_logger
from utils.retry_utils import format_retry_limit, retry_wait_seconds, should_retry_attempt

logger = get_logger(__name__)


class OpenAICompatClient:
    """统一的 OpenAI 兼容 API 客户端"""

    def __init__(self, base_url: str, api_key: str, max_retry: int = 3,
                 timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_retry = max_retry
        self.timeout = timeout

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _parse_sse_stream(self, response) -> str:
        """解析 SSE 流式响应，逐块读取并拼接内容。支持 Ctrl+C 即时中断。"""
        content_parts = []
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
                text = delta.get("content", "")
                if text:
                    content_parts.append(text)
            except RuntimeError:
                raise
            except (json.JSONDecodeError, KeyError, IndexError):
                raw_data_lines.append(data_str[:200])
                continue

        result = "".join(content_parts)

        if not result.strip() and raw_data_lines:
            logger.debug(
                f"SSE 流解析完毕但内容为空，"
                f"共收到 {len(raw_data_lines)} 条未解析的 data 行，"
                f"最后一条: {raw_data_lines[-1]}"
            )

        return result

    def chat(self, model: str, system_prompt: str, user_content: str,
             temperature: float = 0.7, max_tokens: int = 4096,
             fallback_model: str = None) -> str:
        """
        发送对话请求（流式模式）。
        使用 SSE 流式传输，可实时接收数据并支持 Ctrl+C 即时中断。
        fallback_model: 备用模型，主模型全部重试失败后自动切换
        max_retry: 单模型总尝试次数，0 表示无限重试
        """
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
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "stream": True,
                    }
                    response = requests.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                        timeout=(30, self.timeout),
                        stream=True,
                    )
                    response.raise_for_status()
                    response.encoding = "utf-8"

                    content = self._parse_sse_stream(response)

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
