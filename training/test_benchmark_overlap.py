import unittest
from training.audit_benchmark_overlap import make_index, screen


class OverlapTests(unittest.TestCase):
    def setUp(self):
        self.text = "Create a Python function that reads records from a local JSON file and writes sorted unique names to another output file."
        self.sets, self.index = make_index({"example-task": self.text})

    def test_exact_id(self):
        hits, _ = screen({"task": "example-task_copy0001"}, self.sets, self.index)
        self.assertEqual(hits[0]["reason"], "exact_task_id")

    def test_renamed_exact_instruction(self):
        hits, _ = screen({"task": "unrelated-id", "instruction": self.text}, self.sets, self.index)
        self.assertEqual(hits[0]["reason"], "instruction_5gram_overlap")

    def test_unrelated(self):
        hits, present = screen({"instruction": "Calculate galaxy distances using redshift."}, self.sets, self.index)
        self.assertTrue(present)
        self.assertEqual(hits, [])

    def test_missing(self):
        hits, present = screen({}, self.sets, self.index)
        self.assertFalse(present)
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
