"""
Batch Render Module (Stage 6)

Ek folder mein kai project JSON files hon to sab ko ek saath render karo.
Har project ka output: <project_name>_final.mp4
"""

from __future__ import annotations

import sys
from pathlib import Path

from presets import list_qualities
from project import load_project, render_project, save_project


def find_project_files(folder: str | Path) -> list[Path]:
    """Folder ke andar saari .json project files dhoondo (sorted)."""
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Batch folder nahi mili: {folder}")

    files = sorted(folder.glob("*.json"))
    # last_project.json ko skip kar sakte hain agar chaho — yahan sab include
    return files


def batch_render(
    folder: str | Path,
    output_dir: str | Path | None = None,
    quality_override: str | None = None,
) -> list[dict]:
    """
    Folder ki har project JSON ko render karo.

    Returns list of result dicts:
      { "project": path, "ok": bool, "output": path|None, "error": str|None, "info": dict|None }
    """
    folder = Path(folder)
    out_dir = Path(output_dir) if output_dir else folder / "batch_output"
    out_dir.mkdir(parents=True, exist_ok=True)

    project_files = find_project_files(folder)
    if not project_files:
        raise ValueError(f"Folder mein koi .json project nahi mili: {folder}")

    results: list[dict] = []

    for i, project_path in enumerate(project_files, start=1):
        print(f"[{i}/{len(project_files)}] {project_path.name} ...")
        try:
            project = load_project(project_path)
            if quality_override:
                project.setdefault("settings", {})
                project["settings"]["quality"] = quality_override
                # Keep JSON updated if user asked for override
                save_project(project, project_path)

            output_path = out_dir / f"{project.get('name', project_path.stem)}_final.mp4"
            result_path, info = render_project(project, output_path)
            print(f"  OK -> {result_path}")
            results.append(
                {
                    "project": str(project_path),
                    "ok": True,
                    "output": str(result_path),
                    "error": None,
                    "info": info,
                }
            )
        except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
            print(f"  FAIL -> {exc}")
            results.append(
                {
                    "project": str(project_path),
                    "ok": False,
                    "output": None,
                    "error": str(exc),
                    "info": None,
                }
            )

    ok_count = sum(1 for r in results if r["ok"])
    print(f"\nBatch done: {ok_count}/{len(results)} successful")
    return results


def main() -> None:
    """
    Usage:
      python batch_render.py <projects_folder> [output_folder] [--quality fast|balanced|high]
    """
    args = sys.argv[1:]
    if not args:
        print(
            "Usage: python batch_render.py <projects_folder> [output_folder] "
            f"[--quality {'|'.join(list_qualities())}]"
        )
        sys.exit(1)

    folder = args[0]
    output_dir = None
    quality = None

    rest = args[1:]
    i = 0
    while i < len(rest):
        if rest[i] == "--quality" and i + 1 < len(rest):
            quality = rest[i + 1]
            i += 2
        elif not rest[i].startswith("--") and output_dir is None:
            output_dir = rest[i]
            i += 1
        else:
            print(f"Unknown arg: {rest[i]}")
            sys.exit(1)

    # quality stays None unless --quality passed (then override every project)

    try:
        results = batch_render(folder, output_dir=output_dir, quality_override=quality)
        # Non-zero exit if any failed
        if any(not r["ok"] for r in results):
            sys.exit(2)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
