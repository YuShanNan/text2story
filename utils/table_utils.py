import csv
import os

from utils.file_utils import ensure_dir


def _load_csv_rows(path: str, required_columns: list[str]) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []
        missing_columns = [
            column for column in required_columns if column not in fieldnames
        ]
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise ValueError(f"{path} 缺少必填列: {missing}")

        rows = []
        seen_scene_ids = set()
        for row in reader:
            scene_id = row["scene_id"]
            if scene_id in seen_scene_ids:
                raise ValueError(f"{path} 的 scene_id {scene_id} 重复")
            seen_scene_ids.add(scene_id)
            rows.append(row)

        return rows


def merge_prompt_tables(
    storyboard_table_path: str, image_prompt_table_path: str
) -> list[dict[str, str]]:
    storyboard_rows = _load_csv_rows(
        storyboard_table_path, ["scene_id", "storyboard_text"]
    )
    image_prompt_rows = _load_csv_rows(
        image_prompt_table_path, ["scene_id", "raw_image_prompt"]
    )

    prompt_by_scene_id = {
        row["scene_id"]: row["raw_image_prompt"] for row in image_prompt_rows
    }
    storyboard_scene_ids = {row["scene_id"] for row in storyboard_rows}
    prompt_scene_ids = set(prompt_by_scene_id)

    missing_in_prompt_table = storyboard_scene_ids - prompt_scene_ids
    if missing_in_prompt_table:
        missing = ", ".join(sorted(missing_in_prompt_table))
        raise ValueError(f"{image_prompt_table_path} 的 scene_id {missing} 缺失")

    extra_in_prompt_table = prompt_scene_ids - storyboard_scene_ids
    if extra_in_prompt_table:
        extra = ", ".join(sorted(extra_in_prompt_table))
        raise ValueError(f"{image_prompt_table_path} 的 scene_id {extra} 未匹配")

    return [
        {
            "scene_id": row["scene_id"],
            "storyboard_text": row["storyboard_text"],
            "raw_image_prompt": prompt_by_scene_id[row["scene_id"]],
        }
        for row in storyboard_rows
    ]


def merge_video_prompt_tables(
    storyboard_table_path: str, image_prompt_table_path: str
) -> list[dict[str, str]]:
    storyboard_rows = _load_csv_rows(
        storyboard_table_path, ["scene_id", "storyboard_text"]
    )
    image_prompt_rows = _load_csv_rows(
        image_prompt_table_path, ["scene_id", "optimized_image_prompt"]
    )

    prompt_by_scene_id = {
        row["scene_id"]: row["optimized_image_prompt"] for row in image_prompt_rows
    }
    storyboard_scene_ids = {row["scene_id"] for row in storyboard_rows}
    prompt_scene_ids = set(prompt_by_scene_id)

    missing_in_prompt_table = storyboard_scene_ids - prompt_scene_ids
    if missing_in_prompt_table:
        missing = ", ".join(sorted(missing_in_prompt_table))
        raise ValueError(f"{image_prompt_table_path} 的 scene_id {missing} 缺失")

    extra_in_prompt_table = prompt_scene_ids - storyboard_scene_ids
    if extra_in_prompt_table:
        extra = ", ".join(sorted(extra_in_prompt_table))
        raise ValueError(f"{image_prompt_table_path} 的 scene_id {extra} 未匹配")

    return [
        {
            "scene_id": row["scene_id"],
            "storyboard_text": row["storyboard_text"],
            "optimized_image_prompt": prompt_by_scene_id[row["scene_id"]],
        }
        for row in storyboard_rows
    ]


def write_optimized_prompt_table(
    output_path: str, rows: list[dict[str, str]]
) -> None:
    fieldnames = [
        "scene_id",
        "storyboard_text",
        "raw_image_prompt",
        "optimized_image_prompt",
        "notes_cn",
    ]

    ensure_dir(os.path.dirname(output_path))
    with open(output_path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_video_prompt_table(output_path: str, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "scene_id",
        "storyboard_text",
        "optimized_image_prompt",
        "video_prompt",
        "notes_cn",
    ]

    ensure_dir(os.path.dirname(output_path))
    with open(output_path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
