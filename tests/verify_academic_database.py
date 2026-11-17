"""Opt-in live DB verification; all test users and rows are rolled back, no emails sent."""
import json
from contextlib import contextmanager
from uuid import uuid4
from unittest.mock import patch

from fastapi import BackgroundTasks
from src.db.connection import connect
from src.academic import routes
from src.web.auth import AuthUser


def main():
    conn=connect()
    @contextmanager
    def service():
        with conn.transaction():
            yield conn
    @contextmanager
    def personal(claims):
        with conn.transaction():
            conn.execute("select set_config('request.jwt.claims',%s,true),set_config('request.jwt.claim.sub',%s,true)",
                         (json.dumps(claims),claims['sub']))
            conn.execute('set local role authenticated')
            try:
                yield conn
            finally:
                if conn.info.transaction_status.name != 'INERROR':
                    conn.execute('reset role')
    try:
        conn.execute('select 1')
        users=[]
        for _ in range(2):
            uid=str(uuid4())
            conn.execute("""insert into auth.users(id,instance_id,aud,role,email,raw_user_meta_data,raw_app_meta_data,created_at,updated_at)
                values(%s,'00000000-0000-0000-0000-000000000000','authenticated','authenticated',%s,'{}','{}',now(),now())""",
                (uid,uid+'@test.invalid'))
            users.append(AuthUser(uid,{'sub':uid,'role':'authenticated','aud':'authenticated'}))
        school='테스트대학교-'+str(uuid4())[:8]
        request=routes.SchoolRequest(school=school,major='인공지능소프트웨어학과',year=2026)
        event={'title':'검증용 개강','start_date':'2026-03-02','end_date':'2026-03-02','event_type':'SEMESTER_START',
               'semester':'1','source_url':'https://test.ac.kr/calendar','evidence':'테스트 트랜잭션에만 존재하는 일정'}
        with patch.object(routes,'service_transaction',service),patch.object(routes,'user_transaction',personal),patch.object(routes,'discover',return_value=[event]) as ai:
            tasks=BackgroundTasks();first=routes.lookup(request,tasks,users[0]);assert first['status']=='pending'
            tasks.tasks[0].func(*tasks.tasks[0].args,**tasks.tasks[0].kwargs)
            second=routes.lookup(request,BackgroundTasks(),users[1]);assert second['status']=='ready' and second['source']=='database'
            assert ai.call_count==1
            body=routes.Selection(lookup_id=second['id'],indices=[0])
            routes.confirm(body,users[0]);routes.confirm(body,users[0])
            one=routes.calendar(users[0])['events'];assert len(one)==1
            assert not routes.calendar(users[1])['events']
            routes.confirm(body,users[1]);two=routes.calendar(users[1])['events'];assert len(two)==1
            assert one[0]['id']!=two[0]['id']
            routes.edit_calendar(one[0]['id'],routes.PersonalAcademicEdit(title='개인 수정',date='2026-03-03'),users[0])
            assert routes.calendar(users[1])['events'][0]['title']=='검증용 개강'
            assert routes.get_lookup(body.lookup_id,users[0])['events'][0]['title']=='검증용 개강'
            routes.remove_calendar(one[0]['id'],users[0]);assert not routes.calendar(users[0])['events']
            assert len(routes.calendar(users[1])['events'])==1
        print('PASS: first AI discovery, second-user DB cache, idempotent import, RLS isolation, private edits/deletes')
    finally:
        conn.rollback();conn.close()
        print('All verification users and rows rolled back.')


if __name__=='__main__':
    main()
