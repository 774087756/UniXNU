"""Build an offline property manifest, NOT a bootable ADT or image."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import struct


def prepare(raw):
    nodes, _ = runpy.run_path(str(Path(__file__).with_name('inspect-houji-fdt.py')))['parse'](raw)
    soc = nodes['/soc']
    if (soc['#address-cells'], soc['#size-cells']) != (struct.pack('>I',1),)*2:
        raise ValueError('Unexpected soc cells')
    if nodes['/']['#address-cells'] != struct.pack('>I',2):
        raise ValueError('Unexpected root address width')
    child, parent, span = struct.unpack('>IQI', soc['ranges'])
    gics = [v for v in nodes.values() if b'arm,gic-v3' in v.get('compatible',b'').split(b'\0')]
    if len(gics) != 1:
        raise ValueError('Expected exactly one GICv3')
    gic = gics[0]
    regions = struct.unpack('>4I', gic['reg'])
    stride, = struct.unpack('>Q', gic['redistributor-stride'])
    if stride not in (0x20000,0x30000,0x40000):
        raise ValueError('Unsupported stride')
    if regions[1] < 0x10000 or regions[3] < 0x20000:
        raise ValueError('GIC range too small')
    for base, size in zip(regions[::2], regions[1::2]):
        if base < child or base-child+size > span:
            raise ValueError('GIC outside bus window')
    method = nodes['/soc/psci']['method']
    if method not in (b'smc\0', b'hvc\0'):
        raise ValueError('Unknown PSCI conduit')
    if nodes['/cpus']['#address-cells'] != struct.pack('>I',2):
        raise ValueError('Unexpected CPU cells')
    cpus = []
    for path, props in nodes.items():
        if path.startswith('/cpus/') and props.get('device_type') == b'cpu\0':
            affinity, = struct.unpack('>Q',props['reg'])
            if affinity > 0xffffffff:
                raise ValueError('CPU affinity cannot fit current driver ABI')
            cpus.append({'source': path, 'affinity': hex(affinity), 'reg_le32': struct.pack('<I',affinity).hex()})
    if not cpus or len({c['affinity'] for c in cpus}) != len(cpus):
        raise ValueError('Empty/duplicate CPU affinities')
    return {'status': 'OFFLINE_CONTRACT_ONLY_NOT_BOOTABLE',
            'fdt_sha256':hashlib.sha256(raw).hexdigest(),
            'properties_hex': {'/arm-io:ranges':struct.pack('<3Q',child,parent,span).hex(),
                '/arm-io/intc:reg':struct.pack('<4Q',*regions).hex(),
                '/arm-io/intc:compatible':b'arm,gic-v3\0'.hex(),
                '/arm-io/intc:redistributor-stride':struct.pack('<Q',stride).hex(),
                '/psci:method':method.hex()},
            'cpu_candidates':cpus,
            'blockers':['Boot MPIDR and unique CPU state=running selection not verified; XNU AFF1/AFF0 lookup audited',
                        'Current UEFI memory ownership and contiguous allocation not verified',
                        'GOP, exception level and complete ADT requirements not verified'],
            'smp_enabled':False}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('fdt',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    result=prepare(a.fdt.read_bytes())
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Validated and saved offline property manifest; no boot image generated.')
