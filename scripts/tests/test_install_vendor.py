"""Regression layer: scripts/install.sh lays each vendored skill out the way Claude Code loads a
personal skill, as ~/.claude/skills/<name>/SKILL.md."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/install.sh'
ECC = sorted(path for path in (ROOT / 'vendor/ecc-skills').glob('*.md') if path.name != 'ATTRIBUTION.md')


class VendorSkillTests(unittest.TestCase):
    """What install.sh writes under ~/.claude/skills for the vendored ECC skills."""

    def scratch_home(self):
        """A HOME of its own, removed after the case."""
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        return home

    def install(self, home):
        """Run the installer's vendor step alone against `home`."""
        run = subprocess.run(['bash', str(SCRIPT), '--no-design-skills', '--no-personal', '--no-mcp'],
                             env=dict(os.environ, HOME=str(home)), capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_each_ecc_skill_is_a_directory_holding_its_skill_file(self):
        """Each vendored file was linked loose as skills/<name>.md, which Claude Code never loads:
        a personal skill is read only as skills/<name>/SKILL.md."""
        home = self.scratch_home()
        self.install(home)
        skills = home / '.claude/skills'
        self.assertTrue(ECC)
        for source in ECC:
            with self.subTest(skill=source.stem):
                target = skills / source.stem / 'SKILL.md'
                self.assertTrue(target.is_symlink())
                self.assertEqual(target.resolve(), source.resolve())
                self.assertFalse((skills / source.name).is_symlink())

    def test_a_loose_link_an_earlier_run_left_is_replaced_by_the_directory(self):
        """A run of the earlier script left skills/<name>.md behind; running this one, twice, leaves
        only the directory form."""
        home = self.scratch_home()
        skills = home / '.claude/skills'
        skills.mkdir(parents=True)
        (skills / ECC[0].name).symlink_to(ECC[0])
        self.install(home)
        self.install(home)
        self.assertFalse((skills / ECC[0].name).is_symlink())
        self.assertEqual((skills / ECC[0].stem / 'SKILL.md').resolve(), ECC[0].resolve())


if __name__ == '__main__':
    unittest.main()
