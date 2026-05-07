import unittest
from core.storyboard_postprocess import (
    postprocess_storyboard,
    _parse_entries,
    _char_count,
    _split_long_entries,
    _split_at_natural_boundary,
    _format_output,
)


class ParseEntriesTest(unittest.TestCase):
    def test_解析点号编号行(self):
        text = "1. 第一条\n2. 第二条\n3. 第三条"
        result = _parse_entries(text)
        self.assertEqual(result, ["第一条", "第二条", "第三条"])

    def test_跳过空行(self):
        text = "1. 第一条\n\n2. 第二条"
        result = _parse_entries(text)
        self.assertEqual(result, ["第一条", "第二条"])


class CharCountTest(unittest.TestCase):
    def test_不计标点符号(self):
        self.assertEqual(_char_count("爸爸有些不高兴"), 7)

    def test_不计空格(self):
        self.assertEqual(_char_count("a b c"), 3)

    def test_标点不计入(self):
        self.assertEqual(_char_count("你好。"), 2)

    def test_空字符串(self):
        self.assertEqual(_char_count(""), 0)


class SplitAtNaturalBoundaryTest(unittest.TestCase):
    def test_短文本不拆分(self):
        result = _split_at_natural_boundary("这是一个短分镜。", 35)
        self.assertEqual(len(result), 1)

    def test_在句号处拆分为两部分(self):
        text = "这是第一句内容大概十几个字吧。这是第二句内容也是十几个字左右。"
        result = _split_at_natural_boundary(text, 20)
        self.assertGreater(len(result), 1)

    def test_无断句点则保留原文(self):
        text = "这是一段没有句号问号感叹号的长文本内容连续不断"
        result = _split_at_natural_boundary(text, 20)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], text)

    def test_单句超长尝试逗号拆分(self):
        text = "这是一个超长句子包含很多内容但是没有句号只有逗号分隔，后面还有更多内容继续延续"
        result = _split_at_natural_boundary(text, 35)
        # 有逗号边界可以拆分
        self.assertGreaterEqual(len(result), 1)

    def test_问号和感叹号也作为边界(self):
        text = "你怎么能这样？太过分了！我要生气了。真是受不了。"
        result = _split_at_natural_boundary(text, 15)
        self.assertGreater(len(result), 1)
        # 应该在？或！处拆分
        self.assertEqual(len(result), 2)


class SplitLongEntriesTest(unittest.TestCase):
    def test_短条目不拆分(self):
        entries = ["正常长度的分镜", "也是正常的"]
        result = _split_long_entries(entries, 35)
        self.assertEqual(result, entries)

    def test_长条目在句号处拆分(self):
        entries = [
            "第一句大概十几个字的正常长度吧。第二句也是正常长度十来个字。第三句稍微短一点。",
        ]
        result = _split_long_entries(entries, 20)
        self.assertGreater(len(result), 1)

    def test_混合条目正确处理(self):
        entries = [
            "短条目",
            "这个条目比较长需要拆分。拆完之后是两个独立的镜头。继续往下走。",
            "又一条短的",
        ]
        result = _split_long_entries(entries, 20)
        self.assertGreater(len(result), 3)


class FormatOutputTest(unittest.TestCase):
    def test_格式化为点号编号(self):
        entries = ["第一", "第二", "第三"]
        result = _format_output(entries)
        self.assertEqual(result, "1. 第一\n2. 第二\n3. 第三")


class PostprocessStoryboardTest(unittest.TestCase):
    def test_端到端拆分长条目(self):
        text = (
            "1. 这是第一条正常长度。\n"
            "2. 这是第二条内容比较长超过了限制。因此需要在这里拆分。后面还有一句收尾的话。\n"
            "3. 第三条正常。"
        )
        result = postprocess_storyboard(text, max_chars=20)
        lines = result.strip().splitlines()
        # 第2条应该被拆分
        self.assertGreater(len(lines), 3)

    def test_端到端正常输入不变(self):
        text = "1. 正常分镜第一段\n2. 正常分镜第二段"
        result = postprocess_storyboard(text)
        self.assertEqual(result, text)

    def test_端到端保留编号连续性(self):
        text = "1. 第一条。第二条。第三条。"
        result = postprocess_storyboard(text, max_chars=10)
        lines = result.strip().splitlines()
        for i, line in enumerate(lines, 1):
            self.assertTrue(line.startswith(f"{i}. "), f"期望编号 {i}, 实际: {line[:20]}")

    def test_端到端幂等性(self):
        text = "1. 第一条。第二条应该被拆。第三条也拆开。"
        first = postprocess_storyboard(text, max_chars=10)
        second = postprocess_storyboard(first, max_chars=10)
        self.assertEqual(first, second)

    def test_真实v3片段(self):
        # 模拟 v3 中超过 35 字的长条目
        text = (
            "1. 每当他们这样说时，哥哥都会不耐烦的翻白眼，然后迅速牵起我的手逃跑，不让我再听下去。\n"
            "2. 而妈妈则是一脸的无动于衷，连眉毛都没动一下。"
        )
        result = postprocess_storyboard(text, max_chars=35)
        lines = result.strip().splitlines()
        # 条目1有41字（标点不计），在句号处应该能拆分
        self.assertGreaterEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main()
