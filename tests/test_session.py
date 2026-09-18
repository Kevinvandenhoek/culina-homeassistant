"""Unit tests for the cooking session model."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "culina"))

from session import (  # noqa: E402
    KIND_ALL_DONE,
    KIND_ENDING_SOON,
    KIND_STEP_DONE,
    KIND_STEP_DONE_NEXT,
    Recipe,
    Session,
    Step,
    active_steps,
    group_announcements,
    parse_duration,
    plan_announcements,
    render,
)

CHILI = {
    "id": "r1",
    "title": "Chili con carne",
    "cuisine": {"id": "mexican", "name": "Mexicaans"},
    "steps": [
        {"order": 1, "key": "brown_base", "name": "Bereid de basis", "duration": "PT15M", "durationOffset": "PT0M"},
        {"order": 2, "key": "build_chili", "name": "Voeg tomaten toe", "duration": "PT5M", "durationOffset": "PT15M"},
        {"order": 3, "key": "simmer_chili", "name": "Laat de chili sudderen", "duration": "PT1H30M", "durationOffset": "PT20M", "handsOff": True},
    ],
}

TEMPLATES = {
    "step_ending_soon": "{{step}} is over {{count}} minuut klaar",
    "step_ending_soon_plural": "{{step}} is over {{count}} minuten klaar",
    "step_done": "{{step}} is klaar",
    "step_done_next": "{{step}} is klaar, door naar {{next}}",
    "all_done": "Alle stappen zijn klaar, smakelijk eten",
}


class DurationTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_duration("PT15M"), 900)
        self.assertEqual(parse_duration("PT1H30M"), 5400)
        self.assertEqual(parse_duration("PT0M"), 0)
        self.assertEqual(parse_duration("PT45S"), 45)
        self.assertEqual(parse_duration("P1DT1H"), 90000)
        self.assertEqual(parse_duration(None), 0)
        with self.assertRaises(ValueError):
            parse_duration("15 minutes")


class SessionTest(unittest.TestCase):
    def test_elapsed_running(self):
        session = Session.from_api({"recipeId": "r1", "startedAt": 1_000_000, "elapsedOffset": 30})
        self.assertFalse(session.paused)
        self.assertEqual(session.elapsed_at(1_010_000), 40)

    def test_elapsed_paused(self):
        session = Session.from_api({"recipeId": "r1", "startedAt": None, "elapsedOffset": 30})
        self.assertTrue(session.paused)
        self.assertEqual(session.elapsed_at(9_999_999), 30)


class RecipeTest(unittest.TestCase):
    def test_from_api(self):
        recipe = Recipe.from_api(CHILI)
        self.assertEqual(recipe.cuisine_id, "mexican")
        self.assertEqual(recipe.total_duration, 6600)
        self.assertEqual([s.key for s in recipe.steps], ["brown_base", "build_chili", "simmer_chili"])
        self.assertTrue(recipe.steps[2].hands_off)

    def test_no_cuisine(self):
        recipe = Recipe.from_api({**CHILI, "cuisine": None})
        self.assertIsNone(recipe.cuisine_id)

    def test_active_steps_parallel(self):
        steps = [
            Step(1, "a", "A", 0, 600),
            Step(2, "b", "B", 300, 600),
        ]
        self.assertEqual([s.key for s in active_steps(steps, 100)], ["a"])
        self.assertEqual([s.key for s in active_steps(steps, 400)], ["a", "b"])
        self.assertEqual([s.key for s in active_steps(steps, 700)], ["b"])
        self.assertEqual(active_steps(steps, 900), [])


class PlanTest(unittest.TestCase):
    def test_chili(self):
        recipe = Recipe.from_api(CHILI)
        plan = plan_announcements(recipe.steps)
        self.assertEqual(
            [(a.at, a.kind, a.step.key if a.step else None) for a in plan],
            [
                (840, KIND_ENDING_SOON, "brown_base"),
                (900, KIND_STEP_DONE_NEXT, "brown_base"),
                (1140, KIND_ENDING_SOON, "build_chili"),
                (1200, KIND_STEP_DONE_NEXT, "build_chili"),
                (6540, KIND_ENDING_SOON, "simmer_chili"),
                (6600, KIND_ALL_DONE, None),
            ],
        )
        self.assertEqual(plan[1].next_step.key, "build_chili")

    def test_short_step_has_no_ending_soon(self):
        plan = plan_announcements([Step(1, "a", "A", 0, 90), Step(2, "b", "B", 90, 300)])
        self.assertEqual([a.kind for a in plan], [KIND_STEP_DONE_NEXT, KIND_ENDING_SOON, KIND_ALL_DONE])

    def test_gap_gives_plain_done(self):
        plan = plan_announcements([Step(1, "a", "A", 0, 60), Step(2, "b", "B", 120, 60)])
        self.assertEqual([a.kind for a in plan], [KIND_STEP_DONE, KIND_ALL_DONE])

    def test_parallel_end_is_one_all_done(self):
        plan = plan_announcements([Step(1, "a", "A", 0, 600), Step(2, "b", "B", 300, 300)])
        self.assertEqual([a.kind for a in plan], [KIND_ENDING_SOON, KIND_ENDING_SOON, KIND_ALL_DONE])
        self.assertEqual(len(group_announcements(plan)), 2)

    def test_zero_duration_steps_ignored(self):
        self.assertEqual(plan_announcements([Step(1, "a", "A", 0, 0)]), [])


class RenderTest(unittest.TestCase):
    def test_templates(self):
        recipe = Recipe.from_api(CHILI)
        plan = plan_announcements(recipe.steps)
        self.assertEqual(render(TEMPLATES, plan[0]), "Bereid de basis is over 1 minuut klaar")
        self.assertEqual(render(TEMPLATES, plan[1]), "Bereid de basis is klaar, door naar Voeg tomaten toe")
        self.assertEqual(render(TEMPLATES, plan[-1]), "Alle stappen zijn klaar, smakelijk eten")

    def test_fallback_and_plural(self):
        step = Step(1, "a", "Sear", 0, 600)
        two = plan_announcements([step], ending_soon_seconds=120)[0]
        self.assertEqual(render({}, two), "Sear is done in 2 minutes")
        self.assertEqual(render(None, plan_announcements([step])[1]), "All steps are done, enjoy your meal")


if __name__ == "__main__":
    unittest.main()
