import argparse,hashlib,json
from pathlib import PurePosixPath
def score(files):
 if not isinstance(files,list) or len(files)>1000:return {"ok":False,"errors":["file_bound"]}
 total=0;reasons=[];paths=set()
 for f in files:
  if not isinstance(f,dict) or not isinstance(f.get("path"),str) or PurePosixPath(f["path"]).is_absolute() or ".." in PurePosixPath(f["path"]).parts or f["path"] in paths:return {"ok":False,"errors":["invalid_path"]}
  paths.add(f["path"])
  a=f.get("additions");d=f.get("deletions")
  if not isinstance(a,int) or not isinstance(d,int) or min(a,d)<0:return {"ok":False,"errors":["invalid_lines"]}
  points=min(30,(a+d)//20)
  if f.get("sensitive"):points+=30;reasons.append({"path":f["path"],"reason":"sensitive","points":30})
  if f.get("binary"):points+=15;reasons.append({"path":f["path"],"reason":"binary","points":15})
  if f["path"].startswith(("tests/","test/")):points=max(0,points-5)
  total+=points
 total=min(100,total);band="critical" if total>=75 else "high" if total>=50 else "medium" if total>=20 else "low";body={"score":total,"band":band,"reasons":reasons,"files":len(files)};return {"ok":True,**body,"evidence_sha256":hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest()}
def probe():
 g=score([{"path":"src/a.py","additions":10,"deletions":0}]);b=score([{"path":"../x","additions":1,"deletions":0}]);return {"ok":g["ok"] and not b["ok"],"path_counter_proof":not b["ok"]}
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("command",choices=("score","probe"));p.add_argument("--input");a=p.parse_args(argv);o=probe() if a.command=="probe" else score(json.load(open(a.input))["files"]);print(json.dumps(o,sort_keys=True));return 0 if o["ok"] else 2
