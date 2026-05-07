# Skills Daily Update

Automated skill update tool for openagent framework skills.

## Features

- Fetch skills list from Skill Market API
- Detect git repository updates via commit hash comparison
- Pack changed skills into individual zip archives
- Upload to Aliyun OSS

## Installation

```bash
pip3 install -r requirements.txt
```

## Usage

### 1. Fetch Skills

```bash
python3 scripts/skills_update.py fetch --framework openagent --lang en
```

### 2. Check for Updates

```bash
python3 scripts/skills_update.py check --repos config/repos.json --state state/last_commits.json
```

### 3. Pack Updated Skills

```bash
python3 scripts/skills_update.py pack --plan state/pack_plan.json --output ./dist
```

### 4. Upload to OSS

```bash
python3 scripts/skills_update.py upload --plan state/pack_plan.json
```

## Configuration

### Repositories (config/repos.json)

LLM-maintained configuration mapping skills to their git repositories.

```json
{
  "_default_repo": "https://gitee.com/zerone-agent/agent-use-skills.git",
  "_default_path": "awesome-skills/skills",
  "skills": {
    "skill-market": {
      "repo": null,
      "subdir": "skill-market"
    }
  }
}
```

### Environment Variables

Set these before running upload:

```bash
export OSS_ACCESS_KEY_ID=your-key
export OSS_ACCESS_KEY_SECRET=your-secret
export OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
export OSS_BUCKET=your-bucket
```

## Testing

```bash
python3 tests/test_skills_update.py -v
```

## Architecture

- `RepoManager`: Handles git clone/pull and repo configuration
- `StateStore`: Manages commit hash state persistence
- `SkillsUpdater`: Main class with fetch/check/pack/upload operations
- CLI: argparse-based subcommands for each operation
