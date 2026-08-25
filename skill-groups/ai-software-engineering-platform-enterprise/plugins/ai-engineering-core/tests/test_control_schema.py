from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

from control_trace import EVENT_SCHEMA, event_file, record_event  # noqa: E402
from control_kernel import OPERATION_STATUSES, SCHEMA_VERSION  # noqa: E402


class ControlEventSchemaTests(unittest.TestCase):
    def test_operation_journal_schema_matches_kernel_protocol(self):
        path = PLUGIN / "schemas" / "control-operation.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        operation = schema["$defs"]["operation"]
        self.assertEqual(SCHEMA_VERSION, schema["properties"]["schema_version"]["const"])
        self.assertEqual(OPERATION_STATUSES, set(operation["properties"]["status"]["enum"]))
        for field in (
            "before_fingerprint", "intended_after_fingerprint", "committed_after_fingerprint",
            "domain_commit_timestamp", "trace_status", "retry_count",
        ):
            self.assertIn(field, operation["properties"])

    def test_generated_event_matches_published_closed_schema(self):
        with tempfile.TemporaryDirectory() as project_td, tempfile.TemporaryDirectory() as state_td:
            root = Path(project_td)
            with patch.dict(os.environ, {"HIKER_CONTROL_STATE_DIR": state_td}):
                result = record_event(
                    root,
                    event_type="goal-rebound",
                    summary_code="GOAL_REBOUND",
                    task_id="KG-001",
                    phase="Planning",
                    result="PASS",
                    gate_result="UNAFFECTED",
                    operation_id="OP-SCHEMA-001",
                )
                event = json.loads(event_file(root).read_text(encoding="utf-8").splitlines()[-1])
            schema = json.loads(EVENT_SCHEMA.read_text(encoding="utf-8"))
            self.assertEqual(set(schema["required"]), set(event) & set(schema["required"]))
            self.assertEqual(set(), set(event) - set(schema["properties"]))
            self.assertEqual(event["event_hash"], result["event_hash"])
            self.assertEqual("METADATA_ONLY", event["privacy_class"])


if __name__ == "__main__":
    unittest.main()
