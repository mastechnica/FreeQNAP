#!/usr/bin/env python3
"""Local button policy with durable observations and explicit per-button enable.

Default policy observes only. Neither button ever erases configuration or data.
Each MCU transaction shares the same short-lived exclusive lock as the CLI.
"""
import fcntl
import json
import os
import runpy
import select
import struct
import subprocess
import time
from pathlib import Path

Mcu = runpy.run_path(str(Path(__file__).with_name('eyeq-hwctl.py')))['Mcu']
EVENT = struct.Struct('llHHI')
LOG = Path('/var/log/eyeq-buttons.log')
POLICY = Path('/etc/eyeq-buttons.json')
def log(event, **fields):
    record={'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            'monotonic':time.monotonic(),'event':event,**fields}
    text=json.dumps(record)
    print(text,flush=True)
    fd=os.open(LOG,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_CLOEXEC,0o640)
    try:
        os.write(fd,(text+'\n').encode())
        os.fsync(fd)
    finally:
        os.close(fd)
def policy():
    if not POLICY.exists():
        return {'power':'observe','reset':'observe'}
    value=json.loads(POLICY.read_text())
    assert value.get('power') in ('observe','poweroff')
    assert value.get('reset') in ('observe','reboot')
    return value
def action(button):
    mode=policy()[button]
    log('button-policy',button=button,action=mode)
    if mode!='observe':
        # The final shutdown hook owns actual MCU power removal, after FS shutdown.
        subprocess.run(['/usr/bin/systemctl',mode],check=True,timeout=15)
def open_reset():
    for node in Path('/sys/class/input').glob('event*'):
        if (node/'device/name').read_text().strip()!='eyeq-buttons':
            continue
        fd=os.open('/dev/input/'+node.name,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
        keys=bytearray(64)
        fcntl.ioctl(fd,(2<<30)|(len(keys)<<16)|(ord('E')<<8)|0x18,keys,True)
        pressed=bool(keys[148//8] & (1<<(148%8)))
        log('reset-input-attached',device=node.name,initial_pressed=pressed)
        return fd,not pressed
    return None,False
def main():
    assert os.geteuid()==0 and 'eyeq-ts431xeu' in os.uname().release
    assert Path('/etc/eyeq-platform').read_text().strip()=='qnap-ts431xeu-debian-armhf'
    policy()
    fd=None
    reset_armed=False
    reset_pressed_at=None
    power_armed=False
    previous_power=None
    data=b''
    next_poll=next_attach=0
    last_error=None
    log('button-monitor-started',policy=policy(),root=os.uname().release)
    while True:
        now=time.monotonic()
        if fd is None and now>=next_attach:
            fd,reset_armed=open_reset()
            next_attach=now+1
        if fd is not None and select.select([fd],[],[],0)[0]:
            data+=os.read(fd,4096)
            while len(data)>=EVENT.size:
                sec,usec,kind,code,value=EVENT.unpack(data[:EVENT.size]);data=data[EVENT.size:]
                if kind!=1 or code!=148 or value not in (0,1):
                    continue
                log('reset-input',pressed=bool(value),kernel_sec=sec,kernel_usec=usec)
                event_time=sec+usec/1000000
                if value==1:
                    reset_pressed_at=event_time if reset_armed else None
                else:
                    if reset_pressed_at is not None and event_time-reset_pressed_at>=.05:
                        action('reset')
                    reset_pressed_at=None
                    reset_armed=True
        if now>=next_poll:
            try:
                with Mcu() as mcu:
                    frame=mcu.exchange('@CV',5,b'@CV')
                if frame[3] not in (48,49):
                    raise ValueError('Invalid power-button state')
                pressed=frame[3]==49
                if pressed!=previous_power:
                    log('power-mcu',pressed_2_sec=pressed,frame=frame.hex())
                    previous_power=pressed
                if not pressed:
                    power_armed=True
                elif power_armed:
                    power_armed=False
                    action('power')
                last_error=None
            except (OSError,RuntimeError,TimeoutError,ValueError) as error:
                message=str(error)
                if message!=last_error:
                    log('power-input-unavailable',detail=message)
                    last_error=message
            next_poll=time.monotonic()+.25
        time.sleep(.02)
if __name__=='__main__':
    main()
