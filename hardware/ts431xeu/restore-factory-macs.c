/* SPDX-License-Identifier: MIT
 * TS-431XeU/SPEC3: restore Linux interface MACs from read-only MCU identity data.
 * Does not write EEPROM. Operates only on down interfaces with known PCI paths.
 */
#define _DEFAULT_SOURCE
#include <dirent.h>
#include <fcntl.h>
#include <net/if.h>
#include <net/if_arp.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/utsname.h>
#include <termios.h>
#include <unistd.h>
#include "factory-identity.h"
static void show(const unsigned char *m){printf("%02x:%02x:%02x:%02x:%02x:%02x",m[0],m[1],m[2],m[3],m[4],m[5]);}
int main(int argc,char **argv){
 int dry=argc==2&&!strcmp(argv[1],"--dry-run");
 if(argc>2||(argc==2&&!dry)||geteuid()!=0)return 2;
 struct utsname u;if(uname(&u)||!strstr(u.release,"eyeq-ts431xeu"))return 2;
 char compatible[128]={0};int f=open("/proc/device-tree/compatible",O_RDONLY);
 if(f<0)return 2;
 ssize_t count=read(f,compatible,sizeof(compatible)-1);close(f);
 if(count<=0||strcmp(compatible,"qnap,ts-431xeu")){fputs("Wrong board compatible\n",stderr);return 2;}
 int lock=open("/run/eyeq-mcu.lock",O_CREAT|O_RDWR,0600);
 if(lock<0||flock(lock,LOCK_EX|LOCK_NB)){perror("MCU lock");return 2;}
 int fd=open("/dev/ttyS1",O_RDWR|O_NOCTTY|O_NONBLOCK);
 if(fd<0||ioctl(fd,TIOCEXCL)){perror("MCU exclusive open");return 2;}
 struct termios old,raw;if(tcgetattr(fd,&old))return 2;
 raw=old;cfmakeraw(&raw);cfsetispeed(&raw,B115200);cfsetospeed(&raw,B115200);
 raw.c_cflag=(raw.c_cflag&~(CSIZE|PARENB|CSTOPB|CRTSCTS))|CS8|CLOCAL|CREAD;
 raw.c_cc[VMIN]=0;raw.c_cc[VTIME]=0;
 if(tcsetattr(fd,TCSANOW,&raw))return 2;
 unsigned char frame[512];for(int n=0;n<4&&read(fd,frame,sizeof(frame))>0;n++){}
 const unsigned char query[]={0xf9,0xaa,0x01,0x52};
 if(write(fd,query,sizeof(query))!=(ssize_t)sizeof(query)||tcdrain(fd))return 2;
 size_t total=0;struct pollfd wait={fd,POLLIN,0};
 while(total<sizeof(frame)&&poll(&wait,1,total?100:1000)>0){ssize_t n=read(fd,frame+total,sizeof(frame)-total);if(n<=0)break;total+=(size_t)n;}
 tcsetattr(fd,TCSANOW,&old);ioctl(fd,TIOCNXCL);close(fd);close(lock);
 unsigned char mac[3][6];
 if(!freeqnap_factory_identity(frame,total,mac)){fputs("Factory identity framing/checksum/MAC validation failed\n",stderr);return 1;}
 const char *pci[]={"0000:00:03.0","0000:00:01.0","0000:00:00.0"};
 DIR *dir=opendir("/sys/class/net");if(!dir)return 1;
 int sock=socket(AF_INET,SOCK_DGRAM|SOCK_CLOEXEC,0);if(sock<0)return 1;
 int found=0,failed=0;struct dirent *entry;
 while((entry=readdir(dir))){
  if(entry->d_name[0]=='.'||strlen(entry->d_name)>=IFNAMSIZ)continue;
  char path[512],target[512];snprintf(path,sizeof(path),"/sys/class/net/%s/device",entry->d_name);
  ssize_t n=readlink(path,target,sizeof(target)-1);if(n<=0)continue;target[n]=0;
  char *leaf=strrchr(target,'/');leaf=leaf?leaf+1:target;
  for(int i=0;i<3;i++)if(!strcmp(leaf,pci[i])){
   found++;struct ifreq req={0};strcpy(req.ifr_name,entry->d_name);
   if(ioctl(sock,SIOCGIFFLAGS,&req)){failed++;continue;}
   if(dry){printf("Factory identity %s %s ",pci[i],entry->d_name);show(mac[i]);putchar('\n');continue;}
   if(req.ifr_flags&IFF_UP){fprintf(stderr,"Refusing live MAC change on %s\n",entry->d_name);failed++;continue;}
   req.ifr_hwaddr.sa_family=ARPHRD_ETHER;memcpy(req.ifr_hwaddr.sa_data,mac[i],6);
   if(ioctl(sock,SIOCSIFHWADDR,&req)||ioctl(sock,SIOCGIFHWADDR,&req)||memcmp(req.ifr_hwaddr.sa_data,mac[i],6)){perror("MAC restore/readback");failed++;continue;}
   printf("Restored factory MAC %s %s ",pci[i],entry->d_name);show(mac[i]);putchar('\n');
  }
 }
 closedir(dir);close(sock);
 return found==3&&!failed?0:1;
}
