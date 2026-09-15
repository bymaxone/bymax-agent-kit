---
description: 'Create, verify, list, or clear named checkpoints during a long-running task. A checkpoint snapshots the current git SHA, test pass rate, and coverage so you can compare against it later (e.g., "did this refactor regress tests?"). Logs to `.claude/checkpoints.log` in the project. Useful for marking "feature-start", "core-done", "refactor-done" while building. Args: create <name> | verify <name> | list | clear.'
argument-hint: "create|verify|list|clear [name]"
---

# Checkpoint Command

Create or verify a checkpoint in your workflow.

## Usage

`/bymax-workflow:checkpoint [create|verify|list|clear] [name]`

## Create Checkpoint

When creating a checkpoint:

1. Run `/bymax-workflow:verify quick` to ensure the current state is clean. That is
   Gate 1 only — static checks plus the suppression scan — so it tells you the tree
   builds, lints and passes its tests. It does **not** produce a pass-rate figure or a
   coverage number; read those from the test run itself if the checkpoint needs them.
2. Create a git stash or commit with checkpoint name
3. Log checkpoint to `.claude/checkpoints.log`:

```bash
echo "$(date +%Y-%m-%d-%H:%M) | $CHECKPOINT_NAME | $(git rev-parse --short HEAD)" >> .claude/checkpoints.log
```

4. Report checkpoint created

## Verify Checkpoint

When verifying against a checkpoint:

1. Read checkpoint from log
2. Compare current state to checkpoint:
   - Files added since checkpoint
   - Files modified since checkpoint
   - Test pass rate now vs then
   - Coverage now vs then

3. Report:
```
CHECKPOINT COMPARISON: $NAME
============================
Files changed: X
Tests: +Y passed / -Z failed
Coverage: +X% / -Y%
Build: [PASS/FAIL]
```

## List Checkpoints

Show all checkpoints with:
- Name
- Timestamp
- Git SHA
- Status (current, behind, ahead)

## Workflow

Typical checkpoint flow:

```
[Start] --> /bymax-workflow:checkpoint create "feature-start"
   |
[Implement] --> /bymax-workflow:checkpoint create "core-done"
   |
[Test] --> /bymax-workflow:checkpoint verify "core-done"
   |
[Refactor] --> /bymax-workflow:checkpoint create "refactor-done"
   |
[PR] --> /bymax-workflow:checkpoint verify "feature-start"
```

## Arguments

$ARGUMENTS:
- `create <name>` - Create named checkpoint
- `verify <name>` - Verify against named checkpoint
- `list` - Show all checkpoints
- `clear` - Remove old checkpoints (keeps last 5)
