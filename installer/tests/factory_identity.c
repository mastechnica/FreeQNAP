#include "../../hardware/ts431xeu/factory-identity.h"
#include <assert.h>
#include <stdio.h>
static void crc(unsigned char *f){f[203]=0;for(int i=0;i<203;i++)f[203]^=f[i];}
int main(void){
 unsigned char f[204]={0xf9,0xaa,1,6},out[3][6];memcpy(f+4,"SN:",3);
 memcpy(f+40,"24:5E:BE:01:02:0324:5E:BE:01:02:0424:5E:BE:01:02:05",51);crc(f);
 assert(freeqnap_factory_identity(f,204,out));f[3]=3;crc(f);assert(freeqnap_factory_identity(f,204,out));
 for(int n=0;n<204;n++)assert(!freeqnap_factory_identity(f,n,out));
 f[203]^=1;assert(!freeqnap_factory_identity(f,204,out));crc(f);
 f[0]=0;crc(f);assert(!freeqnap_factory_identity(f,204,out));f[0]=0xf9;
 f[4]='X';crc(f);assert(!freeqnap_factory_identity(f,204,out));f[4]='S';
 f[40]='2';f[41]='5';crc(f);assert(!freeqnap_factory_identity(f,204,out));f[41]='4';
 f[42]='-';crc(f);assert(!freeqnap_factory_identity(f,204,out));f[42]=':';
 memcpy(f+57,f+40,17);crc(f);assert(!freeqnap_factory_identity(f,204,out));
 puts("PASS: opaque per-unit metadata, full frame checksum, all truncations, framing, multicast, separator and duplicate-MAC rejection");return 0;
}
