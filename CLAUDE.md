# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- Install dependencies: `pip install -r requirements.txt`
- Windows bootstrap: `start.bat`
- Interactive wizard: `python main.py`
- Full test suite: `python -m unittest discover -s tests`
- Single test module: `python -m unittest tests.test_prompt_optimizer`
- Single test method: `python -m unittest tests.test_main_optimize_cli.OptimizeCliTest.test_txt_mode_writes_optimized_prompt_txt`

## Architecture

This is a local Python CLI tool that converts SRT subtitle files into storyboard scripts and AI image/video prompts, driven by a single OpenAI-compatible model.

`main.py` is the only CLI entrypoint. Running it bare starts the InquirerPy-based interactive wizard (`core/interactive.py`). Click subcommands expose the same pipeline non-interactively.

**One model for everything.** `config.py` loads `MODEL_API_KEY`, `MODEL_BASE_URL`, `MODEL_NAME`, retry/timeout/chunk-size from `.env`. `api/client_factory.py` builds one `OpenAICompatClient` shared across all AI steps (correction, storyboard, prompt optimization, video prompt generation).

**Data flow (two pipeline stages):**

1. **Stage one** (`python main.py run --input ...`): SRT → AI correction (preserves timestamps, fixes text) → plain-text extraction (strips indices/timestamps/HTML) → storyboard generation (chunked text, context carry-forward between chunks).
2. **Stage two** (`python main.py continue-run --storyboard ... --raw-prompts ...`): image prompt optimization → video prompt generation.

**Key classes by pipeline step:**

| Step | Module | Class |
|------|--------|-------|
| API client | `api/openai_client.py` | `OpenAICompatClient` — SSE-streaming chat, auto-retry with exponential backoff, fallback model |
| SRT correction | `core/srt_corrector.py` | `SrtCorrector` — splits by SRT blocks, batches by char limit |
| SRT→TXT | `core/srt_converter.py` | `convert_srt_to_txt()` — regex-based, no AI |
| Storyboard | `core/storyboard_generator.py` | `StoryboardGenerator` — complex normalization engine |
| Image prompt optimize | `core/prompt_optimizer.py` | `PromptOptimizer` — per-row AI calls, sanitization |
| Video prompt | `core/video_prompt_generator.py` | `VideoPromptGenerator` — continuity-aware (passes previous row as context) |

**TXT vs CSV modes:** `optimize-image-prompts` and `generate-video-prompts` support both. TXT mode aligns inputs by non-empty line count. CSV mode requires exact `scene_id` parity — mismatches raise immediately.

## Key conventions

- **Output paths are stem-based.** Use `utils/file_utils.get_safe_stem()` and `get_output_dir_for_file()` so files land under `output/{stem}/`. Stem is derived relative to `input/` to avoid same-name collisions.
- **Prompt directory names are part of the code contract.** Live categories: `prompts/srt_correction`, `prompts/storyboard`, `prompts/image_prompt`, `prompts/video_prompt`, `prompts/image_prompt_optimize`, `prompts/video_prompt_from_image`. Note `generate-video-prompts` reads from `video_prompt_from_image`, NOT `video_prompt`.
- **Storyboard normalization (`storyboard_generator.py`) is intentionally conservative.** `normalize_storyboard_output()` uses a sequence alignment approach: it normalizes all text, checks total-content parity, detects mechanical line-copying, and falls back to source-line grouping if the model rewrites/drops/merges content incorrectly. When even retries fail, it degrades to numbered source-line output. The "自由拆句分镜" prompt family uses a different path (`_is_flexible_storyboard_prompt`).
- **File I/O is encoding-aware.** Reads auto-detect encoding with `chardet`. Writes default to `utf-8-sig` (BOM). CSV helpers also use BOM-aware UTF-8.
- **Prompt files in `prompts/` are test-covered behavior.** Several tests assert exact contract language in specific Chinese templates. Prompt edits can break the test suite even when Python code is unchanged.
- **All generators use iterator-based progress reporting.** Each step yields events with `batch_index`/`batch_total`/`elapsed_seconds` etc. The interactive layer consumes these to drive Rich progress bars.
- **`MAX_RETRY=0` means infinite retry.** The retry utility (`utils/retry_utils.py`) interprets 0 as unbounded; the formatter renders it as "∞".
