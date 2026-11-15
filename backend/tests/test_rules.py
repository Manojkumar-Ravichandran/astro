from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from astro_market.api import RuleAspectInput, RuleCreate, RulePatch, create_rule, list_rules, retire_rule, update_rule  # noqa: E402
from astro_market.db.sqlite import connect, initialize_database  # noqa: E402


class TraderRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db = os.environ.get("ASTRO_DB_PATH")
        os.environ["ASTRO_DB_PATH"] = str(Path(self.temp_dir.name) / "rules.sqlite3")
        initialize_database()

    def tearDown(self) -> None:
        if self.previous_db is None:
            os.environ.pop("ASTRO_DB_PATH", None)
        else:
            os.environ["ASTRO_DB_PATH"] = self.previous_db
        self.temp_dir.cleanup()

    def test_seeded_hypotheses_and_rule_edit_lifecycle(self) -> None:
        seeds = list_rules()
        self.assertEqual(len(seeds), 3)
        self.assertTrue(all(rule["status"] == "hypothesis" for rule in seeds))
        self.assertEqual(len(seeds[2]["aspects"]), 2)
        with connect() as connection:
            source_id = connection.execute("SELECT id FROM source_documents LIMIT 1").fetchone()[0]

        created = create_rule(
            RuleCreate(
                title="Research note",
                hypothesis_text="Unverified user hypothesis.",
                source_document_id=source_id,
                aspects=[RuleAspectInput(planet_1="Moon", planet_2="Mars", aspect_angle_degrees=90)],
            )
        )
        edited = update_rule(
            created["id"],
            RulePatch(
                status="under_test",
                aspects=[RuleAspectInput(planet_1="Sun", planet_2="Saturn", aspect_angle_degrees=135)],
            ),
        )
        self.assertEqual(edited["status"], "under_test")
        self.assertEqual(edited["aspects"][0]["planet_1"], "Sun")
        self.assertEqual(retire_rule(created["id"])["status"], "retired")
        self.assertEqual(len(list_rules()), 3)
        self.assertEqual(len(list_rules(include_retired=True)), 4)


if __name__ == "__main__":
    unittest.main()
