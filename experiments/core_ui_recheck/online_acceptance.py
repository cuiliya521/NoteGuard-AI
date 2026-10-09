"""Opt-in REAL provider acceptance. Never substitutes mock/local results."""
import argparse
import http.cookiejar
import json
from pathlib import Path
import urllib.request
import uuid
import threading

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8877');parser.add_argument('--output',default='online-acceptance.json');parser.add_argument('--self-host',action='store_true');args=parser.parse_args()
    server = None
    if args.self_host:
        from .server import TestServer
        from .adapter import V2Engine
        server = TestServer(('127.0.0.1',0),V2Engine())
        threading.Thread(target=server.serve_forever,daemon=True).start()
        args.base='http://127.0.0.1:'+str(server.server_address[1])
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with opener.open(args.base+'/api/health') as response:health=json.load(response)
    report={'method':'real HTTP + V2 rule engine; DeepSeek semantic/LLM only when configured','mock':False,'results':[]}
    def post(path, data):
        data['request_id']=str(uuid.uuid4())
        request=urllib.request.Request(args.base+path,json.dumps(data,ensure_ascii=False).encode(),{'Content-Type':'application/json','X-NoteGuard-CSRF':health['csrf']})
        with opener.open(request,timeout=40) as response:return json.load(response)
    original=post('/api/audit',{'title':'30天保证提分50分！初二数学必看','body':'初二数学线上1v1陪练，保证每位学员一个月提高50分。我们会结合错题复盘学习方法。','revision':0})
    report['results'].append({'case':'original','result':original})
    if not health['provider_configured'] or original['status']!='completed':
        report['online_status']='BLOCKED';report['reason']='No configured/working provider. Real rules completed; semantic/LLM acceptance NOT passed.'
        # These are explicit manual test inputs from the user's verified fixture,
        # NOT an AI suggestion returned by this run.
        for revision, body in [(1,'初二数学线上1v1陪练。我们会结合错题复盘学习方法。'),
                               (2,'初二数学线上1v1陪练。我们会结合错题复盘学习方法。保证一个月提高50分。'),
                               (3,'初二数学线上1v1陪练。我们会结合错题复盘学习方法。')]:
            report['results'].append({'case':'manual_fixture_rule_recheck_R'+str(revision),
                                      'input_source':'user_verified_fixture_or_manual_edit_NOT_LLM_output',
                                      'result':post('/api/recheck',{'title':'初二数学必看','body':body,'revision':revision})})
    else:
        suggestion=post('/api/suggest',{'audit_id':original['audit_id'],'content_hash':original['content_hash']});report['results'].append({'case':'real_llm_suggestion','result':suggestion})
        if suggestion['status']!='completed':report['online_status']='FAILED'
        else:
            draft=suggestion['draft'];report['results'].append({'case':'direct_adopt_recheck','result':post('/api/recheck',{'title':draft['title'],'body':draft['body'],'revision':1})})
            for revision,body in [(2,draft['body']+'保证一个月提高50分。'),(3,draft['body'])]:
                report['results'].append({'case':'edited_recheck_R'+str(revision),'result':post('/api/recheck',{'title':draft['title'],'body':body,'revision':revision})})
            report['online_status']='COMPLETED' if all(x['result'].get('status')=='completed' for x in report['results']) else 'FAILED'
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'online_status':report['online_status'],'cases':len(report['results']),'mock':False},ensure_ascii=False))
    if server:
        server.shutdown();server.server_close()

if __name__=='__main__':main()
