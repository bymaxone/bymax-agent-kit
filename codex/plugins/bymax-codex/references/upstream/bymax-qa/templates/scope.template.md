# QA Audit Scope

> The authorization for this audit. Testing is permitted ONLY against what this
> file lists. Production is never a target. Fill every field; the auditor
> refuses to run until `approved-by` is set.

repo: /absolute/path/to/project
slug: owner/repo

# approved-by is REQUIRED. Put a human name and date after the colon. While it is
# empty (as below), the audit refuses to run — an empty value is NOT approval.
approved-by:

## Hosts

Only `local` and `staging` hosts are ever reachable. A `production` row exists
so the auditor recognises and refuses it — never so it is tested.

| Host | Environment | Notes |
| --- | --- | --- |
| localhost | local | dev stack via docker compose |
| 127.0.0.1 | local | same |
| staging.example.test | staging | shared staging — coordinate before load |
| api.example.com | production | OUT OF BOUNDS — listed to be refused |

# Hosts are matched EXACTLY by the qa-guard hook — a subdomain of a listed host
# is not implied. List each host a probe may reach on its own line.
allowed-hosts:
  - localhost
  - 127.0.0.1
  - staging.example.test

base-url: http://localhost:3000
health-path: /health/ready       # a GET here proves the stack is up

## Environment

bring-up: docker compose up -d      # how the stack comes up for --live
test-accounts:                      # named throwaway accounts, or the reg path
  - method: register                # "register" = mint throwaways via the app
    endpoint: POST /auth/register
tenants: 2                          # how many isolated tenants live probes can use

## Owners — component → repo → peer agent

The hand-off routes on this map. A component with no owner routes to an issue
(if allowed) or the human. Run `/bymax-qa:audit init` after `ListAgents` to
seed the peer names; they rotate, so the audit re-checks them live each run.

| Component | Repo (slug) | Owner agent (or "issue" / "human") |
| --- | --- | --- |
| auth | owner/nest-auth | nest-auth (peer session name) |
| backend | owner/repo | backend (peer session name) |
| database | owner/repo | issue |

## Policies

issues:
  allowed: true
  repos:                            # only these repos may receive issues
    - owner/nest-auth
    - owner/repo
  public-repos: []                  # repos that are PUBLIC — HIGH/CRITICAL never
                                    # filed as public issues; use a private advisory

jira:                               # only needed for ticket targets (/bymax-qa:audit BYM-123)
  site: your-org.atlassian.net      # for reference; access is via MCP or the jira/acli CLI
  project-keys:                     # a ticket outside these keys is refused, like an out-of-scope host
    - BYM
    - PROJ
  write-back: false                 # true = post the QA result back to the ticket as a comment
                                    # (never a status change, never secret values)

destructive-probes:
  rate-limit-burst:
    allowed: false                  # a bounded auth-lockout burst — off by default
    host: localhost                 # if enabled, only against this host
  sqlmap: false                     # active SQLi tooling — off unless explicitly on
  nuclei: false
  zap: false

out-of-bounds:                      # things explicitly not to touch, in words
  - any host marked production
  - deleting or mutating real data
  - a nearby admin panel not listed above
