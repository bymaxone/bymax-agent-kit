# Authorization & scope

The scope file is the whole authorization for an audit. It is the difference
between security testing and an attack. Read it before anything, honour it
without exception, and stop when it is missing or ambiguous rather than guess.

## What the scope must answer

`.claude/qa/scope.md` (from `templates/scope.template.md`) has to answer, in
writing:

- **What repository** — absolute path and GitHub slug. The preflight compares
  it to the target's `git rev-parse --show-toplevel`; a mismatch stops the run.
- **Which hosts** may be tested, each tagged `local`, `staging` or
  `production`. Only `local` and `staging` are ever reachable. A `production`
  row exists so the auditor recognises and refuses it, never so it is tested.
- **`base-url`** for live probes, which must resolve to a `local`/`staging`
  host, plus the health path that proves it is up.
- **Environment** — how the stack is brought up (`docker compose up -d`, a
  dev server command), and the named test accounts or the registration path
  used to mint throwaway ones. Never a real user's credentials.
- **Owners** — the component → repository → peer-agent map. This is what a
  hand-off routes on. A component with no owner routes to an issue or the human.
- **Policies** — is issue-filing allowed, and to which repositories; is any
  destructive probe (a bounded rate-limit burst, say) permitted, and against
  which host; what is explicitly out of bounds.
- **`approved-by`** — a human name and date. An unapproved scope is a draft;
  the preflight refuses to run against it.

## The allow-list is enforced, not trusted

The `qa-guard` hook reads `allowed-hosts` from the scope and blocks any
`Bash` command invoking a network tool (`curl`, `wget`, `nc`, `nmap`, `httpie`,
`sqlmap`, `nuclei`, `zap*`, `ffuf`, `nikto`) whose target host is not on the
list, while `.claude/qa/.active` exists. This means:

- A probe against an unlisted host fails at the hook with a message, not
  silently — you will see it and fix the scope or the command, never
  accidentally hit the wrong target.
- The hook resolves the host from the command's URL argument. A command that
  hides its target (a shell variable, an indirect redirect) is refused for
  being unresolvable — write the host literally.
- The hook cannot see intent, only hosts. It is a floor. The rule that you
  test only what the scope authorizes is still yours to keep; the hook just
  makes the common slip impossible.

## When scope is missing or unclear

- **No file** → do not improvise a scope. Run `init`, interview the human, get
  the `approved-by` line filled.
- **Ambiguous host** (a name that could be staging or prod) → treat as
  production and refuse until the human disambiguates in the file.
- **A tempting target just outside the list** (an admin panel on a nearby
  port, a second service) → out of scope is out of scope. Note it as a
  recon observation for the human to add to the scope, and do not touch it.

## `init` mode

1. Confirm the working directory is the project to audit, or ask for its path.
2. Interview: which hosts and environments, how the stack comes up, who owns
   each component (run `ListAgents` and offer the live sessions as candidates),
   whether issues may be filed and where, what is off-limits.
3. **Validate the workspace root, then create it, then write — in this order.**
   The `qa-guard` confinement is **not yet armed** during `init` (no `.active`
   marker), so a symlinked root (e.g. `.claude/qa -> ../src`) would redirect
   these writes into the source tree. Guard against it explicitly:
   1. **Check the existing path components.** If `.claude` exists and is a
      symlink, or `.claude/qa` exists and is a symlink, **refuse** and ask the
      human to remove the link. (On a first `init`, `.claude/qa` normally does
      not exist yet — that is fine; only an existing component that is a symlink
      is refused here.)
   2. **Create the workspace directory:** `mkdir -p .claude/qa`.
   3. **Verify the physical path is canonical:** `cd .claude/qa && pwd -P` must
      equal `<project>/.claude/qa`. If it does not (a symlinked `.claude`
      ancestor), **refuse** — do not write into it.
   4. **Only then write files:** `.claude/qa/scope.md` from the template,
      `registry.md` from `templates/registry.template.md`, and the empty
      subdirectories.
4. **Stop.** Print the scope path and ask the human to review it and fill
   `approved-by`. Never continue into a run from `init`.
