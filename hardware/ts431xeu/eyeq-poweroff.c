/* SPDX-License-Identifier: MIT
 * Final systemd-shutdown hook for SPEC3. Never an ordinary service ExecStop.
 * SYSTEM_OFF_NOW is vendor command0x80430000, wire @C0 + XOR0x33.
 */
#define _DEFAULT_SOURCE
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/statvfs.h>
#include <sys/utsname.h>
#include <termios.h>
#include <unistd.h>

static int board_ok(void) {
 struct utsname u; char compatible[128]={0};
 if(geteuid()!=0 || uname(&u) || !strstr(u.release,"eyeq-ts431xeu")) return 0;
 int fd=open("/proc/device-tree/compatible",O_RDONLY);
 if(fd<0) return 0;
 ssize_t n=read(fd,compatible,sizeof(compatible)-1); close(fd);
 return n>0 && !strcmp(compatible,"qnap,ts-431xeu");
}
static int kernel_poweroff_ready(void) {
 char value[4]={0};
 int fd=open("/sys/module/freeqnap_poweroff/parameters/ready",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0) return 0;
 ssize_t n=read(fd,value,sizeof(value)-1);close(fd);
 return n>0 && value[0]=='Y';
}
int main(int argc,char **argv) {
 if(argc!=2) return 2;
 if(strcmp(argv[1],"poweroff") && strcmp(argv[1],"--check")) return 0;
 struct statvfs fs; char comm[32]={0};
 if(!board_ok() || statvfs("/",&fs)) return 2;
 int fd=open("/proc/1/comm",O_RDONLY);
 if(fd<0) return 2;
 ssize_t n=read(fd,comm,sizeof(comm)-1);close(fd);
 /* systemd may run hooks through an executor child; PID1 itself is authoritative. */
 int shutdown=n>0 && !strncmp(comm,"systemd-shutdow",15);
 int readonly=!!(fs.f_flag & ST_RDONLY);
 if(!strcmp(argv[1],"--check")) {
  printf("EyeQ poweroff guard: board=matched PID1-is-final-shutdown=%d root-readonly=%d kernel-final-off=%d; NO command sent\n",shutdown,readonly,kernel_poweroff_ready());
  return 0;
 }
 if(!shutdown || !readonly) {
  fputs("EyeQ: refusing MCU power-off outside final shutdown with read-only root\n",stderr);return 2;
 }
 /* A registered kernel handler lets normal MD/device shutdown run before
  * chassis power is removed. No MCU frame is sent by this hook in that mode.
  */
 if(kernel_poweroff_ready()) {
  sync();
  fputs("FreeQNAP: read-only root; delegating chassis power-off to final kernel handler\n",stderr);
  return 0;
 }
 int console=open("/dev/console",O_WRONLY|O_NOCTTY|O_CLOEXEC);
 if(console>=0) { dup2(console,STDERR_FILENO);close(console); }
 /* All normal services are gone; /run remains available in systemd-shutdown. */
 int lock=open("/run/eyeq-mcu.lock",O_CREAT|O_RDWR,0600);
 if(lock<0 || flock(lock,LOCK_EX|LOCK_NB)) return 2;
 fd=open("/dev/ttyS1",O_RDWR|O_NOCTTY|O_NONBLOCK);
 if(fd<0 || ioctl(fd,TIOCEXCL)) return 2;
 struct termios old,raw;
 if(tcgetattr(fd,&old)) return 2;
 raw=old;cfmakeraw(&raw);cfsetispeed(&raw,B115200);cfsetospeed(&raw,B115200);
 raw.c_cflag=(raw.c_cflag&~(CSIZE|PARENB|CSTOPB|CRTSCTS))|CS8|CLOCAL|CREAD;
 raw.c_cc[VMIN]=0;raw.c_cc[VTIME]=0;
 if(tcsetattr(fd,TCSANOW,&raw)) return 2;
 unsigned char rx[64];
 for(int i=0;i<4 && read(fd,rx,sizeof(rx))>0;i++){}
 sync();
 fputs("EyeQ final shutdown: root read-only, disks synced; requesting MCU chassis power-off\n",stderr);
 /* Let the console transmit this proof before the MCU may immediately cut power. */
 usleep(100000);
 const unsigned char tx[]={'@','C','0',0x33};
 int sent=write(fd,tx,sizeof(tx))==(ssize_t)sizeof(tx) && !tcdrain(fd);
 struct pollfd wait={fd,POLLIN,0};
 n=sent && poll(&wait,1,1000)>0 ? read(fd,rx,sizeof(rx)) : 0;
 if(n==3 && !memcmp(rx,"@0p",3)) fputs("EyeQ MCU chassis power-off ACKed\n",stderr);
 else fputs("EyeQ MCU power-off ACK not observed; physical result must be checked\n",stderr);
 tcsetattr(fd,TCSANOW,&old);ioctl(fd,TIOCNXCL);close(fd);close(lock);
 return sent?0:2;
}
