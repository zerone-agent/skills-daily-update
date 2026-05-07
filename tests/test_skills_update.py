"""Tests for skills_update.py"""

import json
import os
import tempfile
import unittest
import zipfile

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.skills_update import RepoManager, StateStore, SkillsUpdater


class TestRepoManager(unittest.TestCase):
    def setUp(self):
        self.config = {
            "_default_repo": "https://gitee.com/zerone-agent/agent-use-skills.git",
            "_default_path": "awesome-skills/skills",
            "skills": {
                "skill-market": {"repo": None, "subdir": "skill-market"},
                "custom-skill": {"repo": "https://github.com/example/custom.git", "subdir": "src"},
                "root-skill": {"repo": "https://github.com/example/root.git", "subdir": None},
            },
        }
        self.manager = RepoManager(self.config)

    def test_load_config(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(self.config, f)
            temp_path = f.name
        
        try:
            manager = RepoManager.load(temp_path)
            self.assertEqual(manager.config["_default_repo"], "https://gitee.com/zerone-agent/agent-use-skills.git")
        finally:
            os.unlink(temp_path)

    def test_get_repo_url_default(self):
        url, subdir = self.manager.get_repo_url("skill-market")
        self.assertEqual(url, "https://gitee.com/zerone-agent/agent-use-skills.git")
        self.assertEqual(subdir, "awesome-skills/skills/skill-market")

    def test_get_repo_url_independent(self):
        url, subdir = self.manager.get_repo_url("custom-skill")
        self.assertEqual(url, "https://github.com/example/custom.git")
        self.assertEqual(subdir, "src")

    def test_get_repo_url_root(self):
        url, subdir = self.manager.get_repo_url("root-skill")
        self.assertEqual(url, "https://github.com/example/root.git")
        self.assertIsNone(subdir)

    def test_clone_or_pull(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "test-repo")
            commit = self.manager.clone_or_pull("https://github.com/octocat/Hello-World.git", dest)
            self.assertIsNotNone(commit)
            self.assertEqual(len(commit), 40)


class TestStateStore(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.mktemp(suffix=".json")

    def tearDown(self):
        if os.path.exists(self.temp_file):
            os.remove(self.temp_file)

    def test_load_and_save(self):
        data = {"skill-market": "abc123", "superpowers": "def456"}
        store = StateStore(data)
        store.save(self.temp_file)

        store2 = StateStore.load(self.temp_file)
        self.assertEqual(store2.data, data)

    def test_load_nonexistent(self):
        store = StateStore.load("/nonexistent/path.json")
        self.assertEqual(store.data, {})

    def test_get_commit(self):
        store = StateStore({"skill-market": "abc123"})
        self.assertEqual(store.get_commit("skill-market"), "abc123")
        self.assertIsNone(store.get_commit("nonexistent"))

    def test_update_commit(self):
        store = StateStore()
        store.update_commit("skill-market", "new123")
        self.assertEqual(store.get_commit("skill-market"), "new123")


class TestFetch(unittest.TestCase):
    def test_fetch_skills(self):
        updater = SkillsUpdater()
        skills = updater.fetch(framework="openagent", lang="en")
        self.assertIsInstance(skills, list)
        if skills:
            self.assertIsInstance(skills[0], str)
            self.assertGreater(len(skills[0]), 0)


class TestPack(unittest.TestCase):
    def test_pack(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = os.path.join(tmpdir, "skill-test")
            os.makedirs(skill_dir)
            with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
                f.write("# Test Skill\n")

            plan = {
                "skills": [{
                    "name": "test-skill",
                    "source_path": skill_dir,
                    "commit_hash": "abc123",
                    "zip_path": None,
                    "oss_url": None,
                }],
            }

            plan_path = os.path.join(tmpdir, "pack_plan.json")
            with open(plan_path, "w") as f:
                json.dump(plan, f)

            updater = SkillsUpdater()
            output_dir = os.path.join(tmpdir, "dist")
            updater.pack(plan_path, output_dir)

            with open(plan_path, "r") as f:
                updated_plan = json.load(f)

            self.assertIsNotNone(updated_plan["skills"][0]["zip_path"])
            self.assertTrue(os.path.exists(updated_plan["skills"][0]["zip_path"]))

            zip_path = updated_plan["skills"][0]["zip_path"]
            with zipfile.ZipFile(zip_path, "r") as zf:
                files = zf.namelist()
                self.assertIn("SKILL.md", files)


class TestDiscover(unittest.TestCase):
    def test_discover_skill_market(self):
        updater = SkillsUpdater()
        repo_url = updater.discover("skill-market", framework="openagent", lang="en")
        self.assertIsNotNone(repo_url)
        self.assertTrue(repo_url.startswith("https://"))
        self.assertTrue(repo_url.endswith(".git"))

    def test_discover_nonexistent_skill(self):
        updater = SkillsUpdater()
        repo_url = updater.discover("nonexistent-skill-12345", framework="openagent", lang="en")
        self.assertIsNone(repo_url)


class TestUpload(unittest.TestCase):
    def test_upload_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "test-skill.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("SKILL.md", "# Test\n")

            plan = {
                "skills": [{
                    "name": "test-skill",
                    "source_path": "/tmp/test",
                    "commit_hash": "abc123",
                    "zip_path": zip_path,
                    "oss_url": None,
                }],
            }

            plan_path = os.path.join(tmpdir, "pack_plan.json")
            with open(plan_path, "w") as f:
                json.dump(plan, f)

            updater = SkillsUpdater()
            # This will fail without OSS credentials
            with self.assertRaises((ValueError, ImportError)):
                updater.upload(plan_path)


class TestCLI(unittest.TestCase):
    def test_help(self):
        import subprocess
        result = subprocess.run(
            ["python3", "scripts/skills_update.py", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Skills Daily Update Tool", result.stdout)


if __name__ == "__main__":
    unittest.main()
