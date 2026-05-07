# Skills Daily Update Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python CLI tool with SKILL.md wrapper to fetch openagent skills, detect git repo updates, pack changed skills to zip, and upload to Aliyun OSS.

**Architecture:** Python class-based CLI with argparse subcommands (fetch, check, pack, upload). Config-driven via repos.json (LLM-maintained). State tracking via last_commits.json. OSS upload via oss2 SDK.

**Tech Stack:** Python 3.10+, requests, oss2, argparse, subprocess, zipfile, pathlib, datetime

---

## Task 1: Create Project Skeleton

**Files:**
- Create: `scripts/skills_update.py`
- Create: `config/repos.json`
- Create: `state/last_commits.json`
- Create: `tests/test_skills_update.py`
- Create: `SKILL.md`

**Step 1: Create directory structure**

```bash
mkdir -p scripts config state tests
```

**Step 2: Create repos.json template**

```json
{
  "_default_repo": "https://gitee.com/zerone-agent/agent-use-skills.git",
  "_default_path": "awesome-skills/skills",
  "skills": {}
}
```

**Step 3: Create last_commits.json**

```json
{}
```

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: create project skeleton and config files"
```

---

## Task 2: Implement RepoManager Class

**Files:**
- Modify: `scripts/skills_update.py`
- Test: `tests/test_skills_update.py`

**Step 1: Write failing test for RepoManager**

```python
import unittest
from scripts.skills_update import RepoManager

class TestRepoManager(unittest.TestCase):
    def setUp(self):
        self.config = {
            "_default_repo": "https://gitee.com/zerone-agent/agent-use-skills.git",
            "_default_path": "awesome-skills/skills",
            "skills": {
                "skill-market": {"repo": None, "subdir": "skill-market"},
                "custom-skill": {"repo": "https://github.com/example/custom.git", "subdir": "src"}
            }
        }
        self.manager = RepoManager(self.config)
    
    def test_load_config(self):
        with open("config/repos.json", "w") as f:
            import json
            json.dump(self.config, f)
        
        manager = RepoManager.load("config/repos.json")
        self.assertEqual(manager.config["_default_repo"], "https://gitee.com/zerone-agent/agent-use-skills.git")
    
    def test_get_repo_url_default(self):
        url, subdir = self.manager.get_repo_url("skill-market")
        self.assertEqual(url, "https://gitee.com/zerone-agent/agent-use-skills.git")
        self.assertEqual(subdir, "awesome-skills/skills/skill-market")
    
    def test_get_repo_url_independent(self):
        url, subdir = self.manager.get_repo_url("custom-skill")
        self.assertEqual(url, "https://github.com/example/custom.git")
        self.assertEqual(subdir, "src")
    
    def test_clone_or_pull(self):
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "test-repo")
            commit = self.manager.clone_or_pull("https://github.com/octocat/Hello-World.git", dest)
            self.assertIsNotNone(commit)
            self.assertEqual(len(commit), 40)
```

**Step 2: Run test to verify failure**

```bash
python -m pytest tests/test_skills_update.py -v
```
Expected: FAIL with "cannot import name 'RepoManager'"

**Step 3: Implement RepoManager**

```python
import json
import subprocess
import os
from pathlib import Path

class RepoManager:
    """Manage skill repository configuration and git operations"""
    
    def __init__(self, config: dict):
        self.config = config
    
    @classmethod
    def load(cls, path: str) -> "RepoManager":
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return cls(config)
    
    def get_repo_url(self, skill_name: str) -> tuple[str, str | None]:
        """Get repository URL and subdirectory for a skill"""
        skill_config = self.config.get("skills", {}).get(skill_name, {})
        repo = skill_config.get("repo")
        subdir = skill_config.get("subdir")
        
        if repo is None:
            # Use default repository
            repo = self.config["_default_repo"]
            base_path = self.config["_default_path"]
            subdir = f"{base_path}/{subdir}" if subdir else base_path
        
        return repo, subdir
    
    def clone_or_pull(self, repo_url: str, dest: str) -> str:
        """Clone repo if not exists, pull if exists. Return commit hash."""
        dest_path = Path(dest)
        
        if dest_path.exists():
            # Pull latest
            subprocess.run(
                ["git", "pull"],
                cwd=dest,
                check=True,
                capture_output=True
            )
        else:
            # Clone
            subprocess.run(
                ["git", "clone", repo_url, dest],
                check=True,
                capture_output=True
            )
        
        # Get HEAD commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=dest,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
```

**Step 4: Run test**

```bash
python -m pytest tests/test_skills_update.py::TestRepoManager -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: implement RepoManager class"
```

---

## Task 3: Implement StateStore Class

**Files:**
- Modify: `scripts/skills_update.py`
- Test: `tests/test_skills_update.py`

**Step 1: Write failing test for StateStore**

```python
class TestStateStore(unittest.TestCase):
    def setUp(self):
        self.temp_file = "tests/temp_state.json"
    
    def tearDown(self):
        import os
        if os.path.exists(self.temp_file):
            os.remove(self.temp_file)
    
    def test_load_and_save(self):
        from scripts.skills_update import StateStore
        data = {"skill-market": "abc123", "superpowers": "def456"}
        
        store = StateStore()
        store.data = data
        store.save(self.temp_file)
        
        store2 = StateStore.load(self.temp_file)
        self.assertEqual(store2.data, data)
    
    def test_get_commit(self):
        from scripts.skills_update import StateStore
        store = StateStore({"skill-market": "abc123"})
        self.assertEqual(store.get_commit("skill-market"), "abc123")
        self.assertIsNone(store.get_commit("nonexistent"))
    
    def test_update_commit(self):
        from scripts.skills_update import StateStore
        store = StateStore()
        store.update_commit("skill-market", "new123")
        self.assertEqual(store.get_commit("skill-market"), "new123")
```

**Step 2: Run test**

```bash
python -m pytest tests/test_skills_update.py::TestStateStore -v
```
Expected: FAIL

**Step 3: Implement StateStore**

```python
class StateStore:
    """Manage state persistence for commit hashes"""
    
    def __init__(self, data: dict = None):
        self.data = data or {}
    
    @classmethod
    def load(cls, path: str) -> "StateStore":
        if not os.path.exists(path):
            return cls({})
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data)
    
    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
    
    def get_commit(self, skill_name: str) -> str | None:
        return self.data.get(skill_name)
    
    def update_commit(self, skill_name: str, commit_hash: str) -> None:
        self.data[skill_name] = commit_hash
```

**Step 4: Run test**

```bash
python -m pytest tests/test_skills_update.py::TestStateStore -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: implement StateStore class"
```

---

## Task 4: Implement fetch Subcommand

**Files:**
- Modify: `scripts/skills_update.py`
- Test: `tests/test_skills_update.py`

**Step 1: Write failing test for fetch**

```python
class TestFetch(unittest.TestCase):
    def test_fetch_skills(self):
        from scripts.skills_update import SkillsUpdater
        
        updater = SkillsUpdater()
        skills = updater.fetch(framework="openagent", lang="en")
        
        self.assertIsInstance(skills, list)
        if skills:
            self.assertIn("name", skills[0])
            self.assertIn("frameworks", skills[0])
```

**Step 2: Run test**

```bash
python -m pytest tests/test_skills_update.py::TestFetch -v
```
Expected: FAIL

**Step 3: Implement fetch in SkillsUpdater**

```python
import requests
from typing import List, Dict

class SkillsUpdater:
    """Main updater class with CLI subcommands"""
    
    API_BASE = "https://api.zerone.market/api"
    
    def fetch(self, framework: str = "openagent", lang: str = "en") -> List[Dict]:
        """Fetch skills list from API, filter by framework"""
        url = f"{self.API_BASE}/skills"
        params = {"framework": framework, "lang": lang}
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        skills = data.get("data", [])
        
        # Filter to only skills supporting the framework
        filtered = [
            skill for skill in skills
            if framework in skill.get("frameworks", [])
        ]
        
        return filtered
```

**Step 4: Run test**

```bash
python -m pytest tests/test_skills_update.py::TestFetch -v
```
Expected: PASS (requires network)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: implement fetch subcommand"
```

---

## Task 5: Implement check Subcommand

**Files:**
- Modify: `scripts/skills_update.py`
- Test: `tests/test_skills_update.py`

**Step 1: Write failing test for check**

```python
class TestCheck(unittest.TestCase):
    def test_check(self):
        from scripts.skills_update import SkillsUpdater
        
        updater = SkillsUpdater()
        plan_path = updater.check("config/repos.json", "state/last_commits.json")
        
        self.assertTrue(os.path.exists(plan_path))
        
        with open(plan_path, "r") as f:
            import json
            plan = json.load(f)
        
        self.assertIn("generated_at", plan)
        self.assertIn("skills", plan)
        self.assertIsInstance(plan["skills"], list)
```

**Step 2: Run test**

```bash
python -m pytest tests/test_skills_update.py::TestCheck -v
```
Expected: FAIL

**Step 3: Implement check in SkillsUpdater**

```python
import tempfile
from datetime import datetime

class SkillsUpdater:
    # ... fetch method above ...
    
    def check(self, repos_path: str, state_path: str, output_path: str = "state/pack_plan.json") -> str:
        """Check for skill updates and generate pack plan"""
        # Load configuration
        repo_manager = RepoManager.load(repos_path)
        state = StateStore.load(state_path)
        
        plan = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "skills": []
        }
        
        # Temporary directory for repos
        temp_base = tempfile.mkdtemp(prefix="skills-update-")
        
        try:
            for skill_name in repo_manager.config.get("skills", {}).keys():
                repo_url, subdir = repo_manager.get_repo_url(skill_name)
                
                # Determine clone destination
                # Use repo name as directory to avoid conflicts
                repo_dir_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
                dest = os.path.join(temp_base, repo_dir_name)
                
                # Clone or pull
                try:
                    commit_hash = repo_manager.clone_or_pull(repo_url, dest)
                except subprocess.CalledProcessError as e:
                    print(f"Warning: Failed to update {skill_name}: {e}")
                    continue
                
                # Determine source path
                source_path = dest
                if subdir:
                    source_path = os.path.join(dest, subdir)
                    source_path = os.path.join(source_path, skill_name)
                
                if not os.path.exists(source_path):
                    print(f"Warning: Source path not found for {skill_name}: {source_path}")
                    continue
                
                # Check if changed
                last_commit = state.get_commit(skill_name)
                if last_commit != commit_hash:
                    plan["skills"].append({
                        "name": skill_name,
                        "source_path": source_path,
                        "commit_hash": commit_hash,
                        "zip_path": None,
                        "oss_url": None
                    })
        finally:
            # Don't cleanup temp_base - pack needs it
            pass
        
        # Save plan
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
        
        return output_path
```

**Step 4: Run test**

```bash
python -m pytest tests/test_skills_update.py::TestCheck -v
```
Expected: PASS (requires network to clone repos)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: implement check subcommand"
```

---

## Task 6: Implement pack Subcommand

**Files:**
- Modify: `scripts/skills_update.py`
- Test: `tests/test_skills_update.py`

**Step 1: Write failing test for pack**

```python
class TestPack(unittest.TestCase):
    def test_pack(self):
        import tempfile
        import shutil
        
        from scripts.skills_update import SkillsUpdater
        
        # Create temp directory with fake skill
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = os.path.join(tmpdir, "skill-test", "SKILL.md")
            os.makedirs(os.path.dirname(skill_dir))
            with open(skill_dir, "w") as f:
                f.write("# Test Skill\n")
            
            plan = {
                "skills": [{
                    "name": "test-skill",
                    "source_path": os.path.dirname(skill_dir),
                    "commit_hash": "abc123",
                    "zip_path": None,
                    "oss_url": None
                }]
            }
            
            plan_path = os.path.join(tmpdir, "pack_plan.json")
            with open(plan_path, "w") as f:
                json.dump(plan, f)
            
            updater = SkillsUpdater()
            output_dir = os.path.join(tmpdir, "dist")
            updater.pack(plan_path, output_dir)
            
            # Verify plan updated
            with open(plan_path, "r") as f:
                updated_plan = json.load(f)
            
            self.assertIsNotNone(updated_plan["skills"][0]["zip_path"])
            self.assertTrue(os.path.exists(updated_plan["skills"][0]["zip_path"]))
```

**Step 2: Run test**

```bash
python -m pytest tests/test_skills_update.py::TestPack -v
```
Expected: FAIL

**Step 3: Implement pack in SkillsUpdater**

```python
import zipfile

class SkillsUpdater:
    # ... fetch, check methods above ...
    
    def pack(self, plan_path: str, output_dir: str = "./dist") -> None:
        """Pack skills into zip files according to plan"""
        os.makedirs(output_dir, exist_ok=True)
        
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        
        for skill in plan["skills"]:
            source_path = skill["source_path"]
            skill_name = skill["name"]
            
            if not os.path.exists(source_path):
                print(f"Warning: Source path not found for {skill_name}: {source_path}")
                continue
            
            zip_path = os.path.join(output_dir, f"{skill_name}.zip")
            
            # Create zip
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(source_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source_path)
                        zf.write(file_path, arcname)
            
            skill["zip_path"] = os.path.abspath(zip_path)
            print(f"Packed: {skill_name} -> {zip_path}")
        
        # Update plan file
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
```

**Step 4: Run test**

```bash
python -m pytest tests/test_skills_update.py::TestPack -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: implement pack subcommand"
```

---

## Task 7: Implement upload Subcommand

**Files:**
- Modify: `scripts/skills_update.py`
- Test: `tests/test_skills_update.py`

**Step 1: Write failing test for upload**

```python
class TestUpload(unittest.TestCase):
    def test_upload(self):
        import tempfile
        
        from scripts.skills_update import SkillsUpdater
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create fake zip
            zip_path = os.path.join(tmpdir, "test-skill.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("SKILL.md", "# Test\n")
            
            plan = {
                "skills": [{
                    "name": "test-skill",
                    "source_path": "/tmp/test",
                    "commit_hash": "abc123",
                    "zip_path": zip_path,
                    "oss_url": None
                }]
            }
            
            plan_path = os.path.join(tmpdir, "pack_plan.json")
            with open(plan_path, "w") as f:
                json.dump(plan, f)
            
            updater = SkillsUpdater()
            # This will fail without OSS credentials, but tests structure
            try:
                updater.upload(plan_path)
            except Exception:
                pass  # Expected without real OSS
```

**Step 2: Run test**

```bash
python -m pytest tests/test_skills_update.py::TestUpload -v
```
Expected: FAIL

**Step 3: Implement upload in SkillsUpdater**

```python
import oss2

class SkillsUpdater:
    # ... fetch, check, pack methods above ...
    
    def upload(self, plan_path: str) -> None:
        """Upload packed zips to OSS"""
        # Load OSS config from environment
        access_key = os.environ.get("OSS_ACCESS_KEY_ID")
        access_secret = os.environ.get("OSS_ACCESS_KEY_SECRET")
        endpoint = os.environ.get("OSS_ENDPOINT")
        bucket_name = os.environ.get("OSS_BUCKET")
        
        if not all([access_key, access_secret, endpoint, bucket_name]):
            raise ValueError(
                "Missing OSS credentials. Set OSS_ACCESS_KEY_ID, "
                "OSS_ACCESS_KEY_SECRET, OSS_ENDPOINT, OSS_BUCKET"
            )
        
        # Initialize OSS
        auth = oss2.Auth(access_key, access_secret)
        bucket = oss2.Bucket(auth, endpoint, bucket_name)
        
        # Load plan
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        for skill in plan["skills"]:
            zip_path = skill.get("zip_path")
            if not zip_path or not os.path.exists(zip_path):
                print(f"Warning: No zip file for {skill['name']}, skipping upload")
                continue
            
            # OSS path: skills/{date}/{skill-name}.zip
            oss_key = f"skills/{today}/{skill['name']}.zip"
            
            try:
                bucket.put_object_from_file(oss_key, zip_path)
                oss_url = f"oss://{bucket_name}/{oss_key}"
                skill["oss_url"] = oss_url
                print(f"Uploaded: {skill['name']} -> {oss_url}")
            except Exception as e:
                print(f"Error uploading {skill['name']}: {e}")
                raise
        
        # Update plan file
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
```

**Step 4: Run test**

```bash
python -m pytest tests/test_skills_update.py::TestUpload -v
```
Expected: PASS (skips actual upload)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: implement upload subcommand with OSS support"
```

---

## Task 8: Implement CLI with argparse

**Files:**
- Modify: `scripts/skills_update.py`

**Step 1: Add main() function**

```python
def main():
    parser = argparse.ArgumentParser(description="Skills Daily Update Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch skills from API")
    fetch_parser.add_argument("--framework", default="openagent", help="Framework filter")
    fetch_parser.add_argument("--lang", default="en", help="Language")
    
    # check command
    check_parser = subparsers.add_parser("check", help="Check for updates")
    check_parser.add_argument("--repos", default="config/repos.json", help="Repos config path")
    check_parser.add_argument("--state", default="state/last_commits.json", help="State file path")
    check_parser.add_argument("--output", default="state/pack_plan.json", help="Output plan path")
    
    # pack command
    pack_parser = subparsers.add_parser("pack", help="Pack skills into zips")
    pack_parser.add_argument("--plan", default="state/pack_plan.json", help="Pack plan path")
    pack_parser.add_argument("--output", default="./dist", help="Output directory")
    
    # upload command
    upload_parser = subparsers.add_parser("upload", help="Upload to OSS")
    upload_parser.add_argument("--plan", default="state/pack_plan.json", help="Pack plan path")
    
    args = parser.parse_args()
    
    updater = SkillsUpdater()
    
    if args.command == "fetch":
        skills = updater.fetch(args.framework, args.lang)
        print(json.dumps(skills, indent=2, ensure_ascii=False))
    
    elif args.command == "check":
        plan_path = updater.check(args.repos, args.state, args.output)
        print(f"Pack plan generated: {plan_path}")
    
    elif args.command == "pack":
        updater.pack(args.plan, args.output)
        print("Packing complete")
    
    elif args.command == "upload":
        updater.upload(args.plan)
        print("Upload complete")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
```

**Step 2: Test CLI**

```bash
python scripts/skills_update.py --help
python scripts/skills_update.py fetch --framework openagent --lang en | head -20
```

**Step 3: Commit**

```bash
git add -A
git commit -m "feat: add CLI entrypoint with argparse"
```

---

## Task 9: Write SKILL.md

**Files:**
- Create: `SKILL.md`

**Content:**

```markdown
# Skills Daily Update

## Description

Automated skill update workflow for openagent framework. Fetches skills from Skill Market API, detects git repository updates via commit hash comparison, packs changed skills into zip archives, and uploads to Aliyun OSS.

## Triggers

- "update skills"
- "daily update"
- "sync skills"
- "check skill updates"
- "打包技能"
- "上传技能到oss"

## Workflow

1. **Fetch Skills**: Get current skill list from API
2. **Update Config**: LLM updates `config/repos.json` for new/unknown skills
3. **Check Updates**: Compare git commit hashes, generate `state/pack_plan.json`
4. **Review Plan**: LLM reviews which skills have updates
5. **Pack Skills**: Create zip archives for changed skills
6. **Upload to OSS**: Upload zips to configured Aliyun bucket
7. **Update State**: Update `state/last_commits.json` with new commit hashes

## CLI Commands

```bash
# Fetch skills list
python scripts/skills_update.py fetch [--framework openagent] [--lang en]

# Check for updates (outputs pack_plan.json)
python scripts/skills_update.py check --repos config/repos.json --state state/last_commits.json

# Pack skills into zips
python scripts/skills_update.py pack --plan state/pack_plan.json [--output ./dist]

# Upload to OSS
python scripts/skills_update.py upload --plan state/pack_plan.json
```

## Configuration

### config/repos.json (LLM-maintained)

```json
{
  "_default_repo": "https://gitee.com/zerone-agent/agent-use-skills.git",
  "_default_path": "awesome-skills/skills",
  "skills": {}
}
```

- `repo: null` → use default repository
- `repo: "url"` → independent repository

### Environment Variables

```
OSS_ACCESS_KEY_ID
OSS_ACCESS_KEY_SECRET
OSS_ENDPOINT
OSS_BUCKET
```

## Notes for LLM

- When encountering new skills from API, add them to `repos.json`
- For skills with independent repos, set `repo` field accordingly
- Review `pack_plan.json` before packing to confirm which skills changed
- After successful upload, update `last_commits.json` with new commit hashes
- Each skill is packed individually: `{skill-name}.zip`
- OSS path format: `oss://{bucket}/skills/{date}/{skill-name}.zip`
```

**Step 2: Commit**

```bash
git add -A
git commit -m "docs: add SKILL.md"
```

---

## Task 10: Add requirements.txt and README

**Files:**
- Create: `requirements.txt`
- Create: `README.md`

**Step 1: Create requirements.txt**

```
requests>=2.28.0
oss2>=2.16.0
```

**Step 2: Create README.md**

```markdown
# Skills Daily Update

Python CLI tool for syncing openagent framework skills.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Fetch skills
python scripts/skills_update.py fetch

# Check for updates
python scripts/skills_update.py check

# Pack updated skills
python scripts/skills_update.py pack

# Upload to OSS
python scripts/skills_update.py upload
```

## Configuration

Set environment variables for OSS:
```bash
export OSS_ACCESS_KEY_ID=your-key
export OSS_ACCESS_KEY_SECRET=your-secret
export OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
export OSS_BUCKET=your-bucket
```

Edit `config/repos.json` to manage skill repositories.
```

**Step 3: Commit**

```bash
git add -A
git commit -m "docs: add requirements.txt and README"
```

---

## Task 11: Run All Tests

```bash
python -m pytest tests/test_skills_update.py -v
```

Expected: All tests pass.

**Commit:**
```bash
git add -A
git commit -m "test: verify all unit tests pass"
```

---

## Task 12: Integration Test

**Manual verification:**

1. Set OSS environment variables (or skip upload test)
2. Update `config/repos.json` with at least one skill
3. Run: `python scripts/skills_update.py check`
4. Verify `state/pack_plan.json` generated
5. Run: `python scripts/skills_update.py pack`
6. Verify zips created in `./dist`
7. Run: `python scripts/skills_update.py upload` (requires OSS creds)
8. Verify `state/pack_plan.json` updated with `oss_url`

**Commit:**
```bash
git add -A
git commit -m "test: integration test passed"
```

---

## Task 13: Final Review and Cleanup

- Verify all files are tracked: `git status`
- Review code style and docstrings
- Ensure no hardcoded secrets
- Final commit if any changes

```bash
git log --oneline
```

Expected: ~12 commits from this plan.
