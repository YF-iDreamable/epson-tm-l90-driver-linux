from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def test_staged_install_and_uninstall_preserve_unrelated_files(self):
        with tempfile.TemporaryDirectory() as td:
            stage = Path(td)
            sentinel = stage/'unrelated'; sentinel.write_text('keep')
            args = ['make', f'DESTDIR={td}', 'SERVERBIN=/usr/lib/cups', 'DATADIR=/usr/share/cups']
            subprocess.run(args+['install'], cwd=ROOT, check=True, capture_output=True)
            exe = stage/'usr/lib/cups/filter/rastertotml90'
            ppd = stage/'usr/share/cups/model/cloverhelper/epson-tm-l90.ppd'
            self.assertEqual(exe.stat().st_mode & 0o777, 0o755)
            self.assertEqual(ppd.stat().st_mode & 0o777, 0o644)
            self.assertEqual(ppd.read_bytes(), (ROOT/'ppd/epson-tm-l90.ppd').read_bytes())
            subprocess.run(args+['uninstall'], cwd=ROOT, check=True, capture_output=True)
            self.assertFalse(exe.exists()); self.assertFalse(ppd.exists())
            self.assertEqual(sentinel.read_text(), 'keep')

    def test_queue_script_rejects_invalid_arguments_before_system_changes(self):
        for args in ([], ['bad/name','127.0.0.1'], ['ok','127.0.0.1/?x=1'],
                     ['ok','localhost','Custom.1x25mm'], ['ok','localhost','Custom.50x25mm','Full']):
            p = subprocess.run(['sh', str(ROOT/'scripts/configure-queue.sh'), *args], capture_output=True)
            self.assertNotEqual(p.returncode, 0)
