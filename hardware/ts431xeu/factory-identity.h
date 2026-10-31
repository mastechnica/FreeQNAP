/* SPDX-License-Identifier: MIT
 * SPEC3 block-1 identity decoder. Byte 3 is opaque per-unit identity metadata,
 * not a fixed framing constant. This decoder never writes MCU EEPROM.
 */
#ifndef FREEQNAP_FACTORY_IDENTITY_H
#define FREEQNAP_FACTORY_IDENTITY_H
#include <stddef.h>
#include <string.h>
static int freeqnap_hex(unsigned char c){
 if(c>='0'&&c<='9')return c-'0';
 if(c>='A'&&c<='F')return c-'A'+10;
 if(c>='a'&&c<='f')return c-'a'+10;
 return -1;
}
static int freeqnap_factory_identity(const unsigned char *frame,size_t length,unsigned char output[3][6]){
 if(length!=204||memcmp(frame,"\xf9\xaa\x01",3)||memcmp(frame+4,"SN:",3))return 0;
 unsigned char checksum=0,mac[3][6];for(size_t i=0;i<length;i++)checksum^=frame[i];if(checksum)return 0;
 for(int i=0;i<3;i++){
  const unsigned char *text=frame+40+17*i;
  for(int j=0;j<6;j++){
   int a=freeqnap_hex(text[3*j]),b=freeqnap_hex(text[3*j+1]);
   if(a<0||b<0||(j<5&&text[3*j+2]!=':'))return 0;
   mac[i][j]=(unsigned char)((a<<4)|b);
  }
  if((mac[i][0]&3)||!memcmp(mac[i],"\0\0\0\0\0\0",6)||!memcmp(mac[i],"\xff\xff\xff\xff\xff\xff",6))return 0;
  if(i&&memcmp(mac[0],mac[i],3))return 0;
  for(int j=0;j<i;j++)if(!memcmp(mac[i],mac[j],6))return 0;
 }
 memcpy(output,mac,sizeof(mac));return 1;
}
#endif
