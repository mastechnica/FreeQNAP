#!/usr/bin/env python3
"""Package the reviewed Ethernet repair for RAM testing only; never access a NAS."""
import argparse, datetime, hashlib, importlib.util, json, os, shutil, struct
import subprocess, sys, zlib
from pathlib import Path

BASE_IMAGE = '89d003cb1a547dfdcdac4bf966a8748f0668b090438da3e3f99625bdc5f9af19'
OLD_MODULE = '57f04fdbb922f926f301076a028ba6e3ca2babab38ef806c31983b0bc1349317'
NEW_MODULE = '167740fec091f7a466549b77f29e92c7a8dfc812dd52b571ba5330f404d5473e'
RELEASE = '6.12.114-eyeq-ts431xeu-freeqnap1'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kernel', type=Path, required=True)
    p.add_argument('--bootstrap', type=Path, required=True)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--module', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cross-compile', default='arm-linux-gnueabihf-')
    a = p.parse_args()
    project = Path(__file__).resolve().parents[1]
    if a.output.exists():
        p.error('Use a new output directory; preserve earlier evidence')
    if digest(a.baseline/'uImage') != BASE_IMAGE:
        p.error('Accepted rollback image changed')
    if digest(a.kernel/'arch/arm/boot/zImage') != digest(a.baseline/'zImage'):
        p.error('Kernel tree no longer contains the accepted baseline zImage')
    if digest(a.bootstrap/'lib/modules/al_eth.ko') != OLD_MODULE:
        p.error('Bootstrap Ethernet module changed')
    if digest(a.module) != NEW_MODULE:
        p.error('Use the exact reviewed Ethernet candidate')
    if (a.kernel/'include/config/kernel.release').read_text().strip() != RELEASE:
        p.error('Kernel ABI changed')
    a.output.mkdir(mode=0o700, parents=True)
    tree = a.output/'kernel'
    subprocess.run(['cp', '-a', '--reflink=auto', str(a.kernel), str(tree)], check=True)
    boot = a.output/'bootstrap'
    shutil.copytree(a.bootstrap, boot, symlinks=True)
    mode = (boot/'lib/modules/al_eth.ko').stat().st_mode & 0o777
    shutil.copyfile(a.module, boot/'lib/modules/al_eth.ko')
    (boot/'lib/modules/al_eth.ko').chmod(mode)
    spec = importlib.util.spec_from_file_location('bootstrap_audit', project/'installer/audit-initramfs.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    def audit_legacy(entries):
        # The hash-pinned accepted 004 bootstrap predates the policy helper.
        # Retain that explicit limitation; reject every other audit violation.
        try:
            audit.audit(entries)
        except ValueError as error:
            expected = {'generic_bootstrap_audit': False, 'violations': [
                {'missing_required': ['freeqnap/boot-policy.sh']}]}
            if json.loads(str(error)) != expected:
                raise
    audit_legacy(audit.directory_entries(a.bootstrap))
    audit_legacy(audit.directory_entries(boot))
    baseline_entries = {n: (m, hashlib.sha256(d).hexdigest()) for n, m, d in audit.directory_entries(a.bootstrap)}
    updated_entries = {n: (m, hashlib.sha256(d).hexdigest()) for n, m, d in audit.directory_entries(boot)}
    changed = sorted(n for n in baseline_entries.keys() | updated_entries.keys()
                     if baseline_entries.get(n) != updated_entries.get(n))
    if changed != ['lib/modules/al_eth.ko']:
        raise ValueError('Unexpected bootstrap changes')
    original_config = (tree/'.config').read_text().splitlines()
    subprocess.run([str(tree/'scripts/config'), '--file', str(tree/'.config'),
                    '--set-str', 'INITRAMFS_SOURCE', str(boot.resolve())], check=True)
    env = dict(os.environ, KBUILD_BUILD_VERSION='39', KBUILD_BUILD_USER='freeqnap',
               KBUILD_BUILD_HOST='local-build')
    stamp = struct.unpack('>I', (a.baseline/'uImage').read_bytes()[8:12])[0]
    env['KBUILD_BUILD_TIMESTAMP'] = datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).strftime('%a %b %d %H:%M:%S UTC %Y')
    command = ['make', '-C', str(tree), 'ARCH=arm', 'CROSS_COMPILE='+a.cross_compile]
    with (a.output/'build.log').open('w') as log:
        subprocess.run(command+['olddefconfig'], env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        new_config = (tree/'.config').read_text().splitlines()
        semantic = lambda lines: {v for v in lines if v.startswith(('CONFIG_', '# CONFIG_')) and not v.startswith('CONFIG_INITRAMFS_SOURCE=')}
        if semantic(original_config) != semantic(new_config):
            raise ValueError('Unexpected kernel configuration changes')
        subprocess.run(command+['-j4', 'zImage'], env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    if (tree/'include/config/kernel.release').read_text().strip() != RELEASE:
        raise ValueError('Built kernel ABI changed')
    embedded = {n: (m, hashlib.sha256(d).hexdigest()) for n, m, d in audit.cpio_entries(tree/'usr/initramfs_data.cpio')}
    audit_legacy(audit.cpio_entries(tree/'usr/initramfs_data.cpio'))
    for n, value in updated_entries.items():
        if n and value != embedded.get(n):
            raise ValueError('Embedded bootstrap entry differs: '+n)
    release = a.output/'release'
    release.mkdir(mode=0o700)
    for src, name in [(tree/'arch/arm/boot/zImage', 'zImage'),
                      (a.baseline/'board.dtb', 'board.dtb'), (tree/'.config', 'kernel.config')]:
        shutil.copy2(src, release/name)
    (release/'modules').mkdir()
    shutil.copy2(a.module, release/'modules/al_eth.ko')
    shutil.copy2(boot/'lib/modules/al_thermal.ko', release/'modules/al_thermal.ko')
    (release/'zImage-dtb').write_bytes((release/'zImage').read_bytes()+(release/'board.dtb').read_bytes())
    subprocess.run(['mkimage', '-A', 'arm', '-O', 'linux', '-T', 'kernel', '-C', 'none',
                    '-a', '0x8000', '-e', '0x8000', '-n', 'FreeQNAP safe stats RAM test',
                    '-d', str(release/'zImage-dtb'), str(release/'uImage')], check=True)
    records = {}
    for name in ['uImage', 'zImage', 'board.dtb', 'kernel.config', 'modules/al_eth.ko', 'modules/al_thermal.ko']:
        data = (release/name).read_bytes()
        records[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        if name == 'uImage':
            records[name]['crc32'] = f'{zlib.crc32(data):08x}'
    manifest = {'schema': 1, 'release': 'safe-ethernet-statistics-ram-test',
                'model': 'TS-431XeU', 'architecture': 'armhf', 'kernel': RELEASE,
                'development': True, 'signature_status': 'unsigned local development build',
                'hardware_boot_tested': False, 'ram_only': True, 'flash_allowed': False,
                'generic_root_selector': True, 'root_md_uuid_embedded': False,
                'bootstrap_changed_paths': changed, 'physical_validation': False,
                'legacy_bootstrap_limit': 'Accepted baseline lacks freeqnap/boot-policy.sh; unchanged, not a current-policy acceptance',
                'rollback_sha256': BASE_IMAGE, 'artifacts': records}
    (release/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({'packaged': True, 'ram_only': True, 'flash_allowed': False,
                      'physical_validation': False, 'uimage': records['uImage']}))


if __name__ == '__main__':
    main()
