'use strict';

// Keep the PLSAi interface while reading certifications from the existing API.
let catalogState = 'loading', catalogError = '', detailRequest = 0;
const demoCompetitions = catalog.filter(x => x.kind === 'comp');
catalog.splice(0, catalog.length, ...demoCompetitions);
const prototypeExplore = renderExplore;
let certificationColumns = '1';
try { certificationColumns = localStorage.getItem('specsignal-cert-columns') === '2' ? '2' : '1'; } catch (_) {}
$('search').insertAdjacentHTML('afterend', `<div id="certificationControls" class="certification-controls">
  <div class="certification-filters"><label>자격구분<select class="input" id="qualificationFilter"><option value="">전체 자격구분</option></select></label><label>직무분야<select class="input" id="fieldFilter"><option value="">전체 분야</option></select></label></div>
  <div class="certification-view"><span id="certificationCount" role="status" aria-live="polite"></span><div class="column-options" role="group" aria-label="한 줄에 표시할 자격증 수"><button type="button" id="oneColumn" onclick="setCertificationColumns('1')">1개씩</button><button type="button" id="twoColumns" onclick="setCertificationColumns('2')">2개씩</button></div></div>
</div>`);
$('qualificationFilter').onchange = () => renderExplore();
$('fieldFilter').onchange = () => renderExplore();
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
      const summary = x.field || x.description;
      return `<article class="card certification-card"><div class="certification-copy"><div class="certification-tags">${tags.map((tag, index) => `<span class="tag${index ? ' gray' : ''}">${escapeHTML(tag)}</span>`).join('')}</div><h3>${escapeHTML(x.title)}</h3>${summary && !tags.includes(summary) && summary !== x.title ? `<p>${escapeHTML(summary)}</p>` : ''}</div><button class="btn alt small" onclick="openDetail('${x.id}','explore')">상세보기</button></article>`;
    }).join('') : '<div class="empty"><strong>조건에 맞는 자격증이 없어요</strong>검색어나 카테고리를 변경해 주세요.</div>';
    return;
  }
  prototypeExplore();
};

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
    catalog.splice(0, catalog.length, ...rows, ...demoCompetitions);
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
  if (!item?.live) return;
  $('detailContent').innerHTML = `<div class="card"><span class="tag">공식 API</span><h1>${escapeHTML(item.title)}</h1><p>${escapeHTML(item.category)}</p><a class="link" href="https://www.q-net.or.kr/" target="_blank" rel="noopener noreferrer">공식 안내 사이트 ↗</a></div>`;
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
  if (catalogState !== 'ready') {
    grid.innerHTML = catalogState === 'loading' ? '<p role="status">자격증을 불러오는 중입니다.</p>' : '<button class="btn alt small" onclick="loadCertifications()">다시 시도</button>';
    return;
  }
  const certifications = catalog.filter(x => x.live);
  const selected = [];
  const fields = new Set();
  for (const item of certifications) {
    if (selected.length === 6) break;
    if (!fields.has(item.field)) { selected.push(item); fields.add(item.field); }
  }
  for (const item of certifications) {
    if (selected.length === 6) break;
    if (!selected.includes(item)) selected.push(item);
  }
  grid.innerHTML = selected.map(x => `<button type="button" class="home-discover-card" onclick="openDetail('${x.id}','home')"><span class="home-discover-kind">${escapeHTML(x.qualification)}</span><strong>${escapeHTML(x.title)}</strong><span class="home-discover-foot">자세히 보기 <b aria-hidden="true">›</b></span></button>`).join('');
};
loadCertifications();
