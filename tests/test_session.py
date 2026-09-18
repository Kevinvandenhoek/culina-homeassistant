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
    KIND_STEP_STARTED,
    Recipe,
    Session,
    Step,
    active_steps,
    group_announcements,
    parse_duration,
    plan_announcements,
    render,
    started_announcements,
)

CHILI = {
    "id": "r1",
    "title": "Chili con carne",
    "cuisine": {"id": "mexican", "name": "Mexicaans"},
    "steps": [
        {"order": 1, "key": "brown_base", "name": "Bereid de basis", "description": "Bak het vlees.", "duration": "PT15M", "durationOffset": "PT0M"},
        {"order": 2, "key": "build_chili", "name": "Voeg tomaten toe", "description": "Roer de tomaten erdoor.", "duration": "PT5M", "durationOffset": "PT15M"},
        {"order": 3, "key": "simmer_chili", "name": "Laat de chili sudderen", "description": "", "duration": "PT1H30M", "durationOffset": "PT20M", "handsOff": True},
    ],
}

TEMPLATES = {
    "step_ending_soon": "Nog {{count}} minuut voor: {{step}}",
    "step_ending_soon_plural": "Nog {{count}} minuten voor: {{step}}",
    "step_started": "Nu: {{step}}. {{description}}",
    "step_done": "Klaar met: {{step}}.",
    "step_done_next": "Klaar met: {{step}}. Nu: {{next}}. {{description}}",
    "all_done": "Alle stappen zijn klaar, smakelijk eten",
}


def kinds(plan):
    return [(round(a.at), a.kind, a.step.key if a.step else None) for a in plan]


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
        self.assertEqual(recipe.steps[0].description, "Bak het vlees.")

    def test_no_cuisine_no_description(self):
        recipe = Recipe.from_api({**CHILI, "cuisine": None})
        self.assertIsNone(recipe.cuisine_id)
        self.assertEqual(recipe.steps[2].description, "")

    def test_active_steps_parallel(self):
        steps = [Step(1, "a", "A", 0, 600), Step(2, "b", "B", 300, 600)]
        self.assertEqual([s.key for s in active_steps(steps, 100)], ["a"])
        self.assertEqual([s.key for s in active_steps(steps, 400)], ["a", "b"])
        self.assertEqual([s.key for s in active_steps(steps, 700)], ["b"])
        self.assertEqual(active_steps(steps, 900), [])


class PlanTest(unittest.TestCase):
    def test_chili(self):
        plan = plan_announcements(Recipe.from_api(CHILI).steps)
        self.assertEqual(
            kinds(plan),
            [
                (0, KIND_STEP_STARTED, "brown_base"),
                (840, KIND_ENDING_SOON, "brown_base"),
                (900, KIND_STEP_DONE_NEXT, "brown_base"),
                (1140, KIND_ENDING_SOON, "build_chili"),
                (1200, KIND_STEP_DONE_NEXT, "build_chili"),
                (6540, KIND_ENDING_SOON, "simmer_chili"),
                (6600, KIND_ALL_DONE, None),
            ],
        )
        self.assertEqual(plan[2].next_step.key, "build_chili")
        self.assertEqual(plan[2].description, "Roer de tomaten erdoor.")

    def test_parallel_start_is_step_started(self):
        # macaroni cooks 0-600, roux starts at 60 while nothing ends
        plan = plan_announcements([Step(1, "mac", "Macaroni", 0, 600), Step(2, "roux", "Roux", 60, 120)])
        self.assertEqual(
            kinds(plan),
            [(0, KIND_STEP_STARTED, "mac"), (60, KIND_STEP_STARTED, "roux"), (180, KIND_STEP_DONE, "roux"),
             (540, KIND_ENDING_SOON, "mac"), (600, KIND_ALL_DONE, None)],
        )

    def test_two_end_one_starts_pairs_once(self):
        plan = plan_announcements([Step(1, "a", "A", 0, 600), Step(2, "b", "B", 300, 300), Step(3, "c", "C", 600, 120)])
        at_600 = [(a.kind, a.step.key, a.next_step.key if a.next_step else None) for a in plan if a.at == 600]
        self.assertEqual(at_600, [(KIND_STEP_DONE_NEXT, "a", "c"), (KIND_STEP_DONE, "b", None)])

    def test_one_ends_two_start(self):
        plan = plan_announcements([Step(1, "a", "A", 0, 60), Step(2, "b", "B", 60, 60), Step(3, "c", "C", 60, 120)])
        at_60 = [(a.kind, a.step.key) for a in plan if a.at == 60]
        self.assertEqual(at_60, [(KIND_STEP_DONE_NEXT, "a"), (KIND_STEP_STARTED, "c")])

    def test_short_step_has_no_ending_soon(self):
        plan = plan_announcements([Step(1, "a", "A", 0, 90), Step(2, "b", "B", 90, 300)])
        self.assertEqual([a.kind for a in plan], [KIND_STEP_STARTED, KIND_STEP_DONE_NEXT, KIND_ENDING_SOON, KIND_ALL_DONE])

    def test_parallel_end_is_one_all_done(self):
        plan = plan_announcements([Step(1, "a", "A", 0, 600), Step(2, "b", "B", 300, 300)])
        self.assertEqual([a.kind for a in plan if a.at == 600], [KIND_ALL_DONE])
        self.assertEqual(len(group_announcements(plan)), 4)

    def test_zero_duration_steps_ignored(self):
        self.assertEqual(plan_announcements([Step(1, "a", "A", 0, 0)]), [])

    def test_started_announcements_for_session_start(self):
        steps = Recipe.from_api(CHILI).steps
        self.assertEqual([a.step.key for a in started_announcements(steps, 1230)], ["simmer_chili"])
        self.assertEqual([a.kind for a in started_announcements(steps, 5)], [KIND_STEP_STARTED])


class RenderTest(unittest.TestCase):
    def test_templates(self):
        plan = plan_announcements(Recipe.from_api(CHILI).steps)
        self.assertEqual(render(TEMPLATES, plan[0]), "Nu: Bereid de basis. Bak het vlees.")
        self.assertEqual(render(TEMPLATES, plan[1]), "Nog 1 minuut voor: Bereid de basis")
        self.assertEqual(render(TEMPLATES, plan[2]), "Klaar met: Bereid de basis. Nu: Voeg tomaten toe. Roer de tomaten erdoor.")
        self.assertEqual(render(TEMPLATES, plan[4]), "Klaar met: Voeg tomaten toe. Nu: Laat de chili sudderen.")
        self.assertEqual(render(TEMPLATES, plan[-1]), "Alle stappen zijn klaar, smakelijk eten")

    def test_fallback_and_plural(self):
        step = Step(1, "a", "Sear", 0, 600, description="Sear the beef.")
        two = [a for a in plan_announcements([step], ending_soon_seconds=120) if a.kind == KIND_ENDING_SOON][0]
        self.assertEqual(render({}, two), "2 minutes left for: Sear")
        self.assertEqual(render(None, plan_announcements([step])[0]), "Now: Sear. Sear the beef.")
        self.assertEqual(render({"step_done_next": "{{step}} is done, on to {{next}}"}, plan_announcements([step, Step(2, "b", "Rest", 600, 60)])[2]), "Sear is done, on to Rest")


if __name__ == "__main__":
    unittest.main()
