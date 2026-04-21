import os
import unittest

from utils.file_utils import read_file


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
TARGET_PROMPT_PATH = os.path.join(
    PROJECT_ROOT,
    "prompts",
    "video_prompt_from_image",
    "（默认）2026.4.16-带商业运镜测试优化版.txt",
)


class VideoPromptDefault20260416ContractTest(unittest.TestCase):
    def test_prompt_requires_full_english_single_line_output(self):
        prompt = read_file(TARGET_PROMPT_PATH)

        self.assertIn("fully English only", prompt)
        self.assertIn("one single-line final video prompt in English only", prompt)
        self.assertIn("no Chinese characters", prompt)
        self.assertIn("no bilingual output", prompt)
        self.assertIn("Output only the final single-line English video prompt.", prompt)

    def test_prompt_requires_cross_scene_continuity_preservation(self):
        prompt = read_file(TARGET_PROMPT_PATH)

        self.assertIn("Continuity reference only", prompt)
        self.assertIn("preserve cross-shot continuity", prompt)
        self.assertIn("era / historical period / modernity level", prompt)
        self.assertIn("Do not let adjacent scenes drift", prompt)
        self.assertIn("Use continuity reference to preserve the same world", prompt)

    def test_prompt_forbids_mixed_language_and_non_visual_drift(self):
        prompt = read_file(TARGET_PROMPT_PATH)

        self.assertIn("output any Chinese", prompt)
        self.assertIn("mixed language", prompt)
        self.assertIn("smell / sound / temperature / air-texture inventions", prompt)
        self.assertIn("stagnant air", prompt)
        self.assertIn("still air", prompt)
        self.assertIn("visible cues only", prompt)
        self.assertIn("no white background", prompt)


if __name__ == "__main__":
    unittest.main()
