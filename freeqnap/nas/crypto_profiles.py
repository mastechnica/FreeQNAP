"""Explicit, bounded profiles for newly created USB LUKS2 volumes.

XTS uses two AES keys: 512 total bits means AES-256-XTS; 256 means AES-128-XTS.
Profiles never change an existing volume in place. Password and key-file inputs
use the same encrypted data format and memory-bounded Argon2id key slots.
"""
PROFILES={
    'aes256-xts':{'label':'AES-256-XTS (default)','cipher':'aes-xts-plain64','key_bits':512},
    'aes128-xts':{'label':'AES-128-XTS','cipher':'aes-xts-plain64','key_bits':256},
}
DEFAULT='aes256-xts'

def profile(ident=DEFAULT):
    if not isinstance(ident,str) or ident not in PROFILES:raise ValueError('Choose AES-256-XTS or AES-128-XTS')
    return {'id':ident,**PROFILES[ident],'format':'luks2','pbkdf':'argon2id','memory_kib':131072,'parallel':2,'target_ms':2000}

def format_args(ident=DEFAULT):
    value=profile(ident)
    return ['cryptsetup','luksFormat','--type','luks2','--batch-mode','--cipher',value['cipher'],
            '--key-size',str(value['key_bits']),'--pbkdf','argon2id','--pbkdf-memory','131072',
            '--pbkdf-parallel','2','--iter-time','2000','--key-file','-']
