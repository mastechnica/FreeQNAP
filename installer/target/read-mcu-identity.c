/* SPDX-License-Identifier: MIT
 * Read-only SPEC3 diagnostic: version + identity blocks, no EEPROM writes,
 * fan changes, GPIO or networking. Raw identity output is private support data.
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
int main(void){
 struct utsname name;if(geteuid()||uname(&name)||!strstr(name.release,"eyeq-ts431xeu"))return 2;
 int lock=open("/run/eyeq-mcu.lock",O_CREAT|O_RDWR,0600);if(lock<0||flock(lock,LOCK_EX|LOCK_NB))return 2;
 int fd=open("/dev/ttyS1",O_RDWR|O_NOCTTY|O_NONBLOCK);if(fd<0||ioctl(fd,TIOCEXCL))return 2;
 struct termios before,raw;if(tcgetattr(fd,&before))return 2;raw=before;cfmakeraw(&raw);
 cfsetispeed(&raw,B115200);cfsetospeed(&raw,B115200);raw.c_cflag=(raw.c_cflag&~(CSIZE|PARENB|CSTOPB|CRTSCTS))|CS8|CLOCAL|CREAD;
 if(tcsetattr(fd,TCSANOW,&raw))return 2;
 const unsigned char requests[3][4]={{'%', 'V',0,0},{0xf9,0xaa,1,0},{0xf9,0xaa,2,0}};
 int failed=0;
 for(int operation=0;operation<3;operation++){
  unsigned char b[1024],tx[4],sum=0;size_t n=operation?3:2;
  for(int flush=0;flush<8&&read(fd,b,sizeof(b))>0;flush++){}
  memcpy(tx,requests[operation],n);for(size_t i=0;i<n;i++)sum^=tx[i];tx[n++]=sum;
  if(write(fd,tx,n)!=(ssize_t)n||tcdrain(fd)){failed=1;break;}
  struct pollfd p={fd,POLLIN,0};size_t total=0;
  while(total<sizeof(b)&&poll(&p,1,total?500:1500)>0){ssize_t got=read(fd,b+total,sizeof(b)-total);if(got<=0)break;total+=(size_t)got;}
  sum=0;for(size_t i=0;i<total;i++)sum^=b[i];
  printf("MCU_READ operation=%d bytes=%zu xor=%02x hex=",operation,total,sum);for(size_t i=0;i<total;i++)printf("%02x",b[i]);putchar('\n');fflush(stdout);
  if(!total)failed=1;usleep(200000);
 }
 tcsetattr(fd,TCSANOW,&before);ioctl(fd,TIOCNXCL);close(fd);close(lock);return failed;
}
