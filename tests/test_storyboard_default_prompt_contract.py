import os
import unittest

from utils.file_utils import read_file


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DEFAULT_STORYBOARD_PROMPT_PATH = os.path.join(
    PROJECT_ROOT, "prompts", "storyboard", "（默认）分镜提示词.txt"
)


class DefaultStoryboardPromptContractTest(unittest.TestCase):
    def test_prompt_forbids_mechanical_line_by_line_numbering(self):
        prompt = read_file(DEFAULT_STORYBOARD_PROMPT_PATH)

        self.assertIn("输入中的**换行只是原文素材边界，不是默认分镜边界**", prompt)
        self.assertIn("禁止把输出做成“对原文逐行机械编号的复写版”", prompt)
        self.assertIn("按输入行数逐行编号复写", prompt)
        self.assertIn("不得复述本提示词、不得输出本模板标题、不得输出规则条目", prompt)
        self.assertIn("最终输出的第一行必须直接是 `1. ` 开头的分镜正文", prompt)
        self.assertIn("分镜条数不追求固定压缩比例", prompt)
        self.assertIn("为了压条数强行合并已经完整的单行画面", prompt)
        self.assertIn("同场景不等于必须合并", prompt)

    def test_prompt_requires_merging_dependent_short_lines_into_complete_scene_units(self):
        prompt = read_file(DEFAULT_STORYBOARD_PROMPT_PATH)

        self.assertIn("我在老公的包里 / 发现了半瓶润滑液 / 可我跟他从来没有用过这个", prompt)
        self.assertIn("最近几个月 / 我老公开始健身 / 每天都要带着狗子 / 去外面跑两个小时", prompt)
        self.assertIn("老婆我带王子去洗澡 / 你等我王子 / 就是他养的那条狗", prompt)
        self.assertIn("必须合并成一个完整分镜", prompt)
        self.assertIn("先判断“这一行是否必须依附前后文才能说完整”", prompt)
        self.assertIn("一个分镜可以由 **一条或多条完整原文单行** 组成", prompt)
        self.assertIn("单行成镜是允许且常见的策略", prompt)
        self.assertIn("先逐行判断当前整行是否已经能独立成镜", prompt)
        self.assertIn("我老公当场死亡", prompt)
        self.assertIn("小青梅陷入昏迷", prompt)


if __name__ == "__main__":
    unittest.main()
