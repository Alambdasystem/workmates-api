import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
CONTRACT=json.loads((ROOT/'openapi.json').read_text())

class ContractTests(unittest.TestCase):
    def test_unique_operation_ids(self):
        ids=[op['operationId'] for path in CONTRACT['paths'].values() for op in path.values()]
        self.assertEqual(len(ids),len(set(ids)))
    def test_admin_operations_marked(self):
        for path,method in [('/api/rooms/{room_id}/workmate','patch'),('/api/rooms/{room_id}/members/{user_id}','delete')]:
            self.assertIn('Room owner or platform administrator',CONTRACT['paths'][path][method]['description'])
    def test_mutations_require_csrf_except_login_join(self):
        for path,operations in CONTRACT['paths'].items():
            for method,op in operations.items():
                if method!='get' and path not in ['/api/login','/api/join','/api/signup','/api/waitlist','/api/password/forgot','/api/password/reset','/api/email/verify']:
                    self.assertTrue(any(p['name']=='X-CSRF-Token' and p['required'] for p in op['parameters']))
    def test_backend_routes_and_responses_match_contract(self):
        from jsonschema import Draft202012Validator
        spec=importlib.util.spec_from_file_location('workmates_core',ROOT/'server.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            app=module.create_app(dict(DB_PATH=folder+'/db.sqlite',ADMIN_EMAIL='test@example.com',ADMIN_PASSWORD='long-contract-password',COOKIE_SECURE=False),start_worker=False)
            import re
            actual={(re.sub(r'<([^>]+)>',r'{\1}',r.rule),m.lower()) for r in app.url_map.iter_rules() if r.rule.startswith('/api/') or r.rule=='/healthz' for m in r.methods if m not in ['OPTIONS','HEAD']}
            expected={(p,m) for p,ops in CONTRACT['paths'].items() for m in ops}
            self.assertEqual(actual,expected)
            c=app.test_client()
            c.post('/api/login',json=dict(email='test@example.com',password='long-contract-password'))
            me=c.get('/api/me').json
            csrf={'X-CSRF-Token':me['csrf']}
            result=c.post('/api/rooms',json=dict(name='Contract group',description=''),headers=csrf)
            rid=result.json['id']
            pairs=[('/api/me','get','200',me),('/api/rooms','get','200',c.get('/api/rooms').json),('/api/rooms','post','201',result.json),('/api/rooms/{room_id}','get','200',c.get('/api/rooms/'+rid).json)]
            for p,m,status,value in pairs:
                schema={'components':CONTRACT['components'],**CONTRACT['paths'][p][m]['responses'][status]['content']['application/json']['schema']}
                Draft202012Validator(schema).validate(value)

if __name__=='__main__': unittest.main()
