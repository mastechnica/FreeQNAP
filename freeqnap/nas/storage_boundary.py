"""Known shared storage boundaries; different filesystems do not imply independence."""
def tokens(pool):
    found=set()
    def add(kind,value):
        if isinstance(value,str) and value:found.add((kind,value.strip().lower()))
    add('filesystem',pool.get('filesystem_uuid'))
    if pool.get('md_uuid'):add('array',pool['md_uuid'].replace(':','').replace('-',''))
    add('group',pool.get('group'))
    if pool.get('kind')=='usb':
        external=pool.get('external',{});add('usb-enclosure',external.get('enclosure_id'));add('disk-wwn',external.get('wwn'));add('disk-serial',external.get('disk_serial'))
    for member in pool.get('regions',pool.get('members',[])):
        disk=member.get('disk',member);add('disk-wwn',disk.get('wwn'));add('disk-serial',disk.get('serial'))
    return found

def shared(first,second):return bool(tokens(first)&tokens(second))
