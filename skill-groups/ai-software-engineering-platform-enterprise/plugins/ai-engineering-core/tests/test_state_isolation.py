from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


PLUGIN=Path(__file__).resolve().parents[1]
SCRIPTS=PLUGIN/"scripts"
WORKSPACE_SCRIPTS=PLUGIN.parent/"ai-engineering-workspace"/"scripts"
for value in (str(SCRIPTS),str(WORKSPACE_SCRIPTS)):
    if value not in sys.path:sys.path.insert(0,value)

from bounded_run import read_evidence_page,run_bounded
from context_budget import tracked_file_count
from context_memory import memory_status
from detect_project import detect
from engineering_manifests import discover_engineering_manifests
from source_identity import identify
from source_surface import TraversalBudget,TraversalLimitReached,is_reserved_source_path,walk_source_files
from workspacelib import worktree_fingerprint


def git(root:Path,*args:str)->None:
    subprocess.run(["git",*args],cwd=root,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


class StateIsolationTests(unittest.TestCase):
    def test_source_and_routing_scans_never_enter_large_ai(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/"package.json").write_text('{"dependencies":{"express":"5"}}',encoding="utf-8")
            baseline=detect(root)
            cold=root/".ai"/"archive"/"events";cold.mkdir(parents=True)
            for index in range(10_100):(cold/f"event-{index}.json").touch()
            started=time.perf_counter();detected=detect(root);elapsed=(time.perf_counter()-started)*1000
            sources=discover_engineering_manifests(root,tracked_paths=["package.json",".ai/archive/events/event-0.json"])
        self.assertEqual(["package.json"],[item["path"] for item in sources["manifests"]])
        self.assertEqual(["web-node"],[item["kind"] for item in detected["projects"]])
        self.assertEqual(baseline["projects"],detected["projects"])
        self.assertEqual(baseline["unknown"],detected["unknown"])
        self.assertGreaterEqual(detected["traversal"]["reserved_state_skipped"],1)
        self.assertLess(elapsed,1000)

    def test_git_inventory_and_dirty_fingerprint_exclude_ai(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);git(root,"init","-b","main")
            (root/"package.json").write_text("{}",encoding="utf-8")
            (root/".ai").mkdir();(root/".ai"/"package.json").write_text('{"name":"state"}',encoding="utf-8")
            git(root,"add","package.json");git(root,"add","-f",".ai/package.json")
            baseline=worktree_fingerprint(root);(root/".ai"/"package.json").write_text('{"name":"changed"}',encoding="utf-8")
            after=worktree_fingerprint(root);identity=identify(root)
        self.assertEqual(1,tracked_file_count(root) if root.exists() else identity["tracked_file_count"])
        self.assertEqual(1,identity["tracked_file_count"])
        self.assertEqual(baseline,after)
        self.assertNotIn(".ai",json.dumps(identity["trusted_markers"]))

    def test_traversal_limit_is_structured(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for index in range(8):(root/f"file-{index}.txt").touch()
            with self.assertRaises(TraversalLimitReached) as caught:
                walk_source_files(root,TraversalBudget(max_entries=2))
        self.assertEqual("TRAVERSAL_LIMIT_REACHED",caught.exception.receipt()["status"])
        self.assertEqual("entries",caught.exception.receipt()["limit"])

    def test_read_only_memory_status_does_not_create_ai(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);result=memory_status(root)
            self.assertFalse((root/".ai").exists())
        self.assertEqual(4000,result["policy"]["session_context_max_chars"])

    def test_bounded_run_streams_and_pages_large_output(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            result=run_bounded(root,"large-output",[sys.executable,"-c","import sys;sys.stdout.write('x'*2000000)"],max_chars=2000,max_spool_bytes=128*1024)
            evidence=root/result["evidence_path"]
            page=read_evidence_page(root,result["evidence_path"],0,1024)
        self.assertTrue(result["truncated"])
        self.assertGreaterEqual(result["observed_bytes"],2_000_000)
        self.assertLessEqual(result["stored_bytes"],128*1024)
        self.assertLessEqual(result["returned_count"],2200)
        self.assertLessEqual(evidence.stat().st_size if evidence.exists() else result["stored_bytes"]+32,128*1024+32)
        self.assertEqual(1024,page["returned_bytes"])

    def test_case_insensitive_reserved_path_and_reparse_are_not_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);reserved=root/".AI"/"state.json";reserved.parent.mkdir();reserved.touch()
            self.assertTrue(is_reserved_source_path(root,reserved))
            target=root/"outside";target.mkdir();(target/"package.json").write_text("{}",encoding="utf-8")
            link=root/"linked"
            try:os.symlink(target,link,target_is_directory=True)
            except OSError:return
            files,metrics=walk_source_files(root,TraversalBudget(max_depth=4))
            self.assertNotIn(link/"package.json",files)
            self.assertGreaterEqual(metrics.reparse_points_skipped,1)


if __name__=="__main__":unittest.main()
