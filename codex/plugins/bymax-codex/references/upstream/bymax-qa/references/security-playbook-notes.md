# Security playbook notes — read before running a playbook's commands or scripts

The playbooks under `acs/` ship unchanged, so what their helpers do is fixed upstream. Each
section below says what one playbook's commands and `scripts/` do beyond reading the project.
Read only the section for the playbook in hand, before its first command. A playbook with no
section here reads local files and changes nothing outside the paths you pass it.

Two rules hold for all of them:

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
| `implementing-sigstore-for-software-signing` | `sign-blob` and `sign-container` pass `--yes`, which records the signer's identity permanently in the public Rekor log; contacts Fulcio and Rekor |
| `generating-and-analyzing-sboms` | `--attest-image` pushes an attestation to the registry and to Rekor |
| `continuous-llm-red-teaming-with-promptfoo` | `run` sends attack prompts to the target model (paid), and Promptfoo generates attacks through its cloud by default |
| `implementing-container-image-minimal-base-with-distroless` | pulls and runs the image under test; without `--image`, `process.py` lists pods in every namespace of the current kube context and prints image environment variables |
| `implementing-epss-score-for-vulnerability-prioritization` | sends the project's CVE ids to api.first.org (`process.py` also calls epss.cyentia.com and cisa.gov) |
| `implementing-semgrep-for-custom-sast-rules`, `integrating-sast-into-github-actions-pipeline` | `--config auto` fetches rules from semgrep.dev and enables usage metrics; `semgrep ci` uploads findings when `SEMGREP_APP_TOKEN` is set |
| `implementing-infrastructure-as-code-security-scanning` | Checkov fetches metadata from its vendor by default; `--custom-checks-dir` executes the Python checks in that directory |

## Writes that need care

| Playbook | What it writes |
| --- | --- |
| `implementing-secret-scanning-with-gitleaks` | `--create-baseline` writes unredacted secrets to `.gitleaks-baseline.json` inside the repository; keep it out of git. `agent.py` reports "No secrets detected" when gitleaks errors |
| `implementing-api-key-security-controls` | `generate` writes the full plaintext key into its report |
| `implementing-gdpr-data-subject-access-request` | file scans write raw personal data to `file_scan_results.json`; the database scan only prints queries and its `CAST(* AS TEXT)` is not valid SQL |
| `scanning-docker-images-with-trivy` | `agent.py` writes to `./trivy_docker/` and reports zero vulnerabilities when trivy errors; `process.py` puts the first 50 characters of each detected secret in its report |
| `integrating-sast-into-github-actions-pipeline` | writes SARIF files into the repository; `agent.py` passes its gate when a scanner errors |
| `hardening-docker-containers-for-production` | `process.py` writes `docker_hardening_report.json` to the current directory |
| `securing-github-actions-workflows` | `agent.py` writes to `./gha_audit/`; `process.py` never detects `pull_request_target` (PyYAML reads the `on:` key as `true`), so read the workflow triggers yourself |

## Downloads

Trivy and Grype download their vulnerability databases and pull images from registries. The
IaC playbook's generated CI template references `checkov-action@master`; pin it to a commit SHA
before adding it to a workflow.
