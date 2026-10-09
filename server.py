"""Local-only static server with byte ranges for CCTV replay seeking."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parent
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        self.byte_range=None
        super().__init__(*args,directory=str(ROOT),**kwargs)
    def send_head(self):
        self.byte_range=None
        requested=self.headers.get('Range')
        path=Path(self.translate_path(self.path))
        if not requested or not path.is_file():
            return super().send_head()
        size=path.stat().st_size
        match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
        if not match or not any(match.groups()):
            self.send_error(416,'Invalid range'); return None
        a,b=match.groups()
        start=int(a) if a else max(0,size-int(b))
        end=min(int(b),size-1) if a and b else size-1
        if start> end or start>=size:
            self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return None
        file=path.open('rb');file.seek(start);self.byte_range=(start,end)
        self.send_response(206);self.send_header('Content-Type',self.guess_type(str(path)));self.send_header('Content-Length',str(end-start+1));self.send_header('Content-Range',f'bytes {start}-{end}/{size}');self.send_header('Accept-Ranges','bytes');self.end_headers();return file
    def copyfile(self,source,outputfile):
        try:
            if self.byte_range:
                remaining=self.byte_range[1]-self.byte_range[0]+1
                while remaining:
                    data=source.read(min(65536,remaining))
                    if not data:break
                    outputfile.write(data);remaining-=len(data)
            else:super().copyfile(source,outputfile)
        except (BrokenPipeError,ConnectionResetError):pass
if __name__=='__main__':
    print('Replay running at http://127.0.0.1:8765',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
