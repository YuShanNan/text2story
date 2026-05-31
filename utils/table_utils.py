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


def load_storyboard_table(path: str) -> list[dict[str, str]]:
    return _load_csv_rows(path, ["scene_id", "storyboard_text"])


def write_optimized_prompt_table(
    output_path: str, rows: list[dict[str, str]]
) -> None:
    fieldnames = [
        "scene_id",
        "storyboard_text",
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
        "video_prompt",
        "notes_cn",
    ]

    ensure_dir(os.path.dirname(output_path))
    with open(output_path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
