import copy
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from src.academic.discovery import DiscoveryError, discover, validate_candidates, fetched_evidence, official_url

URL = 'https://www.dongyang.ac.kr/calendar'
EVENT = {'title':'개강','event_type':'SEMESTER_START','semester':'1','start_date':'2026-03-02',
         'end_date':'2026-03-02','source_url':URL,'evidence':'2026년 3월 2일 개강일입니다.'}
DOCUMENT = {'school_name':'동양미래대학교','academic_year':2026,'scope':'undergraduate_common','events':[EVENT]}


class AcademicValidationTests(unittest.TestCase):
    def test_exact_school_year_and_date(self):
        result=validate_candidates(DOCUMENT,'동양미래대학교',2026,{URL})
        self.assertEqual(result[0]['start_date'],'2026-03-02')
        for key,value in [('school_name','다른대학교'),('academic_year',2025),('scope','department')]:
            document=copy.deepcopy(DOCUMENT);document[key]=value
            with self.subTest(key=key),self.assertRaises(DiscoveryError):
                validate_candidates(document,'동양미래대학교',2026,{URL})

    def test_invented_urls_invalid_dates_and_types_rejected(self):
        for key,value in [('source_url','https://fake.ac.kr/schedule'),('end_date','2026-02-01'),('start_date','2026-02-30'),('event_type','UNKNOWN')]:
            document=copy.deepcopy(DOCUMENT);document['events'][0][key]=value
            with self.subTest(key=key),self.assertRaises(DiscoveryError):
                validate_candidates(document,'동양미래대학교',2026,{URL})

    def test_duplicate_events_deduplicated(self):
        doc=copy.deepcopy(DOCUMENT);doc['events']*=2
        self.assertEqual(len(validate_candidates(doc,'동양미래대학교',2026,{URL})),1)

    def test_private_or_nonofficial_urls_rejected(self):
        for url in ['http://school.ac.kr','https://school.ac.kr.evil.com','https://user:pass@school.ac.kr','https://localhost','https://school.ac.kr:8080']:
            self.assertFalse(official_url(url))

    def test_campus_mismatch_rejected(self):
        document=copy.deepcopy(DOCUMENT);document['campus']='다른캠퍼스'
        with self.assertRaises(DiscoveryError):
            validate_candidates(document,'동양미래대학교',2026,{URL},'서울캠퍼스')

    def test_evidence_must_be_present_in_fetched_source(self):
        blocks=[{'type':'web_fetch_tool_result','content':{'type':'web_fetch_result','url':URL,
                 'content':{'type':'document','source':{'type':'text','data':EVENT['evidence']}}}}]
        self.assertIn('2026년3월2일',fetched_evidence(blocks)[URL])
        import json
        payload={'stop_reason':'end_turn','content':blocks+[{'type':'text','text':'Here is the source-backed calendar:\n```json\n'+json.dumps(DOCUMENT,ensure_ascii=False)+'\n```'}]}
        response=SimpleNamespace(ok=True,json=lambda:payload)
        settings=SimpleNamespace(anthropic_api_key='test-key',anthropic_model='test-model')
        with patch('src.academic.discovery.get_settings',return_value=settings),patch('src.academic.discovery.requests.post',return_value=response):
            self.assertEqual(len(discover('동양미래대학교','',2026)),1)
            payload['content'][0]['content']['content']['source']['data']='Different unsupported content'
            with self.assertRaises(DiscoveryError):
                discover('동양미래대학교','',2026)

    def test_auth_error_is_safe(self):
        settings=SimpleNamespace(anthropic_api_key='test-secret',anthropic_model='test-model')
        with patch('src.academic.discovery.get_settings',return_value=settings),patch('src.academic.discovery.requests.post',return_value=SimpleNamespace(ok=False,status_code=401)):
            with self.assertRaises(DiscoveryError) as error:
                discover('동양미래대학교','',2026)
        self.assertNotIn('test-secret',str(error.exception))
