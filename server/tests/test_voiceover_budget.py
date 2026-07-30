from __future__ import annotations

import unittest

from app.engine.audio import generate_voiceover_asset


class VoiceoverBudgetTests(unittest.TestCase):
    def test_rejects_script_that_exceeds_the_montage_budget(self) -> None:
        with self.assertRaisesRegex(ValueError, "has 4 words; maximum is 3"):
            generate_voiceover_asset(
                ["one two", "three four"],
                output_dir="C:/Temp",
                max_words=3,
                force=True,
            )


if __name__ == "__main__":
    unittest.main()
