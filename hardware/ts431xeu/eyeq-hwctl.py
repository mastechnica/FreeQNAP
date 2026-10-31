#!/usr/bin/env python3
"""Local SPEC3 controls for TS-431XeU. No raw commands or EEPROM writes.

The MCU UART is locked exclusively for the complete operation, including bounded
tests and restoration. Power-off is deliberately a separate late-shutdown binary.
"""
import argparse
import contextlib
import fcntl
import json
import os
import select
import signal
import termios
import time
from pathlib import Path

LED = {'red-blink': '4', 'green-blink': '5', 'green': '6', 'red': '7',
       'both-blink': '8', 'off': '9', 'green-slow-blink': 'A',
       'red-slow-blink': 'B', 'both-slow-blink': 'C', 'both': 'D'}
USB = {'on': 'E', 'blink': 'F', 'off': 'G'}
class ProtocolError(RuntimeError):
    pass

class Mcu:
    def __enter__(self):
        if os.geteuid() != 0 or 'eyeq-ts431xeu' not in os.uname().release:
            raise RuntimeError('Requires root on the EyeQ TS-431XeU kernel')
        if Path('/proc/device-tree/compatible').read_bytes().split(b'\0')[0] != b'qnap,ts-431xeu':
            raise RuntimeError('Board mismatch')
        self.lock = os.open('/run/eyeq-mcu.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            deadline = time.monotonic() + 3
            while True:
                try:
                    fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('MCU is busy')
                    time.sleep(.05)
            self.fd = os.open('/dev/ttyS1', os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            try:
                fcntl.ioctl(self.fd, termios.TIOCEXCL)
                self.original = termios.tcgetattr(self.fd)
                raw = termios.tcgetattr(self.fd)
                raw[0] = raw[1] = raw[3] = 0
                raw[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
                raw[4] = raw[5] = termios.B115200
                raw[6][termios.VMIN] = raw[6][termios.VTIME] = 0
                termios.tcsetattr(self.fd, termios.TCSANOW, raw)
                self.drain()
                return self
            except BaseException:
                os.close(self.fd)
                raise
        except BaseException:
            os.close(self.lock)
            raise

    def __exit__(self, *exc):
        try:
            termios.tcsetattr(self.fd, termios.TCSANOW, self.original)
            fcntl.ioctl(self.fd, termios.TIOCNXCL)
        finally:
            os.close(self.fd)
            os.close(self.lock)

    def drain(self):
        for _ in range(8):
            if not select.select([self.fd], [], [], .01)[0]:
                return
            if not os.read(self.fd, 256):
                return
        raise ProtocolError('Unbounded or unsolicited UART traffic')

    def exchange(self, payload, size, prefix):
        self.drain()
        data = payload.encode('ascii')
        checksum = 0
        for byte in data:
            checksum ^= byte
        tx = data + bytes([checksum])
        if os.write(self.fd, tx) != len(tx):
            raise ProtocolError('Short UART write')
        termios.tcdrain(self.fd)
        deadline = time.monotonic() + 1
        rx = b''
        while time.monotonic() < deadline:
            if not select.select([self.fd], [], [], min(.03, max(0, deadline-time.monotonic())))[0]:
                if rx:
                    break
                continue
            rx += os.read(self.fd, 256)
            if len(rx) > size:
                break
        checksum = 0
        for byte in rx:
            checksum ^= byte
        if len(rx) != size or not rx.startswith(prefix) or (size > 1 and checksum):
            raise ProtocolError(f'{payload}: malformed/timeout reply {rx.hex()}')
        return rx

    def ack(self, payload):
        if self.exchange(payload, 3, b'@0') != b'@0p':
            raise ProtocolError('Invalid MCU acknowledgement')

    def status_led(self):
        return self.exchange('@CS', 4, b'@C')[2:3].decode('ascii')

    def set_status_led(self, code):
        if code not in LED.values():
            raise ValueError('Unknown LED mode')
        self.ack('@C' + code)
        if self.status_led() != code:
            raise ProtocolError('LED readback mismatch')

    def status(self):
        result = {'status_led_raw': self.status_led(),
                  'usb_led_raw': self.exchange('@CU', 4, b'@C')[2],
                  'power_button_raw': self.exchange('@CV', 5, b'@CV')[3],
                  'global_fan_mode': self.exchange('@FS', 4, b'@F')[2:3].decode('ascii')}
        result['disk_error_led_raw'] = [self.exchange(f'@R{i}S', 5, f'@R{i}'.encode())[3] for i in range(4)]
        result['fans'] = []
        for i in range(3):
            frame = self.exchange('@F' + chr(65+i), 7, f'@F{i}'.encode())
            counter = int.from_bytes(frame[3:5], 'big')
            result['fans'].append({'channel':i, 'counter':counter, 'vendor_rpm':counter*30, 'state':frame[5]})
        result['ntc2_uncalibrated_c'] = self.exchange('@T3', 5, b'@T3')[3] - 128
        return result

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('status')
    sub.add_parser('led-test')
    sub.add_parser('disk-red-test')
    sub.add_parser('drive-green-enable')
    sub.add_parser('beep')
    led = sub.add_parser('status-led')
    led.add_argument('mode', choices=LED)
    sub.add_parser('button-diagnostics')
    button = sub.add_parser('watch-button')
    button.add_argument('--seconds', type=int, default=120)
    raw = sub.add_parser('watch-mcu')
    raw.add_argument('--seconds', type=int, default=120)
    a = p.parse_args()
    def stop(signum,frame):
        raise SystemExit(128+signum)
    for sig in (signal.SIGTERM,signal.SIGHUP):
        signal.signal(sig,stop)
    with Mcu() as mcu:
        if a.action == 'status':
            print(json.dumps(mcu.status(), indent=2))
        elif a.action == 'drive-green-enable':
            # Preserved vendor emcu_sys_set_led_green(1): command 0x804f000c.
            # Owner confirmed occupied bays 1 and 2 turn green after this exact
            # command. It enables the hardware path; no per-bay GPIO simulation.
            mcu.ack('@O61')
            print('MCU drive green LED enable acknowledged; no gate-state query is available')
        elif a.action == 'led-test':
            original = mcu.status_led()
            if original not in LED.values():
                raise ProtocolError('Cannot safely restore unknown initial LED state: '+repr(original))
            try:
                for name in ('red', 'green-blink', 'green'):
                    mcu.set_status_led(LED[name])
                    print('LED '+name+' ACKed and read back', flush=True)
                    time.sleep(5)
            finally:
                mcu.set_status_led(original)
                print('Original LED mode restored and read back: '+original, flush=True)
        elif a.action == 'beep':
            mcu.ack('@C2')
            print('Single short buzzer command ACKed; physical sound requires observation')
        elif a.action == 'status-led':
            mcu.set_status_led(LED[a.mode])
            print('Status LED '+a.mode+' ACKed and read back')
        elif a.action == 'disk-red-test':
            old=[mcu.exchange(f'@R{i}S',5,f'@R{i}'.encode())[3:4].decode('ascii') for i in range(4)]
            if any(value not in '0123' for value in old):
                raise ProtocolError('Unknown original drive error LED state')
            def set_disk(i,mode):
                mcu.ack(f'@R{i}'+mode)
                if mcu.exchange(f'@R{i}S',5,f'@R{i}'.encode())[3:4].decode('ascii')!=mode:
                    raise ProtocolError('Drive LED readback mismatch')
            try:
                for i in range(4):
                    set_disk(i,'0')
                    print(f'Red drive LED {i+1} on, ACK/readback verified',flush=True)
                    time.sleep(4)
                    set_disk(i,old[i])
            finally:
                for i,mode in enumerate(old):
                    set_disk(i,mode)
                print('Original drive error LED states restored',flush=True)
        elif a.action == 'button-diagnostics':
            for payload, size, prefix in (('@CV',5,b'@CV'),('@C1',5,b'@C'),('@ASR',6,b'@AS'),('@OSS',21,b'@OS')):
                try:
                    reply=mcu.exchange(payload,size,prefix)
                    print(json.dumps({'query':payload,'reply_hex':reply.hex()}),flush=True)
                except ProtocolError as error:
                    print(json.dumps({'query':payload,'diagnostic':str(error)}),flush=True)
        elif a.action == 'watch-button':
            deadline = time.monotonic() + min(max(a.seconds, 1), 600)
            previous = None
            while time.monotonic() < deadline:
                frame = mcu.exchange('@CV', 5, b'@CV')
                if frame[3] not in (48, 49):
                    raise ProtocolError('Invalid power-button state')
                if frame != previous:
                    print(json.dumps({'monotonic':time.monotonic(), 'power_button_2_sec':frame[3]==49, 'frame':frame.hex()}), flush=True)
                    previous = frame
                time.sleep(.2)
        elif a.action == 'watch-mcu':
            print('READY: passive MCU UART capture; no queries or control commands',flush=True)
            deadline=time.monotonic()+min(max(a.seconds,1),600)
            while time.monotonic()<deadline:
                if select.select([mcu.fd],[],[],.2)[0]:
                    data=os.read(mcu.fd,256)
                    if data:
                        print(json.dumps({'monotonic':time.monotonic(),'unsolicited_hex':data.hex()}),flush=True)

if __name__ == '__main__':
    main()
