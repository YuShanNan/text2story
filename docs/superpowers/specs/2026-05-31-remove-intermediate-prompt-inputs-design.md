# Design: Remove Intermediate Prompt Inputs from Optimize & Video Generation

**Date**: 2026-05-31
**Status**: Approved

## Summary

Simplify `PromptOptimizer` and `VideoPromptGenerator` so both generate outputs using only storyboard text + their respective system prompts (instructions), removing the dependency on intermediate prompt files.

## Motivation

Currently each step requires two inputs:

| Step | Before | After |
|------|--------|-------|
| Storyboard → Optimized image prompts | Storyboard + Raw image prompts | Storyboard + instruction |
| Storyboard → Video prompts | Storyboard + Optimized image prompts | Storyboard + instruction |

Both steps become independent, consuming only storyboard text:

```
                 ┌─→ PromptOptimizer (instruction A) → optimized image prompts
Storyboard text ─┤
                 └─→ VideoPromptGenerator (instruction B) → video prompts
```

## Changes

### Core

**`core/prompt_optimizer.py`**:
- `build_rows_from_files()`: remove `raw_prompt_path` parameter, read only storyboard
- `_build_file_rows()`: remove `raw_image_prompt` field from rows
- `optimize_files_batch()`: remove `raw_prompt_path` param; in AI input, only emit storyboard text (no raw prompt line)

**`core/video_prompt_generator.py`**:
- `build_rows_from_files()`: remove `optimized_image_prompt_path` parameter
- rows only contain `storyboard_text`, remove `optimized_image_prompt` field
- `generate_files_batch()`: remove `optimized_image_prompt_path` param; AI input only emits storyboard text

### CLI (`main.py`)

**`optimize-image-prompts`**:
- Remove `--raw-prompts` (TXT) / `--image-prompt-table` (CSV) params
- Only need `--storyboard` (TXT) or `--storyboard-table` (CSV)
- Simplify TXT/CSV mode validation (no need to check dual params)

**`generate-video-prompts`**:
- Remove `--optimized-image-prompts` (TXT) / `--image-prompt-table` (CSV) params
- Only need `--storyboard` (TXT) or `--storyboard-table` (CSV)
- Simplify TXT/CSV mode validation

**`continue-run`**:
- Both steps run independently, each consuming only storyboard text
- No dependency between optimize step output and video step input

### Interactive (`core/interactive.py`)

- Image prompt optimization: no longer scans/selects "画面提示词*.txt" files
- Video prompt generation: no longer scans/selects `_optimized_image_prompts.txt` files
- CSV mode changes similarly

### Utils (`utils/table_utils.py`)

- `merge_prompt_tables()`: simplify or remove (no raw_prompt merge needed)
- `merge_video_prompt_tables()`: simplify or remove (no optimized prompt merge needed)
- `write_optimized_prompt_table()`: remove `raw_image_prompt` from output columns
- `write_video_prompt_table()`: remove `optimized_image_prompt` from output columns

### Unchanged

- Prompt template directory names (`image_prompt_optimize`, `video_prompt_from_image`)
- `PromptOptimizer` output format
- Tests updated to match new signatures

## Non-Goals

- Prompt template content changes (handled separately by user)
- Removing the optimize step from `continue-run`
