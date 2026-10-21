import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from protocol import decode

ROOT = Path(__file__).resolve().parents[1]


def fixture(w=352, h=176, bits=1, space=3, pages=1, compressed=1, copies=1, padding=0, dpi=203, duplex=0):
    return subprocess.check_output([str(ROOT/'build/raster-fixture'), *map(str, (w, h, bits, space, pages, compressed, copies, padding, dpi, duplex))])


def run(data, options='', copies='1', env=None, filename=False):
    args = [str(ROOT/'build/rastertotml90'), '1', 'test', 'fixture', str(copies), options]
    environ = dict(os.environ, PPD=str(ROOT/'ppd/epson-tm-l90.ppd'))
    if env: environ.update(env)
    if filename:
        with tempfile.NamedTemporaryFile() as f:
            f.write(data); f.flush()
            return subprocess.run(args+[f.name], capture_output=True, env=environ)
    return subprocess.run(args, input=data, capture_output=True, env=environ)


class FilterTests(unittest.TestCase):
    def check_ok(self, p):
        self.assertEqual(p.returncode, 0, p.stderr.decode(errors='replace'))
        return decode(p.stdout)

    def check_bad(self, p):
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(p.stdout, b'', 'bad jobs must emit no printer bytes')
        self.assertIn(b'ERROR:', p.stderr)

    def test_pixels_widths_depth_polarity_compression_and_padding(self):
        for w in (1, 7, 8, 9, 351, 352, 575, 576):
            for bits, space, compressed in ((1, 3, 0), (1, 0, 1), (8, 3, 1), (8, 18, 0)):
                with self.subTest(w=w, bits=bits, space=space, compressed=compressed):
                    pages, _ = self.check_ok(run(fixture(w, 259, bits, space, compressed=compressed, padding=3)))
                    self.assertEqual(pages[0]['bands'], [128, 128, 3])
                    expected = [[(x*17+y*13) % 23 < 9 for x in range(w)] for y in range(259)]
                    self.assertEqual(pages[0]['pixels'], expected)

    def test_blank_pages_and_boundaries(self):
        for cut in ('None', 'Page', 'Job'):
            pages, events = self.check_ok(run(fixture(pages=3), f'TML90Cut={cut}'))
            self.assertEqual(len(pages), 3)
            self.assertFalse(any(any(row) for row in pages[1]['pixels']))
            self.assertEqual(events.count('cut'), {'None':0, 'Page':3, 'Job':1}[cut])
            self.assertEqual(events.count('post-cut-feed'), events.count('cut'))
            self.assertEqual(events.count('start'), 4 if cut == 'None' else 3)
            for p, page in enumerate(pages):
                self.assertEqual(len(page['pixels']), 176)
                self.assertEqual(page['pixels'][0], [p % 3 != 1 and (x*17+p*7) % 23 < 9 for x in range(352)])

    def test_copies_are_owned_by_renderer(self):
        data = fixture(pages=3)
        p = run(data, copies=3)
        pages, _ = self.check_ok(p)
        self.assertEqual(len(pages), 3, 'never multiply already expanded CUPS pages by argv copies')
        self.assertEqual(p.stderr.count(b'PAGE:'), 3)
        self.check_bad(run(fixture(copies=2), copies=2))

    def test_filename_and_stdin_match(self):
        data = fixture()
        a, b = run(data), run(data, filename=True)
        self.check_ok(a); self.check_ok(b)
        self.assertEqual(a.stdout, b.stdout)

    def test_invalid_options(self):
        data = fixture()
        for copies in ('0', '-1', '1000', 'abc', '1x'):
            self.check_bad(run(data, copies=copies))
        for opt in ('TML90Cut=Full', 'TML90Cut=page', 'MediaType=Continuous'):
            self.check_bad(run(data, opt))
        self.check_bad(run(data, env={'PPD':'/nonexistent-tml90.ppd'}))

    def test_unsupported_raster(self):
        for kw in ({'w':577}, {'h':2401}, {'bits':4}, {'space':1}, {'dpi':300}, {'duplex':1}):
            with self.subTest(**kw): self.check_bad(run(fixture(**kw)))

    def test_truncation_and_trailing_garbage(self):
        for compressed in (0, 1):
            data = fixture(pages=2, compressed=compressed)
            for length in (0, 1, 3, 4, 20, 100, 1799, len(data)//2, len(data)-1):
                with self.subTest(compressed=compressed, length=length): self.check_bad(run(data[:length]))
            for trailer in (b'x', bytes(100), b'RaSt'):
                with self.subTest(compressed=compressed, trailer=trailer): self.check_bad(run(data+trailer))
        self.check_bad(run(b'%PDF-1.7\nnot raster'))

    def test_broken_output_pipe(self):
        with tempfile.TemporaryFile() as f:
            f.write(fixture()); f.seek(0)
            r, w = os.pipe(); os.close(r)
            p = subprocess.run([str(ROOT/'build/rastertotml90'), '1', 'test', 'fixture', '1', ''], stdin=f, stdout=w, stderr=subprocess.PIPE)
            os.close(w)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn(b'output write failed', p.stderr)

    def test_cancellation_while_reading_emits_nothing(self):
        p = subprocess.Popen([str(ROOT/'build/rastertotml90'), '1', 'test', 'fixture', '1', ''],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.stdin.write(fixture()[:100]); p.stdin.flush()
        time.sleep(.05)
        p.terminate()
        stdout, stderr = p.communicate(timeout=5)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(stdout, b'')
        self.assertIn(b'ERROR:', stderr)

    def test_page_limit_is_atomic(self):
        self.check_bad(run(fixture(w=1, h=1, pages=1001)))


if __name__ == '__main__': unittest.main()
