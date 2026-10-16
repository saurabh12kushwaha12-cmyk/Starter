import json, os, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import xml.etree.ElementTree as ET
BASE=Path(__file__).resolve().parents[1]
def load(n): return json.loads((BASE/'sample-data'/n).read_text())
CUSTOMERS=load('customers.json')['customers'];ACCOUNTS=load('accounts.json')['accounts'];BILLING=load('billing.json')['billing'];OUTAGES=load('network-status.json')['outages'];CASES={};KEYS={}
def find(xs,k,v): return next((x for x in xs if x.get(k)==v),None)
class H(BaseHTTPRequestHandler):
 def js(self,c,o):
  b=json.dumps(o).encode();self.send_response(c);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def body(self): return self.rfile.read(int(self.headers.get('Content-Length','0')))
 def do_GET(self):
  p=urlparse(self.path);a=p.path.strip('/').split('/')
  if p.path=='/health': return self.js(200,{'status':'ok'})
  if len(a)==3 and a[:2]==['api','customers']:
   x=find(CUSTOMERS,'customerId',a[2]);return self.js(200,x) if x else self.js(404,{'error':'not_found'})
  if len(a)==3 and a[:2]==['api','accounts']:
   x=find(ACCOUNTS,'accountId',a[2]);return self.js(200,x) if x else self.js(404,{'error':'not_found'})
  if len(a)==4 and a[:2]==['api','accounts'] and a[3]=='billing':
   m=os.getenv('MOCK_BILLING_MODE','success')
   if m=='unavailable': return self.js(503,{'error':'billing_unavailable'})
   if m=='malformed': return self.js(200,{'unexpected':True})
   x=find(BILLING,'accountId',a[2]);return self.js(200,x) if x else self.js(404,{'error':'not_found'})
  if p.path=='/api/network/outages':
   pc=parse_qs(p.query).get('postalCode',[''])[0];return self.js(200,find(OUTAGES,'postalCode',pc) or {'postalCode':pc,'status':'unknown'})
  return self.js(404,{'error':'not_found'})
 def do_POST(self):
  p=urlparse(self.path)
  if p.path=='/api/auth/login':
   m=os.getenv('MOCK_AUTH_MODE','normal')
   if m=='unavailable': return self.js(503,{'error':'auth_unavailable'})
   d=json.loads(self.body() or b'{}');c=next((x for x in CUSTOMERS if x.get('username')==d.get('username') and x.get('testPassword')==d.get('password')),None)
   if not c:return self.js(401,{'error':'invalid_credentials'})
   return self.js(200,{'accessToken':'expired' if m=='expired' else 'synthetic-'+c['customerId'],'customerId':c['customerId'],'accountId':c.get('accountId'),'roles':c['roles'],'expiresIn':0 if m=='expired' else 3600})
  if p.path=='/api/support-cases':
   if os.getenv('MOCK_CASE_MODE','success')=='unavailable':return self.js(503,{'error':'case_unavailable'})
   d=json.loads(self.body() or b'{}');k=d.get('idempotencyKey')
   if not k:return self.js(400,{'error':'idempotency_key_required'})
   if k in KEYS:return self.js(409,{'error':'duplicate','caseId':KEYS[k]})
   cid='CASE-'+uuid.uuid4().hex[:8].upper();KEYS[k]=cid;CASES[cid]={'caseId':cid,'status':'open',**d};return self.js(201,CASES[cid])
  if p.path=='/api/diagnostics':
   d=json.loads(self.body() or b'{}');return self.js(200,{'diagnosticId':'DIAG-'+uuid.uuid4().hex[:6].upper(),'serviceId':d.get('serviceId'),'result':'no_device_fault_detected'})
  if p.path=='/api/legacy/subscriber-status':
   m=os.getenv('MOCK_LEGACY_MODE','success')
   if m=='timeout':time.sleep(8)
   if m=='unavailable':return self.js(503,{'error':'legacy_unavailable'})
   if m=='malformed':raw=b'<SubscriberStatusResponse><BROKEN>'
   else:
    try:r=ET.fromstring(self.body());acct=r.findtext('AccountNumber');svc=r.findtext('ServiceNumber')
    except Exception:acct=svc=''
    code='0' if acct=='ACC-2001' and svc=='SVC-5001' else '101'
    raw=('<SubscriberStatusResponse><ACCT_NO>'+str(acct)+'</ACCT_NO><SVC_NO>'+str(svc)+'</SVC_NO><SVC_STAT>'+('A' if code=='0' else '')+'</SVC_STAT><NET_STAT>'+('DEGRADED' if code=='0' else '')+'</NET_STAT><ERR_CD>'+code+'</ERR_CD><RESP_TS>2026-10-13T08:30:00Z</RESP_TS></SubscriberStatusResponse>').encode()
   self.send_response(200);self.send_header('Content-Type','application/xml');self.send_header('Content-Length',str(len(raw)));self.end_headers();return self.wfile.write(raw)
  return self.js(404,{'error':'not_found'})
 def log_message(self,*args):pass
if __name__=='__main__':
 port=int(os.getenv('MOCK_PORT','8090'));print('Mock services on http://localhost:'+str(port));ThreadingHTTPServer(('0.0.0.0',port),H).serve_forever()
