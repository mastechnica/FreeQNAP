"""Fixed, actionable download errors without leaking engine paths or source tokens."""
TRANSIENT={'2','5','6','19','29'}
MESSAGES={
 '3':('File not found at the source','The server could not find this file. Find files again from the original listing or add a corrected direct link.'),
 '4':('File not found at the source','Repeated file-not-found responses. Find files again from the original listing or add a corrected link.'),
 '2':('The source timed out','Check the source site and NAS network/VPN connection. This download will retry automatically, or choose Retry now.'),
 '5':('The source was too slow','Check the source site or try again later.'),
 '6':('Network connection failed','Check the source site and NAS network/VPN connection. Do not disable VPN protection to retry.'),
 '19':('The source hostname could not be resolved','Check the URL and NAS DNS/VPN connection, then retry.'),
 '9':('Download storage is full','Free space on the configured download volume, then choose Retry now. Changing the final save folder does not move partial downloads.'),
 '8':('The source cannot resume this download','Add a new download using a fresh job. Existing partial files are preserved.'),
 '13':('A file already exists','Review the existing files. Add a fresh download if needed; existing files will not be overwritten.'),
 '24':('The source requires authentication','Use a publicly accessible direct file link. Your browser login cookies are not sent to download sources.'),
 '22':('The source returned an unexpected HTTP response','Check the source page for a current direct download link, then retry or add a corrected link.'),
 '23':('The source redirected too many times','Use the final direct download link from the source page.'),
 '29':('The source is temporarily unavailable','The source may be busy or under maintenance. This download will retry automatically.'),
 '32':('Downloaded data failed its checksum','Check the expected checksum and source. Do not use the unverified file; add a fresh download if needed.'),
}
def problem(row):
 if row.get('recovery_required'):return {'reason':'Partial download resume data is damaged','next_step':'Existing files are preserved. Add a fresh download or ask an administrator to recover the partial files.','automatic_retry':False,'code':str(row.get('error_code') or '1')}
 if row.get('state')!='error' and not row.get('attention_required'):
  if row.get('engine_error'):return {'reason':'The download engine could not update this job','next_step':'The queue entry is preserved for another attempt. Check Downloads and NAS health if this continues.','automatic_retry':True,'code':None}
  return None
 code=str(row.get('error_code') or '1')
 if code in ('14','15','16','17','18'):reason,step='The download engine could not write its files','Check download-volume availability, free space and write access. Ask an administrator if needed, then retry.'
 elif code in ('10','20','25','26','27'):reason,step='Download metadata or resume data is invalid','Get a fresh source link or torrent and add it as a new download. Existing partial files are preserved.'
 else:reason,step=MESSAGES.get(code,('The download engine reported an error','Check the source link and NAS health, then retry. Existing files are preserved.'))
 return {'reason':reason,'next_step':step,'automatic_retry':code in TRANSIENT,'code':code}
