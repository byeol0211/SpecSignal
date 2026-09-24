'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const today = new Date(); today.setHours(0,0,0,0);
const iso = date => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
const offset = days => {const d = new Date(today); d.setDate(d.getDate()+days); return iso(d);};
const dayDiff = date => Math.round((new Date(`${date}T00:00:00`) - today)/86400000);
const dday = date => dayDiff(date) === 0 ? 'D-DAY' : dayDiff(date) > 0 ? `D-${dayDiff(date)}` : `D+${-dayDiff(date)}`;
const uid = () => crypto.randomUUID();
const defaults = {name:'',school:'',major:'',grade:'3학년',interest:'IT·데이터',role:'개발자',period:'평균',hours:2,auto:false,year:today.getFullYear(),semester:'2학기',start:true,deadline:true,exam:true,contest:true,ai:true};
let state = {profile:{...defaults},favorites:[],events:[],messages:[],anchor:iso(today)};
try {const saved=JSON.parse(localStorage.getItem('specsignal.workspace.v1')); if(saved && Array.isArray(saved.events) && Array.isArray(saved.favorites) && Array.isArray(saved.messages)) state={...state,...saved,profile:{...defaults,...saved.profile}};} catch (_) { /* 손상된 저장 값은 기본 화면으로 복구 */ }
// 데모 날짜는 최초 실행일 기준으로 고정하여 새로고침 때 일정이 이동하지 않는다.
const demoDate = n => {const d=new Date(`${state.anchor}T00:00:00`); d.setDate(d.getDate()+n);return iso(d);};
const catalog = [
 {id:'cert-it',kind:'cert',name:'정보처리기사',field:'IT·데이터',org:'한국산업인력공단',source:'https://www.q-net.or.kr/',days:45,description:'소프트웨어 설계와 개발 역량을 준비하는 국가기술자격입니다.',start:demoDate(2),deadline:demoDate(9),exam:demoDate(55),result:demoDate(75)},
 {id:'cert-sql',kind:'cert',name:'SQL 개발자(SQLD)',field:'IT·데이터',org:'한국데이터산업진흥원',source:'https://www.dataq.or.kr/',days:30,description:'데이터 모델링과 SQL 활용 역량을 준비해보세요.',start:demoDate(-5),deadline:demoDate(5),exam:demoDate(38),result:demoDate(58)},
 {id:'cert-office',kind:'cert',name:'컴퓨터활용능력 1급',field:'경영·사무',org:'대한상공회의소',source:'https://license.korcham.net/',days:35,description:'스프레드시트와 데이터베이스 실무 역량을 준비합니다.',start:demoDate(-3),deadline:demoDate(12),exam:demoDate(48),result:demoDate(68)},
 {id:'cert-design',kind:'cert',name:'웹디자인개발기능사',field:'디자인',org:'한국산업인력공단',source:'https://www.q-net.or.kr/',days:40,description:'웹 화면 설계와 디자인 구현에 관심이 있다면 살펴보세요.',start:demoDate(-30),deadline:demoDate(-2),exam:demoDate(40),result:demoDate(60)},
 {id:'contest-data',kind:'contest',name:'대학생 데이터 활용 아이디어 공모전',field:'IT·데이터',org:'가상 대학생 공모전 운영팀',source:null,days:21,description:'일상 속 문제를 데이터로 해결하는 아이디어를 제안하는 예시 공모전입니다.',start:demoDate(-10),deadline:demoDate(24),result:demoDate(44)},
 {id:'contest-design',kind:'contest',name:'캠퍼스 브랜딩 디자인 공모전',field:'디자인',org:'가상 캠퍼스 디자인 운영팀',source:null,days:14,description:'우리 학교의 새로운 모습을 표현하는 디자인 예시 공모전입니다.',start:demoDate(-4),deadline:demoDate(18),result:demoDate(38)},
 {id:'contest-business',kind:'contest',name:'청년 소셜벤처 아이디어 챌린지',field:'경영·사무',org:'가상 청년 기획 운영팀',source:null,days:28,description:'지속 가능한 비즈니스 아이디어를 제안하는 예시 공모전입니다.',start:demoDate(3),deadline:demoDate(36),result:demoDate(56)}
];
const types={exam:'자격증 시험',deadline:'접수 마감',school:'학교 시험·학사일정',contest:'공모전 마감',start:'접수 시작',result:'발표일'};
const pages=[['MY SPACE','home','홈','home'],['MY SPACE','ai','AI 맞춤 추천','radio'],['MY SPACE','favorites','관심 목록','smile'],['EXPLORE','cert','자격증 둘러보기','list'],['EXPLORE','contest','공모전 둘러보기','list'],['ACCOUNT','profile','프로필 설정','home']];
let page='home', tab='cert', month=new Date(today.getFullYear(),today.getMonth(),1), selected=iso(today), toastTimer;
function notify(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,3500);}
function persist(){try{localStorage.setItem('specsignal.workspace.v1',JSON.stringify(state));return true;}catch(_){notify('저장 공간을 사용할 수 없어 변경 내용이 이번 실행에만 유지됩니다.');return false;}}
function heading(title,description){return `<div class="page-heading"><div class="eyebrow">YOUR NEXT POSSIBILITY</div><h1>${title}</h1><p>${description}</p></div>`;}
function button(text,action,id='',cls=''){return `<button type="button" class="${cls}" data-action="${action}" data-id="${escapeHTML(id)}">${text}</button>`;}
function options(values,current){return values.map(v=>`<option ${String(v)===String(current)?'selected':''}>${escapeHTML(v)}</option>`).join('');}
function field(label,name,value,type='text',extra=''){return `<label class="field">${label}<input name="${name}" type="${type}" value="${escapeHTML(value)}" ${extra}></label>`;}
function toggle(label,name,value){return `<label class="toggle-row"><span>${label}</span><input type="checkbox" name="${name}" ${value?'checked':''}></label>`;}
function route(next){page=pages.some(p=>p[1]===next)?next:'home';if(location.hash!==`#${page}`)location.hash=page;render();}
function render(){
 document.querySelector('.demo-badge').textContent=page==='cert'?'공식 자격증 목록':'데모 미리보기';
 document.querySelector('.footnote').textContent=page==='cert'?'공식 API 제공 범위의 자격증 목록 · 맞춤 보기는 프로필 키워드 기준입니다.':'데모 데이터로 체험하는 SpecSignal · 입력한 내용은 이 브라우저에 저장됩니다.';
 $('profile-name').textContent=state.profile.name || '나의 공간';
 $('navigation').innerHTML=['MY SPACE','EXPLORE','ACCOUNT'].map(group=>`<div class="nav-group"><h2>${group}</h2>${pages.filter(p=>p[0]===group).map(p=>`<button class="nav-item ${page===p[1]?'active':''}" data-page="${p[1]}" ${page===p[1]?'aria-current="page"':''}><img src="/assets/${p[3]}.svg" alt=""><span>${p[2]}</span></button>`).join('')}</div>`).join('');
 const current=pages.find(p=>p[1]===page);$('breadcrumb').textContent=`${current[0]} / ${current[2]}`;document.title=`SpecSignal · ${current[2]}`;
 if(page==='home')renderHome();else if(page==='profile')renderProfile();else if(page==='ai')renderAI();else if(page==='cert')window.renderCertificates($('view'),state.profile);else renderCatalog();
 renderNotifications();
}
function eventRows(events){return events.length ? events.map(e=>`<div class="event-row"><div><strong>${escapeHTML(e.title)}</strong><p class="muted">${escapeHTML(e.date)} · ${types[e.type] || ''}${e.origin==='academic'?' · 학교 일정':''}</p></div><div class="actions">${button('수정','edit-event',e.id)}${button('삭제','delete-event',e.id,'danger')}</div></div>`).join('') : '<p class="muted">등록된 일정이 없어요.</p>';}
function renderHome(){
 const upcoming=state.events.filter(e=>dayDiff(e.date)>=0).sort((a,b)=>a.date.localeCompare(b.date));
 const first=new Date(month.getFullYear(),month.getMonth(),1);first.setDate(first.getDate()-first.getDay());
 const cells=Array.from({length:42},(_,i)=>{const date=new Date(first);date.setDate(date.getDate()+i);const value=iso(date);const events=state.events.filter(e=>e.date===value);return `<button class="day ${date.getMonth()!==month.getMonth()?'outside':''} ${value===selected?'selected':''} ${value===iso(today)?'today':''}" data-action="select-date" data-id="${value}" aria-label="${value}, 일정 ${events.length}개" aria-pressed="${value===selected}"><b>${date.getDate()}</b>${events.slice(0,2).map(e=>`<span class="type-${e.type}">${escapeHTML(e.title)}</span>`).join('')}${events.length>2?`<small>+${events.length-2}개</small>`:''}</button>`;}).join('');
 $('view').innerHTML=heading(`${escapeHTML(state.profile.name || '나')}의 일정 한눈에 보기`,'차근차근, 나의 속도로 준비해요. 중요한 날을 놓치지 않도록.')+`<div class="home-grid"><section><div class="row section-top"><h2>다가오는 일정 <small>${upcoming.length}</small></h2>${button('＋ 일정 추가','new-event','','primary')}</div><div class="notes">${upcoming.slice(0,8).map(e=>`<article class="note type-${e.type}"><div class="row"><span class="dday">${dday(e.date)}</span><div class="note-actions">${button('수정','edit-event',e.id)}${button('삭제','delete-event',e.id)}</div></div><h3>${escapeHTML(e.title)}</h3><small>${escapeHTML(e.date)} · ${types[e.type]}</small></article>`).join('') || '<div class="empty">아직 다가오는 일정이 없어요.<br>첫 번째 포스트잇을 붙여보세요.</div>'}</div><div class="hint">직접 등록한 일정과 확인 후 등록한 학사일정이 표시돼요. 관심 목록과 추천 결과는 별도로 보관됩니다.</div></section><section class="panel"><div class="row calendar-head"><h2>${month.getFullYear()}년 ${month.getMonth()+1}월</h2><div class="actions">${button('‹','prev-month','','icon-button')}${button('오늘','today')}${button('›','next-month','','icon-button')}</div></div><div class="weekdays">${['일','월','화','수','목','금','토'].map(d=>`<span>${d}</span>`).join('')}</div><div class="calendar">${cells}</div><div class="legend">${['exam','deadline','school','contest'].map(t=>`<span><i class="type-${t}"></i>${types[t]}</span>`).join('')}</div><div class="selected-events"><div class="row section-top"><h3>${selected} 일정</h3>${button('＋ 추가','new-event',selected)}</div>${eventRows(state.events.filter(e=>e.date===selected))}</div></section></div>`;
}
function status(item){return item.deadline<iso(today)?'접수 마감':item.start>iso(today)?'접수 예정':'접수 중';}
function itemCard(item,reason=''){
 const saved=state.favorites.includes(item.id);
 return `<article class="card" data-item="${item.id}"><div class="row"><span class="badge">${item.kind==='cert'?'자격증':'공모전'} · ${item.field}</span><span class="badge ${status(item)==='접수 마감'?'status-closed':'status-open'}">${status(item)}</span></div><h3>${item.name}</h3><p>${item.org}</p><p>${item.description}</p><p><strong>접수 마감 ${item.deadline}</strong> · ${dday(item.deadline)}</p>${reason?`<div class="hint">${escapeHTML(reason)}</div>`:''}<small>예시 일정${item.kind==='contest'?' · 가상 공모전':''}</small><div class="actions">${button('상세정보 보기','detail',item.id)}${button(saved?'♥ 저장됨 · 삭제':'♡ 관심 목록에 저장','favorite',item.id)}${button('＋ 내 일정에 추가','add-item',item.id,'primary')}</div></article>`;
}
function renderCatalog(){
 const favorite=page==='favorites',kind=favorite?tab:page;
 $('view').innerHTML=heading(favorite?'관심 목록':kind==='cert'?'자격증 둘러보기':'공모전 둘러보기',favorite?'마음에 드는 기회를 모아두고, 준비가 되면 일정에 추가하세요.':'나에게 맞는 다음 도전을 찾아보세요.')+(favorite?`<div class="tabs" role="tablist" aria-label="관심 항목 종류"><button role="tab" data-action="tab" data-id="cert" aria-selected="${tab==='cert'}">자격증</button><button role="tab" data-action="tab" data-id="contest" aria-selected="${tab==='contest'}">공모전</button></div>`:'')+`<div class="filters"><input id="search" type="search" aria-label="이름 또는 분야 검색" placeholder="이름, 분야로 검색해보세요"><select id="field-filter" aria-label="관심 분야"><option value="">모든 분야</option>${options(['IT·데이터','경영·사무','디자인'],'')}</select><select id="status-filter" aria-label="접수 상태"><option value="">모든 접수 상태</option>${options(['접수 중','접수 예정','접수 마감'],'')}</select></div><p id="result-count" class="muted section-top" aria-live="polite"></p><div id="catalog-cards" class="cards"></div>`;
 const filter=()=>{const query=$('search').value.trim().toLowerCase();const list=catalog.filter(i=>i.kind===kind&&(!favorite||state.favorites.includes(i.id))&&(!query||`${i.name} ${i.field}`.toLowerCase().includes(query))&&(!$('field-filter').value||i.field===$('field-filter').value)&&(!$('status-filter').value||status(i)===$('status-filter').value));$('result-count').textContent=`총 ${list.length}개의 ${kind==='cert'?'자격증':'공모전'}`;$('catalog-cards').innerHTML=list.map(i=>itemCard(i)).join('')||'<div class="empty">표시할 항목이 없어요.<br>검색 조건을 변경하거나 탐색 페이지에서 관심 항목을 저장해보세요.</div>';};
 $('search').addEventListener('input',filter);$('field-filter').addEventListener('change',filter);$('status-filter').addEventListener('change',filter);filter();
}
function showModal(title,html){$('modal-title').textContent=title;$('modal-content').innerHTML=html;if(!$('modal').open)$('modal').showModal();}
function showDetail(item){showModal(item.name,`<span class="badge">${item.field} · ${status(item)}</span><p>${item.description}</p><p>주관: ${item.org}</p><div class="hint">${item.kind==='cert'?'자격증 소개용 데모입니다. 아래 날짜와 공부기간은 공식 공고를 조회한 결과가 아닙니다.':'이 공모전은 사용자 흐름을 확인하기 위한 가상 데이터입니다.'}</div>${['start','deadline','exam','result'].filter(k=>item[k]).map(k=>`<div class="event-row"><span>${types[k]}</span><strong>${item[k]}</strong></div>`).join('')}<p>예시 평균 준비기간: ${item.days}일 (하루 2시간 기준)</p>${item.source?`<a href="${item.source}" target="_blank" rel="noopener noreferrer">공식 기관에서 공고 확인 ↗</a>`:'<p>공식 출처: 미연동 · 실제 공모전 정보는 추후 연결됩니다.</p>'}<div class="actions">${button('관심 목록 저장/해제','favorite',item.id)}${button('내 일정에 추가','add-item',item.id,'primary')}</div>`);}
function addItem(item){
 const keys=['start','deadline','exam','result'].filter(k=>item[k]);
 showModal('내 일정에 추가',`<p><strong>${item.name}</strong><br>등록할 날짜를 선택하고 필요하면 수정해주세요.</p><form id="add-item-form">${keys.map(k=>`<label class="date-choice"><input type="checkbox" name="pick-${k}" ${['deadline','exam'].includes(k)?'checked':''}><span>${types[k]}</span><input type="date" name="date-${k}" aria-label="${types[k]} 날짜" value="${item[k]}" required></label>`).join('')}<div class="hint">예시 날짜입니다. 실제 일정은 공식 공고에서 확인해주세요.</div><label class="field">알림 시점<select name="reminder">${options(['당일','1일 전','3일 전','7일 전','알림 없음'],'3일 전')}</select></label><p id="form-error" role="alert"></p><div class="actions">${button('취소','close')}<button type="submit" class="primary">선택한 일정 저장</button></div></form>`);
 $('add-item-form').addEventListener('submit',e=>{e.preventDefault();const form=new FormData(e.target),chosen=keys.filter(k=>form.has(`pick-${k}`));if(!chosen.length){$('form-error').textContent='등록할 날짜를 하나 이상 선택해주세요.';return;}let count=0;for(const k of chosen){const date=form.get(`date-${k}`),type=item.kind==='contest'&&k==='deadline'?'contest':k;const existing=state.events.find(ev=>ev.itemId===item.id&&ev.slot===k);if(existing){existing.date=date;existing.reminder=form.get('reminder');}else{state.events.push({id:uid(),itemId:item.id,slot:k,title:`${item.name} ${types[type]}`,date,type,reminder:form.get('reminder'),origin:'personal'});count++;}}persist();$('modal').close();render();notify(`${chosen.length}개 일정을 저장했어요${count<chosen.length?' (기존 일정 업데이트)':''}.`);});
}
function editEvent(id='',date=selected,school=false){
 const existing=state.events.find(e=>e.id===id),event=existing||{title:'',date,type:school?'school':'exam',reminder:'3일 전',origin:school?'academic':'personal'};
 showModal(existing?'일정 수정':school?'학사일정 직접 입력':'포스트잇 추가',`<form id="event-form"><div class="fields">${field('일정 이름','title',event.title,'text','required maxlength="80"')}${field('날짜','date',event.date,'date','required')}<label class="field">일정 유형<select name="type">${Object.entries(types).map(([k,v])=>`<option value="${k}" ${k===event.type?'selected':''}>${v}</option>`).join('')}</select></label><label class="field">알림 시점<select name="reminder">${options(['당일','1일 전','3일 전','7일 전','알림 없음'],event.reminder)}</select></label></div><div class="actions">${button('취소','close')}<button type="submit" class="primary">일정 저장</button></div></form>`);
 $('event-form').addEventListener('submit',e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));data.title=data.title.trim();if(!data.title){e.target.elements.title.setCustomValidity('일정 이름을 입력해주세요.');e.target.elements.title.reportValidity();return;}if(existing)Object.assign(existing,data);else state.events.push({...data,id:uid(),origin:event.origin});persist();$('modal').close();render();notify('일정을 저장했어요.');});$('event-form').elements.title.addEventListener('input',e=>e.target.setCustomValidity(''));
}
function deleteEvent(id){const event=state.events.find(e=>e.id===id);if(!event)return;showModal('일정 삭제',`<p>‘${escapeHTML(event.title)}’ 일정을 삭제할까요?</p><div class="actions">${button('취소','close')}${button('삭제','confirm-delete',id,'danger')}</div>`);}
function renderProfile(){const p=state.profile;
 $('view').innerHTML=heading('프로필 설정','나를 알아갈수록, 추천도 더 나다워져요.')+`<form id="profile-form"><div class="profile-grid"><section class="panel"><h2>기본 정보</h2><p>관심 분야와 목표를 알려주세요.</p><div class="fields">${field('이름 또는 닉네임','name',p.name,'text','maxlength="30"')}${field('학교','school',p.school,'text','maxlength="80"')}${field('학과 및 전공','major',p.major,'text','maxlength="80"')}<label class="field">학년 또는 졸업 상태<select name="grade">${options(['1학년','2학년','3학년','4학년','졸업 예정','졸업'],p.grade)}</select></label><label class="field">관심 분야<select name="interest">${options(['IT·데이터','경영·사무','디자인'],p.interest)}</select></label>${field('목표 직무','role',p.role,'text','maxlength="80"')}</div></section><section class="panel"><h2>학사일정 설정</h2><p>학교 일정을 확인하고 내 캘린더에 등록하세요.</p>${toggle('학교 학사일정 자동 조회', 'auto',p.auto)}<div class="fields">${field('조회 연도','year',p.year,'number','min="2020" max="2100" required')}<label class="field">학기<select name="semester">${options(['1학기','2학기'],p.semester)}</select></label></div><div class="hint">자동 조회는 설정만 저장됩니다. 현재는 예시 검색 결과를 확인·수정한 후 등록할 수 있어요.</div><div class="actions">${button('학사일정 검색 결과 확인','academic-search')}${button('직접 입력','school-event')}</div><div id="school-events">${eventRows(state.events.filter(e=>e.origin==='academic'))}</div></section><section class="panel"><h2>AI 추천 설정</h2><p>나에게 맞는 준비 속도를 선택하세요.</p><div class="fields"><label class="field">자격증 공부기간 기준<select name="period">${options(['최소','평균','최대'],p.period)}</select></label>${field('하루 평균 공부 가능 시간','hours',p.hours,'number','min="0.5" max="16" step="0.5" required')}</div><div class="hint">평균 기간을 기본으로 사용해요. 하루 공부 시간과 등록한 학교 일정도 함께 비교합니다.</div></section><section class="panel"><h2>알림 설정</h2><p>앱 안에서 확인할 알림을 선택하세요.</p>${[['접수 시작 알림','start'],['접수 마감 알림','deadline'],['시험일 알림','exam'],['공모전 마감 알림','contest'],['AI 추천 알림','ai']].map(([label,key])=>toggle(label,key,p[key])).join('')}</section></div><div class="profile-save"><button class="primary" type="submit">변경사항 저장</button></div></form>`;
 $('profile-form').addEventListener('submit',e=>{e.preventDefault();saveProfileForm();render();notify('프로필과 추천 설정을 저장했어요.');});
}
function saveProfileForm(){const form=$('profile-form');if(!form||!form.reportValidity())return false;const data=Object.fromEntries(new FormData(form));for(const key of ['auto','start','deadline','exam','contest','ai'])data[key]=form.elements[key].checked;data.hours=Number(data.hours);data.year=Number(data.year);state.profile={...state.profile,...data};persist();return true;}
function academicSearch(){if(!saveProfileForm())return;const p=state.profile;if(!p.school.trim()){notify('학교 이름을 먼저 입력해주세요.');$('profile-form').elements.school.focus();return;}const m=p.semester==='1학기'?'04':'10';showModal('학사일정 검색 결과 · 예시',`<p>${escapeHTML(p.school)} · ${p.year}년 ${p.semester}</p><div class="hint">공식 검색은 아직 연결되지 않았습니다. 아래는 편집 가능한 예시이며, 학교 공식 홈페이지에서 확인한 날짜로 수정해주세요.</div><form id="academic-form"><div class="fields">${field('일정 이름','title','중간고사 기간 시작','text','required maxlength="80"')}${field('날짜','date',`${p.year}-${m}-20`,'date','required')}</div><div class="actions">${button('취소','close')}<button class="primary" type="submit">확인한 일정 등록</button></div></form>`);$('academic-form').addEventListener('submit',e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));if(!data.title.trim())return;const key=`${p.school}-${p.year}-${p.semester}`;const old=state.events.find(ev=>ev.academicKey===key);if(old)Object.assign(old,data);else state.events.push({...data,id:uid(),type:'school',origin:'academic',academicKey:key,reminder:'3일 전'});persist();$('modal').close();render();notify('확인한 학사일정을 캘린더에 등록했어요.');});}
function recommendation(item){const p=state.profile;const days=Math.ceil(item.days*({최소:.7,평균:1,최대:1.4}[p.period]||1)*2/Math.max(.5,p.hours));const target=item.exam||item.deadline;const available=dayDiff(target);const conflicts=state.events.filter(e=>e.type==='school'&&e.date>=iso(today)&&e.date<=target);return `${p.major||'전공 미입력'} / ${p.role||'목표 직무 미입력'} · ${item.field===p.interest?'관심 분야 일치':'다른 분야도 살펴보세요'}. ${p.period} 기준 하루 ${p.hours}시간, 예시 준비기간 ${days}일. ${available>=days?'준비 가능한 기간입니다.':`준비기간이 ${days-available}일 부족해요.`} ${conflicts.length?`준비기간 중 학교 일정 ${conflicts.length}개${conflicts.some(e=>e.date===target)?', 시험·마감일과 날짜가 겹쳐요':', 학습 시간을 조정해주세요'}.`:'등록된 학교 일정과 겹치지 않아요.'}`;}
function recommend(query){const kind=/공모전/.test(query)?'contest':/자격증/.test(query)?'cert':null;const field=/디자인/.test(query)?'디자인':/경영|사무/.test(query)?'경영·사무':/데이터|개발|IT/i.test(query)?'IT·데이터':state.profile.interest;const match=query.match(/(\d+)\s*(주|일|개월)/);const available=match?Number(match[1])*({'주':7,'일':1,'개월':30}[match[2]]):Infinity;return catalog.filter(i=>(!kind||i.kind===kind)&&i.deadline>=iso(today)&&Math.ceil(i.days*({최소:.7,평균:1,최대:1.4}[state.profile.period])*2/state.profile.hours)<=available).sort((a,b)=>(b.field===field)-(a.field===field)).slice(0,2).map(i=>i.id);}
function renderAI(){const p=state.profile;
 $('view').innerHTML=heading('SpecSignal Bot','전공과 관심 분야, 나의 일정에 맞춰 다음 도전을 찾아보세요.')+`<div class="chat-layout"><section class="panel chat-panel"><header class="chat-header"><h2>✦ 나만의 가능성을 찾는 대화</h2><small>데모 추천 · 공식 정보 및 실시간 LLM 연동 예정</small></header><div class="messages" id="messages"><div class="bubble">안녕하세요, ${escapeHTML(p.name||'친구')}님! 어떤 도전을 준비하고 있나요?<br>관심 분야와 준비 가능한 기간을 알려주세요.</div><div class="suggestions">${button('전공에 맞는 자격증 추천','prompt','전공에 맞는 자격증 추천해줘')}${button('한 달 안에 준비할 공모전','prompt','30일 안에 준비할 공모전 추천해줘')}</div>${state.messages.map(m=>`<div class="bubble user">${escapeHTML(m.query)}</div><div class="bubble">${m.ids.length?'현재 프로필과 준비기간을 바탕으로 골라봤어요. 아래 예시 추천 이유를 확인해주세요.':'해당 준비기간에 맞는 예시 항목이 없어요. 기간을 늘려서 다시 알려주세요.'}</div><div class="cards">${m.ids.map(id=>catalog.find(i=>i.id===id)).filter(Boolean).map(i=>itemCard(i,recommendation(i))).join('')}</div>`).join('')}</div><form class="chat-input" id="chat-form"><input id="chat-message" aria-label="메시지" placeholder="예: 데이터 분야 자격증을 60일 안에 준비하고 싶어" required maxlength="500"><button type="submit" class="primary">보내기 ↑</button></form></section><aside class="chat-aside"><section class="panel"><span class="avatar">${escapeHTML((p.name||'S').slice(0,1))}</span><h3>${escapeHTML(p.name||'나의 프로필')}</h3><p>${escapeHTML(p.school||'학교 미설정')}<br>${escapeHTML(p.major||'전공 미설정')} · ${escapeHTML(p.grade)}</p><button data-page="profile">프로필 설정</button></section><section class="panel"><h3>현재 추천 조건</h3><p>관심 분야 · ${escapeHTML(p.interest)}<br>목표 직무 · ${escapeHTML(p.role||'미설정')}<br>공부기간 · ${p.period}<br>하루 공부 · ${p.hours}시간<br>등록 학사일정 · ${state.events.filter(e=>e.type==='school').length}개</p>${toggle('AI 추천 알림','chat-ai',p.ai)}<button data-page="profile">조건 및 알림 설정</button></section></aside></div>`;
 $('chat-form').addEventListener('submit',e=>{e.preventDefault();sendMessage($('chat-message').value);});document.querySelector('[name="chat-ai"]').addEventListener('change',e=>{state.profile.ai=e.target.checked;persist();renderNotifications();});$('messages').scrollTop=$('messages').scrollHeight;
}
function sendMessage(query){query=query.trim();if(!query)return;state.messages.push({id:uid(),query,ids:recommend(query)});persist();renderAI();renderNotifications();}
function notifications(){const rows=[];for(const e of state.events){const enabled=e.type==='school'||e.type==='result'||state.profile[e.type];const threshold={'당일':0,'1일 전':1,'3일 전':3,'7일 전':7}[e.reminder];if(enabled&&threshold!==undefined&&dayDiff(e.date)>=0&&dayDiff(e.date)<=threshold)rows.push({label:e.title,sub:`${dday(e.date)} · ${e.date}`,action:'notification-event',id:e.id});}if(state.profile.contest)for(const id of state.favorites){const i=catalog.find(i=>i.id===id);if(i?.kind==='contest'&&dayDiff(i.deadline)>=0&&dayDiff(i.deadline)<=7)rows.push({label:`관심 공모전 · ${i.name}`,sub:`${dday(i.deadline)} · ${i.deadline}`,action:'detail',id});}if(state.profile.ai&&state.messages.length)rows.push({label:'새로운 AI 추천을 확인해보세요',sub:'SpecSignal Bot · 최근 대화',action:'notification-chat',id:''});return rows;}
function renderNotifications(){const rows=notifications();$('notification-dot').hidden=!rows.length;$('notifications').innerHTML=`<h2>최근 알림 <small>${rows.length}</small></h2>${rows.map(n=>button(`${escapeHTML(n.label)}<small>${escapeHTML(n.sub)}</small>`,n.action,n.id,'notification')).join('')||'<p>아직 새로운 알림이 없어요.<br>등록한 일정의 알림 시점이 되면 여기에 표시돼요.</p>'}<p>앱 내 미리보기 · 실제 알림 발송은 추후 연동</p>`;}
$('notifications-button').addEventListener('click',()=>{const open=$('notifications').hidden;$('notifications').hidden=!open;$('notifications-button').setAttribute('aria-expanded',String(open));});
$('modal-close').addEventListener('click',()=>$('modal').close());
document.addEventListener('click',e=>{
 const nav=e.target.closest('[data-page]');if(nav){route(nav.dataset.page);return;}
 const el=e.target.closest('[data-action]');if(!el){if(!e.target.closest('.workspace-top')){$('notifications').hidden=true;$('notifications-button').setAttribute('aria-expanded','false');}return;}
 const {action,id}=el.dataset,item=catalog.find(i=>i.id===id);
 if(action==='close')$('modal').close();
 if(action==='new-event')editEvent('',id||selected);
 if(action==='school-event'){if(saveProfileForm())editEvent('',selected,true);}
 if(action==='edit-event')editEvent(id);
 if(action==='delete-event')deleteEvent(id);
 if(action==='confirm-delete'){state.events=state.events.filter(e=>e.id!==id);persist();$('modal').close();render();notify('일정을 삭제했어요.');}
 if(action==='select-date'){selected=id;renderHome();}
 if(action==='prev-month'||action==='next-month'){month=new Date(month.getFullYear(),month.getMonth()+(action==='prev-month'?-1:1),1);renderHome();}
 if(action==='today'){month=new Date(today.getFullYear(),today.getMonth(),1);selected=iso(today);renderHome();}
 if(action==='tab'){tab=id;renderCatalog();}
 if(action==='detail'&&item)showDetail(item);
 if(action==='add-item'&&item)addItem(item);
 if(action==='favorite'&&item){const saved=state.favorites.includes(id);state.favorites=saved?state.favorites.filter(v=>v!==id):[...state.favorites,id];persist();if(page==='ai')renderAI();else if(['cert','contest','favorites'].includes(page)){const query=$('search').value,field=$('field-filter').value,status=$('status-filter').value;renderCatalog();$('search').value=query;$('field-filter').value=field;$('status-filter').value=status;$('search').dispatchEvent(new Event('input'));}renderNotifications();notify(saved?'관심 목록에서 삭제했어요.':'관심 목록에 저장했어요.');}
 if(action==='academic-search')academicSearch();
 if(action==='prompt')sendMessage(id);
 if(action==='notification-event'){const event=state.events.find(v=>v.id===id);if(event){selected=event.date;month=new Date(`${event.date.slice(0,7)}-01T00:00:00`);route('home');}}
 if(action==='notification-chat')route('ai');
 if(action.startsWith('notification')||el.closest('#notifications')){$('notifications').hidden=true;$('notifications-button').setAttribute('aria-expanded','false');}
});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('notifications').hidden=true;$('notifications-button').setAttribute('aria-expanded','false');}if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(!$('search'))route('cert');$('search').focus();}});
window.addEventListener('hashchange',()=>{const next=location.hash.slice(1);if(next!==page)route(next);});
window.addEventListener('pywebviewready',async()=>{enableResizeHandles();$('window-controls').hidden=false;$('preview-label').hidden=true;for(const [id,method] of [['window-minimize','minimize'],['window-maximize','toggle_maximize'],['window-close','close']])$(id).addEventListener('click',()=>window.pywebview.api[method]());if(!state.profile.name)try{state.profile.name=(await window.pywebview.api.get_profile()).name||'';persist();render();}catch(_){} });
function element(tag,text,className){const node=document.createElement(tag);node.textContent=text;node.className=className;return node;}
route(location.hash.slice(1)||'home');
function enableResizeHandles() {
  for (const edge of ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']) {
    const handle = element('div', '', `resize-handle resize-${edge}`);
    handle.dataset.edge = edge;
    handle.title = '드래그하여 창 크기 조절';
    handle.setAttribute('aria-hidden', 'true');
    document.body.append(handle);
    handle.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      const start = {x: event.screenX, y: event.screenY, width: innerWidth, height: innerHeight};
      let pending = null;
      let sending = false;
      // 느린 브리지 호출이 쌓이지 않도록 최신 좌표 한 건만 유지한다.
      async function flush() {
        if (sending) return;
        sending = true;
        try {
          while (pending) {
            const size = pending;
            pending = null;
            await window.pywebview.api.resize_window(size.width, size.height, edge);
          }
        } finally {sending = false;}
      }
      function move(current) {
        const dx = current.screenX - start.x;
        const dy = current.screenY - start.y;
        pending = {
          width: Math.max(820, start.width + (edge.includes('e') ? dx : edge.includes('w') ? -dx : 0)),
          height: Math.max(620, start.height + (edge.includes('s') ? dy : edge.includes('n') ? -dy : 0)),
        };
        flush().catch(() => { /* 종료 중인 창의 브리지 호출은 무시 */ });
      }
      function stop(current) {
        if (current.type === 'pointerup') move(current);
        handle.removeEventListener('pointermove', move);
        handle.removeEventListener('pointerup', stop);
        handle.removeEventListener('pointercancel', stop);
        handle.removeEventListener('lostpointercapture', stop);
        if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
      }
      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', stop);
      handle.addEventListener('pointercancel', stop);
      handle.addEventListener('lostpointercapture', stop);
    });
  }
}


