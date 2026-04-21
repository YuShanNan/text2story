import unittest
from unittest.mock import Mock, call, patch

import requests

from api.openai_client import OpenAICompatClient


class OpenAICompatClientRetryTest(unittest.TestCase):
    def _make_response(self) -> Mock:
        response = Mock()
        response.raise_for_status.return_value = None
        response.encoding = "utf-8"
        return response

    def test_chat_retries_until_success_when_max_retry_is_zero(self):
        client = OpenAICompatClient(
            base_url="https://api.example.com",
            api_key="test-key",
            max_retry=0,
            timeout=30,
        )
        response = self._make_response()

        with (
            patch(
                "api.openai_client.requests.post",
                side_effect=[
                    requests.exceptions.Timeout(),
                    requests.exceptions.ConnectionError(),
                    response,
                ],
            ) as post,
            patch.object(client, "_parse_sse_stream", return_value="成功内容"),
            patch("api.openai_client.time.sleep") as sleep,
        ):
            result = client.chat(
                model="test-model",
                system_prompt="系统提示词",
                user_content="用户内容",
            )

        self.assertEqual("成功内容", result)
        self.assertEqual(3, post.call_count)
        self.assertEqual([call(2), call(4)], sleep.call_args_list)

    def test_chat_stops_after_configured_attempts(self):
        client = OpenAICompatClient(
            base_url="https://api.example.com",
            api_key="test-key",
            max_retry=2,
            timeout=30,
        )

        with (
            patch(
                "api.openai_client.requests.post",
                side_effect=requests.exceptions.Timeout(),
            ) as post,
            patch("api.openai_client.time.sleep") as sleep,
        ):
            with self.assertRaisesRegex(RuntimeError, "API 调用失败"):
                client.chat(
                    model="test-model",
                    system_prompt="系统提示词",
                    user_content="用户内容",
                )

        self.assertEqual(2, post.call_count)
        self.assertEqual([call(2)], sleep.call_args_list)


if __name__ == "__main__":
    unittest.main()
