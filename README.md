# text2story - SRT 字幕 → AI 分镜 → 提示词生成工具

将 SRT 字幕文件自动转换为分镜脚本和 AI 绘图/视频提示词。

## 功能流程

```
SRT字幕文件 → 本地转TXT → 统一模型修正文案 → 统一模型生成分镜 → 统一模型生成提示词
```

1. **SRT → TXT**: 本地解析 SRT 格式，去除时间轴/序号，输出纯文本
2. **AI 文案提取 + 语义修正**: 统一模型修正错别字、语法、标点
3. **AI 分镜生成**: 统一模型将文案拆分为分镜脚本（画面描述/镜头运动/旁白/情绪）
4. **AI 提示词生成**: 统一模型将分镜转为图片/视频提示词（用户可选）

## 前置条件

- [Python](https://www.python.org/) 3.10+
- 一个 OpenAI 兼容模型接口的 API Key

## 安装

```bash
# 进入项目目录
cd text2story

# 安装 Python 依赖
pip install -r requirements.txt

# 配置环境变量
copy .env.example .env
# 编辑 .env 填写 API Key 和模型名称
```

## 配置 .env

```env
# 通用模型配置（统一用于修正 / 分镜 / 提示词 / 优化）
MODEL_API_KEY=your-api-key
MODEL_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-chat

# 通用设置
# 0 表示无限重试；大于 0 表示单个 AI 步骤的最大尝试次数
MAX_RETRY=5
REQUEST_TIMEOUT=300
MAX_CHUNK_SIZE=3000
```

## 使用方法

### 交互式向导（推荐）

```bash
python main.py
```

### 两阶段流水线

阶段一会执行到分镜产出后结束：

```bash
python main.py run --input input/example.srt
```

等你手动准备好原始画面提示词 TXT 后，再执行阶段二：

```bash
python main.py continue-run \
    --storyboard output/example/example_storyboard.txt \
    --raw-prompts output/example/raw_image_prompts.txt
```

### 单步执行

```bash
# 步骤1: AI 修正 SRT 字幕
python main.py correct --input input/example.srt

# 步骤2: SRT → TXT 提取文案
python main.py extract --input input/example.srt

# 步骤3: 生成分镜
python main.py storyboard --input output/example/example_corrected.txt

# 步骤4: 优化青风导出的画面提示词（TXT 一一对应模式）
python main.py optimize-image-prompts \
    --storyboard output/example/example_storyboard.txt \
    --raw-prompts output/example/raw_image_prompts.txt

# 步骤5: 根据优化后生图提示词生成视频提示词
python main.py generate-video-prompts \
    --storyboard output/example/example_storyboard.txt \
    --optimized-image-prompts output/example/example_optimized_image_prompts.txt

# 画面提示词优化也支持 CSV 模式
python main.py optimize-image-prompts \
    --storyboard-table output/example/storyboard_table.csv \
    --image-prompt-table output/example/image_prompt_table.csv
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `--input, -i` | 输入文件路径 |
| `--mode, -m` | 提示词模式: `image` / `video` / `both` |
| `--correction-prompt` | 修正提示词名称（默认 `default`） |
| `--storyboard-prompt` | 分镜提示词名称（默认 `default`） |
| `--image-prompt` | 图片提示词模板名称（默认 `default`） |
| `--video-prompt` | 视频提示词模板名称（默认 `default`） |
| `--output-dir, -o` | 自定义输出目录 |

## 自定义提示词

所有系统提示词存放在 `prompts/` 目录下，可自由添加和选择：

```
prompts/
├── correction/        ← 文案提取+语义修正
│   ├── default.txt    ← 默认
│   └── my_style.txt   ← 自定义
├── storyboard/        ← 分镜生成
│   ├── default.txt
│   └── cinematic.txt  ← 电影风格
├── image_prompt/      ← 图片提示词
│   ├── default.txt
│   └── anime.txt      ← 动漫风格
└── video_prompt/      ← 视频提示词
    ├── default.txt
    └── short_video.txt ← 短视频风格
```

使用自定义提示词：
```bash
python main.py run --input input/my.srt --mode both \
    --correction-prompt my_style \
    --storyboard-prompt cinematic \
    --image-prompt anime \
    --video-prompt short_video
```

## 画面提示词优化工作流

项目现已支持 `optimize-image-prompts` 命令，并提供两种输入模式：

1. **TXT 一一对应模式（推荐先用）**
2. **CSV 模式（长期更稳）**

### TXT 一一对应模式

适合你当前这类真实工作流：

- `storyboard.txt`
- 青风导出的原始画面提示词 `.txt`
- 一个画面提示词优化模板

命令示例：

```bash
python main.py optimize-image-prompts \
    --storyboard output/以刚克刚/以刚克刚_storyboard.txt \
    --raw-prompts output/以刚克刚/画面提示词_2026-4-14.txt
```

规则：

- 脚本按两个文件的**非空行**逐段一一对应
- 两边非空段数不一致时直接报错
- 输出文件默认是：
  - `output/{stem}/{stem}_optimized_image_prompts.txt`
- 输出结构保持为：
  - **一行一段提示词**
  - 适合继续按 TXT 方式处理

### CSV 模式

适合长期批量化和严格校对，输入为：

- `storyboard_table.csv`
- `image_prompt_table.csv`
- 一个画面提示词优化模板

命令示例：

```bash
python main.py optimize-image-prompts \
    --storyboard-table output/example/storyboard_table.csv \
    --image-prompt-table output/example/image_prompt_table.csv
```

### 输入文件

CSV 模式会使用 2 个输入文件，加 1 个画面提示词优化模板：

1. `storyboard_table.csv`
   - 每行一个分镜
   - 必填列：
     - `scene_id`
     - `storyboard_text`
2. `image_prompt_table.csv`
   - 每行一个分镜对应一条原始生图提示词
   - 必填列：
     - `scene_id`
     - `raw_image_prompt`
3. `prompts/image_prompt_optimize/*.txt`
   - 画面提示词优化模板
   - 模板内部同时包含通用优化框架和具体规则
   - 通过 `--prompt` 或交互菜单进行选择

### 画面提示词优化模板是什么

画面提示词优化模板用来放你手动整理的“优化要求”，并同时定义优化器的基础输出约束，例如：

- 防穿帮要求
- 空间站位要求
- 动作指向要求
- 人物一致性要求
- 风格统一要求
- 禁止输出的内容
- 输出格式要求

脚本会直接把你选择的这份模板作为唯一优化模板，参与每一条提示词优化。

### 放在哪里

请把这类文件放在：

```text
prompts/
└── image_prompt_optimize/
    ├── default.txt
    └── your_style.txt
```

然后通过以下方式选择：

- CLI：`--prompt default`
- 交互菜单：像其他提示词模板一样直接选择

### 对齐规则

CSV 模式下，两张表会严格按 `scene_id` 对齐：

- 任一必填列缺失：直接报错
- `scene_id` 重复：直接报错
- 两张表无法一一对应：直接报错
- 不做模糊匹配，不做静默兜底

### 输出文件

CSV 模式默认输出：

- `optimized_image_prompt_table.csv`

建议至少包含以下列：

- `scene_id`
- `storyboard_text`
- `raw_image_prompt`
- `optimized_image_prompt`
- `notes_cn`（可选，用于人工复核）

### 什么时候用哪一种

- **想立刻处理现有这部剧**：优先用 **TXT 一一对应模式**
- **想长期稳定批量处理**：优先用 **CSV 模式**
- 两种模式的优化核心相同，差别主要在**对齐稳定性**和**人工维护成本**

## 注意事项

- 长文本会自动分段处理，避免超出模型限制
- API 调用失败会自动重试（最多 3 次，指数退避）
- 支持多种 SRT 文件编码（UTF-8、GBK、GB2312 等）
