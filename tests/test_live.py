"""Offline tests for the workshop board's server-side logic. Run: python3 -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "live"))
import compiler  # noqa: E402
import main  # noqa: E402

CATALOG = compiler.load_catalog()


class ValidateTests(unittest.TestCase):
    def test_accepts_catalog_modules_and_fills_defaults(self):
        mods, unsupported, problems, _ = compiler.validate(
            {"modules": [{"id": "zone_entry", "params": {"dwell_seconds": 2}, "reason": "lane"}, {"id": "near_forklift"}]}, CATALOG)
        self.assertEqual([m["id"] for m in mods], ["zone_entry", "near_forklift"])
        self.assertEqual(mods[1]["params"], {"min_score": 0.4})
        self.assertEqual(problems, [])

    def test_rejects_unknown_modules_and_out_of_range_values(self):
        mods, _, problems, _ = compiler.validate(
            {"modules": [{"id": "hardhat"}, {"id": "lingering", "params": {"dwell_seconds": 999}},
                         {"id": "crowding", "params": {"max_people": "3"}}]}, CATALOG)
        self.assertEqual(mods, [])
        self.assertEqual(len(problems), 3)

    def test_unsupported_uses_catalog_wording_and_ignores_bad_indexes(self):
        _, unsupported, _, _ = compiler.validate({"modules": [], "unsupported": [0, 0, 99, "x"]}, CATALOG)
        self.assertEqual(unsupported, [CATALOG["unsupported"][0]])

    def test_dedupes_and_caps_module_count(self):
        many = [{"id": m["id"]} for m in CATALOG["modules"]] + [{"id": "zone_entry"}]
        mods, _, _, _ = compiler.validate({"modules": many}, CATALOG)
        self.assertLessEqual(len(mods), compiler.MAX_MODULES)
        self.assertEqual(len({m["id"] for m in mods}), len(mods))

    def test_non_object_answer_is_an_error(self):
        with self.assertRaises(ValueError):
            compiler.validate(["zone_entry"], CATALOG)


class FeedTests(unittest.TestCase):
    def test_view_names(self):
        self.assertEqual(main.view_name("x_run_7_seed_9.ceiling_04.rgb_chunk_0000.mp4"), ("Ceiling 04", "Scene 7"))
        self.assertEqual(main.view_name("2025_test_Warehouse_017_Camera_01_chunk_0002.mp4"), ("Camera 01", "Part 3"))

    def test_feed_from_timeline_keeps_order_and_captions(self):
        item = {"original_video": "s3://vss-chunks/t/a.mp4", "total_segments": 2, "camera_id": "sdg_warehouse_cam-2",
                "timeline": [{"segment_number": 2, "segment_start_sec": 5, "segment_end_sec": 10, "source": "s3://vss-chunks-segments/segments/a_2.mp4", "reasoning_content": "B"},
                             {"segment_number": 1, "segment_start_sec": 0, "segment_end_sec": 5, "source": "s3://vss-chunks-segments/segments/a_1.mp4", "reasoning_content": "A"}]}
        feed = main.feed_from_item(item)
        self.assertEqual([s["caption"] for s in feed["segments"]], ["A", "B"])
        self.assertTrue(feed["synthetic"])
        self.assertEqual(feed["duration"], 10)

    def test_incomplete_or_foreign_feeds_are_dropped(self):
        partial = {"original_video": "s3://vss-chunks/t/a.mp4", "total_segments": 3,
                   "timeline": [{"segment_number": 1, "source": "s3://vss-chunks-segments/segments/a_1.mp4"}]}
        self.assertIsNone(main.feed_from_item(partial))
        foreign = {"original_video": "s3://other-team-vss-chunks/a.mp4", "total_segments": 1,
                   "timeline": [{"segment_number": 1, "source": "s3://other-team-vss-chunks-segments/segments/a_1.mp4"}]}
        self.assertIsNone(main.feed_from_item(foreign))

    def test_compact_detections(self):
        out = main.compact_detections({"video_shape": [1080, 1920], "source": "yolo11_coco", "frames": [
            {"time_sec": 0.0333, "detections": [{"label": "person", "confidence": 0.8921, "bbox": [1, 2, 3, 4]}, {"label": "x", "bbox": [1]}]}]})
        self.assertEqual((out["w"], out["h"]), (1920, 1080))
        self.assertEqual(out["frames"], [[0.0333, [["person", 0.892, 1, 2, 3, 4]]]])

    def test_safe_source(self):
        self.assertTrue(main.safe_source("s3://vss-chunks-segments/segments/a.mp4", ""))
        self.assertFalse(main.safe_source("s3://vss-chunks-segments/../x.mp4", ""))
        self.assertFalse(main.safe_source("https://evil.example/a.mp4", ""))


if __name__ == "__main__":
    unittest.main()
