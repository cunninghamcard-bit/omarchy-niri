"""Local browser screen-sharing acceptance server.

Run in a graphical Niri session, open http://127.0.0.1:31679 in Chromium,
click Share this desktop, and choose Entire Screen. Records five real frames
and nonconstant pixel data to ~/niri-browser-capture-result.json, then stops.
Uses a local-only server; nothing is uploaded outside the test computer.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
PAGE=b'''<!doctype html><meta charset="utf-8"><title>Niri screen sharing acceptance</title><style>body{font:20px sans-serif;padding:24px}button{font:inherit;padding:16px}video{width:100%}</style><h2>Niri screen sharing acceptance</h2><button id=start>Share this desktop</button><pre id=status>Ready</pre><video muted autoplay></video><canvas hidden></canvas><script>
start.onclick=async()=>{try{
 const stream=await navigator.mediaDevices.getDisplayMedia({video:true});
 const v=document.querySelector('video');v.srcObject=stream;await v.play();
 let frames=0;const tick=()=>{frames++;if(frames<5)return v.requestVideoFrameCallback(tick);
 const c=document.querySelector('canvas');c.width=v.videoWidth;c.height=v.videoHeight;const ctx=c.getContext('2d');ctx.drawImage(v,0,0);const pixels=ctx.getImageData(0,0,c.width,c.height).data;const values=new Set();for(let i=0;i<pixels.length;i+=16)values.add(pixels[i]);
 const result={pass:frames>=5&&v.videoWidth>0&&values.size>1,frames,width:v.videoWidth,height:v.videoHeight,colorValues:values.size};document.getElementById('status').textContent=JSON.stringify(result,null,2);fetch('/result',{method:'POST',body:JSON.stringify(result)});stream.getTracks().forEach(t=>t.stop());};v.requestVideoFrameCallback(tick);
}catch(error){fetch('/result',{method:'POST',body:JSON.stringify({pass:false,error:String(error)})});document.getElementById('status').textContent=String(error)}};
</script>'''
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(PAGE)
 def do_POST(self):
  data=self.rfile.read(int(self.headers.get('Content-Length',0)));Path.home().joinpath('niri-browser-capture-result.json').write_bytes(data);self.send_response(204);self.end_headers();print(data.decode(),flush=True)
HTTPServer(('127.0.0.1',31679),Handler).serve_forever()
