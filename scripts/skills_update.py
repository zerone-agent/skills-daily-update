#!/usr/bin/env python3
"""
Skills Daily Update Tool

Fetches openagent skills from API, detects git repo updates,
packs changed skills into zips, and publishes to Agent Hub.
"""

import argparse
import json
import os
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import requests
from dotenv import load_dotenv

# Auto-load .env file from project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(project_root, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)


class RepoManager:
    """Manage skill repository configuration and git operations."""

    def __init__(self, config: dict):
        self.config = config

    @classmethod
    def load(cls, path: str) -> "RepoManager":
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return cls(config)

    def get_repo_url(self, skill_name: str) -> tuple[str, Optional[str]]:
        """Get repository URL and subdirectory for a skill."""
        skill_config = self.config.get("skills", {}).get(skill_name, {})
        repo = skill_config.get("repo")
        subdir = skill_config.get("subdir")

        if repo is None:
            repo = self.config["_default_repo"]
            base_path = self.config["_default_path"]
            subdir = f"{base_path}/{subdir}" if subdir else base_path

        return repo, subdir

    def clone_or_pull(self, repo_url: str, dest: str) -> str:
        """Clone repo if not exists, pull if exists. Return commit hash."""
        dest_path = Path(dest)

        if dest_path.exists():
            subprocess.run(
                ["git", "pull"],
                cwd=str(dest_path),
                check=True,
                capture_output=True,
            )
        else:
            subprocess.run(
                ["git", "clone", repo_url, str(dest_path)],
                check=True,
                capture_output=True,
            )

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(dest_path),
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()


class StateStore:
    """Manage state persistence for commit hashes."""

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

    def get_commit(self, skill_name: str) -> Optional[str]:
        return self.data.get(skill_name)

    def update_commit(self, skill_name: str, commit_hash: str) -> None:
        self.data[skill_name] = commit_hash


class SkillsUpdater:
    """Main updater class with CLI subcommands."""

    API_BASE = "https://api.zerone.market/api"
    
    # 黑名单：发布时忽略这些技能
    PUBLISH_BLACKLIST = {
        "reports-summary",
        "weekly-report",
        "huashu-design",
        "ppt-master",
        "baoyu-skills",
        "ljg-skills",
        "minimax-skills",
        "opencli",
        "qiushi-skill",
        "colleague-skill",
        "skill-market",
    }
    
    # 网络配置
    PUBLISH_TIMEOUT = 10  # 10秒超时
    PUBLISH_MAX_RETRIES = 3  # 最大重试次数
    PUBLISH_RETRY_DELAY = 1  # 重试间隔（秒）

    def fetch(self, framework: str = "openagent", lang: str = "en") -> List[str]:
        """Fetch skills list from API, filter by framework, return names only."""
        url = f"{self.API_BASE}/skills"
        params = {"framework": framework, "lang": lang}

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        skills = data.get("data", [])

        names = [
            skill["name"]
            for skill in skills
            if framework in skill.get("frameworks", [])
        ]

        return names

    def discover(self, skill_name: str, framework: str = "openagent", lang: str = "en") -> Optional[str]:
        """Discover real repo URL for a skill via install API.
        
        Calls /api/skills/:name/install and extracts git clone URL from markdown.
        Returns repo URL or None if not found.
        """
        url = f"{self.API_BASE}/skills/{skill_name}/install"
        params = {"framework": framework, "lang": lang}

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Warning: Failed to fetch install info for {skill_name}: {e}")
            return None

        content = response.text
        
        # Extract git clone URL from markdown code blocks
        import re
        
        # Match git clone commands in markdown code blocks
        patterns = [
            r'git clone\s+(https?://[^\s]+\.git)',
            r'git clone\s+(https?://[^\s]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                repo_url = match.group(1)
                # Add .git if missing
                if not repo_url.endswith('.git'):
                    repo_url += '.git'
                return repo_url
        
        return None

    def check(self, repos_path: str, state_path: str, output_path: str = "state/pack_plan.json") -> str:
        """Check for skill updates using persistent local cache and generate pack plan."""
        repo_manager = RepoManager.load(repos_path)
        state = StateStore.load(state_path)

        plan = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "skills": [],
        }

        cache_dir = os.path.expanduser("~/.cache/skills-daily-update/repos")
        os.makedirs(cache_dir, exist_ok=True)

        for skill_name in repo_manager.config.get("skills", {}).keys():
            # 检查黑名单，跳过不需要更新的技能
            if skill_name in self.PUBLISH_BLACKLIST:
                print(f"Skipping blacklisted skill in check: {skill_name}")
                continue
            
            repo_url, subdir = repo_manager.get_repo_url(skill_name)

            repo_dir_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
            dest = os.path.join(cache_dir, repo_dir_name)

            try:
                commit_hash = repo_manager.clone_or_pull(repo_url, dest)
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to update {skill_name}: {e}")
                continue

            source_path = dest
            if subdir:
                source_path = os.path.join(dest, subdir)

            if not os.path.exists(source_path):
                print(f"Warning: Source path not found for {skill_name}: {source_path}")
                continue

            last_commit = state.get_commit(skill_name)
            if last_commit != commit_hash:
                plan["skills"].append({
                    "name": skill_name,
                    "source_path": source_path,
                    "commit_hash": commit_hash,
                    "zip_path": None,
                    "oss_url": None,
                })

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)

        return output_path

    def pack(self, plan_path: str, output_dir: str = "./dist") -> None:
        """Pack skills into zip files according to plan."""
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

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(source_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # Add skill name as top-level directory
                        rel_path = os.path.relpath(file_path, source_path)
                        arcname = os.path.join(skill_name, rel_path)
                        zf.write(file_path, arcname)

            skill["zip_path"] = os.path.abspath(zip_path)
            print(f"Packed: {skill_name} -> {zip_path}")

        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)

    def upload(self, plan_path: str) -> None:
        """Upload packed zips to OSS (legacy, use publish instead)."""
        access_key = os.environ.get("OSS_ACCESS_KEY_ID")
        access_secret = os.environ.get("OSS_ACCESS_KEY_SECRET")
        endpoint = os.environ.get("OSS_ENDPOINT")
        bucket_name = os.environ.get("OSS_BUCKET")

        if not all([access_key, access_secret, endpoint, bucket_name]):
            raise ValueError(
                "Missing OSS credentials. Set OSS_ACCESS_KEY_ID, "
                "OSS_ACCESS_KEY_SECRET, OSS_ENDPOINT, OSS_BUCKET"
            )

        try:
            import oss2
        except ImportError:
            raise ImportError("oss2 is required for upload. Install: pip install oss2")

        auth = oss2.Auth(access_key, access_secret)
        bucket = oss2.Bucket(auth, endpoint, bucket_name)

        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)

        today = datetime.utcnow().strftime("%Y-%m-%d")

        for skill in plan["skills"]:
            zip_path = skill.get("zip_path")
            if not zip_path or not os.path.exists(zip_path):
                print(f"Warning: No zip file for {skill['name']}, skipping upload")
                continue

            oss_key = f"skills/{skill['name']}_{today}.zip"

            try:
                bucket.put_object_from_file(oss_key, zip_path)
                oss_url = f"oss://{bucket_name}/{oss_key}"
                skill["oss_url"] = oss_url
                print(f"Uploaded: {skill['name']} -> {oss_url}")
            except Exception as e:
                print(f"Error uploading {skill['name']}: {e}")
                raise

        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)

    def publish(self, plan_path: str, title_prefix: str = "", description: str = "", skill_type: str = "community") -> None:
        """Publish packed skills to Agent Hub via yioneai adapter."""
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)

        published = []
        
        # Load repos config for descriptions
        repos_path = Path(plan_path).parent.parent / "config" / "repos.json"
        try:
            with open(repos_path, "r", encoding="utf-8") as f:
                repos_config = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load repos.json: {e}")
            repos_config = {"skills": {}}

        for skill in plan["skills"]:
            zip_path = skill.get("zip_path")
            if not zip_path or not os.path.exists(zip_path):
                print(f"Warning: No zip file for {skill['name']}, skipping publish")
                continue

            skill_name = skill["name"]
            
            # 检查黑名单
            if skill_name in self.PUBLISH_BLACKLIST:
                print(f"Skipping blacklisted skill: {skill_name}")
                skill["published"] = False
                continue
            
            title = f"{title_prefix}{skill_name}" if title_prefix else skill_name
            
            # Get skill-specific description from repos.json
            skill_config = repos_config.get("skills", {}).get(skill_name, {})
            skill_description = skill_config.get("description", "")
            desc = skill_description or description or f"Auto-published from skills-daily-update"
            
            title_en = skill_name
            desc_en = skill_config.get("description_en", desc)

            # 检查是否存在同名技能，如果存在则删除
            try:
                # 获取所有技能列表
                list_result = subprocess.run(
                    ["opencli", "yioneai", "list", "-f", "json"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                existing_skills = json.loads(list_result.stdout)
                
                # 查找同名技能
                existing_skill = None
                for s in existing_skills:
                    if s.get("name") == skill_name:
                        existing_skill = s
                        break
                
                if existing_skill:
                    print(f"Found existing skill '{skill_name}' with ID {existing_skill.get('id')}, deleting...")
                    delete_result = subprocess.run(
                        ["opencli", "yioneai", "delete", skill_name],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    print(f"Deleted existing skill: {skill_name}")
                    time.sleep(2)  # 等待删除完成
                    
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
                print(f"Warning: Failed to check/delete existing skill {skill_name}: {e}")
                # 继续尝试发布，即使检查失败

            # 重试机制
            for attempt in range(self.PUBLISH_MAX_RETRIES):
                try:
                    # Call opencli yioneai create with timeout and trace
                    cmd = [
                        "opencli", "yioneai", "create", skill_name,
                        "--title", title,
                        "--title-en", title_en,
                        "--file", zip_path,
                        "--description", desc,
                        "--description-en", desc_en,
                        "--type", skill_type,
                        "-f", "json",
                        "--trace", "retain-on-failure"
                    ]
                    result = subprocess.run(
                        cmd,
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=self.PUBLISH_TIMEOUT,
                    )

                    output = json.loads(result.stdout)
                    if output and len(output) > 0:
                        skill["published"] = True
                        skill["hub_id"] = output[0].get("id")
                        skill["hub_url"] = output[0].get("url")
                        published.append(skill_name)
                        print(f"Published: {skill_name} -> ID {output[0].get('id')}")
                        break  # 成功，跳出重试循环
                    else:
                        print(f"Warning: Empty response for {skill_name}")
                        skill["published"] = False
                        break

                except subprocess.CalledProcessError as e:
                    print(f"Attempt {attempt + 1}/{self.PUBLISH_MAX_RETRIES} failed for {skill_name}")
                    print(f"  Return code: {e.returncode}")
                    if e.stdout:
                        print(f"  Stdout: {e.stdout[:500]}")
                    if e.stderr:
                        print(f"  Stderr: {e.stderr[:500]}")
                    
                    # 分析具体错误类型
                    error_output = e.stderr or e.stdout or str(e)
                    if "EPIPE" in error_output:
                        print(f"  Error type: Broken pipe (EPIPE) - 可能是网络连接中断或服务器关闭连接")
                    elif "ECONNRESET" in error_output:
                        print(f"  Error type: Connection reset (ECONNRESET) - 服务器重置了连接")
                    elif "ETIMEDOUT" in error_output:
                        print(f"  Error type: Connection timed out (ETIMEDOUT) - 连接超时")
                    elif "ENOTFOUND" in error_output:
                        print(f"  Error type: DNS resolution failed (ENOTFOUND) - 域名解析失败")
                    elif "已存在" in error_output:
                        print(f"  Error type: Skill already exists")
                    else:
                        print(f"  Error type: Unknown network error")
                    
                    if attempt < self.PUBLISH_MAX_RETRIES - 1:
                        print(f"  Retrying in {self.PUBLISH_RETRY_DELAY} seconds...")
                        time.sleep(self.PUBLISH_RETRY_DELAY)
                    else:
                        print(f"Failed to publish {skill_name} after {self.PUBLISH_MAX_RETRIES} attempts")
                        skill["published"] = False

                except subprocess.TimeoutExpired:
                    print(f"Attempt {attempt + 1}/{self.PUBLISH_MAX_RETRIES} timeout for {skill_name}")
                    print(f"  Timeout after {self.PUBLISH_TIMEOUT} seconds")
                    if attempt < self.PUBLISH_MAX_RETRIES - 1:
                        print(f"  Retrying in {self.PUBLISH_RETRY_DELAY} seconds...")
                        time.sleep(self.PUBLISH_RETRY_DELAY)
                    else:
                        print(f"Failed to publish {skill_name} after {self.PUBLISH_MAX_RETRIES} attempts (timeout)")
                        skill["published"] = False

                except json.JSONDecodeError as e:
                    print(f"Attempt {attempt + 1}/{self.PUBLISH_MAX_RETRIES} JSON error for {skill_name}: {e}")
                    if attempt < self.PUBLISH_MAX_RETRIES - 1:
                        print(f"  Retrying in {self.PUBLISH_RETRY_DELAY} seconds...")
                        time.sleep(self.PUBLISH_RETRY_DELAY)
                    else:
                        print(f"Failed to publish {skill_name} after {self.PUBLISH_MAX_RETRIES} attempts (JSON error)")
                        skill["published"] = False

                except Exception as e:
                    print(f"Attempt {attempt + 1}/{self.PUBLISH_MAX_RETRIES} unexpected error for {skill_name}: {e}")
                    if attempt < self.PUBLISH_MAX_RETRIES - 1:
                        print(f"  Retrying in {self.PUBLISH_RETRY_DELAY} seconds...")
                        time.sleep(self.PUBLISH_RETRY_DELAY)
                    else:
                        print(f"Failed to publish {skill_name} after {self.PUBLISH_MAX_RETRIES} attempts (unexpected error)")
                        skill["published"] = False

        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)

        print(f"\nPublished {len(published)} skills: {', '.join(published)}")


def main():
    parser = argparse.ArgumentParser(description="Skills Daily Update Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    fetch_parser = subparsers.add_parser("fetch", help="Fetch skills from API")
    fetch_parser.add_argument("--framework", default="openagent", help="Framework filter")
    fetch_parser.add_argument("--lang", default="en", help="Language")

    check_parser = subparsers.add_parser("check", help="Check for updates")
    check_parser.add_argument("--repos", default="config/repos.json", help="Repos config path")
    check_parser.add_argument("--state", default="state/last_commits.json", help="State file path")
    check_parser.add_argument("--output", default="state/pack_plan.json", help="Output plan path")

    pack_parser = subparsers.add_parser("pack", help="Pack skills into zips")
    pack_parser.add_argument("--plan", default="state/pack_plan.json", help="Pack plan path")
    pack_parser.add_argument("--output", default="./dist", help="Output directory")

    upload_parser = subparsers.add_parser("upload", help="Upload to OSS (legacy)")
    upload_parser.add_argument("--plan", default="state/pack_plan.json", help="Pack plan path")

    publish_parser = subparsers.add_parser("publish", help="Publish to Agent Hub via yioneai adapter")
    publish_parser.add_argument("--plan", default="state/pack_plan.json", help="Pack plan path")
    publish_parser.add_argument("--title-prefix", default="", help="Prefix for skill titles")
    publish_parser.add_argument("--description", default="", help="Default description for skills")
    publish_parser.add_argument("--type", default="community", choices=["expert", "community"], help="Skill type (default: community)")

    discover_parser = subparsers.add_parser("discover", help="Discover skill repo URLs from install API")
    discover_parser.add_argument("--skill", help="Single skill name to discover (if not set, discovers all in repos.json)")
    discover_parser.add_argument("--repos", default="config/repos.json", help="Repos config path")
    discover_parser.add_argument("--framework", default="openagent", help="Framework")
    discover_parser.add_argument("--lang", default="en", help="Language")

    args = parser.parse_args()

    updater = SkillsUpdater()

    if args.command == "fetch":
        skills = updater.fetch(args.framework, args.lang)
        print(json.dumps(skills, indent=2, ensure_ascii=False))

    elif args.command == "discover":
        if args.skill:
            # Single skill mode
            repo_url = updater.discover(args.skill, args.framework, args.lang)
            result = {args.skill: repo_url} if repo_url else {args.skill: None}
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            # Batch mode: discover all skills in repos.json
            repo_manager = RepoManager.load(args.repos)
            results = {}
            for skill_name in repo_manager.config.get("skills", {}).keys():
                repo_url = updater.discover(skill_name, args.framework, args.lang)
                results[skill_name] = repo_url
                if not repo_url:
                    print(f"Failed: {skill_name}")
            print(json.dumps(results, indent=2, ensure_ascii=False))

    elif args.command == "check":
        plan_path = updater.check(args.repos, args.state, args.output)
        print(f"Pack plan generated: {plan_path}")

    elif args.command == "pack":
        updater.pack(args.plan, args.output)
        print("Packing complete")

    elif args.command == "upload":
        updater.upload(args.plan)
        print("Upload complete")

    elif args.command == "publish":
        updater.publish(args.plan, args.title_prefix, args.description, args.type)
        print("Publish complete")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
