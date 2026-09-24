window.renderCertificates = function(root, profile) {
  root.innerHTML = "<div class=\"page-heading\"><div class=\"eyebrow\">EXPLORE</div><h1>자격증 둘러보기</h1><p>한국산업인력공단 · 공공데이터포털</p></div>\n<div class=\"tabs\" role=\"group\" aria-label=\"자격증 보기 모드\"><button id=\"mode-all\" aria-pressed=\"true\" class=\"primary\">전체 보기</button><button id=\"mode-personal\" aria-pressed=\"false\">나에게 맞는 자격증</button></div><p id=\"mode-description\" class=\"hint\">프로필과 관계없이 API가 제공하는 모든 자격증을 표시합니다.</p>\n<div class=\"filters\"><input id=\"search\" type=\"search\" placeholder=\"자격증 이름, 분야 또는 코드 검색\" aria-label=\"자격증 이름, 분야 또는 코드 검색\" disabled><select id=\"category\" aria-label=\"자격구분\" disabled><option value=\"\">모든 자격구분</option></select><select id=\"field\" aria-label=\"직무분야\" disabled><option value=\"\">모든 직무분야</option></select></div><div class=\"row section-top\"><p id=\"result-summary\" aria-live=\"polite\">목록을 불러오는 중입니다.</p><button id=\"reload\">새로고침 ↻</button></div><div id=\"cards\" class=\"cards live-cards\" aria-busy=\"true\"></div><div id=\"empty\" class=\"empty\">공식 자격증 정보를 불러오는 중입니다.</div><button id=\"more\" hidden>더 보기</button><details id=\"error-panel\" hidden><summary>연결 오류 상세</summary><pre id=\"error\"></pre></details><div class=\"hint\"><span id=\"status-dot\"></span><span id=\"status\" role=\"status\"></span> <small id=\"meta\"></small><p><a href=\"https://www.data.go.kr/data/15003024/openapi.do\" target=\"_blank\" rel=\"noreferrer\">공식 데이터 출처 ↗</a></p></div>  <dialog id=\"info-dialog\" class=\"info-dialog\" aria-labelledby=\"info-title\">\n    <div class=\"dialog-toolbar\"><span>QUALIFICATION DETAILS</span><button id=\"close-info\" class=\"icon-button\" type=\"button\" aria-label=\"상세정보 닫기\">×</button></div>\n    <header class=\"detail-heading\"><p id=\"info-code\"></p><h2 id=\"info-title\">자격증 정보</h2><p>자격증의 기본 정보부터 시험일정까지 한곳에서 확인하세요.</p></header>\n    <div class=\"detail-body\">\n      <section aria-labelledby=\"detail-section-title\"><div class=\"section-heading\"><h3 id=\"detail-section-title\">자격정보</h3><span>한국산업인력공단 제공</span></div><div id=\"details-content\" aria-live=\"polite\"></div></section>\n      <section class=\"schedule-section\" aria-labelledby=\"schedule-title\"><div class=\"section-heading\"><h3 id=\"schedule-title\">시험일정</h3><form id=\"schedule-form\"><label for=\"year\">조회 연도</label><input id=\"year\" type=\"number\" min=\"1000\" max=\"9999\" required><button type=\"submit\">조회</button></form></div><p class=\"schedule-note\">공고된 기간 기준입니다. 같은 회차의 접수기간이 여러 건이면 각각 표시합니다.</p><div id=\"schedule-content\" aria-live=\"polite\"></div></section>\n      <p class=\"detail-disclaimer\">응시 전 공식 공고에서 응시요건과 최종 일정을 확인해주세요.</p>\n    </div>\n  </dialog>\n";
  const nodes = new Map([...root.querySelectorAll('[id]')].map(n => [n.id,n]));
  const $ = id => nodes.get(id);
  let mode = 'all';
  const groups = [
    ['컴퓨터','소프트웨어','개발','데이터','IT·데이터','정보','통신','프로그래밍'],
    ['경영','사무','회계','재무','세무','마케팅','사회조사','직업상담'],
    ['디자인','시각','미술','그래픽','웹디자인'],
    ['전기','전자','반도체'], ['건축','건설','토목'], ['기계','자동차','설비'],
    ['화학','환경','에너지'], ['식품','조리','영양'], ['안전','소방','산업안전']
  ];
  function matchesProfile(item) {
    const values = [profile.major, profile.role, profile.interest].filter(Boolean);
    const input = values.join(' ').toLowerCase();
    const keywords = new Set(groups.filter(g => g.some(k => input.includes(k.toLowerCase()))).flat());
    for (const v of values) for (const token of v.split(/[\s·,/]+/)) if(token.length >= 2) keywords.add(token);
    const text = [item.jmfldnm,item.obligfldnm,item.mdobligfldnm,item.seriesnm].join(' ').toLowerCase();
    // '안전기사'에 포함된 '전기'를 전기 분야로 잘못 분류하지 않는다.
    return [...keywords].some(k => k === '전기' ? /(^|[^안])전기/.test(text) : text.includes(k.toLowerCase()));
  }
let items = [];
let visible = 8;

// API 응답은 HTML로 삽입하지 않고 텍스트로만 표시합니다.
function element(tag, text, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

function fillOptions(id, key) {
  const select = $(id);
  select.length = 1;
  [...new Set(items.map(item => item[key]).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, 'ko'))
    .forEach(value => select.add(new Option(value, value)));
}

function render() {
  const query = $('search').value.trim().toLowerCase();
  const filtered = items.filter(item =>
    (mode === 'all' || matchesProfile(item)) &&
    (!$('category').value || item.qualgbnm === $('category').value) &&
    (!$('field').value || item.obligfldnm === $('field').value) &&
    Object.values(item).some(value => value.toLowerCase().includes(query))
  );
  $('cards').replaceChildren();
  for (const item of filtered.slice(0, visible)) {
    const card = element('article', '', 'card');
    const header = element('div', '', 'card-header');
    header.append(element('span', item.qualgbnm || '구분 미제공', 'badge'));
    header.append(element('h3', item.jmfldnm || '종목명 미제공'));
    card.append(header);
    card.title = `종목코드 ${item.jmcd}`;
    const list = element('dl', '');
    for (const [label, value, cls] of [
      ['계열', item.seriesnm], ['직무분야', item.obligfldnm],
      ['세부분야', item.mdobligfldnm]
    ]) {
      const row = element('div', '', cls);
      const description = element('dd', value || '미제공');
      description.title = value || '미제공';
      row.append(element('dt', label), description);
      list.append(row);
    }
    card.append(list);
    const infoButton = element('button', '상세정보 및 시험정보 보기', 'info-button');
    infoButton.type = 'button';
    infoButton.addEventListener('click', () => openInfo(item));
    card.append(infoButton);
    $('cards').append(card);
  }
  $('mode-description').textContent = mode === 'all' ? '프로필과 관계없이 API가 제공하는 모든 자격증을 표시합니다.' : '전공·목표 직무·관심 분야와 종목명/직무분야의 키워드를 비교한 결과입니다. 응시자격 판정은 아닙니다.';
  $('result-summary').textContent = `전체 ${items.length.toLocaleString()}개 중 ${filtered.length.toLocaleString()}개 · ${Math.min(visible, filtered.length)}개 표시`;
  $('empty').hidden = filtered.length > 0;
  if (!filtered.length) {
    $('empty').replaceChildren(element('div', '⌕'), element('h3', '표시할 자격증이 없습니다.'), element('p', mode === 'all' ? '검색어와 필터를 확인해주세요.' : '프로필의 전공·목표 직무·관심 분야를 확인하거나 전체 보기로 전환해주세요.'));
  }
  $('more').hidden = filtered.length <= visible;
}

async function load() {
  if ($('reload').disabled) return;
  $('reload').disabled = true;
  $('reload').textContent = '불러오는 중…';
  $('status').textContent = '공식 API에 연결하고 있습니다…';
  $('meta').textContent = '응답을 기다리는 중입니다.';
  $('error-panel').hidden = true;
  $('status-dot').className = 'status-dot';
  $('cards').setAttribute('aria-busy', 'true');
  try {
    const response = await fetch('/api/items', {cache: 'no-store'});
    const data = await response.json();
    if (!response.ok || !data.ok) {
      $('meta').textContent = data.http_status ? `외부 API HTTP ${data.http_status}` : '외부 API 응답 상태 없음';
      throw new Error(data.error || '데이터를 불러오지 못했습니다.');
    }
    items = data.items;
    visible = 8;
    fillOptions('category', 'qualgbnm');
    fillOptions('field', 'obligfldnm');
    for (const id of ['search', 'category', 'field']) $(id).disabled = false;
    $('status').textContent = `연결 성공 · ${items.length.toLocaleString()}개 종목`;
    $('status-dot').className = 'status-dot success';
    $('meta').textContent = `${new Date(data.fetched_at).toLocaleString('ko-KR')} 업데이트`;
    render();
  } catch (error) {
    $('status').textContent = '목록을 불러오지 못했습니다.';
    $('status-dot').className = 'status-dot error';
    $('error').textContent = error.message;
    $('error-panel').hidden = false;
    $('error-panel').open = true;
    if (items.length) $('result-summary').textContent = '갱신 실패 · 아래는 이전 조회 결과입니다.';
    else {
      $('result-summary').textContent = '자격증 목록을 불러오지 못했습니다.';
      $('empty').hidden = false;
      $('empty').replaceChildren(element('div', '!'), element('h3', '연결을 확인해주세요.'), element('p', '새로고침 버튼으로 다시 시도할 수 있습니다. 아래 오류 상세를 확인해주세요.'));
    }
  } finally {
    $('reload').disabled = false;
    $('reload').textContent = '새로고침 ↻';
    $('cards').setAttribute('aria-busy', 'false');
  }
}

$('reload').addEventListener('click', load);
for (const id of ['search', 'category', 'field']) {
  $(id).addEventListener(id === 'search' ? 'input' : 'change', () => {visible = 8; render();});
}
$('more').addEventListener('click', () => {visible += 8; render();});

let selected = null;
let selectionVersion = 0;
let scheduleVersion = 0;
$('year').value = new Date().getFullYear();
$('close-info').addEventListener('click', () => $('info-dialog').close());
$('info-dialog').addEventListener('close', () => {selectionVersion++; scheduleVersion++;});
$('schedule-form').addEventListener('submit', event => {event.preventDefault(); loadSchedule();});

async function fetchInfo(path) {
  const response = await fetch(path, {cache: 'no-store'});
  const data = await response.json();
  if (!response.ok || !data.ok) {
    const error = new Error(data.error || '조회 실패');
    error.diagnostic = `HTTP ${data.http_status ?? '응답 없음'}\n${data.diagnostic || ''}`;
    throw error;
  }
  return data;
}

function showFailure(target, error, retry) {
  $(target).replaceChildren(element('p', error.message));
  if (retry) {
    const button = element('button', '다시 조회');
    button.type = 'button';
    button.addEventListener('click', retry);
    $(target).append(button);
  }
  if (error.diagnostic) {
    const details = element('details', '');
    details.append(element('summary', '오류 상세'), element('pre', error.diagnostic));
    $(target).append(details);
  }
}

async function openInfo(item) {
  selected = item;
  ++selectionVersion;
  $('info-title').textContent = item.jmfldnm;
  $('info-code').textContent = `${item.qualgbnm} · 종목코드 ${item.jmcd}`;
  $('details-content').replaceChildren(element('p', '상세정보를 불러오는 중…'));
  $('info-dialog').showModal();
  $('info-dialog').scrollTop = 0;
  loadSchedule();
  loadDetails();
}

async function loadDetails() {
  const item = selected;
  const version = selectionVersion;
  $('details-content').replaceChildren(element('p', '상세정보를 불러오는 중… 일시적 연결 오류는 자동으로 재시도합니다.'));
  try {
    const data = await fetchInfo(`/api/details?${new URLSearchParams({jmcd: item.jmcd})}`);
    if (version !== selectionVersion) return;
    $('details-content').replaceChildren();
    if (!data.items.length) $('details-content').append(element('p', '이 자격증에 대해 API에서 제공하는 관련 정보가 없습니다.'));
    for (const row of data.items) {
      const section = element('details', '', 'qualification-detail');
      section.open = row.infogb === '취득방법' || data.items.length === 1;
      const content = (row.contents || '').replace(/\r\n?/g, '\n').replace(/[\t ]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
      section.append(element('summary', row.infogb), element('div', content || '내용 미제공', 'detail-text'));
      $('details-content').append(section);
    }
  } catch (error) {
    if (version === selectionVersion) showFailure('details-content', error, loadDetails);
  }
}

function dateText(value) {
  return /^\d{8}$/.test(value || '') ? `${value.slice(0,4)}.${value.slice(4,6)}.${value.slice(6,8)}` : (value || '미제공');
}

function period(start, end) {
  if (!start && !end) return '미제공';
  if (start === end) return dateText(start);
  return `${dateText(start)} ~ ${dateText(end)}`;
}

async function loadSchedule() {
  if (!selected) return;
  const version = ++scheduleVersion;
  const selection = selectionVersion;
  const year = $('year').value;
  $('schedule-content').replaceChildren(element('p', `${year}년 일정을 불러오는 중…`));
  try {
    const query = new URLSearchParams({jmcd: selected.jmcd, category: selected.qualgbcd, year});
    const data = await fetchInfo(`/api/schedules?${query}`);
    if (version !== scheduleVersion || selection !== selectionVersion) return;
    $('schedule-content').replaceChildren(element('p', `${year}년 · 공고 일정 ${data.items.length}건`, 'subtle'));
    if (!data.items.length) $('schedule-content').append(element('p', '선택한 연도·종목에 대해 API에서 반환한 일정이 없습니다.'));
    for (const row of data.items) {
      const section = element('article', '', 'schedule-card');
      section.append(element('h4', row.description || `${row.implYy}년 ${row.implSeq}회`));
      const list = element('dl', '');
      for (const [label, value] of [
        ['필기 접수', period(row.docRegStartDt, row.docRegEndDt)],
        ['필기 시험', period(row.docExamStartDt, row.docExamEndDt)],
        ['필기 발표', dateText(row.docPassDt)],
        ['실기·면접 접수', period(row.pracRegStartDt, row.pracRegEndDt)],
        ['실기·면접 시험', period(row.pracExamStartDt, row.pracExamEndDt)],
        ['실기·면접 발표', dateText(row.pracPassDt)],
      ]) {
        const line = element('div', '');
        line.append(element('dt', label), element('dd', value));
        list.append(line);
      }
      section.append(list);
      $('schedule-content').append(section);
    }
  } catch (error) {
    if (version === scheduleVersion && selection === selectionVersion) showFailure('schedule-content', error, loadSchedule);
  }
}


  for (const [id, value] of [['mode-all','all'],['mode-personal','personal']]) {
    $(id).addEventListener('click', () => {
      mode=value; visible=8;
      for(const key of ['search','category','field']) $(key).value='';
      for(const [buttonId, buttonMode] of [['mode-all','all'],['mode-personal','personal']]) {
        $(buttonId).setAttribute('aria-pressed', String(mode===buttonMode));
        $(buttonId).classList.toggle('primary', mode===buttonMode);
      }
      if(items.length) render();
      else $('mode-description').textContent=mode==='all'?'프로필과 관계없이 API가 제공하는 모든 자격증을 표시합니다.':'프로필의 전공·목표 직무·관심 분야로 목록을 좁힙니다.';
    });
  }
  load();
};
