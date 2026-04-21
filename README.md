# text2story

把 **SRT 字幕**整理成适合 AI 生产链路继续使用的文本资产：先修正文案，再生成分镜，接着衔接画面提示词优化和视频提示词生成。

这个项目更适合已经有字幕脚本、想把内容继续整理成分镜与提示词的人。它是一个本地 Python CLI 工具，支持交互式向导，也支持命令行分步执行。

## 这个项目能做什么

- **修正 SRT 字幕**：保留时间戳和块结构，只修正文案内容
- **提取纯文本**：把 SRT 转成后续处理更方便的 TXT
- **生成分镜脚本**：将文案拆成逐条分镜
- **优化画面提示词**：把外部工具导出的原始生图提示词重新整理成更稳定的版本
- **生成视频提示词**：基于分镜原文和优化后的生图提示词继续生成视频提示词
- **支持两种使用方式**：交互式菜单、CLI 命令行

## 适合什么场景

- 你已经有一份 `.srt` 字幕文件，想快速整理成分镜文本
- 你已经有分镜和原始画面提示词，想继续做提示词优化
- 你希望把流程拆开执行，而不是每次都从头到尾重跑
- 你想把产物统一沉淀到 `output/{文件名}/` 目录下，方便管理

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制模板并填写你自己的模型配置：

```bash
copy .env.example .env
```

`.env` 示例：

```env
MODEL_API_KEY=your-api-key
MODEL_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-chat

MAX_RETRY=5
REQUEST_TIMEOUT=300
MAX_CHUNK_SIZE=3000
```

字段说明：

| 配置项 | 说明 |
| --- | --- |
| `MODEL_API_KEY` | OpenAI 兼容接口的密钥 |
| `MODEL_BASE_URL` | 模型接口地址 |
| `MODEL_NAME` | 使用的模型名称 |
| `MAX_RETRY` | 单个 AI 步骤最大重试次数；`0` 表示无限重试 |
| `REQUEST_TIMEOUT` | 单次请求超时时间（秒） |
| `MAX_CHUNK_SIZE` | 长文本分段处理时的最大块大小 |

### 3. 先跑起来

如果你想先用交互方式体验：

```bash
python main.py
```

如果你想直接跑阶段一示例：

```bash
python main.py run --input input/example.srt
```

## Windows 一键启动

仓库自带 `start.bat`，适合 Windows 用户快速启动：

```bash
start.bat
```

它会自动尝试完成这些事情：

1. 检测 Python 是否可用
2. 创建或复用 `venv`
3. 安装 `requirements.txt` 中的依赖
4. 检查 `.env`、`input`、`output`
5. 启动 `main.py`

## 推荐工作流

这个项目最实用的路径通常不是“一条命令做完所有事”，而是按阶段处理。

### 工作流 A：从 SRT 到分镜

适合你手里只有字幕文件的时候。

```bash
python main.py run --input input/example.srt
```

这个阶段会依次完成：

1. AI 修正 SRT 字幕
2. 从修正后的 SRT 提取纯文本
3. 根据文案生成分镜

默认输出会落到：

```text
output/example/
├── example_corrected.srt
├── example_corrected.txt
└── example_storyboard.txt
```

### 工作流 B：从分镜到视频提示词

适合你已经准备好了：

- 分镜 TXT
- 原始画面提示词 TXT

然后继续做后处理：

```bash
python main.py continue-run ^
  --storyboard output/example/example_storyboard.txt ^
  --raw-prompts output/example/raw_image_prompts.txt
```

这个阶段会依次完成：

1. 画面提示词优化
2. 视频提示词生成

默认会继续产出：

```text
output/example/
├── example_optimized_image_prompts.txt
└── example_video_prompts.txt
```

## 常用命令

### 交互式入口

```bash
python main.py
```

### 单步命令

```bash
# 从 SRT 提取纯文本
python main.py extract --input input/example.srt

# AI 修正 SRT（保留时间戳）
python main.py correct --input input/example.srt

# 根据修正后的文案生成分镜
python main.py storyboard --input output/example/example_corrected.txt

# 优化画面提示词
python main.py optimize-image-prompts ^
  --storyboard output/example/example_storyboard.txt ^
  --raw-prompts output/example/raw_image_prompts.txt

# 根据优化后的生图提示词生成视频提示词
python main.py generate-video-prompts ^
  --storyboard output/example/example_storyboard.txt ^
  --optimized-image-prompts output/example/example_optimized_image_prompts.txt
```

### 分阶段命令

```bash
# 阶段一：SRT -> 修正 -> 提取 -> 分镜
python main.py run --input input/example.srt

# 阶段二：分镜 -> 画面提示词优化 -> 视频提示词
python main.py continue-run ^
  --storyboard output/example/example_storyboard.txt ^
  --raw-prompts output/example/raw_image_prompts.txt
```

## 画面提示词优化

`optimize-image-prompts` 支持两种输入方式。

### 方式 1：TXT 一一对应模式

适合先快速处理现有项目。

输入：

- `storyboard.txt`
- 原始画面提示词 `.txt`

命令示例：

```bash
python main.py optimize-image-prompts ^
  --storyboard output/example/example_storyboard.txt ^
  --raw-prompts output/example/raw_image_prompts.txt
```

规则：

- 按两个文件的**非空行**逐条对齐
- 非空行数量不一致会直接报错
- 默认输出为 `output/{stem}/{stem}_optimized_image_prompts.txt`

### 方式 2：CSV 模式

适合长期批量处理和人工复核。

输入：

- `storyboard_table.csv`
- `image_prompt_table.csv`

命令示例：

```bash
python main.py optimize-image-prompts ^
  --storyboard-table output/example/storyboard_table.csv ^
  --image-prompt-table output/example/image_prompt_table.csv
```

CSV 规则：

- 必填列必须存在
- `scene_id` 必须一一对应
- 不做模糊匹配
- 重复、缺失、无法对齐会直接报错

默认输出为：

```text
output/{stem}/{stem}_optimized_image_prompts.csv
```

## 视频提示词生成

`generate-video-prompts` 同样支持 TXT 和 CSV 两种模式。

### TXT 模式

输入：

- `storyboard.txt`
- `*_optimized_image_prompts.txt`

命令示例：

```bash
python main.py generate-video-prompts ^
  --storyboard output/example/example_storyboard.txt ^
  --optimized-image-prompts output/example/example_optimized_image_prompts.txt
```

默认输出：

```text
output/{stem}/{stem}_video_prompts.txt
```

### CSV 模式

输入：

- `storyboard_table.csv`
- 含 `optimized_image_prompt` 列的提示词表

命令示例：

```bash
python main.py generate-video-prompts ^
  --storyboard-table output/example/storyboard_table.csv ^
  --image-prompt-table output/example/optimized_image_prompt_table.csv
```

默认输出：

```text
output/{stem}/{stem}_video_prompts.csv
```

## 输出规则

- 默认输出目录采用 `output/{stem}/`
- `stem` 会尽量根据输入文件名安全生成，避免重名文件互相覆盖
- 文本文件默认写入为 `utf-8-sig`
- CSV 也使用带 BOM 的 UTF-8，方便在常见表格工具中打开

## 提示词模板

当前仓库里实际使用到的提示词模板目录包括：

```text
prompts/
├── srt_correction/
├── storyboard/
├── image_prompt_optimize/
└── video_prompt_from_image/
```

你可以通过命令中的 `--prompt`、`--correction-prompt`、`--storyboard-prompt`、`--optimize-prompt`、`--video-prompt` 来选择模板名称（文件名不带 `.txt`）。

例如：

```bash
python main.py correct --input input/example.srt --prompt default
python main.py run --input input/example.srt --storyboard-prompt default
python main.py continue-run ^
  --storyboard output/example/example_storyboard.txt ^
  --raw-prompts output/example/raw_image_prompts.txt ^
  --optimize-prompt default ^
  --video-prompt default
```

## 项目结构

```text
text2story/
├── api/                       # OpenAI 兼容客户端封装
├── core/                      # 主要处理流程
├── input/                     # 输入素材（仓库保留 example.srt）
├── output/                    # 运行产物
├── prompts/                   # 各阶段提示词模板
├── tests/                     # 单元测试
├── utils/                     # 文件、表格、重试等工具函数
├── .env.example               # 环境变量模板
├── config.py                  # 统一配置入口
├── main.py                    # CLI 入口
├── requirements.txt           # Python 依赖
└── start.bat                  # Windows 一键启动脚本
```

## 使用前要知道的几点

- 这是一个**依赖外部模型接口**的工具，不内置模型本身
- SRT 修正、分镜生成、提示词优化、视频提示词生成都共享同一套模型配置
- 长文本会自动分段处理，避免一次性塞给模型过多内容
- API 调用失败时会按配置重试
- 文件读取会自动识别常见中文编码

## 测试

运行完整测试：

```bash
python -m unittest discover -s tests
```

运行单个测试模块：

```bash
python -m unittest tests.test_prompt_optimizer
```

## 当前更推荐怎么用

如果你是第一次接触这个项目，建议按下面顺序：

1. 复制 `.env.example` 为 `.env`
2. 填写模型配置
3. 运行 `python main.py`
4. 先用 `input/example.srt` 跑通阶段一
5. 再根据自己的工作流使用 `continue-run`、`optimize-image-prompts` 或 `generate-video-prompts`

这样最容易判断问题出在哪一步，也最符合这个项目当前的使用方式。
