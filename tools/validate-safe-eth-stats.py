#!/usr/bin/env python3
"""Exercise the actual patched callback against software fixtures only."""
from pathlib import Path
import re,subprocess,json,hashlib
import argparse,tempfile
parser=argparse.ArgumentParser(description='Fixture validation only; never loads a kernel module or accesses hardware.')
parser.add_argument('--source',type=Path,required=True);parser.add_argument('--cc',default='cc');args=parser.parse_args()
workspace=tempfile.TemporaryDirectory(prefix='freeqnap-safe-stats-');root=Path(workspace.name);text=args.source.read_text();start=text.index('static void al_eth_get_stats64(');begin=text.index('{',start);level=1;end=begin+1
while level:
 if text[end]=='{':level+=1
 if text[end]=='}':level-=1
 end+=1
fn=text[start:end];mac=sorted(set(re.findall(r'mac_stats->(\w+)',fn)));fields=sorted(set(re.findall(r'stats->(\w+)',fn)))
# Remove names which were matched inside mac_stats-> above.
fields=[f for f in fields if f.startswith(('rx_','tx_')) or f in ('multicast','collisions')]
harness='#include <stdint.h>\n#include <string.h>\n#include <assert.h>\n#include <stdio.h>\ntypedef uint64_t u64;\n'
harness+='struct al_eth_mac_stats {'+';'.join('u64 '+k for k in mac)+';};\n'
harness+='struct rtnl_link_stats64 {'+';'.join('u64 '+k for k in fields)+';};\n'
harness+='struct al_eth_ring {int syncp; struct {u64 packets,bytes,skb_alloc_fail,dma_mapping_err;} rx_stats,tx_stats;};\n'
harness+='struct al_eth_adapter {int up,num_rx_queues,num_tx_queues,hal_adapter;struct al_eth_ring rx_ring[2],tx_ring[2];struct al_eth_mac_stats mac_stats;};\n'
harness+='struct net_device {struct al_eth_adapter *adapter;};static int board=1,hardware_calls=0,fetches=0;\n'
harness+='static void *netdev_priv(struct net_device *d){return d->adapter;}\nstatic int of_machine_is_compatible(const char *s){return board && !strcmp(s,"qnap,ts-431xeu");}\nstatic unsigned u64_stats_fetch_begin(int *p){fetches++;return 0;}\nstatic int u64_stats_fetch_retry(int *p,unsigned start){return 0;}\n'
harness+='static void al_eth_mac_stats_get(int *a,struct al_eth_mac_stats *s){hardware_calls++;s->aFramesTransmittedOK=17;}\n'+fn+'\n'
harness+='''int main(void){struct al_eth_adapter a={.up=1,.num_rx_queues=2,.num_tx_queues=2};struct net_device d={&a};struct rtnl_link_stats64 s={0};
a.rx_ring[0].rx_stats.packets=5;a.rx_ring[1].rx_stats.packets=7;a.rx_ring[0].rx_stats.bytes=1ULL<<35;a.rx_ring[1].rx_stats.bytes=9;a.rx_ring[0].rx_stats.skb_alloc_fail=2;a.rx_ring[1].rx_stats.dma_mapping_err=3;
a.tx_ring[0].tx_stats.packets=11;a.tx_ring[1].tx_stats.packets=13;a.tx_ring[0].tx_stats.bytes=1ULL<<36;a.tx_ring[1].tx_stats.bytes=15;
al_eth_get_stats64(&d,&s);assert(hardware_calls==0);assert(fetches==4);assert(s.rx_packets==12);assert(s.tx_packets==24);assert(s.rx_bytes==(1ULL<<35)+9);assert(s.tx_bytes==(1ULL<<36)+15);assert(s.rx_dropped==5);
a.up=0;al_eth_get_stats64(&d,&s);assert(hardware_calls==0);assert(fetches==4);
a.up=1;board=0;al_eth_get_stats64(&d,&s);assert(hardware_calls==1);assert(s.tx_packets==17);puts("PASS: TS-431XeU statistics avoid MAC MMIO; synchronized multi-queue sums preserve 64-bit totals; down state and other boards retain behavior.");}
'''
p=root/'test-safe-stats.c';p.write_text(harness)
subprocess.run([args.cc,'-std=c11','-Werror=implicit-function-declaration',str(p),'-o',str(root/'test-safe-stats')],check=True)
subprocess.run([str(root/'test-safe-stats')],check=True)

workspace.cleanup()
