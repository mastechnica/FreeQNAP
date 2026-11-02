/* SPDX-License-Identifier: MIT
 * Attended SP805 acceptance in the dedicated disposable RAM rescue only.
 * Never invoke on the installed NAS OS. Expiry intentionally resets hardware.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/watchdog.h>
#include <stdio.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/sysmacros.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t aborted;
static void abort_test(int sig){(void)sig;aborted=1;}
static int text_is(const char *path,const char *expected){
 char b[256];int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return 0;
 ssize_t n=read(fd,b,sizeof(b)-1);close(fd);if(n<0)return 0;b[n]=0;b[strcspn(b,"\n")]=0;return !strcmp(b,expected);
}
static int ram_guard(void){
 if(geteuid()!=0||!text_is("/proc/device-tree/compatible","qnap,ts-431xeu"))return 0;
 if(!text_is("/run/freeqnap-watchdog-rescue","RAM-ONLY-NO-PERSISTENT-MOUNTS")||access("/run/freeqnap-cooling-ack",F_OK))return 0;
 struct statfs fs;if(statfs("/",&fs)||((unsigned long)(unsigned int)fs.f_type!=0x858458f6UL&&(unsigned long)(unsigned int)fs.f_type!=0x01021994UL))return 0;
 FILE *f=fopen("/proc/mounts","r");if(!f)return 0;
 char source[1024],target[1024],kind[128],options[2048];int a,b,ok=1;
 while(fscanf(f,"%1023s %1023s %127s %2047s %d %d",source,target,kind,options,&a,&b)==6){
  if(strcmp(kind,"rootfs")&&strcmp(kind,"ramfs")&&strcmp(kind,"tmpfs")&&strcmp(kind,"proc")&&strcmp(kind,"sysfs")&&strcmp(kind,"devtmpfs")&&strcmp(kind,"devpts")){ok=0;break;}
 }
 if(!feof(f))ok=0;
 fclose(f);if(!ok)return 0;
 f=fopen("/proc/mdstat","r");if(f){char line[2048];while(fgets(line,sizeof(line),f))if(line[0]=='m'&&line[1]=='d'&&line[2]>='0'&&line[2]<='9')ok=0;fclose(f);}else return 0;
 return ok&&text_is("/sys/class/watchdog/watchdog0/state","inactive")&&text_is("/sys/class/watchdog/watchdog0/nowayout","0")&&text_is("/sys/class/watchdog/watchdog0/identity","sp805-wdt");
}
static double now(void){struct timespec ts;clock_gettime(CLOCK_MONOTONIC,&ts);return ts.tv_sec+ts.tv_nsec/1e9;}
static int keepalive(int fd){int rc=ioctl(fd,WDIOC_KEEPALIVE,0);if(rc)perror("KEEPALIVE FAILED");return rc;}
static int disarm(int fd){
 int option=WDIOS_DISABLECARD;
 if(ioctl(fd,WDIOC_SETOPTIONS,&option))return -1;
 if(write(fd,"V",1)!=1)return -1;
 if(close(fd))return -1;
 return text_is("/sys/class/watchdog/watchdog0/state","inactive")?0:-1;
}
static void intervention(int fd){
 puts("WATCHDOG_DISARM_FAILED: operator intervention required; retaining ownership and feeding. RAM only.");fflush(stdout);
 for(;;){keepalive(fd);sleep(1);}
}
int main(int argc,char **argv){
 setvbuf(stdout,NULL,_IOLBF,0);signal(SIGINT,abort_test);signal(SIGTERM,abort_test);signal(SIGHUP,abort_test);
 if(argc!=3||strcmp(argv[2],"RAM-WATCHDOG-TEST")||(strcmp(argv[1],"disarm")&&strcmp(argv[1],"expire"))){fputs("Usage: watchdog-ram-probe disarm|expire RAM-WATCHDOG-TEST\n",stderr);return 2;}
 if(!ram_guard()){fputs("REFUSED: dedicated RAM rescue, full cooling, no persistent mounts/arrays and inactive disarmable SP805 required. Device was not opened.\n",stderr);return 2;}
 int lock=open("/run/watchdog-test.lock",O_CREAT|O_RDWR|O_CLOEXEC|O_NOFOLLOW,0600);
 if(lock<0||flock(lock,LOCK_EX|LOCK_NB)){perror("Single watchdog owner required");return 2;}
 struct stat expected,actual;unsigned major_id,minor_id;
 FILE *dev=fopen("/sys/class/watchdog/watchdog0/dev","r");if(!dev)return 2;
 int matched=fscanf(dev,"%u:%u",&major_id,&minor_id);fclose(dev);
 if(matched!=2||lstat("/dev/watchdog0",&expected)||!S_ISCHR(expected.st_mode)||major(expected.st_rdev)!=major_id||minor(expected.st_rdev)!=minor_id)return 2;
 int fd=open("/dev/watchdog0",O_WRONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0){perror("watchdog exclusive open");return 2;}
 /* From this point, errors require an explicit disarm or retained feeding. */
 int timeout=10,accepted=0;struct watchdog_info info;
 if(fstat(fd,&actual)||actual.st_rdev!=expected.st_rdev||ioctl(fd,WDIOC_GETSUPPORT,&info)||!(info.options&WDIOF_MAGICCLOSE)||ioctl(fd,WDIOC_SETTIMEOUT,&timeout)||ioctl(fd,WDIOC_GETTIMEOUT,&accepted)||accepted!=timeout||accepted<2||accepted>60){
  puts("WATCHDOG_SETUP_FAILED");if(disarm(fd))intervention(fd);return 1;
 }
 printf("WATCHDOG_ARMED mode=%s accepted_timeout=%d nowayout=0\n",argv[1],accepted);
 for(int i=0;i<3;i++){if(aborted||keepalive(fd)){puts("WATCHDOG_TEST_ABORTED");if(disarm(fd))intervention(fd);return 1;}sleep(1);}
 if(!strcmp(argv[1],"disarm")){
  if(disarm(fd))intervention(fd);
  printf("WATCHDOG_DISARMED: inactive; observing %d seconds for unintended reset\n",2*accepted+3);
  double observation=now();while(now()-observation<2*accepted+3&&!aborted)sleep(1);
  if(aborted)return 1;
  if(!text_is("/sys/class/watchdog/watchdog0/state","inactive"))return 1;
  puts("WATCHDOG_DISARM_PASS");return 0;
 }
 if(aborted||keepalive(fd)){puts("WATCHDOG_TEST_ABORTED");if(disarm(fd))intervention(fd);return 1;}double start=now();printf("WATCHDOG_FEED_STOPPED monotonic=%.6f expected_seconds=%d; FD remains open\n",start,accepted);
 while(now()-start<3*accepted+5&&!aborted)sleep(1);
 puts("WATCHDOG_EXPIRATION_FAILED: no bounded physical reset");
 if(disarm(fd))intervention(fd);
 return 1;
}
