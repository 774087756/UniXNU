"""Offline checks for the historical empty CHRP fixture, not kernel execution."""
import ast
import json
from pathlib import Path
import struct
import zlib


def validate(props):
    bank = props['nvram-proxy-data']
    if len(props['nvram-bank-size']) != 4:
        raise ValueError('Invalid size property width')
    size, = struct.unpack('<I', props['nvram-bank-size'])
    if size != len(bank) or size < 32:
        raise ValueError('Bank length mismatch')
    if bank[4:16].rstrip(b'\0') != b'nvram':
        raise ValueError('Expected v1 bank')
    if struct.unpack_from('<I', bank, 16)[0] != zlib.adler32(bank[20:]):
        raise ValueError('Adler mismatch')
    offset, parts = 0, []
    while offset < size:
        if offset+16 > size:
            raise ValueError('Truncated partition')
        sig, checksum, blocks, name = struct.unpack_from('<BBH12s',bank,offset)
        header = bank[offset:offset+16]
        total = sig + sum(header[2:])
        while total > 255:
            total = (total & 255)+(total >> 8)
        if checksum != total:
            raise ValueError('CHRP checksum mismatch')
        length = blocks*16
        if length < 16 or offset+length > size:
            raise ValueError('Invalid partition length')
        parts.append((name.rstrip(b'\0').decode('ascii'),offset,length))
        offset += length
    if len([p for p in parts if p[0]=='common']) != 1:
        raise ValueError('Expected one common partition')
    return parts


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    source = root.parent/'UniXNU-houji/archive/scripts/make-houji-adt.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    func = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='nvram_proxy')
    ns = {'struct':struct,'zlib':zlib}
    exec(compile(ast.Module(body=[func],type_ignores=[]),str(source),'exec'),ns)
    props = ns['nvram_proxy']()
    parts = validate(props)
    for offset in [1,16,100]:
        bad = dict(props)
        bank = bytearray(props['nvram-proxy-data']);bank[offset] ^= 1
        bad['nvram-proxy-data'] = bytes(bank)
        try:
            validate(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('Corrupt bank accepted')
    # Recompute Adler to isolate partition bound validation.
    bad = dict(props);bank=bytearray(props['nvram-proxy-data'])
    struct.pack_into('<H',bank,34,0xffff)
    total=bank[32]+sum(bank[34:48])
    while total>255: total=(total&255)+(total>>8)
    bank[33]=total
    struct.pack_into('<I',bank,16,zlib.adler32(bank[20:]))
    bad['nvram-proxy-data']=bytes(bank)
    try: validate(bad)
    except ValueError: pass
    else: raise AssertionError('Out-of-bounds partition accepted')
    print(json.dumps({'result':'PASS','bank_bytes':len(props['nvram-proxy-data']),
                      'partitions':parts,'negative_cases':4,'scope':'offline model only'},indent=2))
