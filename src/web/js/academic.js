'use strict';

let academicToken = sessionStorage.getItem('specsignal-access') || '';
let activeAcademicJob = null, academicPoll = 0;
const currentYear = new Date().getFullYear();
// Keep account access and profile editing in separate views.
const profileFields=document.createElement('div');
profileFields.id='profileFields'; profileFields.className='hide';
const profileCard=document.querySelector('#profile .card');
while(profileCard.firstChild) profileFields.appendChild(profileCard.firstChild);
profileCard.appendChild(profileFields);
document.querySelector('#profile .card').insertAdjacentHTML('afterbegin', `
  <div class="account-fields"><h2>계정 연결</h2>
  <section id="accountLogin" aria-labelledby="loginHeading">
    <h3 id="loginHeading">로그인</h3><p class="muted">가입한 계정으로 내 학사일정을 불러오세요.</p>
    <form id="loginForm">
      <label class="field" for="loginEmail">이메일</label><input class="input" type="email" id="loginEmail" autocomplete="username" required/>
      <label class="field" for="loginPassword">비밀번호</label><input class="input" type="password" id="loginPassword" autocomplete="current-password" required/>
      <button class="btn full" id="loginAccount" type="submit">로그인</button>
    </form>
    <p>아직 계정이 없으신가요? <button class="account-text-link" type="button" onclick="showAccountScreen('signup')">회원가입으로 이동</button></p>
  </section>
  <section id="accountSignup" class="hide" aria-labelledby="signupHeading">
    <h3 id="signupHeading">회원가입</h3><p class="muted">이메일 인증 후 학사일정을 내 계정에 저장할 수 있어요.</p>
    <form id="signupForm">
      <label class="field" for="signupEmail">이메일</label><input class="input" type="email" id="signupEmail" autocomplete="username" required/>
      <label class="field" for="signupPassword">비밀번호 (8자 이상)</label><input class="input" type="password" id="signupPassword" autocomplete="new-password" minlength="8" required/>
      <label class="field" for="signupPasswordConfirm">비밀번호 확인</label><input class="input" type="password" id="signupPasswordConfirm" autocomplete="new-password" minlength="8" required/>
      <button class="btn full" id="signupAccount" type="submit">회원가입</button>
    </form>
    <p>이미 계정이 있으신가요? <button class="account-text-link" type="button" onclick="showAccountScreen('login')">로그인으로 이동</button></p>
  </section>
  <p id="accountStatus" role="status" aria-live="polite"></p></div>`);
let accountScreen='login', accountBusy=false;
for(const action of ['login','signup']) $(action+'Form').addEventListener('submit', event=>{
  event.preventDefault(); connectAcademicAccount(action);
});
function showAccountScreen(action, message='') {
  if(accountBusy) return;
  accountScreen=action;
  $('accountLogin').classList.toggle('hide',action!=='login');
  $('accountSignup').classList.toggle('hide',action!=='signup');
  for(const id of ['loginPassword','signupPassword','signupPasswordConfirm']) $(id).value='';
  $('accountStatus').textContent=message;
  $(action+'Email').focus();
}
function showProfileFields(visible) {
  $('profileFields').classList.toggle('hide',!visible);
  document.querySelector('.account-fields').classList.toggle('hide',visible);
  document.querySelector('#profile h1').textContent=visible?'프로필 설정':'계정 연결';
  document.querySelector('#profile > .muted').textContent=visible?'처음 한 번 기본 정보를 입력해 주세요. 이후 마이페이지에서 수정할 수 있어요.':'로그인하거나 새 계정을 만들어 주세요.';
}
async function restoreAccountProfile() {
  const me=await academicRequest('/api/v1/me'), p=me.profile, prefs=me.preferences||{};
  const complete=Boolean(p.school_name?.trim() && p.major?.trim());
  data.profile=complete?{nickname:p.display_name||'',school:p.school_name,major:p.major,
    career:(p.interest_jobs||[])[0]||'',study:'2시간',period:'평균',campus:'',year:prefs.academic_year||currentYear}:null;
  for(const [id,value] of Object.entries({nickname:p.display_name||'',school:p.school_name||'',major:p.major||'',career:(p.interest_jobs||[])[0]||'',profileCampus:'',profileAcademicYear:prefs.academic_year||currentYear})) $(id).value=value;
  persist();
  showProfileFields(!complete);
  navigate(complete?'home':'profile');
  await syncAcademicCalendar();
}
const originalEditMyProfile=editMyProfile;
editMyProfile=function() { showProfileFields(true); originalEditMyProfile(); $('profileCampus').value=data.profile?.campus||''; $('profileAcademicYear').value=data.profile?.year||currentYear; };
$('school').required = true; $('major').required = true;
$('school').insertAdjacentHTML('afterend', `<label class="field" for="profileCampus">캠퍼스 (여러 캠퍼스가 있는 학교는 입력)</label><input class="input" id="profileCampus" maxlength="50" placeholder="예: 서울캠퍼스"/><label class="field" for="profileAcademicYear">학년도</label><select class="input" id="profileAcademicYear">${[currentYear-1,currentYear,currentYear+1].map(year=>`<option value="${year}" ${year===currentYear?'selected':''}>${year}학년도</option>`).join('')}</select><p class="small-muted">중간고사·기말고사 일정만 조회합니다. 학과·과목별 시험일은 별도 확인이 필요합니다.</p>`);
document.querySelector('#mypage').insertAdjacentHTML('afterbegin', '<div class="row"><button class="btn alt small" onclick="navigate(\'academic\')">학사일정 조회·등록</button><button class="btn line small" onclick="logoutAcademicAccount()">로그아웃</button></div>');
$('academicSchool').insertAdjacentHTML('afterend', '<label class="field" for="academicCampus">캠퍼스</label><input class="input" id="academicCampus" maxlength="50"/>');
$('academicYear').replaceChildren(...[currentYear-1,currentYear,currentYear+1].map(year=>new Option(year+'학년도',year,false,year===currentYear)));

async function academicRequest(path, body, method) {
  const response = await fetch(path, {method: method || (body ? 'POST' : 'GET'), headers:{
    'Content-Type':'application/json', ...(academicToken ? {Authorization:'Bearer '+academicToken} : {})
  }, ...(body ? {body:JSON.stringify(body)} : {})});
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401) { academicToken=''; sessionStorage.removeItem('specsignal-access'); }
    throw new Error(typeof result.detail === 'string' ? result.detail : '요청을 처리하지 못했습니다. 입력과 연결 상태를 확인해 주세요.');
  }
  return result;
}

async function connectAcademicAccount(action) {
  if(accountBusy) return;
  const email=$(action+'Email'), password=$(action+'Password');
  if(!email.value.trim() || !email.checkValidity()) { $('accountStatus').textContent='올바른 이메일 주소를 입력해 주세요.'; email.focus(); return; }
  if(!password.value || (action==='signup' && password.value.length<8)) { $('accountStatus').textContent=action==='signup'?'비밀번호를 8자 이상 입력해 주세요.':'비밀번호를 입력해 주세요.'; password.focus(); return; }
  if(action==='signup' && password.value!==$('signupPasswordConfirm').value) { $('accountStatus').textContent='비밀번호가 일치하지 않습니다.'; $('signupPasswordConfirm').focus(); return; }
  const button=$(action+'Account'); button.disabled=true; accountBusy=true;
  $('accountStatus').textContent=action==='signup'?'회원가입을 진행하고 있습니다.':'로그인하고 있습니다.';
  try {
    const result=await academicRequest('/api/auth/'+action,{email:email.value.trim(),password:password.value});
    password.value=''; $('signupPasswordConfirm').value='';
    if (result.confirmation_required) {
      $('loginEmail').value=email.value.trim(); accountBusy=false;
      showAccountScreen('login','가입 요청을 접수했습니다. 이메일의 인증 링크를 연 뒤 로그인해 주세요. 메일이 없으면 스팸함도 확인해 주세요. 이미 가입한 주소라면 바로 로그인할 수 있습니다.'); return;
    }
    academicToken=result.access_token; sessionStorage.setItem('specsignal-access',academicToken);
    academicPoll++; activeAcademicJob=null;
    // Do not carry another user's browser-only calendar or bookmarks into this account.
    data=structuredClone(defaults); persist();
    await restoreAccountProfile();
  } catch(error) { if(!academicToken) showProfileFields(false); $('accountStatus').textContent=error.message; if(page!=='profile'||$('profileFields').classList.contains('hide')===false) toast(error.message); }
  finally { button.disabled=false; accountBusy=false; }
}

function logoutAcademicAccount() {
  academicToken=''; academicPoll++; activeAcademicJob=null;
  profileReturn='home';
  sessionStorage.removeItem('specsignal-access');
  data=structuredClone(defaults); persist();
  showProfileFields(false);
  $('loginEmail').value=''; $('signupEmail').value='';
  showAccountScreen('login','로그아웃했습니다.');
  for(const id of ['nickname','school','major','career','profileCampus']) $(id).value='';
  navigate('profile');
}

saveProfile=async function () {
  const school=$('school').value.trim(),major=$('major').value.trim();
  if(!school||!major) { $('profileError').textContent='학교와 학과를 입력해 주세요.'; $('profileError').classList.remove('hide');return; }
  if(!academicToken) { $('accountStatus').textContent='먼저 로그인해 주세요.'; $(accountScreen+'Email').focus(); return; }
  const profile={nickname:$('nickname').value.trim(),school,major,career:$('career').value.trim(),study:$('study').value,period:$('period').value,campus:$('profileCampus').value.trim(),year:Number($('profileAcademicYear').value)};
  try {
    await academicRequest('/api/account/profile',profile,'PUT');
    data.profile=profile; persist(); $('profileError').classList.add('hide');
    const destination=profileReturn==='mypage'?'mypage':'home'; profileReturn='home';
    navigate(destination); toast('정보가 저장되었어요');
  } catch(error) { $('profileError').textContent=error.message; $('profileError').classList.remove('hide'); }
};

const originalAcademicRender=renderAcademic;
renderAcademic=function () {
  originalAcademicRender();
  $('academicCampus').value=data.profile?.campus||'';
  $('academicYear').value=data.profile?.year||currentYear;
  if(activeAcademicJob) displayAcademicJob(activeAcademicJob);
};

loadAcademic=async function () {
  if(!academicToken) { navigate('profile'); $('accountStatus').textContent='학사일정 조회·등록에는 로그인이 필요합니다.';return; }
  const generation=++academicPoll;
  $('academicResult').innerHTML='<div class="notice" role="status">저장된 학교 학사일정을 확인하고 있습니다. 처음 조회하는 학교는 공식 자료 검색에 몇 분 걸릴 수 있습니다.</div>';
  try {
    let job=await academicRequest('/api/academic/lookup',{
      school:$('academicSchool').value.trim(),campus:$('academicCampus').value.trim(),year:Number($('academicYear').value),
      major:data.profile.major,nickname:data.profile.nickname||'',career:data.profile.career||''
    });
    data.profile.school=job.school;data.profile.campus=job.campus;data.profile.year=job.year;persist();
    for(let attempt=0;attempt<240;attempt++) {
      if(generation!==academicPoll) return;
      activeAcademicJob=job;displayAcademicJob(job);
      if(job.status!=='pending') return;
      await new Promise(resolve=>setTimeout(resolve,3000));
      if(generation!==academicPoll) return;
      job=await academicRequest('/api/academic/lookup/'+job.id);
    }
    throw new Error('검색이 오래 걸리고 있습니다. 잠시 후 다시 조회해 주세요.');
  } catch(error) { if(generation===academicPoll) $('academicResult').innerHTML=`<div class="notice error" role="alert">${escapeHTML(error.message)}<button class="btn alt small" onclick="loadAcademic()">다시 조회</button></div>`; }
};

function displayAcademicJob(job) {
  if(job.status==='pending') { $('academicResult').innerHTML='<div class="notice" role="status">공식 학교 자료에서 학사일정을 확인하고 있습니다. 다른 화면을 둘러봐도 됩니다.</div>';return; }
  if(job.status!=='ready') { $('academicResult').innerHTML=`<div class="notice error" role="alert">${escapeHTML(job.message||'학교·캠퍼스·학년도를 확인해 주세요.')}<button class="btn alt small" onclick="loadAcademic()">다시 조회</button></div>`;return; }
  if(!job.events.length) { $('academicResult').innerHTML='<div class="notice" role="status">조회 자료에서 확인 가능한 중간고사·기말고사 일정이 없습니다. 학교 공식 학사일정을 확인해 주세요.</div>';return; }
  $('academicResult').innerHTML=`<div class="notice"><strong>${escapeHTML(job.school)} · ${job.year}학년도</strong><p>공식 자료에서 확인한 중간고사·기말고사 일정입니다. 날짜·캠퍼스·출처를 확인하고 내 일정에 넣을 항목을 선택해 주세요. 학과별 시험 일정은 포함되지 않습니다.</p></div><button class="btn line small" onclick="document.querySelectorAll('.academic-choice').forEach(x=>x.checked=true)">전체 선택</button><button class="btn line small" onclick="document.querySelectorAll('.academic-choice').forEach(x=>x.checked=false)">선택 해제</button><div class="academic-candidates">${job.events.map((event,index)=>`<div class="card"><label class="academic-choice-label"><input type="checkbox" class="academic-choice" value="${index}"/><span><strong>${escapeHTML(event.title)}</strong><br/>${escapeHTML(event.start_date)} ~ ${escapeHTML(event.end_date)}</span></label><a class="link" href="${escapeHTML(event.source_url)}" target="_blank" rel="noopener noreferrer">공식 출처 확인 ↗</a><details class="detail-fold"><summary>추출 근거 보기</summary><p>${escapeHTML(event.evidence)}</p></details></div>`).join('')}</div><button class="btn full" id="confirmAcademic" onclick="confirmAcademicSelection()">확인한 일정만 등록</button><p id="academicConfirmStatus" role="status"></p>`;
}

async function confirmAcademicSelection() {
  const indices=[...document.querySelectorAll('.academic-choice:checked')].map(x=>Number(x.value));
  if(!indices.length) { $('academicConfirmStatus').textContent='등록할 일정을 선택해 주세요.';return; }
  $('confirmAcademic').disabled=true;
  try {
    const result=await academicRequest('/api/academic/confirm',{lookup_id:activeAcademicJob.id,indices});
    applyAcademicCalendar(result.events);persist();toast('확인한 학사일정을 계정에 등록했어요');navigate('home');
  } catch(error) { $('academicConfirmStatus').textContent=error.message; }
  finally { if($('confirmAcademic')) $('confirmAcademic').disabled=false; }
}

function applyAcademicCalendar(events) {
  data.academic=events.map(event=>({id:'db-'+event.id,dbId:event.id,title:event.title,date:event.start_date,endDate:event.end_date,source:event.memo}));
}
async function syncAcademicCalendar() { const result=await academicRequest('/api/academic/calendar');applyAcademicCalendar(result.events);persist();if(page==='home') renderHome();if(page==='mypage') renderMyPage();if(page==='academic') renderAcademicSaved(); }

const originalRenderMyPage=renderMyPage;
renderMyPage=function() {
  originalRenderMyPage();
  const schedules=[...data.events.map(x=>({...x,schoolSchedule:false})),...data.academic.map(x=>({...x,schoolSchedule:true}))].sort((a,b)=>a.date.localeCompare(b.date));
  $('myEventCount').textContent=schedules.length;
  $('mySchedules').innerHTML=schedules.length?`<div class="schedule-list">${schedules.map(scheduleItem).join('')}</div>`:'<div class="empty">등록된 일정이 없어요.</div>';
};

const originalDeleteAcademic=deleteAcademic;
deleteAcademic=async function(id) {
  const event=data.academic.find(x=>x.id===id);
  if(!event?.dbId) { originalDeleteAcademic(id);return; }
  try { await academicRequest('/api/academic/calendar/'+event.dbId,null,'DELETE');await syncAcademicCalendar();renderAcademicSaved(); }
  catch(error) { toast(error.message); }
};
const originalDeleteSelected=deleteSelectedSchedule;
deleteSelectedSchedule=async function () {
  const event=data.academic.find(x=>x.id===selectedScheduleId);
  if(!event?.dbId) { originalDeleteSelected();return; }
  if(!confirm('내 계정에서 이 학사일정을 삭제할까요? 학교 공통 자료는 유지됩니다.'))return;
  await deleteAcademic(event.id);navigate('home');
};
const originalSaveEvent=saveEvent;
saveEvent=async function () {
  const event=data.academic.find(x=>x.id===editingId);
  if(!event?.dbId) { originalSaveEvent();return; }
  if(!$('eventTitle').value.trim()||!$('eventDate').value) { $('eventError').classList.remove('hide');return; }
  try {
    await academicRequest('/api/academic/calendar/'+event.dbId,{title:$('eventTitle').value.trim(),date:$('eventDate').value},'PATCH');
    await syncAcademicCalendar();editingId=null;editingAcademic=false;navigate('home');toast('내 일정만 수정했습니다. 학교 공통 자료는 유지됩니다.');
  } catch(error) { toast(error.message); }
};
const originalRemoveEvent=removeEvent;
removeEvent=async function () {
  const event=data.academic.find(x=>x.id===editingId);
  if(!event?.dbId) { originalRemoveEvent();return; }
  await deleteAcademic(event.id);editingId=null;editingAcademic=false;navigate('home');
};
const originalScheduleDetail=renderScheduleDetail;
renderScheduleDetail=function () {
  originalScheduleDetail();
  const previous=$('academicScheduleSource');if(previous)previous.remove();
  const event=data.academic.find(x=>x.id===selectedScheduleId);
  if(!event?.dbId)return;
  if(event.endDate&&event.endDate!==event.date) $('scheduleDate').textContent=event.date+' ~ '+event.endDate;
  const url=event.source||'';
  if(/^https:\/\//.test(url)) document.querySelector('#scheduleDetail .schedule-detail-card').insertAdjacentHTML('beforeend',`<p id="academicScheduleSource"><a class="link" href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer">학교 공식 출처 확인 ↗</a></p>`);
};

// Always restore account-owned events from DB, never another account's cached browser state.
if(academicToken) {
  $('accountStatus').textContent='이 브라우저 탭에 로그인되어 있습니다.';
  data=structuredClone(defaults); persist(); navigate('profile'); showProfileFields(false);
  restoreAccountProfile().catch(error=>{navigate('profile');showProfileFields(false);$('accountStatus').textContent=error.message;});
} else {
  data=structuredClone(defaults);persist();navigate('profile');showProfileFields(false);
}
