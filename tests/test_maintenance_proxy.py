import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class MaintenanceProxyTests(unittest.TestCase):
    def run_install(self, invalid_second=False, fail_validation=False):
        spec = importlib.util.spec_from_file_location('maintenance', Path(__file__).resolve().parents[1] / 'scripts/install_maintenance_proxy.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sites = root / 'sites'; sites.mkdir()
            backups = root / 'backups'
            original = 'server {\n location / {\n proxy_pass http://127.0.0.1:5055;\n }\n}\n'
            first = sites / 'first'; second = sites / 'second'
            first.write_text(original)
            second.write_text(original * 2 if invalid_second else original)
            class Sites:
                def iterdir(self): return iter([first, second])
            def mapped(value):
                if str(value) == '/etc/nginx/sites-enabled': return Sites()
                if str(value) == '/var/backups/shanklife-nginx': return backups
                return Path(value)
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                if fail_validation and len(calls) == 1:
                    raise subprocess.CalledProcessError(1, command)
            with patch.object(module, 'Path', mapped), patch.object(sys, 'argv', ['test', '--app-dir', '/tmp/test', '--port', '5055']), patch.object(module.subprocess, 'run', run):
                with self.assertRaises(SystemExit if invalid_second else subprocess.CalledProcessError):
                    module.main()
            self.assertEqual(first.read_text(), original)
            self.assertEqual(second.read_text(), original * 2 if invalid_second else original)
            self.assertEqual(len(calls), 0 if invalid_second else 2)

    def test_later_invalid_vhost_never_changes_prior_vhost(self):
        self.run_install(invalid_second=True)

    def test_nginx_validation_failure_restores_all_files(self):
        self.run_install(fail_validation=True)
