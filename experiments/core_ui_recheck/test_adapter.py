"""Real V2 rules + HTTP transport checks; simulated provider tests clearly labeled."""
import contextlib
import http.cookiejar
import json
import os
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from services.workflow_v2 import SemanticReview, SemanticIssue, Draft
from .adapter import V2Engine, InputError, fingerprint
from .server import TestServer

TITLE = '30天保证提分50分！初二数学必看'
BODY = '初二数学线上1v1陪练，保证每位学员一个月提高50分。我们会结合错题复盘学习方法。'
def payload(title=TITLE, body=BODY, revision=0):
    return dict(title=title, body=body, revision=revision, request_id='test-'+str(revision))

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'DEEPSEEK_API_KEY': ''})
        self.env.start()
        self.engine = V2Engine()
    def tearDown(self):
        self.env.stop()
    def test_real_rules_original_offsets(self):
        result, _ = self.engine.audit(payload())
        self.assertGreater(result['rules']['count'], 0)
        for f in result['rules']['items']:
            text = TITLE if f['field'] == 'title' else BODY
            self.assertEqual(text[f['start']:f['end']], f['term'])
        self.assertEqual(result['provenance']['mode'], 'real_v2')
    def test_real_rules_confirmed_candidate_not_llm_generated(self):
        result, _ = self.engine.audit(payload('初二数学必看', '初二数学线上1v1陪练。我们会结合错题复盘学习方法。', 1))
        self.assertEqual(result['rules']['count'], 0)
        self.assertIsNone(result['conclusion'])
        self.assertEqual(result['semantic']['status'], 'failed')
    def test_real_rules_reintroduced_promise(self):
        result, _ = self.engine.audit(payload('初二数学必看', '初二数学线上1v1陪练。保证一个月提高50分。', 2))
        self.assertGreater(result['rules']['count'], 0)
        self.assertEqual(result['revision'], 2)
    def test_missing_key_no_fake_semantic(self):
        result, internal = self.engine.audit(payload())
        self.assertEqual(result['status'], 'partial_failure')
        self.assertIsNone(result['semantic']['count'])
        self.assertIsNone(result['conclusion'])
        suggestion = self.engine.suggest(internal)
        self.assertEqual(suggestion['status'], 'failed')
        self.assertIsNone(suggestion['draft'])
    def test_empty_body_rejected(self):
        for body in ['', ' \n\t']:
            with self.assertRaises(InputError):
                self.engine.audit(payload(body=body))
    def test_oversize_and_invalid_revision(self):
        with self.assertRaises(InputError):
            self.engine.audit(payload(body='x'*5001))
        with self.assertRaises(InputError):
            self.engine.audit(payload(revision=True))
    def test_hash_and_snapshot_identity(self):
        self.assertNotEqual(fingerprint(TITLE, BODY), fingerprint(TITLE, BODY+'保证'))
        result, _ = self.engine.audit(payload(revision=3))
        self.assertEqual(result['document'], {'title': TITLE, 'body': BODY})
        self.assertEqual(result['request_id'], 'test-3')
    def test_simulated_semantic_repeated_quote_positions(self):
        # MOCK provider: adapter format/position checks only, not online acceptance.
        issue = SemanticIssue('正文', '保证', '效果承诺', 'high')
        with patch('experiments.core_ui_recheck.adapter.review_semantics', return_value=SemanticReview((issue,), True)):
            result, _ = self.engine.audit(payload(body='保证，保证。'))
        self.assertEqual(result['semantic']['items'][0]['occurrences'], [{'start': 0, 'end': 2}, {'start': 3, 'end': 5}])
    def test_simulated_provider_failure_does_not_leak_error(self):
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-only-not-a-real-key'}), patch('experiments.core_ui_recheck.adapter.review_semantics', return_value=SemanticReview(error='secret-value timed out')):
            result, _ = self.engine.audit(payload())
        self.assertEqual(result['semantic']['error']['code'], 'timeout')
        self.assertNotIn('secret-value', json.dumps(result))
    def test_simulated_local_fallback_not_labeled_success(self):
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-only-not-a-real-key'}), patch('experiments.core_ui_recheck.adapter.make_draft', return_value=Draft('数学', '正文', '本地回退', '本地规则')):
            suggestion = self.engine.suggest((TITLE, BODY, (), SemanticReview((), True)))
        # Empty findings means no-change; add a real rule finding for draft path.
        result, internal = self.engine.audit(payload())
        internal = (*internal[:3], SemanticReview((), True))
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-only-not-a-real-key'}), patch('experiments.core_ui_recheck.adapter.make_draft', return_value=Draft('数学', '正文', '本地回退', '本地规则')):
            suggestion = self.engine.suggest(internal)
        self.assertEqual(suggestion['status'], 'failed')
        self.assertIsNone(suggestion['draft'])

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = patch.dict(os.environ, {'DEEPSEEK_API_KEY': ''});cls.env.start()
        cls.server = TestServer(('127.0.0.1', 0), V2Engine())
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True);cls.thread.start()
        cls.base = 'http://127.0.0.1:'+str(cls.server.server_address[1])
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.env.stop()
    def setUp(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with self.opener.open(self.base+'/api/health') as r:self.health=json.load(r)
    def post(self, path, data, csrf=True, origin=None):
        headers={'Content-Type':'application/json'}
        if csrf:headers['X-NoteGuard-CSRF']=self.health['csrf']
        if origin:headers['Origin']=origin
        request=urllib.request.Request(self.base+path, json.dumps(data).encode(), headers)
        return self.opener.open(request)
    def test_real_http_rule_and_semantic_unavailable(self):
        with self.post('/api/audit',payload()) as r:result=json.load(r)
        self.assertGreater(result['rules']['count'],0)
        self.assertEqual(result['semantic']['error']['code'],'missing_key')
        with self.post('/api/suggest',{'audit_id':result['audit_id'],'content_hash':result['content_hash'],'request_id':'suggest-1'}) as r:s=json.load(r)
        self.assertIsNone(s['draft'])
    def test_real_http_empty_body_400(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.post('/api/recheck',payload(body=''))
        self.assertEqual(e.exception.code,400)
    def test_csrf_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.post('/api/audit',payload(),csrf=False)
        self.assertEqual(e.exception.code,403)
    def test_cross_origin_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.post('/api/audit',payload(),origin='http://untrusted.invalid')
        self.assertEqual(e.exception.code,403)
    def test_no_secret_file_or_source_exposure(self):
        for path in ['/.env','/adapter.py','/../../.env']:
            with self.assertRaises(urllib.error.HTTPError) as e:self.opener.open(self.base+path)
            self.assertEqual(e.exception.code,404)
    def test_session_isolation(self):
        with self.post('/api/audit',payload()) as r:result=json.load(r)
        self.setUp()
        with self.assertRaises(urllib.error.HTTPError) as e:self.post('/api/suggest',{'audit_id':result['audit_id'],'content_hash':result['content_hash']})
        self.assertEqual(e.exception.code,409)
    def test_html_is_same_origin_and_no_fixture_outputs(self):
        with self.opener.open(self.base+'/') as r:html=r.read().decode();csp=r.headers['Content-Security-Policy']
        self.assertIn('workflow.js',html)
        self.assertIn("connect-src 'self'",csp)
        with self.opener.open(self.base+'/workflow.js') as r:js=r.read().decode()
        self.assertNotIn('const risks=',js)
        self.assertNotIn('DEEPSEEK_API_KEY',js)

if __name__ == '__main__':
    unittest.main(verbosity=2)
