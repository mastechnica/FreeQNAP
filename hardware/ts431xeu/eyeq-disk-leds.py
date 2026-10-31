#!/usr/bin/env python3
"""Per-bay presence/activity LEDs, with required MCU green enable at startup.

The owner observed none of the four green LEDs during the October 28 test,
including occupied bays 1 and 2, before the required MCU @O61 enable was found.
The exact stock kernel's al_ahci_transmit_led_message confirms GPIO control.
With MCU @O61 enabled, the owner confirmed occupied-bay presence and real read
activity in all four bays, by moving the two mirrored OS drives while powered off.
Physical LEDs are active-low; empty bays remain dark under the presence policy.
Sysfs brightness alone is not proof of physical illumination.
No disk writes.
"""
import argparse
import fcntl
import json
import os
import signal
import time
from pathlib import Path

CONTROLLER = Path('/sys/bus/pci/devices/0000:00:09.0')
LEDS = [Path('/sys/class/leds/eyeq:green:disk'+str(i)) for i in range(1,5)]
def write(path, text):
    path.write_text(str(text)+'\n')
def current_trigger(led):
    return next(x[1:-1] for x in (led/'trigger').read_text().split() if x.startswith('['))
def lock_leds(block):
    fd = os.open('/run/eyeq-disk-leds.lock', os.O_CREAT|os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX|(0 if block else fcntl.LOCK_NB))
    except BlockingIOError:
        os.close(fd)
        return None
    return fd
def test(identify=None, seconds=120, blink=False):
    fd = lock_leds(True)
    old = [(current_trigger(led),(led/'brightness').read_text().strip()) for led in LEDS]
    try:
        for led in LEDS:
            write(led/'trigger','none')
            write(led/'brightness',0)
        for i,led in enumerate(LEDS,1):
            if identify is not None and i != identify:
                continue
            if blink:
                end=time.monotonic()+min(max(seconds,1),180)
                state=1
                while time.monotonic()<end:
                    write(led/'brightness',state)
                    assert (led/'brightness').read_text().strip()==str(state)
                    print(f'Green output {i} LED-class brightness request {state}; physical illumination requires observation',flush=True)
                    time.sleep(min(2,max(0,end-time.monotonic())))
                    state=1-state
            else:
                write(led/'brightness',1)
                assert (led/'brightness').read_text().strip()=='1'
                print('Green output '+str(i)+' LED-class brightness 1; sysfs readback verified; physical illumination requires observation',flush=True)
                time.sleep(min(max(seconds,1),180) if identify is not None else 4)
            write(led/'brightness',0)
    finally:
        for led,(trigger,brightness) in zip(LEDS,old):
            write(led/'brightness',brightness)
            write(led/'trigger',trigger)
        os.close(fd)
        print('Original drive LED states/triggers restored',flush=True)
def run():
    ports = sorted(CONTROLLER.glob('ata*'),key=lambda p:int(p.name[3:]))
    assert len(ports)==4
    # This board's AHCI ports enumerate ata1..4, port_no1..4, corresponding to
    # its model.conf device-port0..3. Do not map by mutable sdX names.
    assert [int((Path('/sys/class/ata_port')/p.name/'port_no').read_text()) for p in ports]==[1,2,3,4]
    # Physical LEDs are active-low: the owner observed idle raw1 as dark and
    # activity raw0 as a light pulse. Older test DTs incorrectly declare HIGH;
    # compensate only for those flags, without double inversion on corrected DTs.
    kernel_active_low = []
    for i in range(1,5):
        cells=(Path('/proc/device-tree/leds')/('disk'+str(i))/'gpios').read_bytes()
        assert len(cells)==12
        flags=int.from_bytes(cells[8:12],'big')
        assert flags in (0,1)
        kernel_active_low.append(flags==1)
    last_counts = [None]*4
    last_activity = [0.0]*4
    displayed = [None]*4
    next_status = 0
    while True:
        now = time.monotonic()
        disks = []
        for port in ports:
            disks.append([p for p in Path('/sys/class/block').glob('sd*')
                          if not (p/'partition').exists() and str(p.resolve()).startswith(str(port.resolve())+'/')])
        fd = lock_leds(False)
        states = []
        try:
            for i,(led,matches) in enumerate(zip(LEDS,disks)):
                assert len(matches)<=1
                count = None
                if matches:
                    counters = [int(x) for x in (matches[0]/'stat').read_text().split()]
                    count = counters[0]+counters[4]
                    if last_counts[i] is not None and count!=last_counts[i]:
                        last_activity[i] = now
                last_counts[i] = count
                active = bool(matches) and now-last_activity[i]<.25
                brightness = int(bool(matches) and (not active or int(now*10)%2==0))
                request = brightness if kernel_active_low[i] else 1-brightness
                if fd is not None:
                    if displayed[i] != request or current_trigger(led) != 'none':
                        write(led/'trigger','none')
                        write(led/'brightness',request)
                        displayed[i] = request
                else:
                    displayed[i] = None
                states.append({'bay':i+1,'ata_port':ports[i].name,'disk':matches[0].name if matches else None,
                               'present':bool(matches),'recent_activity':active,'brightness':brightness,
                               'class_brightness':request,'kernel_active_low':kernel_active_low[i]})
        finally:
            if fd is not None:
                os.close(fd)
        if now >= next_status:
            result={'updated_monotonic':now,'test_in_progress':fd is None,'ports':states}
            tmp=Path('/run/eyeq-disk-leds.json.next')
            tmp.write_text(json.dumps(result,indent=2)+'\n')
            tmp.replace('/run/eyeq-disk-leds.json')
            next_status=now+1
        time.sleep(.1)
def main():
    p=argparse.ArgumentParser()
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--test',action='store_true')
    mode.add_argument('--identify',type=int,choices=range(1,5))
    p.add_argument('--seconds',type=int,default=120)
    p.add_argument('--blink',action='store_true')
    a=p.parse_args()
    if a.blink and a.identify is None:
        p.error('--blink requires one --identify bay')
    assert os.geteuid()==0 and 'eyeq-ts431xeu' in os.uname().release
    assert Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0]==b'qnap,ts-431xeu'
    assert (CONTROLLER/'vendor').read_text().strip()=='0x1c36'
    assert (CONTROLLER/'class').read_text().strip()=='0x010601'
    assert all((led/'brightness').exists() for led in LEDS)
    def stop(signum,frame):
        raise SystemExit(128+signum)
    for sig in (signal.SIGTERM,signal.SIGHUP):
        signal.signal(sig,stop)
    test(a.identify,a.seconds,a.blink) if a.test or a.identify is not None else run()
if __name__=='__main__':
    main()
