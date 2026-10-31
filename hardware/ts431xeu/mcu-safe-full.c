/* SPDX-License-Identifier: MIT
 * Early bench cooling: set the physically tested global full-speed mode.
 * Single owner, bounded exchanges, exact ACK/readback. Never stops a fan.
 */
#define _DEFAULT_SOURCE
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/utsname.h>
#include <termios.h>
#include <unistd.h>
static int exchange(int fd,const unsigned char *tx,size_t n,const unsigned char *expected,size_t want){
 unsigned char b[32];size_t total=0;struct pollfd p={fd,POLLIN,0};
 if(write(fd,tx,n)!=(ssize_t)n||tcdrain(fd))return -1;
 while(total<sizeof(b)&&poll(&p,1,total?100:1000)>0){ssize_t r=read(fd,b+total,sizeof(b)-total);if(r<=0)break;total+=(size_t)r;}
 return total==want&&!memcmp(b,expected,want)?0:-1;
}
int main(void){
 struct utsname u;
 if(geteuid()!=0||uname(&u)||!strstr(u.release,"eyeq-ts431xeu")){fputs("EyeQ kernel/root required\n",stderr);return 2;}
 int lock=open("/run/eyeq-mcu.lock",O_RDWR|O_CREAT,0600);
 if(lock<0){lock=open("/tmp/eyeq-mcu-reader.lock",O_RDWR|O_CREAT,0600);}
 if(lock<0||flock(lock,LOCK_EX|LOCK_NB)){perror("MCU lock");return 2;}
 int fd=open("/dev/ttyS1",O_RDWR|O_NOCTTY|O_NONBLOCK);
 if(fd<0||ioctl(fd,TIOCEXCL)){perror("MCU exclusive open");return 2;}
 struct termios before,raw;
 if(tcgetattr(fd,&before)){perror("MCU termios");return 2;}
 raw=before;cfmakeraw(&raw);cfsetispeed(&raw,B115200);cfsetospeed(&raw,B115200);
 raw.c_cflag=(raw.c_cflag&~(CSIZE|PARENB|CSTOPB|CRTSCTS))|CS8|CLOCAL|CREAD;
 raw.c_cc[VMIN]=0;raw.c_cc[VTIME]=0;
 if(tcsetattr(fd,TCSANOW,&raw)){perror("MCU raw mode");return 2;}
 const unsigned char set[]={0x40,0x46,0x37,0x31},ack[]={0x40,0x30,0x70};
 const unsigned char query[]={0x40,0x46,0x53,0x55},full[]={0x40,0x46,0x37,0x31};
 int ok=-1;
 for(int attempt=0;attempt<3;attempt++){
  unsigned char stale[64];for(int n=0;n<4&&read(fd,stale,sizeof(stale))>0;n++){}
  if(!exchange(fd,set,sizeof(set),ack,sizeof(ack))&&!exchange(fd,query,sizeof(query),full,sizeof(full))){ok=0;break;}
 }
 tcsetattr(fd,TCSANOW,&before);ioctl(fd,TIOCNXCL);close(fd);close(lock);
 if(ok){fputs("MCU full-speed ACK/readback unavailable; cooling not verified\n",stderr);return 1;}
 puts("MCU global 100% fan mode ACKed and read back; fixed bench cooling active");return 0;
}
