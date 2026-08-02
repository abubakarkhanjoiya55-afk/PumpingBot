"""
Basic unit tests for Stage 1/2/6/7 helpers.

Run:
  python -m unittest tests.test_core -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from presets import get_quality_settings
from project import apply_cut_plan_edits, assign_movie_match, build_project
from scene_matcher import match_scenes, similarity_score
from srt_parser import parse_srt


BASE = Path(__file__).resolve().parents[1]


class SrtParserTests(unittest.TestCase):
    def test_parse_sample_movie(self):
        entries = parse_srt(str(BASE / "sample_movie.srt"))
        self.assertGreaterEqual(len(entries), 5)
        first = entries[0]
        self.assertIn("index", first)
        self.assertIn("text", first)
        self.assertIsInstance(first["start"], float)
        # HTML tags cleaned
        self.assertNotIn("<i>", first["text"])

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            parse_srt(str(BASE / "no_such_file.srt"))


class MatcherTests(unittest.TestCase):
    def test_similarity_prefers_overlap(self):
        a = "We need to find the hidden door"
        close = "They need to find the hidden door before night"
        far = "The weather is sunny today"
        self.assertGreater(similarity_score(a, close), similarity_score(a, far))

    def test_match_scenes_sample(self):
        movie = parse_srt(str(BASE / "sample_movie.srt"))
        narration = parse_srt(str(BASE / "sample_narration.srt"))
        plan = match_scenes(movie, narration)
        self.assertEqual(len(plan), len(narration))
        self.assertTrue(any(item["matched"] for item in plan))


class ProjectEditTests(unittest.TestCase):
    def test_assign_movie_match_and_edit(self):
        movie = parse_srt(str(BASE / "sample_movie.srt"))
        narration = parse_srt(str(BASE / "sample_narration.srt"))
        plan = match_scenes(movie, narration)
        updated = assign_movie_match(plan[0], movie[-1], sync_to_narration=True)
        self.assertTrue(updated["matched"])
        self.assertEqual(updated["movie_index"], movie[-1]["index"])
        self.assertTrue(updated["manual_match"])

        edited = apply_cut_plan_edits(
            plan,
            [
                {
                    "narration_index": plan[0]["narration_index"],
                    "matched": True,
                    "movie_start": 0,
                    "movie_end": 1,
                    "assign_movie_index": movie[-1]["index"],
                }
            ],
            movie_entries=movie,
            sync_to_narration=True,
        )
        self.assertEqual(edited[0]["movie_index"], movie[-1]["index"])

    def test_build_project_quality(self):
        movie = parse_srt(str(BASE / "sample_movie.srt"))
        narration = parse_srt(str(BASE / "sample_narration.srt"))
        plan = match_scenes(movie, narration)
        project = build_project(
            name="t",
            video_path=BASE / "sample_movie.srt",  # path only stored; not opened here
            movie_srt_path=BASE / "sample_movie.srt",
            narration_srt_path=BASE / "sample_narration.srt",
            cut_plan=plan,
            quality="high",
        )
        self.assertEqual(project["settings"]["quality"], "high")


class PresetTests(unittest.TestCase):
    def test_unknown_falls_back(self):
        settings = get_quality_settings("not-real")
        self.assertEqual(settings["preset"], "veryfast")


class ExportEngineTests(unittest.TestCase):
    def test_timeline_srt_and_stage5_sample(self):
        from export_engine import build_timeline_srt, run_stage1_to_stage5
        from video_cutter import create_sample_video

        plan = [
            {
                "matched": True,
                "clip_start": 1.0,
                "clip_end": 3.5,
                "clip_duration": 2.5,
                "narration_text": "One",
            },
            {
                "matched": True,
                "clip_start": 20.0,
                "clip_end": 22.5,
                "clip_duration": 2.5,
                "narration_text": "Two",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            srt_path = Path(tmp) / "t.srt"
            build_timeline_srt(plan, srt_path)
            text = srt_path.read_text(encoding="utf-8")
            self.assertIn("One", text)
            self.assertIn("Two", text)
            self.assertIn("00:00:00,000 --> 00:00:02,500", text)

        video = BASE / "sample_movie.mp4"
        create_sample_video(video, duration_seconds=60.0)
        out = BASE / "output" / "test_stage5_final.mp4"
        result = run_stage1_to_stage5(
            video_path=video,
            movie_srt_path=str(BASE / "sample_movie_cluster.srt"),
            narration_srt_path=str(BASE / "sample_narration.srt"),
            output_path=out,
            narration_audio_path=None,  # synthetic VO ok
            max_clip_duration=5.0,
            burn_subs=True,
            quality="fast",
        )
        self.assertTrue(Path(result["output_video"]).exists())
        self.assertGreater(Path(result["output_video"]).stat().st_size, 1000)
        self.assertTrue(Path(result["timeline_srt"]).exists())


class CuttingEngineTests(unittest.TestCase):
    def test_match_plan_to_cut_plan_and_sample_pipeline(self):
        from cutting_engine import match_plan_to_cut_plan, run_stage1_to_stage4
        from video_cutter import create_sample_video

        plan = [
            {
                "matched": True,
                "clip_start": 1.0,
                "clip_end": 3.5,
                "narration_index": 1,
            },
            {"matched": False, "clip_start": None, "clip_end": None},
            {
                "matched": True,
                "clip_start": 5.0,
                "clip_end": 4.0,  # invalid, skipped
                "narration_index": 2,
            },
        ]
        cut_plan = match_plan_to_cut_plan(plan)
        self.assertEqual(len(cut_plan), 1)
        self.assertEqual(cut_plan[0]["movie_start"], 1.0)
        self.assertEqual(cut_plan[0]["movie_end"], 3.5)

        # Real ffmpeg sample cut (short video is enough if we use early timestamps)
        video = BASE / "sample_movie.mp4"
        create_sample_video(video, duration_seconds=60.0)
        out = BASE / "output" / "test_stage4_cut.mp4"
        result = run_stage1_to_stage4(
            video_path=video,
            movie_srt_path=str(BASE / "sample_movie_cluster.srt"),
            narration_srt_path=str(BASE / "sample_narration.srt"),
            output_path=out,
            max_clip_duration=5.0,
            quality="fast",
        )
        self.assertTrue(Path(result["output_video"]).exists())
        self.assertGreater(Path(result["output_video"]).stat().st_size, 1000)
        self.assertGreaterEqual(result["stats"]["matched"], 1)


class MatchingEngineTests(unittest.TestCase):
    def test_trim_and_match_plan(self):
        from matching_engine import (
            match_narration_to_scenes,
            run_stage1_to_stage3,
            trim_scene_to_clip,
        )

        scene = {
            "scene_id": 1,
            "start": 10.0,
            "end": 20.0,
            "combined_text": "find the hidden door",
            "subtitle_count": 2,
        }
        clip = trim_scene_to_clip(scene, target_duration=3.0, max_clip_duration=5.0)
        self.assertEqual(clip["clip_start"], 10.0)
        self.assertEqual(clip["clip_end"], 13.0)
        self.assertTrue(clip["trimmed"])

        # max 5s cap
        clip2 = trim_scene_to_clip(scene, target_duration=9.0, max_clip_duration=5.0)
        self.assertEqual(clip2["clip_duration"], 5.0)

        scenes = [
            {
                "scene_id": 1,
                "start": 0.0,
                "end": 8.0,
                "combined_text": "welcome movie hidden door oak tree",
                "subtitle_count": 3,
            },
            {
                "scene_id": 2,
                "start": 20.0,
                "end": 30.0,
                "combined_text": "right place trust me lets go",
                "subtitle_count": 3,
            },
        ]
        narr = [
            {"index": 1, "text": "find the hidden door near oak", "start": 0.0, "end": 2.5},
            {"index": 2, "text": "is this the right place trust me", "start": 3.0, "end": 5.5},
        ]
        plan = match_narration_to_scenes(scenes, narr, max_clip_duration=5.0)
        self.assertEqual(len(plan), 2)
        self.assertTrue(plan[0]["matched"])
        self.assertTrue(plan[1]["matched"])
        self.assertLessEqual(plan[0]["clip_duration"], 5.0)

        # End-to-end on sample files
        result = run_stage1_to_stage3(
            str(BASE / "sample_movie_cluster.srt"),
            str(BASE / "sample_narration.srt"),
            max_clip_duration=5.0,
        )
        self.assertGreaterEqual(result["stats"]["matched"], 1)
        self.assertTrue(result["scenes"])
        self.assertTrue(result["match_plan"])


class SceneClusteringTests(unittest.TestCase):
    def test_cluster_by_gap_and_merge_short(self):
        from scene_clustering import cluster_movie_scenes, merge_short_scenes

        entries = [
            {"text": "A one", "start": 0.0, "end": 1.0},
            {"text": "A two", "start": 1.5, "end": 2.5},  # gap 0.5 -> same
            {"text": "Tiny", "start": 10.0, "end": 10.5},  # gap 7.5 -> new
            {"text": "B one", "start": 12.0, "end": 14.0},  # gap 1.5 -> same as tiny after merge path
        ]
        scenes = cluster_movie_scenes(entries, gap_threshold=6.0)
        # First block (0-2.5), second starts at 10.0, third? 
        # Tiny end 10.5 to B start 12.0 gap=1.5 < 6 => same scene
        self.assertEqual(len(scenes), 2)
        self.assertEqual(scenes[0]["subtitle_count"], 2)
        self.assertIn("A one", scenes[0]["combined_text"])
        self.assertEqual(scenes[1]["subtitle_count"], 2)

        # Make an isolated tiny scene then merge forward
        entries2 = [
            {"text": "Long enough scene text", "start": 0.0, "end": 3.0},
            {"text": "Hi", "start": 10.0, "end": 10.4},  # short alone
            {"text": "Next scene continues", "start": 20.0, "end": 23.0},
        ]
        raw = cluster_movie_scenes(entries2, gap_threshold=6.0)
        self.assertEqual(len(raw), 3)
        cleaned = merge_short_scenes(raw, min_duration=2.0)
        # short middle merges into NEXT => 2 scenes
        self.assertEqual(len(cleaned), 2)
        self.assertIn("Hi", cleaned[1]["combined_text"])
        self.assertEqual(cleaned[0]["scene_id"], 1)
        self.assertEqual(cleaned[1]["scene_id"], 2)


class ConfigTests(unittest.TestCase):
    def test_load_and_normalize(self):
        from config import load_config, save_config

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            save_config(
                {
                    "quality": "nope",
                    "transition": "fade",
                    "transition_duration": 9,
                    "sync_to_narration": 1,
                    "burn_subs": 0,
                },
                path,
            )
            cfg = load_config(path)
            self.assertEqual(cfg["quality"], "balanced")  # invalid -> default
            self.assertEqual(cfg["transition"], "fade")
            self.assertLessEqual(cfg["transition_duration"], 1.5)
            self.assertTrue(cfg["sync_to_narration"])
            self.assertFalse(cfg["burn_subs"])

    def test_progress_logger_counts(self):
        from progress import ProgressLogger

        logs: list[str] = []
        p = ProgressLogger(
            total=2,
            callback=lambda msg, cur, tot: logs.append(f"{cur}/{tot}:{msg}"),
        )
        p.step("one")
        p.step("two")
        self.assertEqual(p.current, 2)
        self.assertEqual(len(logs), 2)


class ReportTests(unittest.TestCase):
    def test_html_report_without_video_still_works(self):
        from report import generate_html_report

        movie = parse_srt(str(BASE / "sample_movie.srt"))
        narration = parse_srt(str(BASE / "sample_narration.srt"))
        plan = match_scenes(movie, narration)
        project = build_project(
            name="report_test",
            video_path=BASE / "missing_video.mp4",
            movie_srt_path=BASE / "sample_movie.srt",
            narration_srt_path=BASE / "sample_narration.srt",
            cut_plan=plan,
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "r.html"
            path = generate_html_report(project, out)
            text = path.read_text(encoding="utf-8")
            self.assertIn("Auto Scene Cutter Report", text)
            self.assertIn("report_test", text)


if __name__ == "__main__":
    unittest.main()
