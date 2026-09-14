# Check the local Codex integration

1. Read `codex --version` and `codex plugin --help` if the executable is present.
   A Codex desktop task can run this package's instructions without launching a
   nested CLI review; do not install Claude or its Codex companion plugin.
2. For marketplace installation, check the CLI supports `plugin marketplace add`,
   `plugin add`, and `plugin list --json`. If absent, direct the user to the current
   official Codex installation/update documentation and verify the installed
   version afterward. Do not guess an old subcommand such as `plugin install`.
3. Read `codex plugin list --marketplace bymax-codex --json`. Match the installed,
   enabled `bymax-codex` entry and its version/path to this package. A marketplace
   listing alone is not evidence that the plugin is installed.
4. If installation is requested, follow the repository's `CODEX.md` and run its
   dedicated `scripts/install-codex.sh`. It registers only the Codex marketplace
   and package; it does not restore Claude settings or install unrelated plugins.
5. Check Python 3 and Git for review capture; check `gh auth status` only for
   GitHub workflows. Test actual scope capture on the user's chosen repository
   before claiming the helper works there. No billed model call is required for
   this check. Start a new Codex task to verify skill discovery after installation.

Report each status with the command/read that established it. An unavailable
CLI or GitHub login is a missing capability, not a successful installation.
