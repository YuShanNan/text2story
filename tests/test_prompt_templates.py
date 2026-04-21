import os
import unittest


class PromptTemplateTest(unittest.TestCase):
    def _read_target_prompt(self) -> str:
        project_root = os.path.dirname(os.path.dirname(__file__))
        prompt_path = os.path.join(
            project_root,
            "prompts",
            "image_prompt_optimize",
            "2版简化版- TXT-6秒竖屏短视频画面提示词优化.txt",
        )

        with open(prompt_path, "r", encoding="utf-8") as file:
            return file.read()

    def _read_default_named_target_prompt(self) -> str:
        project_root = os.path.dirname(os.path.dirname(__file__))
        prompt_path = os.path.join(
            project_root,
            "prompts",
            "image_prompt_optimize",
            "（默认）2版简化版- TXT-6秒竖屏短视频画面提示词优化.txt",
        )

        with open(prompt_path, "r", encoding="utf-8") as file:
            return file.read()

    def test_image_prompt_optimize_template_uses_single_prompt_io_contract(self):
        content = self._read_target_prompt()

        self.assertIn("分镜原文", content)
        self.assertIn("原始画面提示词", content)
        self.assertIn("不要假设还会有第二份“优化规则”文本额外提供给你", content)
        self.assertIn("只输出当前这一条分镜对应的一段最终画面提示词", content)

        self.assertNotIn("A列", content)
        self.assertNotIn("B列", content)
        self.assertNotIn("最终输出模板表格", content)
        self.assertNotIn("序号+视频提示词", content)

    def test_image_prompt_optimize_template_strengthens_style_and_constraint_requirements(self):
        content = self._read_target_prompt()

        self.assertIn("禁止输出主观情绪判断、心理活动、性格评价、抽象氛围词", content)
        self.assertIn("每一个角色名都必须统一写成 `[角色名]` 形式", content)
        self.assertIn("也必须继续使用`[角色名]`", content)
        self.assertIn("必须写清谁在前景、谁在后景、谁面向谁、谁背对镜头/侧对镜头/侧背对镜头", content)
        self.assertIn("容易生成双方同时面对镜头，这类表达视为失败", content)
        self.assertIn("必须显式保留 9:16竖屏构图、8K分辨率", content)
        self.assertIn("负面提示词固定5个必须完整保留在最终输出末尾", content)
        self.assertIn("人物头身比、面部特征、衣着、配饰锁定信息应作为硬约束保留在最终输出中", content)
        self.assertIn("优先沿用原始画面提示词的句式与信息顺序", content)
        self.assertIn("仅在必要处做增补、替换与压错，不要整段重写", content)
        self.assertIn("不得新增原文和原始画面提示词中没有的职业、身份、设定标签或英文安全标签", content)
        self.assertIn("负面提示词部分必须使用固定前缀“负面提示词：”", content)
        self.assertIn("禁止使用“理性冷静”", content)

    def test_image_prompt_optimize_template_blocks_non_visual_air_and_sensory_language(self):
        content = self._read_target_prompt()

        self.assertIn("空气里还残留着卫生间方向传来的潮湿水汽", content)
        self.assertIn("空气沉闷得像凝住了一样", content)
        self.assertIn("室内空气静止", content)
        self.assertIn("空气通透", content)
        self.assertIn("空气潮闷", content)
        self.assertIn("潮湿水汽", content)
        self.assertIn("刺鼻气味", content)
        self.assertIn("压抑呼吸感", content)
        self.assertIn("湿热感", content)
        self.assertIn("能听到轻微的布料摩擦声", content)
        self.assertIn("能听见脚步声", content)
        self.assertIn("床面出现塌陷与空隙", content)
        self.assertIn("沙发坐垫被压出明显空隙", content)
        self.assertIn("床垫因受力形成明显凹陷细节", content)
        self.assertIn("仿佛", content)
        self.assertIn("任何“空气+形容词/状态词”的写法都视为非视觉化失败表达", content)
        self.assertIn("只允许保留灯光、门缝、湿脚印、物体位置、人物动作、表情、视线等可见信息", content)
        self.assertIn("嘴唇紧抿", content)
        self.assertNotIn("嘴唇发白", content)
        self.assertIn("若出现上述禁词或禁加细节，视为失败，必须整句重写", content)
        self.assertIn("禁止输出任何不能被镜头直接拍到的空气感、气味、温度、湿热感、压迫感、呼吸感", content)
        self.assertIn("禁止原样输出，禁止轻微改写后继续输出", content)
        self.assertIn("只能改写成可见信息，不得保留感官结论本身", content)
        self.assertIn("禁止为了证明人物接触了床、沙发、椅子、墙面、门把手等物体，而补充难以稳定生成的微观受力反馈、材质摩擦反馈、细小空隙、轻微声响", content)
        self.assertIn("脸色铁青", content)
        self.assertIn("脸色发白", content)
        self.assertIn("脸色青紫", content)
        self.assertIn("不得用脸色颜色词下结论", content)
        self.assertIn("哭红了眼", content)
        self.assertIn("苦红的眼睛", content)
        self.assertIn("眼眶哭红", content)
        self.assertIn("鼻尖发红", content)
        self.assertIn("眼眶湿润", content)
        self.assertIn("睫毛沾泪", content)
        self.assertIn("鼻翼轻颤", content)
        self.assertNotIn("眼皮微肿、鼻尖发红、嘴唇紧抿", content)
        self.assertIn("不得用眼睛发红/哭红类颜色词或鼻尖颜色词下结论", content)

    def test_image_prompt_optimize_template_adds_output_self_check_for_names_and_orientation(self):
        content = self._read_target_prompt()

        self.assertIn("输出前必须自检", content)
        self.assertIn("是否仍存在任何非视觉/不可稳定生图描述", content)
        self.assertIn("是否所有角色名都已统一写成`[角色名]`", content)
        self.assertIn("是否已经明确前景后景与镜头朝向，避免多人同时正对镜头", content)

    def test_default_named_image_prompt_optimize_template_keeps_same_key_constraints(self):
        content = self._read_default_named_target_prompt()

        self.assertIn("每一个角色名都必须统一写成 `[角色名]` 形式", content)
        self.assertIn("容易生成双方同时面对镜头，这类表达视为失败", content)
        self.assertIn("能听到轻微的布料摩擦声", content)
        self.assertIn("床面出现塌陷与空隙", content)
        self.assertIn("脸色铁青", content)
        self.assertIn("不得用脸色颜色词下结论", content)
        self.assertIn("哭红了眼", content)
        self.assertIn("鼻尖发红", content)
        self.assertIn("不得用眼睛发红/哭红类颜色词或鼻尖颜色词下结论", content)
        self.assertIn("输出前必须自检", content)

    def _read_video_target_prompt(self) -> str:
        project_root = os.path.dirname(os.path.dirname(__file__))
        prompt_path = os.path.join(
            project_root,
            "prompts",
            "video_prompt_from_image",
            "2026.4.13-带商业运镜测试简化版2(1).txt",
        )

        self.assertTrue(os.path.exists(prompt_path), f"模板不存在: {prompt_path}")

        with open(prompt_path, "r", encoding="utf-8") as file:
            return file.read()

    def test_video_prompt_from_image_template_uses_single_row_io_contract(self):
        content = self._read_video_target_prompt()

        self.assertIn("分镜原文", content)
        self.assertIn("优化后生图提示词", content)
        self.assertIn("只输出当前这一条分镜对应的一段最终视频提示词", content)
        self.assertIn("不要假设还会有下一组", content)

        self.assertNotIn("A列", content)
        self.assertNotIn("B列", content)
        self.assertNotIn("| 序号 | 文案 | 视频提示词 |", content)
        self.assertNotIn("第X组", content)
        self.assertNotIn("是否生成第X+1组", content)

    def test_video_prompt_from_image_template_preserves_motion_constraints(self):
        content = self._read_video_target_prompt()

        self.assertIn("6秒一镜到底", content)
        self.assertIn("景别+运镜+参数", content)
        self.assertIn("运镜模块必须为连续纯英文", content)
        self.assertIn("不改原始生图提示词中的人物、衣着、空间关系核心约束", content)
        self.assertIn("只在其基础上补足可执行的视频运镜与动作衔接", content)
        self.assertIn("不得写成“中景(MS)”", content)
        self.assertIn("不得输出“B级运镜”", content)
        self.assertIn("英文运镜模块内部不得出现中文逗号、中文顿号、中文冒号、中文括号", content)
        self.assertIn("这不是创意改写任务", content)
        self.assertIn("若拿不准，宁可少补，不可脑补", content)
        self.assertIn("不得把谐音、代称、模糊品牌词扩写成明确品牌名", content)
        self.assertIn("禁止输出“感激”", content)
        self.assertIn("不得写成“MS，DollyIn+FocusLock”", content)
        self.assertIn("禁止输出“困惑”", content)
        self.assertIn("禁止输出“讥诮”", content)
        self.assertIn("禁止输出“思考状”", content)
        self.assertIn("不得新增嗅觉、听觉、温度、空气质感等原文未给出的感官氛围细节", content)
        self.assertIn("禁止输出“错愕”", content)
        self.assertIn("禁止输出“空气凝滞”", content)
        self.assertIn("禁止输出“气味弥漫”", content)
        self.assertIn("禁止输出“仿佛”", content)
        self.assertIn("禁止输出“脚步声”", content)
        self.assertIn("禁止输出“器械提示音”", content)
        self.assertIn("禁止输出“环境音”", content)
        self.assertIn("禁止输出“从期待变成”", content)
        self.assertIn("若需要表达等待回应，只能改写成目光停留、嘴唇微动、手指停顿等可见动作", content)
        self.assertIn("输出前自检", content)
        self.assertIn("若出现上述禁词或禁加细节，视为失败，必须整句重写", content)


if __name__ == "__main__":
    unittest.main()
