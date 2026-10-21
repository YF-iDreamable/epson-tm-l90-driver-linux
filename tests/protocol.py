"""Independent strict decoder for the documented command subset, not a printer emulator."""
import struct


def decode(data):
    assert data.startswith(bytes.fromhex('1b40 1d6100 1d50cbcb 1d4c0000')), 'job initialization'
    pos = 13
    pages, events, pending, current = [], [], None, None
    while pos < len(data):
        if data[pos:pos+3] == b'\x1c(L':
            length, fn, mode = struct.unpack_from('<HBB', data, pos+3)
            assert length == 2 and mode == 48
            if fn == 67:
                events.append('start')
                current = {'bands': [], 'pixels': [], 'width': None}
            elif fn == 66:
                events.append('cut-position')
            else:
                raise AssertionError(f'unknown label function {fn}')
            pos += 7
        elif data[pos:pos+3] == b'\x1d(L':
            length = struct.unpack_from('<H', data, pos+3)[0]
            body = data[pos+5:pos+5+length]
            assert len(body) == length, 'truncated graphics'
            if body[:2] == b'0p':
                assert pending is None and current is not None
                assert body[2:6] == b'0\x01\x011'
                w, h = struct.unpack_from('<HH', body, 6)
                assert 1 <= w <= 576 and 1 <= h <= 128
                stride = (w + 7) // 8
                assert len(body) == 10 + stride * h
                pixels = []
                for y in range(h):
                    row = body[10+y*stride:10+(y+1)*stride]
                    if w % 8:
                        assert row[-1] & ((1 << (8-w % 8))-1) == 0, 'dirty row padding'
                    pixels.append([bool(row[x//8] & (128 >> (x % 8))) for x in range(w)])
                pending = (w, h, pixels)
            elif body == b'02':
                assert pending is not None and current is not None
                w, h, pixels = pending
                if current['width'] is None:
                    current['width'] = w
                    pages.append(current)
                assert current['width'] == w
                current['bands'].append(h)
                current['pixels'].extend(pixels)
                pending = None
            else:
                raise AssertionError(f'unknown graphics function {body[:2]!r}')
            pos += 5 + length
        elif data[pos:pos+3] == b'\x1dV\x01':
            assert events[-1] == 'cut-position'
            events.append('cut')
            pos += 3
        elif data[pos:pos+3] == b'\x1bJ\x10':
            assert events[-1] == 'cut'
            events.append('post-cut-feed')
            pos += 3
        else:
            raise AssertionError(f'unexpected bytes at {pos}: {data[pos:pos+20].hex()}')
    assert pending is None
    return pages, events
