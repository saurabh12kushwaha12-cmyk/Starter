import json,os,urllib.request,uuid,datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
API=os.getenv('MOCK_API_BASE','http://localhost:8090');EVENTS=Path(__file__).parent/'events.jsonl'
def emit(kind,trace,status='success'):
 e={'eventId':'EVT-'+uuid.uuid4().hex[:8],'traceId':trace,'sessionId':'starter','timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'eventType':kind,'component':'starter-app','status':status}
 with EVENTS.open('a') as f:f.write(json.dumps(e)+'\n')
def get(path):
 with urllib.request.urlopen(API+path,timeout=3) as r:return json.loads(r.read())
HTML="""<!doctype html><html><body style='font-family:Arial;max-width:800px;margin:40px auto'><h1>Incomplete Starter CX Solution</h1><p>Reviewer starter mode</p><textarea id='m' style='width:100%;height:80px'>What internet plan am I currently using?</textarea><button onclick='go()'>Send</button><pre id='o'></pre><script>async function go(){let r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:m.value})});o.textContent=JSON.stringify(await r.json(),null,2)}</script></body></html>"""
class H(BaseHTTPRequestHandler):
 def out(self,c,o,ct='application/json'):
  b=o.encode() if isinstance(o,str) else json.dumps(o).encode();self.send_response(c);self.send_header('Content-Type',ct);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):
  if self.path=='/':return self.out(200,HTML,'text/html')
  if self.path=='/health':return self.out(200,{'status':'ok'})
  return self.out(404,{'error':'not_found'})
 def do_POST(self):
  if self.path!='/chat':return self.out(404,{'error':'not_found'})
  trace='TRACE-'+uuid.uuid4().hex[:8];emit('request.received',trace);d=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}');m=d.get('message','').lower()
  try:
   if 'plan' in m:a=get('/api/accounts/ACC-2001');answer='Your plan is '+a['plan']['name']
   elif 'not working' in m:answer='Which service is affected: home internet or mobile?'
   else:answer='Starter could not classify the request.'
   emit('workflow.resolved',trace);return self.out(200,{'traceId':trace,'answer':answer,'warning':'Intentionally incomplete and not authorized.'})
  except Exception:emit('workflow.failed',trace,'failure');return self.out(500,{'traceId':trace,'error':'starter_failure'})
 def log_message(self,*args):pass
if __name__=='__main__':
 port=int(os.getenv('APP_PORT','8080'));print('Starter on http://localhost:'+str(port));ThreadingHTTPServer(('0.0.0.0',port),H).serve_forever()
