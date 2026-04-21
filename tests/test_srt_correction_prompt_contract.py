import os
import re
import unittest

from utils.file_utils import read_file


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
SRT_CORRECTION_PROMPT_PATH = os.path.join(
    PROJECT_ROOT, "prompts", "srt_correction", "default.txt"
)


def load_prompt():
    return read_file(SRT_CORRECTION_PROMPT_PATH)


def assert_prompt_contains_any(testcase, prompt, tokens, message):
    testcase.assertTrue(any(token in prompt for token in tokens), msg=message)


def assert_prompt_matches_any(testcase, prompt, patterns, message):
    testcase.assertTrue(
        any(re.search(pattern, prompt) for pattern in patterns),
        msg=f"{message}; patterns={patterns!r}",
    )


class SrtCorrectionPromptContractTest(unittest.TestCase):
    def test_prompt_preserves_srt_format_and_allows_same_block_minimal_reflow(self):
        prompt = load_prompt()

        for expected in (
            "SRT格式",
            "时间戳",
            "原文每一句话的字词顺序",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, prompt)

        assert_prompt_matches_any(
            self,
            prompt,
            (
                r"(同一字幕块内|同一字幕块|单个字幕块内|块内).{0,18}"
                r"(重排|换行|重组|断行|调整顺序).{0,18}"
                r"(最小化修改|仅限|只允许|只做|仅做|最少改动)",
                r"(重排|换行|重组|断行|调整顺序).{0,18}"
                r"(同一字幕块内|同一字幕块|单个字幕块内|块内).{0,18}"
                r"(最小化修改|仅限|只允许|只做|仅做|最少改动)",
            ),
            "should express same-block minimal reflow as one semantic rule",
        )

    def test_prompt_forbids_cross_block_reflow_and_strengthens_correction_guidance(self):
        prompt = load_prompt()

        assert_prompt_matches_any(
            self,
            prompt,
            (
                r"(每个|各个|单个).{0,10}(字幕块|块).{0,12}(输出|生成|改写).{0,12}"
                r"(仅|只能|必须|都应).{0,12}(来自|取自|源自).{0,12}(本块|该块|当前块).{0,12}"
                r"(原文|原始文本|原始内容)",
                r"(输出|生成|改写).{0,12}(文本|内容).{0,12}"
                r"(仅|只能|必须|都应).{0,12}(来自|取自|源自).{0,12}(本块|该块|当前块).{0,12}"
                r"(原文|原始文本|原始内容)",
            ),
            "should require each block's output to come only from that block's original text",
        )
        assert_prompt_matches_any(
            self,
            prompt,
            (
                r"(不得|禁止|不要|勿|严禁).{0,12}(借用|挪用|引用|拼接).{0,12}"
                r"(相邻|前一|后一|上下).{0,12}(字幕块|块).{0,12}"
                r"(来完成|补全|凑成|补齐|补足).{0,12}(当前|本|该).{0,12}(字幕块|块)",
                r"(当前|本|该).{0,12}(字幕块|块).{0,12}"
                r"(不得|禁止|不要|勿|严禁).{0,12}(借用|挪用|引用|拼接).{0,12}"
                r"(相邻|前一|后一|上下).{0,12}(字幕块|块)",
            ),
            "should explicitly forbid borrowing adjacent-block text to complete the current block",
        )

        for label, patterns in (
            (
                "cross-block reflow",
                (
                    r"(禁止|不得|不要|勿|严禁).{0,12}(跨字幕块|跨块|跨字幕)",
                    r"(跨字幕块|跨块|跨字幕).{0,12}(禁止|不得|不要|勿|严禁)",
                ),
            ),
            (
                "polish/optimization",
                (
                    r"(禁止|不得|不要|勿|严禁).{0,12}(润色|优化|修饰)",
                    r"(润色|优化|修饰).{0,12}(禁止|不得|不要|勿|严禁)",
                ),
            ),
            (
                "meaning rewrite",
                (
                    r"(禁止|不得|不要|勿|严禁).{0,12}(改写原意|改动原意|擅自改写)",
                    r"(改写原意|改动原意|擅自改写).{0,12}(禁止|不得|不要|勿|严禁)",
                ),
            ),
        ):
            with self.subTest(forbidden=label):
                assert_prompt_matches_any(
                    self,
                    prompt,
                    patterns,
                    f"should explicitly prohibit {label}",
                )

        assert_prompt_contains_any(
            self,
            prompt,
            ("不确定", "不确定时", "若不确定", "少改", "尽量少改"),
            "should mention uncertainty/minimal-correction guidance",
        )
        assert_prompt_contains_any(
            self,
            prompt,
            ("错别字", "漏字", "多字", "专有名词", "代词"),
            "should keep correction guidance focused on concrete error types",
        )


if __name__ == "__main__":
    unittest.main()
