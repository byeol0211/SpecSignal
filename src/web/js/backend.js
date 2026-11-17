'use strict';

// Keep the PLSAi interface while reading certifications from the existing API.
let catalogState = 'loading', catalogError = '', detailRequest = 0;
catalog.splice(0, catalog.length);
let contestState='loading', contestError='';
function catalogSaveButton(item) {
  const saved=data.bookmarks.includes(item.id);
  return `<button class="catalog-save" type="button" aria-pressed="${saved}" onclick="toggleBookmark('${item.id}')">${saved?'♥ 저장됨':'♡ 관심 저장'}</button>`;
}
function catalogActions(item, includeSave=true) {
  return `<div class="catalog-actions">${includeSave?catalogSaveButton(item):''}<button class="catalog-detail" type="button" aria-label="${escapeHTML(item.title)} 상세보기" onclick="openDetail('${item.id}','explore')"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 5 7 7-7 7"/></svg></button></div>`;
}
const originalToggleBookmark=toggleBookmark;
toggleBookmark=function(id) { originalToggleBookmark(id); if(page==='explore') renderExplore(); };
const prototypeExplore = renderExplore;
let certificationColumns = '1';
try { certificationColumns = localStorage.getItem('specsignal-cert-columns') === '2' ? '2' : '1'; } catch (_) {}
$('search').insertAdjacentHTML('afterend', `<div id="certificationControls" class="certification-controls">
  <div class="certification-filters"><label>자격구분<select class="input" id="qualificationFilter"><option value="">전체 자격구분</option></select></label><label>직무분야<select class="input" id="fieldFilter"><option value="">전체 분야</option></select></label></div>
  <div class="certification-view"><span id="certificationCount" role="status" aria-live="polite"></span><div class="column-options" role="group" aria-label="한 줄에 표시할 자격증 수"><button type="button" id="oneColumn" onclick="setCertificationColumns('1')">1개씩</button><button type="button" id="twoColumns" onclick="setCertificationColumns('2')">2개씩</button></div></div>
</div>`);
$('qualificationFilter').onchange = () => renderExplore();
$('fieldFilter').onchange = () => renderExplore();
$('certificationControls').insertAdjacentHTML('afterend', `<div id="contestControls" class="certification-controls" hidden><label class="field" for="contestCategoryFilter">공모전 분야</label><select class="input" id="contestCategoryFilter"><option value="">전체 분야</option></select><p class="small-muted" id="contestCount" role="status" aria-live="polite"></p></div>`);
$('contestCategoryFilter').onchange=()=>renderExplore();
function populateContestFilters() {
  const select=$('contestCategoryFilter'), previous=select.value;
  const values=[...new Set(catalog.filter(x=>x.kind==='comp').flatMap(x=>x.categories))].sort((a,b)=>a.localeCompare(b,'ko'));
  select.replaceChildren(new Option('전체 분야',''),...values.map(value=>new Option(value,value)));
  if(values.includes(previous)) select.value=previous;
}
function setCertificationColumns(value) {
  certificationColumns = value === '2' ? '2' : '1';
  try { localStorage.setItem('specsignal-cert-columns', certificationColumns); } catch (_) {}
  renderExplore();
}
function populateCertificationFilters() {
  for (const [id, key, label] of [['qualificationFilter', 'qualification', '전체 자격구분'], ['fieldFilter', 'field', '전체 분야']]) {
    const select = $(id), previous = select.value;
    select.replaceChildren(new Option(label, ''));
    const values = [...new Set(catalog.filter(x => x.live).map(x => x[key]).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ko'));
    for (const value of values) select.add(new Option(value, value));
    if (values.includes(previous)) select.value = previous;
  }
}
renderExplore = function () {
  const isCertification = category === 'cert';
  $('certificationControls').hidden = !isCertification;
  $('contestControls').hidden = isCertification;
  $('contestCount').textContent='';
  $('exploreResults').classList.toggle('certification-grid', isCertification && catalogState === 'ready');
  $('exploreResults').classList.toggle('two-columns', isCertification && certificationColumns === '2');
  for (const [id, value] of [['oneColumn', '1'], ['twoColumns', '2']]) {
    $(id).setAttribute('aria-pressed', String(certificationColumns === value));
  }
  if (category === 'cert' && catalogState !== 'ready') {
    $('certificationCount').textContent = '';
    $('exploreResults').innerHTML = catalogState === 'loading'
      ? '<div class="notice" role="status">자격증 목록을 불러오는 중입니다.</div>'
      : `<div class="notice error" role="alert">${escapeHTML(catalogError)}<button class="btn alt small" onclick="loadCertifications()">다시 시도</button></div>`;
    return;
  }
  if (isCertification) {
    const query = $('search').value.trim().toLocaleLowerCase('ko');
    const qualification = $('qualificationFilter').value, field = $('fieldFilter').value;
    const items = catalog.filter(x => x.live && (!qualification || x.qualification === qualification) && (!field || x.field === field) && `${x.title} ${x.category} ${x.field} ${x.description}`.toLocaleLowerCase('ko').includes(query));
    $('certificationCount').textContent = `${items.length}개 자격증`;
    $('exploreResults').innerHTML = items.length ? items.map(x => {
      const qualification = x.qualification || '국가자격증';
      const tags = [...new Set([qualification, x.category || x.field].filter(Boolean))];
      return `<article class="card certification-card"><div class="certification-copy"><div class="certification-tags">${tags.map((tag, index) => `<span class="tag${index ? ' gray' : ''}">${escapeHTML(tag)}</span>`).join('')}</div><h3>${escapeHTML(x.title)}</h3>${catalogSaveButton(x)}</div>${catalogActions(x,false)}</article>`;
    }).join('') : '<div class="empty"><strong>조건에 맞는 자격증이 없어요</strong>검색어나 카테고리를 변경해 주세요.</div>';
    return;
  }
  if(contestState!=='ready') {
    $('exploreResults').innerHTML=contestState==='loading'?'<div class="notice" role="status">공모전을 불러오는 중입니다.</div>':`<div class="notice error" role="alert">${escapeHTML(contestError)}<button class="btn alt small" onclick="loadContests()">다시 시도</button></div>`;
    return;
  }
  const query=$('search').value.trim().toLocaleLowerCase('ko');
  const field=$('contestCategoryFilter').value;
  const contests=catalog.filter(x=>x.kind==='comp' && (!field||x.categories.includes(field)) && `${x.title} ${x.category} ${x.organizer} ${x.description}`.toLocaleLowerCase('ko').includes(query));
  $('contestCount').textContent=`${contests.length}개 공모전`;
  $('exploreResults').innerHTML=contests.length?contests.map(x=>`<article class="card">${contestImage(x)}<span class="tag">공모전</span> <span class="tag gray">${escapeHTML(x.category)}</span><h3>${escapeHTML(x.title)}</h3><p>${escapeHTML(x.organizer||'주최기관 미제공')}</p><p>접수 마감: ${escapeHTML(x.deadline)}</p><p>${escapeHTML(x.status||'')}</p>${catalogActions(x)}</article>`).join(''):'<div class="empty">조건에 맞는 공모전이 없어요.</div>';
};

function contestImage(item, detail=false) {
  return item.imageUrl?`<img class="contest-image${detail?' contest-image-detail':''}" src="${escapeHTML(item.imageUrl)}" alt="${escapeHTML(item.title)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()"/>`:'';
}
function contestUrl(value) {
  try { const url=new URL(value); return ['https:','http:'].includes(url.protocol)?url.href:''; } catch(_) { return ''; }
}
async function loadContests() {
  contestState='loading'; if(category==='comp') renderExplore();
  try {
    const result=await api('/api/contests');
    const rows=result.items.map(x=>({id:'contest-'+x.id,kind:'comp',real:true,title:x.title,
      categories:x.categories?.length?x.categories:['기타'],category:(x.categories||[]).join(' · ')||'기타',organizer:x.organizer,status:x.status,
      description:x.description||'상세 설명이 제공되지 않았습니다.',eligibility:x.eligibility||'공식 모집 안내를 확인해 주세요.',
      createdAt:x.created_at,sourceId:String(x.id),imageUrl:contestUrl(x.image_url),prizes:x.prizes,deadline:x.end_date||'미정',startDate:x.start_date,exam:x.end_date||'미정',url:contestUrl(x.source_url)}));
    const certifications=catalog.filter(x=>x.kind==='cert');
    catalog.splice(0,catalog.length,...certifications,...rows); populateContestFilters(); contestState='ready';
  } catch(error) { contestState='error'; contestError=error.message; }
  if(category==='comp') renderExplore(); if(page==='mypage') renderMyPage(); if(page==='home') renderHome();
}

async function api(path) {
  const response = await fetch(path, {headers: {Accept: 'application/json'}});
  const result = await response.json();
  if (!response.ok || result.ok === false) {
    throw new Error(typeof result.detail === 'string' ? result.detail : result.error || '정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.');
  }
  return result;
}

async function loadCertifications() {
  catalogState = 'loading'; renderExplore();
  try {
    const result = await api('/api/items');
    const rows = result.items.map(x => {
      if (!/^\d+$/.test(x.jmcd)) throw new Error('자격증 코드 형식이 올바르지 않습니다.');
      return {id: 'cert-' + x.jmcd, jmcd: x.jmcd, kind: 'cert', live: true,
        title: x.jmfldnm, category: x.mdobligfldnm || x.obligfldnm || x.qualgbnm,
        qualification: x.qualgbnm || '', qualgbcd: x.qualgbcd, field: x.obligfldnm || x.mdobligfldnm || '',
        description: x.qualgbnm || '국가자격증', eligibility: '공식 안내에서 응시자격을 확인해 주세요.',
        deadline: '상세 일정에서 확인', exam: '상세 일정에서 확인', url: 'https://www.q-net.or.kr/'};
    });
    catalog.splice(0, catalog.length, ...rows, ...catalog.filter(x=>x.kind==='comp'));
    populateCertificationFilters();
    catalogState = 'ready';
  } catch (error) { catalogState = 'error'; catalogError = error.message; }
  renderExplore();
  if (page === 'mypage') renderMyPage();
  if (page === 'home') renderHome();
}

const prototypeDetail = renderDetail;
renderDetail = function () {
  const token = ++detailRequest;
  prototypeDetail();
  const item = catalog.find(x => x.id === selectedId);
  if(item?.real && item.kind==='comp') {
    $('detailContent').innerHTML=`<div class="card">${contestImage(item,true)}<span class="tag">공모전</span><h1>${escapeHTML(item.title)}</h1><p>${escapeHTML(item.category)}</p><h2>주최기관</h2><p>${escapeHTML(item.organizer||'미제공')}</p><h2>접수 기간</h2><p>${escapeHTML(item.startDate||'미정')} ~ ${escapeHTML(item.deadline)}</p><p>${escapeHTML(item.status||'')}</p><h2>상세 안내</h2><p style="white-space:pre-wrap">${escapeHTML(item.description)}</p><h2>참가 조건</h2><p style="white-space:pre-wrap">${escapeHTML(item.eligibility)}</p><h2>시상 내역</h2><p style="white-space:pre-wrap">${escapeHTML(item.prizes||'공식 모집 안내를 확인해 주세요.')}</p>${item.url?`<a class="link" href="${escapeHTML(item.url)}" target="_blank" rel="noopener noreferrer">모집 원문 확인 ↗</a>`:''}</div>`;
    return;
  }
  if (!item?.live) return;
  $('detailContent').innerHTML = `<div class="card">${contestImage(item,true)}<span class="tag">공식 API</span><h1>${escapeHTML(item.title)}</h1><p>${escapeHTML(item.category)}</p><a class="link" href="https://www.q-net.or.kr/" target="_blank" rel="noopener noreferrer">공식 안내 사이트 ↗</a></div>`;
  $('detailContent').insertAdjacentHTML('beforeend', '<div class="card" id="officialDetails" role="status">상세정보를 불러오는 중입니다.</div><div class="card"><h2>시험일정</h2><label for="examYear">연도</label><select class="input" id="examYear"></select><div id="officialExams" role="status"></div></div>');
  const year = new Date().getFullYear();
  for (let value = year - 1; value <= year + 1; value++) $('examYear').add(new Option(value + '년', value, false, value === year));
  $('examYear').onchange = () => loadExams(item, token);
  api('/api/details?jmcd=' + encodeURIComponent(item.jmcd)).then(result => {
    if (token !== detailRequest) return;
    $('officialDetails').innerHTML = '<h2>공식 상세정보</h2>' + (result.items.length ? result.items.map(x => `<details class="detail-fold"><summary>${escapeHTML(x.infogb)}</summary><p style="white-space:pre-wrap">${escapeHTML(x.contents)}</p></details>`).join('') : '<p>제공된 상세정보가 없습니다.</p>') + (result.stale ? '<p>최근 수집이 실패하여 이전 저장 정보를 표시합니다.</p>' : '');
  }).catch(error => { if (token === detailRequest) $('officialDetails').innerHTML = `<p role="alert">${escapeHTML(error.message)}</p><button class="btn alt small" onclick="renderDetail()">다시 시도</button>`; });
  loadExams(item, token);
};

let examRequest = 0;
let eventDateRequest=0, eventDateRevision=0;
$('eventDate').insertAdjacentHTML('beforebegin','<div id="officialEventDateControls" class="hide"><label class="field" for="officialEventDate">공식 일정 선택</label><select class="input hide" id="officialEventDate"></select><p class="small-muted" id="officialEventDateStatus" role="status"></p></div>');
$('eventDate').addEventListener('input',()=>{eventDateRevision++;});
$('officialEventDate').addEventListener('change',()=>{eventDateRevision++;$('eventDate').value=$('officialEventDate').value;});
function officialDate(value) {
  const text=String(value||'');
  const iso=/^\d{8}$/.test(text)?`${text.slice(0,4)}-${text.slice(4,6)}-${text.slice(6,8)}`:text;
  if(!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return '';
  const date=new Date(iso+'T00:00:00Z');
  return !Number.isNaN(date.getTime())&&date.toISOString().slice(0,10)===iso?iso:'';
}
const originalOpenEvent=openEvent;
openEvent=async function(itemId) {
  const request=++eventDateRequest, revision=eventDateRevision;
  originalOpenEvent(itemId);
  const item=catalog.find(x=>x.id===itemId), controls=$('officialEventDateControls'), select=$('officialEventDate'), status=$('officialEventDateStatus');
  controls.classList.toggle('hide',!item); select.classList.add('hide');select.replaceChildren();
  if(!item) return;
  $('eventDate').value='';
  if(item.kind==='comp') {
    const date=officialDate(item.deadline);$('eventDate').value=date;
    status.textContent=date?'공모전 접수 마감일을 기본으로 입력했습니다. 날짜는 변경할 수 있어요.':'공식 마감일이 없어 날짜를 직접 입력해 주세요.';
    return;
  }
  status.textContent='공식 시험일을 확인하고 있습니다. 날짜를 직접 입력하면 입력한 값을 유지합니다.';
  const now=new Date(),today=dateKey(now.getFullYear(),now.getMonth(),now.getDate());
  try {
    let dates=[];
    for(const year of [now.getFullYear(),now.getFullYear()+1]) {
      const result=await api(`/api/schedules?jmcd=${encodeURIComponent(item.jmcd)}&year=${year}&category=${encodeURIComponent(item.qualgbcd||'')}`);
      if(request!==eventDateRequest||page!=='event'||editingId) return;
      for(const row of result.items) for(const [prefix,label] of [['doc','필기'],['prac','실기']]) {
        const date=officialDate(row[prefix+'ExamStartDt']);
        if(date&&date>=today) dates.push({date,label:`${row.implSeq||''}회 ${label} 시험 · ${date}`});
      }
      if(dates.length) break;
    }
    dates.sort((a,b)=>a.date.localeCompare(b.date));
    if(!dates.length) {status.textContent='올해·내년의 예정된 공식 시험일이 없습니다. 날짜를 직접 입력해 주세요.';return;}
    select.replaceChildren(...dates.map(x=>new Option(x.label,x.date)));
    select.classList.remove('hide');
    if(eventDateRevision===revision&&!$('eventDate').value) {
      $('eventDate').value=dates[0].date;
      status.textContent='가장 가까운 시험 시작일을 입력했습니다. 회차·필기·실기를 선택하거나 날짜를 수정할 수 있어요.';
    } else status.textContent='직접 입력한 날짜를 유지했습니다. 공식 일정도 선택할 수 있어요.';
  } catch(error) {
    if(request===eventDateRequest&&page==='event'&&!editingId) status.textContent='공식 시험일을 불러오지 못했습니다. 날짜를 직접 입력해 주세요.';
  }
};
const originalEditEvent=editEvent;
editEvent=function(id) {eventDateRequest++;$('officialEventDateControls').classList.add('hide');originalEditEvent(id);};
const originalEditSelectedSchedule=editSelectedSchedule;
editSelectedSchedule=function() {eventDateRequest++;$('officialEventDateControls').classList.add('hide');originalEditSelectedSchedule();};
async function loadExams(item, token) {
  const request = ++examRequest;
  $('officialExams').textContent = '시험일정을 불러오는 중입니다.';
  try {
    const result = await api(`/api/schedules?jmcd=${encodeURIComponent(item.jmcd)}&year=${$('examYear').value}&category=${encodeURIComponent(item.qualgbcd)}`);
    if (token !== detailRequest || request !== examRequest) return;
    const formatDate = value => /^\d{8}$/.test(value || '') ? `${value.slice(0,4)}-${value.slice(4,6)}-${value.slice(6,8)}` : value || '미제공';
    $('officialExams').innerHTML = result.items.length ? result.items.map(x => `<details class="detail-fold"><summary>${escapeHTML(x.implSeq)}회 ${escapeHTML(x.description || '')}</summary>${[['doc','필기'],['prac','실기']].map(([prefix,label]) => `<h4>${label}</h4><p>접수: ${escapeHTML(formatDate(x[prefix+'RegStartDt']))} ~ ${escapeHTML(formatDate(x[prefix+'RegEndDt']))}</p><p>시험: ${escapeHTML(formatDate(x[prefix+'ExamStartDt']))} ~ ${escapeHTML(formatDate(x[prefix+'ExamEndDt']))}</p><p>발표: ${escapeHTML(formatDate(x[prefix+'PassDt']))}</p>`).join('')}</details>`).join('') : '<p>공식 API가 해당 연도·자격증의 일정을 제공하지 않았습니다.</p>';
  } catch (error) { if (token === detailRequest && request === examRequest) $('officialExams').innerHTML = `<p role="alert">${escapeHTML(error.message)}</p><button class="btn alt small" onclick="renderDetail()">다시 시도</button>`; }
}

// Fixed prototype suggestions must not refer to deleted sample certification IDs.
runRecommendation = function () { toast('AI 추천은 아직 연결되지 않았어요. 탐색에서 실제 자격증을 확인해 주세요.'); };
const prototypeHome = renderHome;
renderHome = function () {
  prototypeHome();
  const grid = document.querySelector('.home-discover-grid');
  const card=(item,label)=>`<button type="button" class="home-discover-card" onclick="openDetail('${item.id}','home')"><span class="home-discover-kind">${label}</span><strong>${escapeHTML(item.title)}</strong><span class="home-discover-foot">${item.kind==='comp'?'접수 마감: '+escapeHTML(item.deadline):'자세히 보기'} <b aria-hidden="true">›</b></span></button>`;
  const certifications=catalog.filter(x=>x.live && x.kind==='cert');
  const selected=[];
  for(const name of ['정보처리기사','산업안전기사','전기기사']) {
    const item=certifications.find(x=>x.title===name); if(item) selected.push(item);
  }
  for(const item of certifications) { if(selected.length===3) break; if(!selected.includes(item)) selected.push(item); }
  const newest=catalog.filter(x=>x.kind==='comp').sort((a,b)=>
    (Date.parse(b.createdAt)||0)-(Date.parse(a.createdAt)||0)||b.sourceId.localeCompare(a.sourceId,undefined,{numeric:true})).slice(0,3);
  const stateMessage=(state,retry,label)=>state==='loading'?`<p class="home-discover-status" role="status">${label} 불러오는 중입니다.</p>`:state==='error'?`<button class="btn alt small" onclick="${retry}()">${label} 다시 불러오기</button>`:'<p class="home-discover-status">등록된 항목이 없습니다.</p>';
  grid.innerHTML=
    (catalogState==='ready'&&selected.length?selected.map(x=>card(x,'추천 자격증')).join(''):stateMessage(catalogState,'loadCertifications','자격증'))+
    (contestState==='ready'&&newest.length?newest.map(x=>card(x,'새 공모전')).join(''):stateMessage(contestState,'loadContests','공모전'));
};
loadCertifications();
loadContests();
