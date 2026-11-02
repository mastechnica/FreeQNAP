"""Read-only installation journal summary; never authorizes a retry or mutation."""
import json
from pathlib import Path


def session_status(directory):
    root=Path(directory)
    def read(filename,required=False):
        path=root/filename
        if not path.exists() and not required:return None
        value=json.loads(path.read_text())
        if not isinstance(value,dict):raise ValueError('Installation journal must contain objects')
        return value
    state=read('session.json',True);connection=read('connection.json',True)
    disk=read('disk-operation.json');flash=read('flash-operation.json')
    for record,key in ((disk,'disk_writes_started'),(flash,'write_started')):
        if record is not None and type(record.get(key)) is not bool:
            raise ValueError('Write journal is incomplete; inspect before continuing')
    disk_started=bool(disk and disk['disk_writes_started'])
    flash_started=bool(flash and flash['write_started'])
    disk_complete=bool(disk and disk.get('status')=='installed_pending_boot_validation')
    flash_complete=bool(flash and flash.get('readback_verified') is True)
    reconcile=(disk_started and not disk_complete) or (flash_started and not flash_complete)
    return {'phase':state['phase'],'capture':connection['capture'],
            'disk_writes':disk_started,'disk_operation':disk,
            'flash_writes':flash_started,'flash_operation':flash,
            'requires_reconciliation':reconcile,
            'next_step':'Stop and inspect the retained operation; do not repeat writes.' if reconcile else 'Review acceptance evidence before the next separately authorized step.',
            'journal_only':True,'hardware_rechecked':False,'retry_authorized':False}
