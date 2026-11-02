#!/usr/bin/env python3
"""Read-only ARM kernel hardening evidence; never claims firmware mitigation from sysfs alone."""
import argparse,gzip,json,os,re,subprocess
from pathlib import Path
REQUIRED=('STRICT_KERNEL_RWX','STRICT_MODULE_RWX','DEBUG_ALIGN_RODATA','ARM_DEBUG_WX','STACKPROTECTOR','STACKPROTECTOR_STRONG','HARDENED_USERCOPY','FORTIFY_SOURCE','BPF_UNPRIV_DEFAULT_OFF','CPU_SPECTRE','HARDEN_BRANCH_PREDICTOR','HARDEN_BRANCH_HISTORY')

def assess(kernel,expected,config,cmdline,log,bpf,vulnerabilities,online_cpus=None):
    enabled={name:bool(re.search(r'^CONFIG_'+name+r'=y$',config,re.M)) for name in REQUIRED}
    disabled=any(x in cmdline.split() for x in ('rodata=off','mitigations=off','nospectre_v2','nospectre_bhb'))
    wx_pass=bool(re.search(r'Checked W\+X mappings: passed, no W\+X pages found\.?\s*$',log,re.M))
    wx_failure=bool(re.search(r'Checked W\+X mappings: FAILED',log))
    ibe_cpus=sorted(set(int(x) for x in re.findall(r'CPU(\d+): Spectre v2: firmware did not set auxiliary control register IBE bit',log)))
    iciallu_cpus=sorted(set(int(x) for x in re.findall(r'CPU(\d+): Spectre v2: using ICIALLU workaround',log)))
    online=sorted(online_cpus or [])
    ibe_confirmed=not ibe_cpus and online==[0,1,2,3] and iciallu_cpus==online
    okay=kernel==expected and all(enabled.values()) and bpf in (1,2) and not disabled and wx_pass and not wx_failure
    return {'read_only':True,'kernel':kernel,'expected_kernel_matches':kernel==expected,'configuration':enabled,'unprivileged_bpf_disabled':bpf in (1,2),'command_line_disables_protection':disabled,'boot_wx_check_passed':wx_pass and not wx_failure,'memory_and_bpf_hardening_passed':okay,'firmware_ibe_warning_cpus':ibe_cpus,'online_cpus':online,'iciallu_workaround_cpus':iciallu_cpus,'cpu_ibe_workaround_confirmed':ibe_confirmed,'firmware_mitigation_complete':False if ibe_cpus else None,'reported_cpu_vulnerabilities':vulnerabilities,'scope':'Configuration, runtime BPF policy and boot permission-check evidence; no exploit test, firmware repair or complete CVE audit.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--expected-kernel',required=True);p.add_argument('--require-memory-hardening',action='store_true');p.add_argument('--require-cpu-ibe',action='store_true');a=p.parse_args()
    if Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0]!=b'qnap,ts-431xeu':raise ValueError('Exact board required')
    with gzip.open('/proc/config.gz','rt') as f:config=f.read(4*1024*1024+1)
    if len(config)>4*1024*1024:raise ValueError('Kernel configuration too large')
    log=subprocess.check_output(['dmesg','--color=never'],text=True,timeout=10)
    vulnerabilities={p.name:p.read_text().strip() for p in Path('/sys/devices/system/cpu/vulnerabilities').iterdir() if p.is_file()}
    online=[]
    for part in Path('/sys/devices/system/cpu/online').read_text().strip().split(','):
        bounds=list(map(int,part.split('-')))
        if len(bounds) not in (1,2) or not 0<=bounds[0]<=bounds[-1]<=4095:raise ValueError('Invalid online CPU list')
        online.extend(range(bounds[0],bounds[-1]+1))
    report=assess(os.uname().release,a.expected_kernel,config,Path('/proc/cmdline').read_text(),log,int(Path('/proc/sys/kernel/unprivileged_bpf_disabled').read_text()),vulnerabilities,online_cpus=online)
    print(json.dumps(report,indent=2))
    if a.require_memory_hardening and not report['memory_and_bpf_hardening_passed']:raise SystemExit(1)
    if a.require_cpu_ibe and not report['cpu_ibe_workaround_confirmed']:raise SystemExit(1)
if __name__=='__main__':main()
