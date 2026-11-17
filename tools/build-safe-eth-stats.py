#!/usr/bin/env python3
"""Build the exact-board repair in a new directory; never install or load it."""
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path

BASE='7b3b7b09ec04de5bc3dfe414b9dd2109f76b97a140f01c9d46d1242ae90ca983'
PATCHED='d6bbb435c7364cda91d49e30eafd1aee7c8acc4d7ba32a016891f4bf2d66eb41'
RELEASE='6.12.114-eyeq-ts431xeu-freeqnap1'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True,help='Reviewed standalone Ethernet src directory')
p.add_argument('--kernel',type=Path,required=True,help='Prepared exact-ABI kernel build directory')
p.add_argument('--output',type=Path,required=True,help='New directory; existing output is refused')
p.add_argument('--cross-compile',default='arm-linux-gnueabihf-')
a=p.parse_args();project=Path(__file__).resolve().parents[1]
if a.output.exists():p.error('Output already exists; inspect it instead of overwriting')
raw=(a.source/'al_eth_main.c').read_bytes()
if hashlib.sha256(raw).hexdigest()!=BASE:p.error('Ethernet source is not the reviewed baseline')
if (a.kernel/'include/config/kernel.release').read_text().strip()!=RELEASE:p.error('Kernel ABI differs; do not force compatibility')
patch=project/'hardware/ts431xeu/patches/0002-ts431xeu-software-network-statistics.patch'
shutil.copytree(a.source,a.output);source=a.output/'al_eth_main.c';crlf=b'\r\n' in raw
source.write_bytes(raw.replace(b'\r\n',b'\n'))
subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(patch.resolve())],cwd=a.output,check=True)
if crlf:source.write_bytes(source.read_bytes().replace(b'\n',b'\r\n'))
if hashlib.sha256(source.read_bytes()).hexdigest()!=PATCHED:raise SystemExit('Patched source checksum mismatch')
subprocess.run([sys.executable,str(project/'tools/validate-safe-eth-stats.py'),'--source',str(source)],check=True)
with (a.output/'build.log').open('w') as log:
 subprocess.run(['make','-C',str(a.kernel.resolve()),'M='+str(a.output.resolve()),'ARCH=arm','CROSS_COMPILE='+a.cross_compile,'-j4','modules'],stdout=log,stderr=subprocess.STDOUT,check=True)
module=a.output/'al_eth.ko'
result={'board':'qnap,ts-431xeu','kernel_release':RELEASE,'base_source_sha256':BASE,'patched_source_sha256':PATCHED,'module_sha256':hashlib.sha256(module.read_bytes()).hexdigest(),'compile_passed':True,'callback_fixture_passed':True,'physical_validation':False,'installed':False,'activation_requires_separate_maintenance':True}
(a.output/'source-review.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
