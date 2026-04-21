# text2story Copilot Instructions

## Commands

- Install dependencies: `pip install -r requirements.txt`
- Windows bootstrap: `start.bat`
- Interactive wizard: `python main.py`
- Full pipeline: `python main.py run --input input/example.srt --mode both`
- Full test suite: `python -m unittest discover -s tests`
- Single test module: `python -m unittest tests.test_prompt_optimizer`
- Single test method: `python -m unittest tests.test_main_optimize_cli.OptimizeCliTest.test_txt_mode_writes_optimized_prompt_txt`

## Architecture

- `main.py` is the only CLI entrypoint. Running it without a subcommand starts the Inquirer-based wizard in `core/interactive.py`; the Click subcommands expose the same pipeline non-interactively.
- The project uses one shared OpenAI-compatible model configuration for every AI step. `config.py` loads `MODEL_API_KEY`, `MODEL_BASE_URL`, `MODEL_NAME`, retry, timeout, and chunk-size settings; `api/client_factory.py` builds a single `OpenAICompatClient` used by correction, storyboard generation, prompt generation, optimization, and video prompt generation.
- The main pipeline is:
  1. `core/srt_corrector.py` preserves SRT block structure and timestamps while correcting subtitle text in batches.
  2. `core/srt_converter.py` strips indices, timestamps, and HTML tags to produce plain text.
  3. `core/storyboard_generator.py` chunks corrected text, carries forward short context between chunks, and normalizes model output back into numbered storyboard lines.
  4. `core/prompt_generator.py` splits storyboard text into scenes and generates image and/or video prompts per scene.
- `optimize-image-prompts` and `generate-video-prompts` are separate downstream workflows. Both support TXT mode (line-aligned files) and CSV mode (table-aligned rows), with CSV merging/writing handled in `utils/table_utils.py`.

## Key conventions

- Keep output paths stem-based. Use `utils.file_utils.get_safe_stem()` and `get_output_dir_for_file()` so files land under `output/{stem}/`; the stem is derived relative to `input/` to avoid collisions between same-named files in different subdirectories.
- Prompt directory names are part of the code contract. The live categories are `prompts/srt_correction`, `prompts/storyboard`, `prompts/image_prompt`, `prompts/video_prompt`, `prompts/image_prompt_optimize`, and `prompts/video_prompt_from_image`. `generate-video-prompts` reads from `video_prompt_from_image`, not `video_prompt`.
- Treat prompt files in `prompts/` as test-covered behavior, not freeform copy. Several tests assert exact contract language in specific Chinese templates, so prompt edits can break the suite even when Python code is unchanged.
- TXT optimization/video workflows align inputs by **non-empty line count**. CSV workflows require exact `scene_id` parity with no duplicates, extras, or fuzzy matching; mismatches should raise immediately rather than falling back silently.
- `core/storyboard_generator.normalize_storyboard_output()` is intentionally conservative: if the model rewrites, drops, or merges source content incorrectly, it falls back to numbered output derived from the source lines. Preserve that normalization behavior when changing storyboard generation.
- File I/O is encoding-aware. Reads auto-detect encoding with `chardet`; writes default to `utf-8-sig`, and CSV helpers also use BOM-aware UTF-8. Preserve that behavior when touching import/export code.
