import unittest

from core.storyboard_generator import normalize_storyboard_output


class StoryboardNormalizationTest(unittest.TestCase):
    def test_preserves_grouping_when_raw_output_is_high_similarity(self):
        source_text = "\n".join(
            [
                "我在老公的包里",
                "发现了半瓶润滑液",
                "可我跟他从来没有用过这个",
                "我买了两瓶502灌进去",
            ]
        )
        raw_output = "\n".join(
            [
                "1. 我在老公的包里发现了半瓶润滑液，可我跟他从来没有用过这个。",
                "2. 我买了两瓶502灌进去吗",
            ]
        )

        result = normalize_storyboard_output(source_text, raw_output)

        self.assertEqual(
            "\n".join(
                [
                    "1. 我在老公的包里发现了半瓶润滑液可我跟他从来没有用过这个",
                    "2. 我买了两瓶502灌进去",
                ]
            ),
            result,
        )

    def test_falls_back_to_line_atomic_output_when_raw_output_drops_content(self):
        source_text = "\n".join(
            [
                "我在老公的包里",
                "发现了半瓶润滑液",
                "可我跟他从来没有用过这个",
            ]
        )
        raw_output = "1. 我在老公的包里发现了半瓶润滑液"

        result = normalize_storyboard_output(source_text, raw_output)

        self.assertEqual(
            "\n".join(
                [
                    "1. 我在老公的包里",
                    "2. 发现了半瓶润滑液",
                    "3. 可我跟他从来没有用过这个",
                ]
            ),
            result,
        )

    def test_keeps_local_grouping_for_adjacent_short_lines(self):
        source_text = "\n".join(
            [
                "我拿起枕头下的水果刀",
                "慢慢朝外面走去",
                "实在不行",
                "割了呗",
                "打开门一看",
                "我愣了",
                "地上躺着两个人",
                "他们紧紧抱在一起",
            ]
        )
        raw_output = "\n".join(
            [
                "1. 我拿起枕头下的水果刀，慢慢朝外面走去，实在不行，割了呗。",
                "2. 打开门一看，我愣了，地上躺着两个人，他们紧紧抱在一起。",
            ]
        )

        result = normalize_storyboard_output(source_text, raw_output)

        self.assertEqual(
            "\n".join(
                [
                    "1. 我拿起枕头下的水果刀慢慢朝外面走去实在不行割了呗",
                    "2. 打开门一看我愣了地上躺着两个人他们紧紧抱在一起",
                ]
            ),
            result,
        )

    def test_prefers_numbered_lines_and_ignores_non_numbered_heading(self):
        source_text = "\n".join(
            [
                "妈妈给我转账30万",
                "做生日礼物",
            ]
        )
        raw_output = "\n".join(
            [
                "以下是分镜：",
                "1. 妈妈给我转账30万，做生日礼物。",
            ]
        )

        result = normalize_storyboard_output(source_text, raw_output)

        self.assertEqual("1. 妈妈给我转账30万做生日礼物", result)

    def test_preserves_model_grouping_when_source_line_contains_fused_segments(self):
        source_text = "\n".join(
            [
                "我在老公的包里",
                "发现了半瓶润滑液",
                "可我跟他从来没有用过这个",
            ]
        )
        raw_output = "\n".join(
            [
                "1. 我在老公的包里发现了半瓶",
                "2. 润滑液，可我跟他从来没有用过这个。",
            ]
        )

        result = normalize_storyboard_output(source_text, raw_output)

        self.assertEqual(
            "\n".join(
                [
                    "1. 我在老公的包里发现了半瓶",
                    "2. 润滑液，可我跟他从来没有用过这个。",
                ]
            ),
            result,
        )

    def test_regroups_mechanical_line_by_line_output_for_oversplit_source(self):
        source_text = "\n".join(
            [
                "老公的小青梅带着她的孩子",
                "和我老公去野炊的时候",
                "在高速上出了车祸",
                "我老公当场死亡",
                "我接到消息后",
                "迅速将我老公送去火化",
                "公公和婆婆从外地赶来",
                "第一时间",
                "就把孩子接到了家里",
            ]
        )
        raw_output = "\n".join(
            [
                "1. 老公的小青梅带着她的孩子",
                "2. 和我老公去野炊的时候",
                "3. 在高速上出了车祸",
                "4. 我老公当场死亡",
                "5. 我接到消息后",
                "6. 迅速将我老公送去火化",
                "7. 公公和婆婆从外地赶来",
                "8. 第一时间",
                "9. 就把孩子接到了家里",
            ]
        )

        result = normalize_storyboard_output(source_text, raw_output)

        self.assertEqual(
            "\n".join(
                [
                    "1. 老公的小青梅带着她的孩子和我老公去野炊的时候在高速上出了车祸",
                    "2. 我老公当场死亡",
                    "3. 我接到消息后迅速将我老公送去火化",
                    "4. 公公和婆婆从外地赶来第一时间就把孩子接到了家里",
                ]
            ),
            result,
        )

    def test_flexible_prompt_merges_transition_fragment_into_following_item(self):
        source_text = "我那时问过他。看到我受伤，你会心疼吗？哪怕只有一点点？"
        raw_output = "\n".join(
            [
                "1. 我那时问过他。",
                "2. 看到我受伤，你会心疼吗？哪怕只有一点点？",
            ]
        )

        result = normalize_storyboard_output(source_text, raw_output, prompt_name="自由拆句分镜")

        self.assertEqual(
            "1. 我那时问过他。看到我受伤，你会心疼吗？哪怕只有一点点？",
            result,
        )

    def test_default_prompt_keeps_transition_fragment_split(self):
        source_text = "我那时问过他。看到我受伤，你会心疼吗？哪怕只有一点点？"
        raw_output = "\n".join(
            [
                "1. 我那时问过他。",
                "2. 看到我受伤，你会心疼吗？哪怕只有一点点？",
            ]
        )

        result = normalize_storyboard_output(source_text, raw_output)

        self.assertEqual(
            "\n".join(
                [
                    "1. 我那时问过他。",
                    "2. 看到我受伤，你会心疼吗？哪怕只有一点点？",
                ]
            ),
            result,
        )

    def test_flexible_prompt_resplits_overlong_sentence_item(self):
        source_text = (
            "还有你，聂清月。"
            "我特意找大师算过，他说今年你不宜婚嫁，我这才将你的婚事往后推了推，想着明年再让你抛绣球。"
            "你怎么也不听话呢？"
        )
        raw_output = (
            "1. 还有你，聂清月。我特意找大师算过，他说今年你不宜婚嫁，我这才将你的婚事往后推了推，想着明年再让你抛绣球。"
            "你怎么也不听话呢？"
        )

        result = normalize_storyboard_output(source_text, raw_output, prompt_name="自由拆句分镜")

        self.assertEqual(
            "\n".join(
                [
                    "1. 还有你，聂清月。",
                    "2. 我特意找大师算过，他说今年你不宜婚嫁，我这才将你的婚事往后推了推，想着明年再让你抛绣球。",
                    "3. 你怎么也不听话呢？",
                ]
            ),
            result,
        )

    def test_flexible_prompt_falls_back_when_character_level_alignment_drops_text(self):
        source_text = "\n".join(
            [
                "可我万万没想到，她接过去之后，反手就把绣球抛给了崔昭的父亲。",
                "啊？",
                "绣球稳稳落进崔明和手里。",
            ]
        )
        raw_output = "\n".join(
            [
                "1. 可我万万没想到，她接过去之后，反手就把绣球抛给了崔昭的父亲。",
                "2. 绣球稳稳落进崔明和手里。",
            ]
        )

        result = normalize_storyboard_output(source_text, raw_output, prompt_name="自由拆句分镜")

        self.assertEqual(
            "\n".join(
                [
                    "1. 可我万万没想到，她接过去之后，反手就把绣球抛给了崔昭的父亲。",
                    "2. 啊？",
                    "3. 绣球稳稳落进崔明和手里。",
                ]
            ),
            result,
        )

    def test_flexible_prompt_splits_short_dialogue_from_following_narration(self):
        source_text = "没印象。她冷冷丢下三个字，拉着我就走。"
        raw_output = "1. 没印象。她冷冷丢下三个字，拉着我就走。"

        result = normalize_storyboard_output(source_text, raw_output, prompt_name="自由拆句分镜")

        self.assertEqual(
            "\n".join(
                [
                    "1. 没印象。",
                    "2. 她冷冷丢下三个字，拉着我就走。",
                ]
            ),
            result,
        )

    def test_flexible_prompt_splits_overlong_dialogue_at_secondary_boundary_when_needed(self):
        source_text = (
            "不过姐姐还是得提醒你，崔昭这人相貌家世都不错，"
            "可身板太薄，经不起折腾，只怕是个花拳绣腿，生不出孩子。"
        )
        raw_output = (
            "1. 不过姐姐还是得提醒你，崔昭这人相貌家世都不错，"
            "可身板太薄，经不起折腾，只怕是个花拳绣腿，生不出孩子。"
        )

        result = normalize_storyboard_output(source_text, raw_output, prompt_name="自由拆句分镜")

        self.assertEqual(
            "\n".join(
                [
                    "1. 不过姐姐还是得提醒你，崔昭这人相貌家世都不错，",
                    "2. 可身板太薄，经不起折腾，只怕是个花拳绣腿，生不出孩子。",
                ]
            ),
            result,
        )

    def test_flexible_prompt_keeps_sentence_final_split_from_remerging(self):
        source_text = "就怕多说一句会把娘亲气晕。当鹌鹑似地缩着头，被三人轮着骂过一遍后，爹爹大手一挥，让我俩去跪祠堂。"
        raw_output = "1. 就怕多说一句会把娘亲气晕。当鹌鹑似地缩着头，被三人轮着骂过一遍后，爹爹大手一挥，让我俩去跪祠堂。"

        result = normalize_storyboard_output(source_text, raw_output, prompt_name="自由拆句分镜")

        self.assertEqual(
            "\n".join(
                [
                    "1. 就怕多说一句会把娘亲气晕。",
                    "2. 当鹌鹑似地缩着头，被三人轮着骂过一遍后，爹爹大手一挥，让我俩去跪祠堂。",
                ]
            ),
            result,
        )

    def test_flexible_prompt_splits_adjacent_complete_sentences_into_separate_shots(self):
        source_text = "及笄那年，我抛绣球招婿，接到绣球的人是崔昭。我们成了亲，做了一世相敬如宾的夫妻。"
        raw_output = "1. 及笄那年，我抛绣球招婿，接到绣球的人是崔昭。我们成了亲，做了一世相敬如宾的夫妻。"

        result = normalize_storyboard_output(source_text, raw_output, prompt_name="自由拆句分镜")

        self.assertEqual(
            "\n".join(
                [
                    "1. 及笄那年，我抛绣球招婿，接到绣球的人是崔昭。",
                    "2. 我们成了亲，做了一世相敬如宾的夫妻。",
                ]
            ),
            result,
        )

    def test_flexible_prompt_splits_new_time_phase_sentence_into_separate_shot(self):
        source_text = "为了让他瞑目，我应了。再睁眼，我就把手里的绣球递给了庶姐。"
        raw_output = "1. 为了让他瞑目，我应了。再睁眼，我就把手里的绣球递给了庶姐。"

        result = normalize_storyboard_output(source_text, raw_output, prompt_name="自由拆句分镜")

        self.assertEqual(
            "\n".join(
                [
                    "1. 为了让他瞑目，我应了。",
                    "2. 再睁眼，我就把手里的绣球递给了庶姐。",
                ]
            ),
            result,
        )


if __name__ == "__main__":
    unittest.main()
