#!/usr/bin/env python3
"""Compare a supplied/running kernel base with kernel.org's current maintained series.

Read-only. No automatic downloads of executable images, flashing or CVE-free claim.
"""
import argparse,json,platform,re,urllib.request
from datetime import datetime,timezone

def assess(running,releases):
 match=re.match(r'^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$',running)
 if not match:raise ValueError('A stable kernel version, including patch number, is required')
 series='.'.join(match.groups()[:2]);same=[r for r in releases['releases'] if r.get('version','').startswith(series+'.') and r.get('moniker') in ('stable','longterm') and not r.get('iseol',True)]
 if not same:return {'running':running,'series':series,'maintained_series_found':False,'current_in_series':False,'action':'Review migration to a supported branch; do not flash without board regression/rollback tests.'}
 latest=max(same,key=lambda r:tuple(map(int,r['version'].split('.'))));base='.'.join(match.groups())
 return {'running':running,'base':base,'series':series,'maintained_series_found':True,'latest_in_series':latest['version'],'released':latest['released']['isodate'],'current_in_series':base==latest['version'],'action':'No newer upstream patch release in this series.' if base==latest['version'] else 'Review and build the complete current stable update; RAM-test before installation.','cve_applicability_audited':False,'custom_board_patch_review_required':True}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kernel',default=platform.release());a=p.parse_args()
 try:
  with urllib.request.urlopen('https://www.kernel.org/releases.json',timeout=20) as response:
   raw=response.read(1024**2+1)
  if len(raw)>1024**2:raise ValueError('Release response too large')
  result=assess(a.kernel,json.loads(raw));result.update(checked_at=datetime.now(timezone.utc).isoformat(),source='https://www.kernel.org/releases.json',verification='version and active-series check only')
  print(json.dumps(result,indent=2))
 except (OSError,ValueError,KeyError) as error:
  print(json.dumps({'verified':False,'error':str(error),'running':a.kernel}));raise SystemExit(2)
if __name__=='__main__':main()
