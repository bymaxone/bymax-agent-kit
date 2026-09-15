# Target resolution

The audit is pointed at one **target**, and the target decides what is examined.
The same engine — recon, hunt, verify, hand off, re-test — runs behind all of
them; only the scope changes. The target is the first positional argument
**after the recognized flags and their values are removed** (`--depth <level>`,
`--domains <list>`, `--live`, `--no-handoff`, `--no-issues`), so a flag value
like the `full` in `--depth full` is never mistaken for the target; the rest of
the line is a free-text instruction that steers focus and depth.

```
/bymax-qa:audit <target> [free-text instruction] [flags]
```

An audit that guesses its target wrong wastes a run, so resolution is
deterministic and always reported back in the run header: "Target: <what> →
<resolved scope>". When the automatic classification could go two ways, an
explicit prefix settles it.

## Classification (first match wins)

| The argument looks like | Resolves to | Example |
| --- | --- | --- |
| `ticket:<KEY>` or a bare Jira key `^[A-Z][A-Z0-9]+-\d+$` | a **ticket** target | `BYM-123`, `ticket:PROJ-45` |
| `pr:<n>` or `#<n>` or a PR URL | a **pull-request** target | `#182`, `pr:182` |
| `branch:<name>`, or a token that `git rev-parse --verify` resolves to a ref | a **branch** target | `feat/login`, `branch:release/2.1` |
| a token containing `..` or `...` | a **range** target | `main..HEAD`, `v1.2...HEAD` |
| `path:<dir>` or an existing file/directory | a **path** target | `src/modules/auth`, `path:apps/backend` |
| nothing | the **whole system**, scoped by `.claude/qa/scope.md` | `/bymax-qa:audit` |

Precedence resolves a genuine collision: a bare token that matches the Jira-key
pattern **and** names a git ref is treated as a ticket **only if Jira access
resolves** (below); otherwise it falls through to the branch reading. The
explicit prefixes (`ticket:`, `branch:`, `pr:`, `path:`) override the
inference entirely — reach for them the moment a name is ambiguous, and the
free-text instruction can restate it in words ("audit the branch, not the
ticket").

## What each target changes

Everything else — the domains, the verifier, the finding contract, the hook,
the workspace, the hand-off — is identical. The target changes two things: the
**surface** the hunt covers, and whether an **acceptance-criteria axis** runs.

| Target | Surface hunted | Acceptance axis | Notes |
| --- | --- | --- | --- |
| whole system | every mounted route and boundary from recon | no | the full audit; `scope.md` required |
| branch / range / PR | the changed files and the routes/behaviour they touch | no | scopes the hunt to the diff, the way a code review scopes a change — see below |
| path | the files under the path and the routes/guards/queries/config they define or touch | no | audits a subtree (a module, a service) in place — recon still maps the whole system; see below |
| ticket | the change the ticket produced (its linked branch/PR, or the diff you name) | **yes** — `references/acceptance.md` | criteria pass/fail **and** security on the touched surface |

## Branch, range and PR targets

Scope the hunt to the change, not the whole tree:

1. Resolve the base the way `/bymax-quality:code-review` does — the repository's
   real default branch, never assumed `main`. For a range, honour both sides;
   for a PR, `gh pr checkout` then diff against its base.
2. Compute the changed surface: `git diff --name-only <base>...<head>`, plus the
   routes, guards, queries and config those files define or touch.
3. Run the full domain pipeline over that surface only. Recon still draws the
   whole trust-boundary map (a change is judged against the system it lands in),
   but the hunters spend their effort on the diff.

This **complements** `/bymax-quality:code-review`, it does not replace it. That
command is a static review of the diff against the Bymax conventions and blocks
a commit; this one runs the system and looks for an exploitable defect in the
same change, with a reproduction and, under `--live`, a probe. Same scope, two
different lenses — say so in the report so a reader does not take one for the
other.

## Path targets

`path:<dir>` — or a bare argument that names an existing file or directory —
scopes the hunt to a **subtree** instead of a diff. Reach for it to audit one
module or service in place ("audit the backend"), where there is no single
branch or ticket to point at:

1. Resolve the path against the repository root, confirm it **exists** and lies
   **inside** the scope's `repo` (`git rev-parse --show-toplevel`); a path
   outside the scoped repository is refused the way an out-of-scope host is.
2. The hunted surface is every file under that path — tracked **and**
   untracked-but-not-ignored, since a path audits code as it stands and the run
   allows a dirty tree (`git ls-files -- <path>` plus
   `git ls-files --others --exclude-standard -- <path>`) — plus the routes,
   guards, queries and config those files define or touch. Recon still draws the
   **whole** trust-boundary map — a subtree is judged against the system it
   lives in — but the hunters spend their effort inside the path.
3. A path target audits code **as it stands**, not a change: there is no diff
   and no acceptance axis (that is a ticket-only concern). A path target needs
   only a minimal scope (its `repo` and `approved-by`); as with every target,
   `--live` additionally requires `allowed-hosts` and `base-url`.

## Ticket targets and Jira access

When the target is a ticket, the skill needs to read it, and it **verifies
access before promising anything** — it never fabricates a criterion. The
ladder, in order, stopping at the first that works:

1. **An Atlassian MCP** — if a tool like `mcp__atlassian__*` (or any Jira MCP)
   is available this session, fetch the issue through it: summary, description,
   the acceptance-criteria field, the definition of done, and the development
   panel (linked branch, commits, PR) when exposed.
2. **A CLI** — else `command -v jira` (the `ankitpokhrel/jira-cli`) or `acli`
   (Atlassian's official CLI). Read the issue non-interactively, e.g.
   `jira issue view <KEY> --plain`, and its linked development info if the tool
   exposes it.
3. **Neither** — stop and ask the human to paste the ticket's description and
   acceptance criteria, or to give a branch/PR target instead. Do not invent
   the criteria, and do not proceed as if the ticket said nothing.

Record which method was used in the run header ("Ticket: BYM-123 via atlassian
MCP"). The `jira:` block in `scope.md` (site, project keys, whether write-back
is allowed) tightens this: a ticket key outside the configured projects is
refused the way an out-of-scope host is.

From a ticket the skill also derives the **change to audit** — the linked
branch or PR from the development panel, or a branch whose name carries the key
(`feat/BYM-123-…`) — so a ticket target is the acceptance axis **and** a branch
scoping, combined. If no change can be linked, audit runs against the branch or
range the human names alongside the ticket.

## The free-text instruction

Whatever follows the target steers the run without new flags: "focus on the
auth changes", "only the acceptance criteria, skip the security sweep", "just
the two endpoints the ticket adds". Read it as intent and reflect what you did
in the report. The instruction narrows or directs; it never widens the target
beyond what the scope authorizes. It also **cannot enable live probes**: those
run only under the `--live` flag (with the scope's `allowed-hosts` + `base-url`,
per `SKILL.md`). A free-text "run it live" is a prompt to re-run with `--live`,
never a trigger for a live request on its own — a run without the flag stays
static against every host.
