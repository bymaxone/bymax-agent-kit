"""Diagnostic tests: incomplete local setup must never be reported ready."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('doctor', Path(__file__).resolve().parents[1] / 'doctor.py')
DOCTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOCTOR)


class DoctorTests(unittest.TestCase):
    """Check installation drift and absent prerequisites with no account or network access."""

    def test_missing_runtime_and_cli_are_not_ready(self):
        """Having Python alone cannot satisfy the dual-review prerequisites."""
        with tempfile.TemporaryDirectory() as directory, patch.object(DOCTOR.Path, 'home', return_value=Path(directory)):
            with patch.object(DOCTOR.shutil, 'which', return_value=None):
                results = {item['name']: item['ok'] for item in DOCTOR.inspect()}
        self.assertFalse(results['claude'])
        self.assertFalse(results['installed review_claude.py'])
        self.assertFalse(all(results.values()))

    def test_source_drift_is_detected_after_installation(self):
        """One stale helper invalidates readiness even when every executable is present."""
        with tempfile.TemporaryDirectory() as directory, patch.object(DOCTOR.Path, 'home', return_value=Path(directory)):
            runtime = Path(directory) / '.claude/bymax-review'
            runtime.mkdir(parents=True)
            for source in (DOCTOR.ROOT / 'plugins/bymax-quality/scripts').glob('review*'):
                if source.is_file():
                    (runtime / source.name).write_bytes(source.read_bytes())
            with patch.object(DOCTOR.shutil, 'which', return_value='/fixture/tool'):
                self.assertTrue(all(item['ok'] for item in DOCTOR.inspect()))
                (runtime / 'review_delivery.py').write_text('outdated')
                results = {item['name']: item['ok'] for item in DOCTOR.inspect()}
                self.assertFalse(results['installed review_delivery.py'])


if __name__ == '__main__':
    unittest.main()
