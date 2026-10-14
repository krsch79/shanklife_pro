import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class MaintenanceSchedulerTests(unittest.TestCase):
    def test_golfbox_runner_does_not_import_app_or_connect_during_maintenance(self):
        with tempfile.TemporaryDirectory() as directory:
            flag = Path(directory) / 'maintenance.lock'
            flag.touch()
            env = {**os.environ, 'SHANKLIFE_MAINTENANCE_FILE': str(flag), 'DATABASE_URL': 'invalid-database://must-not-connect'}
            result = subprocess.run([sys.executable, 'scripts/run_scheduled_golfbox_bookings.py'], env=env, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('deferred during maintenance',result.stdout)
