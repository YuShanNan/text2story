import os
import unittest

from utils.file_utils import read_file, load_prompt


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
FLEXIBLE_STORYBOARD_PROMPT_PATH = os.path.join(
    PROJECT_ROOT, "prompts", "storyboard", "自由拆句分镜.txt"
)


class FlexibleStoryboardPromptContractTest(unittest.TestCase):
    def test_prompt_keeps_default_output_contract(self):
        prompt = read_file(FLEXIBLE_STORYBOARD_PROMPT_PATH)

        self.assertIn("按顺序编号", prompt)
        self.assertIn("每个分镜单独占一行", prompt)
        self.assertIn("分镜之间不得插入空行", prompt)
        self.assertIn("6秒一镜", prompt)
        self.assertIn("40 字以内", prompt)

    def test_prompt_allows_semantic_splitting_inside_original_line(self):
        prompt = read_file(FLEXIBLE_STORYBOARD_PROMPT_PATH)

        self.assertIn("允许在单条原文内部拆句", prompt)
        self.assertIn("可以在单条原文内部，按照动作完成点、结果出现点、主体/焦点切换点、场景切换点、时间跳转点、对话与旁白切换点进行拆句", prompt)
        self.assertIn("默认模板中的“原文单行不可拆”规则在本模板中失效", prompt)
        self.assertNotIn("`*_corrected.txt` 中的每一条单行文本都必须作为不可拆分的整体处理", prompt)
        self.assertNotIn("不得把任意一行拆开后，分别和前一行或后一行拼接成新的分镜", prompt)

    def test_prompt_preserves_original_text_fidelity(self):
        prompt = read_file(FLEXIBLE_STORYBOARD_PROMPT_PATH)

        self.assertIn("不得增删实词，不得改写，不得换词，不得调整原文叙事顺序", prompt)
        self.assertIn("拆句后的各段必须仍然完全来自原文，且保持原文顺序", prompt)
        self.assertIn("拆分后的每个片段都必须自足、完整、可直接成画面", prompt)

    def test_prompt_rejects_mechanical_punctuation_splitting(self):
        prompt = read_file(FLEXIBLE_STORYBOARD_PROMPT_PATH)

        self.assertIn("自由拆句不等于任意切碎", prompt)
        self.assertIn("禁止把一句话机械按逗号、顿号、句号平均切碎", prompt)
        self.assertIn("我推开卧室门一看老公正抱着那个女人坐在床边我当场僵住", prompt)
        self.assertIn("她刚把离婚协议拍到桌上婆婆就冲进来一把抢过去撕了个粉碎", prompt)

    def test_prompt_discourages_transition_only_micro_shots_and_requires_resplitting_long_items(self):
        prompt = read_file(FLEXIBLE_STORYBOARD_PROMPT_PATH)

        self.assertIn("纯过渡叙述默认不得单独成镜", prompt)
        self.assertIn("我那时问过他", prompt)
        self.assertIn("我懂他的意思", prompt)
        self.assertIn("我答得很干脆", prompt)
        self.assertIn("若同一条原文内部已经出现两个完整句意", prompt)
        self.assertIn("配音友好优先", prompt)
        self.assertIn("短台词 + 后续动作说明", prompt)
        self.assertIn("若同一人的一句长台词没有场景切换，但明显超过 40 字，也应优先压到 40 字以内", prompt)
        self.assertIn("取消“同一句话尽量留在同一分镜”的保守倾向", prompt)
        self.assertIn("再睁眼", prompt)

    def test_load_prompt_can_load_flexible_storyboard_prompt_by_name(self):
        prompt = read_file(FLEXIBLE_STORYBOARD_PROMPT_PATH).strip()

        prompts_dir = os.path.join(PROJECT_ROOT, "prompts")
        self.assertEqual(prompt, load_prompt(prompts_dir, "storyboard", "自由拆句分镜"))


if __name__ == "__main__":
    unittest.main()
