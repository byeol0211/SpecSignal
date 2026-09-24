const $ = (id) => document.getElementById(id);
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
  $('count').textContent = items.length.toLocaleString();
  $('result-summary').textContent = `전체 ${items.length.toLocaleString()}개 중 ${filtered.length.toLocaleString()}개 · ${Math.min(visible, filtered.length)}개 표시`;
  $('empty').hidden = filtered.length > 0;
  if (!filtered.length) {
    $('empty').replaceChildren(element('div', '⌕'), element('h3', '표시할 자격증이 없습니다.'), element('p', '검색어와 필터를 확인해주세요.'));
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

// 브라우저 미리보기와 데스크톱 앱이 같은 화면과 API를 사용한다.
function resetFilters() {
  $('search').value = '';
  $('category').value = '';
  $('field').value = '';
  visible = 8;
  if (items.length) render();
  $('main-content').scrollTop = 0;
}
$('certifications-nav').addEventListener('click', resetFilters);
$('brand-home').addEventListener('click', resetFilters);
$('explore').addEventListener('click', () => {$('main-content').scrollTop = 0; $('search').focus();});
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && !document.querySelector('dialog[open]')) {
    event.preventDefault();
    $('search').focus();
  }
});

let displayName = '';
function setProfileName(name) {
  displayName = name;
  $('profile-name').textContent = name || '나의 공간';
}
try {setProfileName(localStorage.getItem('specsignal.displayName') || '');} catch (_) { /* 저장 제한 환경에서는 기본 이름 사용 */ }
$('profile-open').addEventListener('click', () => {
  $('display-name').value = displayName;
  $('profile-error').hidden = true;
  $('profile-dialog').showModal();
  $('display-name').focus();
});
$('profile-close').addEventListener('click', () => $('profile-dialog').close());
$('profile-form').addEventListener('submit', async event => {
  event.preventDefault();
  const name = $('display-name').value.trim();
  try {
    if (window.pywebview?.api) await window.pywebview.api.save_profile(name);
    else localStorage.setItem('specsignal.displayName', name);
    setProfileName(name);
    $('profile-dialog').close();
  } catch (_) {
    $('profile-error').textContent = '프로필을 저장하지 못했습니다. 다시 시도해주세요.';
    $('profile-error').hidden = false;
  }
});
window.addEventListener('pywebviewready', async () => {
  enableResizeHandles();
  $('window-controls').hidden = false;
  $('preview-label').hidden = true;
  $('window-minimize').addEventListener('click', () => window.pywebview.api.minimize());
  $('window-maximize').addEventListener('click', () => window.pywebview.api.toggle_maximize());
  $('window-close').addEventListener('click', () => window.pywebview.api.close());
  try {setProfileName((await window.pywebview.api.get_profile()).name);} catch (_) { /* 기본 이름 유지 */ }
});

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

// 버튼 조작 없이 시작과 동시에 목록을 조회한다.
load();
