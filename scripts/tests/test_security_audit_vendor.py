"""Regression layer: the vendored third-party skills stay the upstream files.

`plugins/bymax-qa/skills/security-audit/` (Cloudflare) and `plugins/bymax-qa/references/acs/`
(Anthropic-Cybersecurity-Skills) ship upstream files unchanged so that what is installed does
what the original does. This module pins that: every copied file must match the SHA-256
recorded in that folder's `upstream.json`, nothing may be added or dropped beside it, the
Cloudflare validator suites must pass where Node is installed, and the security-playbooks index
must name exactly the playbooks that ship.

Run as a script with `--write-manifest <commit>` or `--write-acs-manifest <commit>` to rewrite
the matching `upstream.json` after a refresh.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / 'plugins/bymax-qa/skills/security-audit'
MANIFEST = SKILL / 'upstream.json'
SUITES = ('validate-findings.test.cjs', 'validate-coverage-ledger.test.cjs')
ACS = ROOT / 'plugins/bymax-qa/references/acs'
ACS_MANIFEST = ACS / 'upstream.json'
ACS_REPOSITORY = 'https://github.com/mukul975/Anthropic-Cybersecurity-Skills'
ROUTER = ROOT / 'plugins/bymax-qa/skills/security-playbooks/SKILL.md'
_SPEC = importlib.util.spec_from_file_location('vendor_manifest',
                                               ROOT / 'scripts/lib/vendor_manifest.py')
vendor_manifest = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vendor_manifest)
digest = vendor_manifest.digest
_EFFECTS = importlib.util.spec_from_file_location('playbook_effects',
                                                  ROOT / 'scripts/lib/playbook_effects.py')
playbook_effects = importlib.util.module_from_spec(_EFFECTS)
_EFFECTS.loader.exec_module(playbook_effects)
NOTES = ROOT / 'plugins/bymax-qa/references/security-playbook-notes.md'


def copied(skill=SKILL):
    """The upstream files of `skill`, the vendored folder by default."""
    return vendor_manifest.copied(skill)


def record(manifest_path, folder, identity):
    """Write `identity` plus the hash of every upstream file under `folder` to the manifest."""
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    manifest.update(identity)
    manifest['files'] = {name: digest(path) for name, path in copied(folder).items()}
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')


def write_manifest(commit):
    """Record the Cloudflare commit and the hash of every copied file."""
    record(MANIFEST, SKILL, {'repository': 'https://github.com/cloudflare/security-audit-skill',
                             'commit': commit, 'path': 'skills/security-audit',
                             'license_path': 'LICENSE'})


def write_acs_manifest(commit):
    """Record the Anthropic-Cybersecurity-Skills commit and the hash of every copied file."""
    record(ACS_MANIFEST, ACS, {'repository': ACS_REPOSITORY, 'commit': commit,
                               'path': 'skills/<playbook>', 'license_path': 'LICENSE'})


def playbooks(folder=ACS):
    """The playbook folders that ship, by name."""
    return sorted(path.name for path in folder.iterdir() if path.is_dir())


def indexed(router=ROUTER):
    """The playbook names the security-playbooks index links to."""
    return sorted(set(re.findall(r'\(\.\./\.\./references/acs/([a-z0-9-]+)/SKILL\.md\)',
                                 router.read_text())))


class SecurityAuditVendorTests(unittest.TestCase):
    """The installed security-audit skill is the upstream skill, byte for byte."""

    def manifest(self):
        """The recorded upstream identity."""
        return json.loads(MANIFEST.read_text())

    def test_the_manifest_names_one_upstream_commit(self):
        """A refresh without a recorded commit leaves no way to diff against upstream."""
        manifest = self.manifest()
        self.assertRegex(manifest['commit'], r'^[0-9a-f]{40}$')
        self.assertEqual(manifest['repository'], 'https://github.com/cloudflare/security-audit-skill')

    def test_every_copied_file_matches_its_upstream_hash(self):
        """An edit to a vendored file changes what the skill does without anyone deciding to."""
        recorded = self.manifest()['files']
        present = copied()
        self.assertEqual(sorted(present), sorted(recorded),
                         'files were added to or removed from the vendored skill')
        for name, path in present.items():
            with self.subTest(file=name):
                self.assertEqual(digest(path), recorded[name], f'{name} differs from upstream')

    def test_the_skill_keeps_its_entrypoint_license_and_validators(self):
        """The skill loads from SKILL.md and its workflow runs both validators by path."""
        present = copied()
        for name in ('SKILL.md', 'LICENSE', 'report-schema.json',
                     'validate-findings.cjs', 'validate-coverage-ledger.cjs', *SUITES):
            self.assertIn(name, present)
        self.assertIn('MIT License', (SKILL / 'LICENSE').read_text())

    def test_a_changed_file_is_caught(self):
        """The hash check is proved against a copy with one byte changed, not trusted."""
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, True)
        target = scratch / 'security-audit'
        shutil.copytree(SKILL, target)
        schema = target / 'report-schema.json'
        schema.write_bytes(schema.read_bytes() + b' ')
        recorded = self.manifest()['files']
        drifted = [name for name, path in copied(target).items() if digest(path) != recorded[name]]
        self.assertEqual(drifted, ['report-schema.json'])

    def test_a_file_added_in_a_subfolder_is_caught(self):
        """A file in a subfolder ships with the skill, so the file-set check has to see it.

        The listing read only the top level, so a nested addition left the set equal to the
        manifest and every case green.
        """
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, True)
        target = scratch / 'security-audit'
        shutil.copytree(SKILL, target)
        (target / 'extra').mkdir()
        (target / 'extra' / 'NOTE.md').write_text('added\n')
        # Only the top-level `OWN` files are this repository's own; a file with one of those
        # names deeper down is an addition like any other.
        (target / 'extra' / 'ATTRIBUTION.md').write_text('added\n')
        present = copied(target)
        self.assertIn('extra/NOTE.md', present)
        self.assertIn('extra/ATTRIBUTION.md', present)
        self.assertNotEqual(sorted(present), sorted(self.manifest()['files']))

    def test_the_upstream_validator_suites_pass(self):
        """The validators the skill runs still pass their own suites.

        Node is installed in CI, where this case is required. Locally a machine without it
        skips the case and says so.
        """
        node = shutil.which('node')
        if node is None:
            if os.environ.get('CI'):
                self.fail('node is required in CI to run the security-audit validator suites')
            self.skipTest('node is not installed; the security-audit validator suites did not run')
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch, True)
        run = subprocess.run([node, '--test', *(str(SKILL / name) for name in SUITES)],
                             cwd=scratch, capture_output=True, text=True, timeout=300)
        self.assertEqual(run.returncode, 0, run.stdout[-4000:] + run.stderr[-4000:])


class AcsPlaybookVendorTests(unittest.TestCase):
    """The shipped Anthropic-Cybersecurity-Skills playbooks are the upstream files, indexed once."""

    def manifest(self):
        """The recorded upstream identity."""
        return json.loads(ACS_MANIFEST.read_text())

    def test_the_manifest_names_one_upstream_commit(self):
        """A refresh without a recorded commit leaves no way to diff against upstream."""
        manifest = self.manifest()
        self.assertRegex(manifest['commit'], r'^[0-9a-f]{40}$')
        self.assertEqual(manifest['repository'], ACS_REPOSITORY)

    def test_every_copied_file_matches_its_upstream_hash(self):
        """An edit, addition or removal in a playbook changes what it does unannounced."""
        recorded = self.manifest()['files']
        present = copied(ACS)
        self.assertEqual(sorted(present), sorted(recorded),
                         'files were added to or removed from the vendored playbooks')
        for name, path in present.items():
            with self.subTest(file=name):
                self.assertEqual(digest(path), recorded[name], f'{name} differs from upstream')

    def test_each_playbook_keeps_its_entrypoint_and_licence(self):
        """Apache-2.0 travels with the work: the root licence and each playbook's own copy."""
        self.assertIn('Apache License', (ACS / 'LICENSE').read_text())
        self.assertTrue(playbooks())
        for name in playbooks():
            with self.subTest(playbook=name):
                self.assertTrue((ACS / name / 'SKILL.md').is_file())
                self.assertIn('Apache License', (ACS / name / 'LICENSE').read_text())

    def test_the_index_names_exactly_the_playbooks_that_ship(self):
        """The index is the only way a playbook is loaded, so it must match the folder.

        A playbook nobody indexes is dead weight in both packages; an index row whose folder is
        gone sends the agent to a missing file.
        """
        self.assertEqual(indexed(), playbooks())

    def test_a_playbook_missing_from_the_index_is_caught(self):
        """The index check is proved against a router with one row removed, not trusted."""
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, True)
        router = scratch / 'SKILL.md'
        text = ROUTER.read_text()
        first = playbooks()[0]
        rows = [line for line in text.splitlines(True) if f'/acs/{first}/SKILL.md' not in line]
        router.write_text(''.join(rows))
        self.assertNotIn(first, indexed(router))
        self.assertNotEqual(indexed(router), playbooks())


class PlaybookApprovalTests(unittest.TestCase):
    """Every command a playbook prescribes that changes another system needs an approval row."""

    def test_every_remote_write_in_a_playbook_has_an_approval_row(self):
        """The notes are the approval list, so a remote write they do not name runs unasked.

        The list was built from the helper scripts alone, and two procedures went unlisted: an
        upload that switched a Cloudflare zone to blocking, and a PUT that replaced a branch's
        protection.
        """
        self.assertEqual(playbook_effects.unlisted(ACS, NOTES), {})

    def test_the_detector_reads_known_remote_writes(self):
        """A detector that stops matching would make the case above pass on nothing."""
        found = playbook_effects.remote_writes(ACS)
        self.assertIn('api.cloudflare.com', found['implementing-api-schema-validation-security'])
        self.assertIn('gh api', found['integrating-sast-into-github-actions-pipeline'])
        self.assertIn('--force', found['implementing-secret-scanning-with-gitleaks'])
        self.assertIn('cosign sign', found['implementing-sigstore-for-software-signing'])

    # Every spelling the detector claims, and reads that resemble them. A refresh that brings
    # a new spelling in adds a row here; the notes' rule, not this list, is what asks the user.
    WRITES = ('curl -X POST https://api.example.org/v1', 'curl --request PUT https://api.example.org/v1',
              'curl -s -d @body.json https://api.example.org/v1', 'curl --data-binary @f https://h/x',
              'curl --json {} https://h/x', 'curl -F file=@a https://h/x', 'curl -T a.tgz https://h/x',
              'gh api repos/o/r/branches/main/protection --method PUT',
              'gh api repos/o/r/labels -f name=bug', 'gh api repos/o/r/hooks --input hook.json',
              'kubectl apply -f deploy.yaml', 'kubectl debug -it pod --image=busybox --target=app',
              'kubectl exec -it pod -- sh', 'kubectl rollout restart deploy/app',
              'helm install op chart/op', 'helm rollback app 1', 'terraform apply', 'terraform import a.b id',
              'docker push registry/app:1', 'docker trust sign registry/app:1', 'npm publish',
              'cosign sign --yes registry/app@sha256:x', 'cosign attest --predicate s.json img',
              'git push --force --all', 'git push -f origin main')
    READS = ('curl -sSfL https://api.example.org/v1', 'curl -X GET https://h/x', 'cosign verify --key k img',
             'kubectl get pods -A', 'gh api repos/o/r/pulls', 'helm template chart', 'terraform plan',
             'docker pull registry/app:1', 'git push origin HEAD:feature', 'a cosign signature is checked')

    def test_each_listed_spelling_of_a_remote_write_is_recognised(self):
        """The detector is a tripwire for refreshes, so each spelling it claims must trip it.

        It began with `-X` for curl and four kubectl verbs, and reviewers found `curl --request`,
        `docker trust sign` and `kubectl debug` in the shipped playbooks with no row.
        """
        for command in self.WRITES:
            with self.subTest(command=command):
                self.assertIsNotNone(playbook_effects.REMOTE_WRITE.search(command))
        for command in self.READS:
            with self.subTest(command=command):
                self.assertIsNone(playbook_effects.REMOTE_WRITE.search(command))

    def test_a_command_continued_on_the_next_line_is_read_whole(self):
        """A method flag on a continuation line belongs to the command above it."""
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, True)
        (scratch / 'demo').mkdir()
        (scratch / 'demo' / 'SKILL.md').write_text('gh api repos/o/r/branches/main/protection \\\n'
                                                   '  --method PUT --input rules.json\n'
                                                   'cosign verify --key k img\n')
        self.assertEqual(playbook_effects.remote_writes(scratch), {'demo': {'gh api': ['SKILL.md:1']}})

    def test_only_a_playbook_row_in_the_approval_table_lists_an_effect(self):
        """An effect named under another heading, or in another playbook's row, asks nobody."""
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, True)
        for name, command in (('first', 'curl -X POST https://api.example.org/x'),
                              ('second', 'git push --force origin main')):
            (scratch / 'acs' / name).mkdir(parents=True)
            (scratch / 'acs' / name / 'SKILL.md').write_text(command + '\n')
        notes = scratch / 'notes.md'
        notes.write_text('## Ask before running\n\n| Playbook | Effect |\n| --- | --- |\n'
                         '| `other` | like `first`, it writes to api.example.org |\n\n'
                         '## Writes that need care\n\n| `second` | `--force` rewrites history |\n')
        self.assertEqual(sorted(playbook_effects.unlisted(scratch / 'acs', notes)), ['first', 'second'])


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--write-manifest':
        write_manifest(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == '--write-acs-manifest':
        write_acs_manifest(sys.argv[2])
    else:
        unittest.main()
