import os
import unittest

from utils.file_utils import read_file, load_prompt


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DEFAULT_STORYBOARD_PROMPT_PATH = os.path.join(
    PROJECT_ROOT, "prompts", "storyboard", "（默认）分镜提示词.txt"
)


class StoryboardPromptContractTest(unittest.TestCase):
    def test_default_prompt_requires_numbered_single_line_output_without_blank_lines(self):
        prompt = read_file(DEFAULT_STORYBOARD_PROMPT_PATH)

        self.assertIn("按顺序编号", prompt)
        self.assertIn("每个分镜单独占一行", prompt)
        self.assertIn("分镜之间不得插入空行", prompt)
        self.assertNotRegex(prompt, r"分镜间以空行分隔")

    def test_default_prompt_treats_each_original_single_line_as_atomic(self):
        prompt = read_file(DEFAULT_STORYBOARD_PROMPT_PATH)

        self.assertIn("`*_corrected.txt` 中的每一条单行文本都必须作为不可拆分的整体处理", prompt)
        self.assertIn("不得把任意一行拆开后，分别和前一行或后一行拼接成新的分镜", prompt)

    def test_default_prompt_uses_6_second_limit_and_internal_self_check(self):
        prompt = read_file(DEFAULT_STORYBOARD_PROMPT_PATH)

        self.assertIn("6秒", prompt)
        self.assertIn("40 字以内", prompt)
        self.assertIn("内部自检", prompt)
        self.assertNotIn("50个字符", prompt)

    def test_load_prompt_resolves_storyboard_default_aliases(self):
        prompt = read_file(DEFAULT_STORYBOARD_PROMPT_PATH).strip()

        prompts_dir = os.path.join(PROJECT_ROOT, "prompts")
        self.assertEqual(prompt, load_prompt(prompts_dir, "storyboard", "default"))
        self.assertEqual(prompt, load_prompt(prompts_dir, "storyboard", "默认分镜提示词"))


if __name__ == "__main__":
    unittest.main()
