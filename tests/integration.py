#!/usr/bin/env python3
"""Real CUPS render + socket backend tests; --queue also exercises cupsd/lp.

Run --queue only on a disposable Linux test machine/VM with the driver installed.
Creates a unique temporary queue, removes it in finally, uses loopback only.
"""
import argparse
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
import time
from protocol import decode

ROOT = Path(__file__).resolve().parents[1]
PPD = ROOT/'ppd/epson-tm-l90.ppd'


def command(args, **kw):
    p = subprocess.run(list(map(str, args)), capture_output=True, timeout=90, **kw)
    if p.returncode:
        raise AssertionError(f'{args}: {p.returncode}\n{p.stderr.decode(errors="replace")}')
    return p


def make_pdf(path):
    # 50 x 25 mm, 10-mm black square at (6,6), blank page, smaller square.
    streams = [b'0 g 17.007874 17.007874 28.346457 28.346457 re f\n', b'',
               b'0 g 17.007874 17.007874 14.173228 14.173228 re f\n']
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R 5 0 R 7 0 R] /Count 3 >>']
    for i, stream in enumerate(streams):
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 141.732283 70.866142] /Resources << >> /Contents {4+2*i} 0 R >>'.encode())
        objects.append(f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream')
    data, offsets = b'%PDF-1.4\n', [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data)); data += f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref = len(data)
    data += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    data += b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets[1:])
    data += f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    path.write_bytes(data)


class Sink:
    def __init__(self, reset=False):
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0)); self.sock.listen()
        self.sock.settimeout(45)
        self.port = self.sock.getsockname()[1]
        self.reset, self.data, self.error = reset, b'', None
        self.thread = threading.Thread(target=self.receive, daemon=True)
        self.thread.start()

    def receive(self):
        try:
            conn, _ = self.sock.accept()
            with conn:
                conn.settimeout(45)
                while True:
                    b = conn.recv(1024 if self.reset else 65536)
                    if not b: break
                    self.data += b
                    if self.reset:
                        conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                        break
        except Exception as e:
            self.error = e
        finally:
            self.sock.close()

    def finish(self):
        self.thread.join(50)
        assert not self.thread.is_alive(), 'network sink timed out'
        assert self.error is None, self.error
        return self.data

    def uri(self):
        return f'socket://127.0.0.1:{self.port}/?waiteof=false&contimeout=2'


def bbox(page):
    pixels = [(x, y) for y, row in enumerate(page['pixels']) for x, v in enumerate(row) if v]
    if not pixels: return None
    return (min(x for x, _ in pixels), min(y for _, y in pixels),
            max(x for x, _ in pixels), max(y for _, y in pixels))


def verify_pdf(data, copies=1, collated=True):
    pages, events = decode(data)
    assert len(pages) == 3*copies, len(pages)
    assert events.count('cut') == len(pages)
    kinds = []
    for page in pages:
        assert abs(page['width'] - 352) <= 1, page['width']
        assert abs(len(page['pixels']) - 176) <= 1, len(page['pixels'])
        box = bbox(page)
        if box is None:
            kinds.append('blank'); continue
        width = box[2]-box[0]+1
        kinds.append('large' if width > 60 else 'small')
        assert abs(box[0]-24) <= 2, box
        if width > 60:
            assert abs(width-80) <= 2 and abs(box[1]-60) <= 2, box
        else:
            assert abs(width-40) <= 2 and abs(box[1]-100) <= 2, box
    expected = ['large', 'blank', 'small']*copies if collated else [k for k in ('large','blank','small') for _ in range(copies)]
    assert kinds == expected, (kinds, expected)


def backend_tests(data, temp):
    serverbin = command(['cups-config', '--serverbin']).stdout.decode().strip()
    backend = Path(serverbin)/'backend/socket'
    source = temp/'job.prn'; source.write_bytes(data)
    sink = Sink()
    env = dict(os.environ, DEVICE_URI=sink.uri())
    command([backend, '1', 'test', 'fixture', '1', '', source], env=env)
    assert sink.finish() == data, 'CUPS socket backend altered payload'
    print('PASS: CUPS socket backend delivered exact bytes to TCP sink')
    # An unbound loopback port, held/reserved until the backend starts.
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    env['DEVICE_URI'] = f'socket://127.0.0.1:{port}/?contimeout=2'
    p = subprocess.run([str(backend), '2', 'test', 'refused', '1', '', str(source)], env=env, capture_output=True, timeout=15)
    assert p.returncode != 0, p.stderr
    print(f'PASS: refused connection reported failure (backend exit {p.returncode})')
    # Large stream forces write-side failure rather than fitting entirely in TCP buffers.
    source.write_bytes(data * (16*1024*1024//len(data)+1))
    sink = Sink(reset=True); env['DEVICE_URI'] = sink.uri()
    p = subprocess.run([str(backend), '3', 'test', 'reset', '1', '', str(source)], env=env, capture_output=True, timeout=15)
    received = sink.finish()
    assert received and len(received) < source.stat().st_size
    assert p.returncode != 0, p.stderr
    print(f'PASS: mid-job reset reported failure after {len(received)} bytes (backend exit {p.returncode})')


def queue_tests(pdf, temp):
    queue = f'tml90-test-{os.getpid()}'
    created = False
    try:
        for collated in (True, False):
            sink = Sink()
            command(['lpadmin', '-p', queue, '-E', '-v', sink.uri(), '-P', PPD,
                     '-o', 'printer-is-shared=false', '-o', 'printer-error-policy=stop-printer'])
            created = True
            command(['lp', '-d', queue, '-n', '2', '-o', 'media=Custom.50x25mm', '-o', 'TML90Cut=Page',
                     '-o', f'Collate={str(collated).lower()}', pdf])
            verify_pdf(sink.finish(), 2, collated)
            deadline = time.monotonic()+20
            while command(['lpstat', '-W', 'not-completed', '-o', queue]).stdout.strip():
                assert time.monotonic() < deadline, 'job did not complete'
                time.sleep(.2)
            print(f'PASS: lp -> cupsd -> PDF filters -> driver -> socket, 3 pages x 2 copies, Collate={collated}')
        text = temp/'order.txt'; text.write_text('\ufeffCloverAgent test\nOrder 123\n', encoding='utf-8')
        sink = Sink()
        command(['lpadmin', '-p', queue, '-v', sink.uri()])
        command(['lp', '-d', queue, '-n', '2', '-o', 'media=Custom.50x25mm', '-o', 'TML90Cut=Page',
                 '-o', 'document-format=text/plain;charset=utf-8', '-o', 'fit-to-page',
                 '-o', 'page-left=18', '-o', 'page-right=0', '-o', 'page-top=0', '-o', 'page-bottom=0', text])
        pages, _ = decode(sink.finish())
        assert len(pages) == 2 and all(bbox(p) for p in pages), len(pages)
        print('PASS: existing CloverAgent text/plain options and 2 copies through cupsd')
        # Confirm a delivery failure is visible at queue level with our policy.
        s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
        command(['lpadmin', '-p', queue, '-v', f'socket://127.0.0.1:{port}/?contimeout=2'])
        command(['lp', '-d', queue, pdf])
        deadline = time.monotonic()+35
        while True:
            state = command(['lpstat', '-p', queue, '-l']).stdout.decode()
            if 'disabled' in state: break
            assert time.monotonic() < deadline, f'queue did not expose failure: {state}'
            time.sleep(.2)
        assert command(['lpstat', '-W', 'not-completed', '-o', queue]).stdout.strip()
        print('PASS: refused queue job remained pending and printer stopped under stop-printer policy')
    finally:
        if created:
            subprocess.run(['cancel', '-a', queue], capture_output=True)
            command(['lpadmin', '-x', queue])


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--queue', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='tml90-integration-') as directory:
        temp = Path(directory); pdf = temp/'labels.pdf'; make_pdf(pdf)
        raster = command(['cupsfilter', '-p', PPD, '-i', 'application/pdf', '-m', 'application/vnd.cups-raster',
                          '-o', 'media=Custom.50x25mm', pdf]).stdout
        data = command([ROOT/'build/rastertotml90', '1', 'test', 'fixture', '1', 'TML90Cut=Page'],
                       input=raster, env=dict(os.environ, PPD=str(PPD))).stdout
        verify_pdf(data)
        print('PASS: CUPS PDF rendering, measured 50x25-mm geometry, blank-page preservation')
        for media, w, h in [('1x2Rotated', 50.8, 25.4), ('40x58mmRotated', 58, 40),
                            ('50x70mmRotated', 70, 50), ('Custom.38x15mm', 38, 15),
                            ('Custom.78x300mm', 78, 300)]:
            ras = command(['cupsfilter', '-p', PPD, '-i', 'application/pdf', '-m', 'application/vnd.cups-raster',
                           '-o', f'media={media}', pdf]).stdout
            encoded = command([ROOT/'build/rastertotml90', '1', 'test', 'sizes', '1', ''], input=ras,
                              env=dict(os.environ, PPD=str(PPD))).stdout
            pages, _ = decode(encoded)
            assert len(pages) == 3
            for page in pages:
                assert abs(page['width']-(w-6)*203/25.4) <= 1, (media, page['width'])
                assert abs(len(page['pixels'])-(h-3)*203/25.4) <= 1, (media, len(page['pixels']))
        print('PASS: other preset sizes and both custom-size limits through CUPS rendering')
        backend_tests(data, temp)
        if args.queue: queue_tests(pdf, temp)


if __name__ == '__main__': main()
