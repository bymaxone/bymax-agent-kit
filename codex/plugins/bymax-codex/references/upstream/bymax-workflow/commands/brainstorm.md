---
description: Refine a rough idea before planning. Ask clarifying questions, explore alternatives, surface tradeoffs, and produce a short design spec the user signs off on. WAIT for explicit user approval before handing off to /bymax-workflow:plan.
argument-hint: "[rough idea]"
---

# Brainstorm Command

Pre-plan discipline. Inspired by the `brainstorming` skill from the Superpowers framework.

This command runs **before** `/bymax-workflow:plan`. It refuses to jump into implementation details. Its only job is to make sure we are solving the right problem before any time is spent on a plan.

## When to Use

Use `/bymax-workflow:brainstorm` when:

- The request is vague, ambiguous, or one-line ("add notifications", "improve onboarding", "make it faster").
- More than one reasonable approach exists and the tradeoffs are not obvious.
- Touching domain-critical code (auth, payments, medication safety, privacy) where the wrong design is expensive to undo.
- The user said "I'm thinking about…" or "what if we…" — that's a brainstorm, not a plan.

Do NOT use for:

- Trivial bug fixes with one obvious cause.
- Pure refactors with no behavior change.
- Tasks where the user already wrote the spec.

## How It Works

The agent must walk these phases **in order**. Do not skip ahead.

### 1. Restate the goal

One paragraph in the user's own framing. No solutions yet. End with: "Did I understand the goal correctly?" — and wait.

### 2. Ask clarifying questions

Group questions into batches of 3–5. Cover:

- **Scope**: what's in, what's out, what's "out for v1, in for v2".
- **Users**: who is this for, what do they do today instead.
- **Success**: what does "done" look like — measurable if possible.
- **Constraints**: deadline, performance budget, privacy, regulatory, platform.
- **Non-goals**: things this is explicitly NOT trying to do.

Ask only what is load-bearing. Don't interrogate.

### 3. Explore 2–3 alternatives

For each:

- One-sentence summary.
- Pros (what this is good at).
- Cons (where it bites later).
- Rough effort (S/M/L).
- Key risk.

Recommend one with a short rationale. Make it clear the user can override.

### 4. Produce the spec

Once an approach is chosen, write a short design document:

```
# Design: <short title>

## Goal
<one paragraph>

## Approach
<the chosen alternative, expanded>

## Scope (v1)
- in: ...
- out: ...

## Success criteria
- ...

## Open questions
- ...

## Risks
- ...
```

Keep it under 1 page. No code yet.

### 5. Wait for sign-off

Present the spec and STOP. Do not call `/bymax-workflow:plan`. Do not write code. Do not refactor anything.

The user must respond with one of:

- "approved" / "ok" / "go" → hand off to `/bymax-workflow:plan` with the spec as input.
- "modify: …" → revise the spec.
- "different approach" → go back to step 3.

## Output discipline

- No code in this phase. Not even pseudocode beyond a 1-line shape.
- No file paths, no function signatures. That's `/bymax-workflow:plan`'s job.
- If the user starts answering before you finish asking, pause and integrate — don't bulldoze through your script.

## Integration with other commands

```
/bymax-workflow:brainstorm  →  spec
    ↓
/bymax-workflow:plan        →  step-by-step plan (waits for confirm)
    ↓
/bymax-quality:tdd         →  red-green-refactor implementation
    ↓
/bymax-workflow:verify      →  prove it works, not just compiles
    ↓
/bymax-quality:code-review →  final review
```

## Anti-patterns to refuse

- Skipping straight to "here's how I'd build it" without restating the goal.
- Listing 7 alternatives — that's analysis paralysis, pick the 2–3 that actually compete.
- Producing a 5-page spec for a 2-hour task.
- Asking 20 questions in one batch — overwhelming, batch them.
