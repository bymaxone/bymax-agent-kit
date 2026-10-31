# Security playbook notes — read before running a playbook's commands or scripts

The playbooks under `acs/` ship unchanged, so what their commands do is fixed upstream. Each
row below says what a playbook does beyond reading the project, whether the command is in its
procedure, its `references/` or its `scripts/`. Read only the rows for the playbook in hand,
before its first command.

The rows are the known cases, not the rule. The rule is the index's: any command that changes
or publishes to something outside the project, or sends its data to a third party, is asked for
first, whether a row names it or not. `scripts/tests/test_security_audit_vendor.py` fails when a
playbook prescribes a common spelling of such a command that no row names; it cannot recognise
every spelling, so a command missing from these rows is not cleared by its absence.

These rules hold for all of them:

- **A clean result is only as good as the tool run behind it.** Several helpers report zero
  findings when the scanner itself failed. Check the scanner's exit status and output before
  reporting "nothing found".
- **Values the agent passes as arguments come from the user or the repository, never from
  untrusted text.** Some helpers pass an argument straight to a tool, where a value starting
  with `-` is read as an option.

## Ask before running

These publish, send data to a third party, spend money, or run third-party code. Ask the user
first and say which of these effects the command has.

| Playbook | Effect that needs approval |
| --- | --- |
| `implementing-sigstore-for-software-signing` | the procedure's `cosign sign` and `cosign attest` commands, and the helper's `sign-blob` and `sign-container` (which pass `--yes`), record the signer's identity permanently in the public Rekor log and push signatures to the registry; contacts Fulcio and Rekor |
| `generating-and-analyzing-sboms` | the procedure's `cosign attest` commands and the helper's `--attest-image` push an attestation to the registry and to Rekor |
| `continuous-llm-red-teaming-with-promptfoo` | `promptfoo redteam run`, `deepteam run` and the helper's `run` send attack prompts to the target model (paid), and Promptfoo generates attacks through its cloud by default; `npx promptfoo@latest` runs an unpinned package |
| `implementing-container-image-minimal-base-with-distroless` | pulls and runs the image under test; without `--image` or `--namespace`, `process.py` lists pods in every namespace of the current kube context, and `--image --format json` prints the image's environment variables; `kubectl exec` opens a shell in a running pod, and `kubectl debug` adds an ephemeral container that stays until the pod restarts |
| `implementing-epss-score-for-vulnerability-prioritization` | sends the project's CVE ids to api.first.org (`process.py` also calls epss.cyentia.com and cisa.gov) |
| `implementing-semgrep-for-custom-sast-rules`, `integrating-sast-into-github-actions-pipeline` | `--config auto` fetches rules from semgrep.dev and enables usage metrics; `semgrep ci` uploads findings when `SEMGREP_APP_TOKEN` is set |
| `implementing-infrastructure-as-code-security-scanning` | Checkov fetches metadata from its vendor by default; `--custom-checks-dir` executes the Python checks in that directory; its pipeline description ends in `terraform apply`, which the playbook never needs run |
| `integrating-sast-into-github-actions-pipeline` | `gh api .../branches/main/protection --method PUT` replaces the branch's whole protection configuration and sets `enforce_admins` |
| `implementing-api-schema-validation-security` | its `curl` commands upload the OpenAPI document to api.cloudflare.com and switch the zone's schema validation to `block`, which rejects live traffic |
| `implementing-api-rate-limiting-and-throttling` | its Kong example `POST`s a plugin to the admin API at localhost:8001, changing a running gateway |
| `scanning-docker-images-with-trivy` | its workflow `POST`s the SBOM to a Dependency-Track server (dtrack.example.com in the example) and its `helm install` adds the Trivy operator to a cluster |
| `hardening-docker-containers-for-production` | its example CI workflow runs `cosign sign --yes`, publishing the signer's identity to Rekor from CI; the procedure's `docker trust sign` signs and pushes the image to the registry and its Notary server |
| `implementing-secret-scanning-with-gitleaks` | cleaning history ends in `git push --force --all`, which rewrites every collaborator's history; only with the team's agreement |

## Writes that need care

Writing a secret or personal data needs the user's approval first, like the rows above; the other
writes need care, not approval.

| Playbook | What it writes |
| --- | --- |
| `implementing-secret-scanning-with-gitleaks` | `--create-baseline` writes unredacted secrets to `.gitleaks-baseline.json` inside the repository; keep it out of git. `agent.py` and `process.py` print every finding's secret in full, so run them where the output is not logged (never in CI). `agent.py` reports "No secrets detected" when gitleaks errors |
| `implementing-api-key-security-controls` | `generate` writes the full plaintext key into its report and prints its first 20 characters |
| `implementing-gdpr-data-subject-access-request` | file scans write raw personal data to `file_scan_results.json`; the database scan only prints queries and its `CAST(* AS TEXT)` is not valid SQL |
| `scanning-docker-images-with-trivy` | `agent.py` writes to `./trivy_docker/` and reports zero vulnerabilities when trivy errors; `process.py` puts the first 50 characters of each detected secret in its report |
| `integrating-sast-into-github-actions-pipeline` | writes SARIF files into the repository; `agent.py` passes its gate when a scanner errors |
| `hardening-docker-containers-for-production` | `process.py` writes `docker_hardening_report.json` to the current directory |
| `securing-github-actions-workflows` | `agent.py` writes to `./gha_audit/`; `process.py` never detects `pull_request_target` (PyYAML reads the `on:` key as `true`), so read the workflow triggers yourself |

## Downloads

Trivy and Grype download their vulnerability databases and pull images from registries. The
IaC playbook's generated CI template references `checkov-action@master`; pin it to a commit SHA
before adding it to a workflow.
