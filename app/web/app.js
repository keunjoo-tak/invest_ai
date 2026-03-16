const qs = (selector) => document.querySelector(selector);

const T = {
  ok: '정상',
  error: '오류',
  loading: '리포트를 생성하는 중입니다...',
  noSubs: '저장된 워치리스트가 없습니다. 오른쪽 상단의 버튼으로 종목을 저장해 보세요.',
  inputRequired: '티커 또는 종목명을 입력해 주세요.',
};

const SOURCE_LABELS = {
  memory_cache: '메모리 캐시',
  stale_memory_cache: '이전 캐시 복구',
  batch_snapshot: '배치 스냅샷',
  batch_build: '배치 생성',
  live_collection: '실시간 수집',
  live_check: '실시간 점검',
  derived_from_stock_decision: '종목 판단 기반',
};

const REPORT_TARGETS = {
  market: '#report-market',
  stock: '#report-stock',
  action: '#report-action',
  watch: '#report-watch',
};

const headlineBriefStore = new Map();

async function request(method, url, body) {
  const response = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = { raw: text };
  }
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}\n${JSON.stringify(data, null, 2)}`);
  }
  return data;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatError(err) {
  return err instanceof Error ? err.message : String(err);
}

function formatDate(value) {
  if (!value) return '정보 없음';
  try {
    return new Date(value).toLocaleString('ko-KR', { hour12: false });
  } catch {
    return String(value);
  }
}

function toneClassByScore(value) {
  const score = Number(value || 0);
  if (score >= 70) return 'report-tone-positive';
  if (score <= 45) return 'report-tone-negative';
  return 'report-tone-neutral';
}

function sourceLabel(code) {
  return SOURCE_LABELS[code] || code || '실시간 계산';
}

function mountReport(key, html) {
  const target = qs(REPORT_TARGETS[key]);
  if (target) {
    target.classList.remove('report-empty');
    target.innerHTML = html;
  }
}

function mountLoading(key) {
  mountReport(
    key,
    `<div class="report-shell"><div class="report-top"><div class="report-badge-row"><span class="report-badge">생성 중</span></div><h4 class="report-headline">${T.loading}</h4><p class="report-summary">외부 데이터와 내부 판단 로직을 결합해 리포트를 구성하고 있습니다.</p></div></div>`
  );
}

function mountError(key, err) {
  mountReport(
    key,
    `<div class="report-shell"><div class="report-top"><div class="report-badge-row"><span class="report-badge">오류</span></div><h4 class="report-headline">리포트 생성에 실패했습니다.</h4><p class="report-summary">${escapeHtml(formatError(err))}</p></div></div>`
  );
}

function renderStatus(status) {
  if (!status || Object.keys(status).length === 0) {
    return '';
  }
  const chips = [];
  if (status.response_source) {
    chips.push(`<span class="status-chip">응답 경로: ${escapeHtml(sourceLabel(status.response_source))}</span>`);
  }
  if (status.analysis_mode) {
    chips.push(`<span class="status-chip">분석 모드: ${escapeHtml(status.analysis_mode)}</span>`);
  }
  if (status.snapshot_ready) {
    chips.push('<span class="status-chip">사전 계산 완료</span>');
  }
  if (status.snapshot_generated_at_utc) {
    chips.push(`<span class="status-chip">스냅샷 생성: ${escapeHtml(formatDate(status.snapshot_generated_at_utc))}</span>`);
  }
  if (status.cache_expires_at_utc) {
    chips.push(`<span class="status-chip">유효 시각: ${escapeHtml(formatDate(status.cache_expires_at_utc))}</span>`);
  }
  const note = status.note ? `<p class="status-note">${escapeHtml(status.note)}</p>` : '';
  return `<div class="status-stack">${chips.join('')}${note}</div>`;
}

function renderSummaryGrid(items) {
  return `<div class="summary-grid">${items
    .map(
      (item) => `
      <article class="summary-kpi">
        <span>${escapeHtml(item.label)}</span>
        <strong class="${item.tone || ''}">${escapeHtml(item.value)}</strong>
      </article>`
    )
    .join('')}</div>`;
}

function renderScoreRows(items) {
  return `<div class="score-stack">${items
    .map((item) => {
      const value = Math.max(0, Math.min(100, Number(item.value || 0)));
      return `
        <div class="score-row">
          <div class="score-label"><span>${escapeHtml(item.label)}</span><strong>${value.toFixed(1)}</strong></div>
          <div class="score-track"><div class="score-fill" style="width:${value}%"></div></div>
        </div>`;
    })
    .join('')}</div>`;
}

function renderList(items, className = 'report-list') {
  if (!items || items.length === 0) {
    return '<p class="section-copy">표시할 항목이 없습니다.</p>';
  }
  return `<ul class="${className}">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
}

function renderMetricPairs(items) {
  return items
    .map(
      (item) => `
      <div class="metric-pair">
        <span>${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.value)}</strong>
      </div>`
    )
    .join('');
}

function renderSignalChips(items) {
  return `<div class="signal-chip-row">${items.map((item) => `<span class="signal-chip">${escapeHtml(item)}</span>`).join('')}</div>`;
}

function renderTimeline(items) {
  if (!items || items.length === 0) {
    return '<p class="section-copy">최근 이벤트가 없습니다.</p>';
  }
  return `<div class="timeline-grid">${items
    .map(
      (item) => `
      <article class="timeline-card">
        <div class="timeline-meta">
          <span class="timeline-chip">${escapeHtml(item.source || '문서')}</span>
          <span class="timeline-chip">${escapeHtml(item.event_type || '이벤트')}</span>
        </div>
        <h5>${escapeHtml(item.title || '')}</h5>
        <p>${escapeHtml(item.summary || '')}</p>
        <p class="timeline-date">${escapeHtml(formatDate(item.published_at))}</p>
      </article>`
    )
    .join('')}</div>`;
}

function renderPeerTable(items) {
  if (!items || items.length === 0) {
    return '<p class="section-copy">비교 가능한 섹터 peer 데이터가 없습니다.</p>';
  }
  return `
    <div class="peer-table-wrap">
      <table class="peer-table">
        <thead>
          <tr>
            <th>구분</th>
            <th>종목</th>
            <th>20일 수익률</th>
            <th>상대 거래량</th>
            <th>거래대금 Z</th>
          </tr>
        </thead>
        <tbody>
          ${items
            .map(
              (item) => `
              <tr>
                <td>${escapeHtml(item.role === 'leader' ? '대장주' : item.role === 'target' ? '입력 종목' : 'peer')}</td>
                <td>${escapeHtml(`${item.name || item.ticker} (${item.ticker})`)}</td>
                <td>${(Number(item.return_20d || 0) * 100).toFixed(1)}%</td>
                <td>${Number(item.rel_volume || 0).toFixed(2)}</td>
                <td>${Number(item.turnover_zscore || 0).toFixed(2)}</td>
              </tr>`
            )
            .join('')}
        </tbody>
      </table>
    </div>`;
}

function renderDisclosureCards(items) {
  if (!items || items.length === 0) {
    return '<p class="section-copy">즉시 반영할 수시공시 점수 데이터가 없습니다.</p>';
  }
  return `<div class="timeline-grid">${items
    .map(
      (item) => `
      <article class="timeline-card">
        <div class="timeline-meta">
          <span class="timeline-chip">${escapeHtml(item.event_label || '공시')}</span>
          <span class="timeline-chip">순효과 ${(Number(item.net_score || 0) * 100).toFixed(1)}</span>
        </div>
        <h5>${escapeHtml(item.title || '')}</h5>
        <p>호재 ${Number(item.bullish_score || 0).toFixed(2)} / 악재 ${Number(item.bearish_score || 0).toFixed(2)} / 중요도 ${Number(item.event_severity || 0).toFixed(2)}</p>
        <p>${escapeHtml(item.rationale || '')}</p>
      </article>`
    )
    .join('')}</div>`;
}

function renderEventPattern(info, features) {
  if (!info || Object.keys(info).length === 0) {
    return '<p class="section-copy">이벤트 패턴 매칭 데이터가 없습니다.</p>';
  }
  const caution = !!info.volatility_caution_mode;
  return `<div>
    ${renderMetricPairs([
      { label: '현재 이벤트 유형', value: String(info.current_event_type || '정보 없음') },
      { label: '유사 이벤트 표본', value: String(info.sample_size || 0) },
      { label: '평균 1일 반응', value: `${(Number(info.avg_return_1d || 0) * 100).toFixed(2)}%` },
      { label: '평균 5일 반응', value: `${(Number(info.avg_return_5d || 0) * 100).toFixed(2)}%` },
      { label: '패턴 신뢰도', value: Number(features.event_pattern_confidence || 0).toFixed(2) },
      { label: '변동성 주의 점수', value: Number(features.event_volatility_score || 0).toFixed(2) },
    ])}
    <p class="section-copy">${caution ? '이벤트 당일 또는 직후로 판단되어 일반 예측보다 변동성 관리와 장중 확인을 우선합니다.' : '과거 유사 이벤트 패턴을 참고하되 일반 분석 로직을 함께 사용합니다.'}</p>
  </div>`;
}

function renderOvernightTransmission(info, features) {
  if (!info || !info.applied) {
    return '<p class="section-copy">장전 조건이 아니거나 미국 전일 종가가 확정되지 않아 야간 전이 계수를 적용하지 않았습니다.</p>';
  }
  return `<div>${renderMetricPairs([
    { label: '참조 지수', value: `${info.reference_label || info.reference_index} (${info.latest_us_trade_date || '-'})` },
    { label: '미국 전일 수익률', value: `${(Number(info.latest_us_return || 0) * 100).toFixed(2)}%` },
    { label: '전이 베타 / 상관', value: `${Number(features.overnight_us_beta || 0).toFixed(2)} / ${Number(features.overnight_us_correlation || 0).toFixed(2)}` },
    { label: '예상 갭 영향', value: `${(Number(features.overnight_us_signal || 0) * 100).toFixed(2)}%p` },
  ])}</div>`;
}

function reportShell({ badges = [], title, summary, statusHtml = '', body }) {
  return `
    <article class="report-shell">
      <header class="report-top">
        <div class="report-badge-row">${badges.map((item) => `<span class="report-badge">${escapeHtml(item)}</span>`).join('')}</div>
        <h4 class="report-headline">${escapeHtml(title)}</h4>
        <p class="report-summary">${escapeHtml(summary)}</p>
        ${statusHtml}
      </header>
      <div class="report-grid">${body}</div>
    </article>`;
}

function average(values) {
  if (!values || values.length === 0) return 0;
  return values.reduce((sum, value) => sum + Number(value || 0), 0) / values.length;
}

function clampValue(value, min = 0, max = 100) {
  return Math.max(min, Math.min(max, Number(value || 0)));
}

function formatInstrumentLabel(row) {
  const ticker = String(row?.ticker || '').trim();
  const name = String(row?.name || row?.instrument_name || ticker || '').trim();
  if (ticker && name && name !== ticker) {
    return `${name}(${ticker})`;
  }
  return ticker || name || '-';
}

function getRiskFlagCodes(signal) {
  return signal?.risk_flag_codes || signal?.risk_flags || [];
}

function formatKstDateTime(value) {
  if (!value) return '\uc815\ubcf4 \uc5c6\uc74c';
  try {
    return new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(new Date(value));
  } catch {
    return String(value);
  }
}

function marketSessionLabel(value) {
  if (!value) return '\uae30\uc900 \uc2dc\uc810 \uc815\ubcf4 \uc5c6\uc74c';
  const dt = new Date(value);
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Seoul',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(dt);
  const hour = Number(parts.find((item) => item.type === 'hour')?.value || 0);
  const minute = Number(parts.find((item) => item.type === 'minute')?.value || 0);
  const minuteOfDay = hour * 60 + minute;
  if (minuteOfDay < 9 * 60) return '\uc7a5\uc804';
  if (minuteOfDay < 15 * 60 + 30) return '\uc7a5\uc911';
  return '\uc7a5\ud6c4';
}

function freshnessLabel(value) {
  if (!value) return '\uc2e0\uc120\ub3c4 \uc815\ubcf4 \uc5c6\uc74c';
  const diffMin = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (diffMin < 60) return `${diffMin}\ubd84 \uc804 \uc0dd\uc131`;
  if (diffMin < 24 * 60) return `${Math.round(diffMin / 60)}\uc2dc\uac04 \uc804 \uc0dd\uc131`;
  return `${Math.round(diffMin / (24 * 60))}\uc77c \uc804 \uc0dd\uc131`;
}

function regimeConfidenceLabel(score, risingRatio) {
  const absScore = Math.abs(Number(score || 0));
  if (absScore >= 6 || risingRatio >= 0.8 || risingRatio <= 0.2) return 'High';
  if (absScore >= 3) return 'Medium';
  return 'Low';
}

function regimeDirectionLabel(score) {
  const value = Number(score || 0);
  if (value >= 4) return '\uc704\ud5d8\uc120\ud638 \uac15\ud654';
  if (value >= 1.5) return '\uc704\ud5d8\uc120\ud638 \uae30\uc6b8\uae30';
  if (value <= -4) return '\uc704\ud5d8\ud68c\ud53c \uac15\ud654';
  if (value <= -1.5) return '\uc704\ud5d8\ud68c\ud53c \uae30\uc6b8\uae30';
  return '\uc911\ub9bd \uc720\uc9c0';
}

function macroDriverDirection(row) {
  const surprise = Number(row?.surprise_std || 0);
  if (surprise >= 0.4) return '\uc0c1\ubc29';
  if (surprise <= -0.4) return '\ud558\ubc29';
  return '\uc911\ub9bd';
}

function macroDriverStrength(row) {
  const surprise = Math.abs(Number(row?.surprise_std || 0));
  if (surprise >= 1.2) return 'High';
  if (surprise >= 0.5) return 'Medium';
  return 'Low';
}

function sectorReason(row, tone) {
  const ret = Number(row?.ret20_pct || 0).toFixed(1);
  const vol = Number(row?.vol20_pct || 0).toFixed(1);
  if (tone === 'strong') {
    return `20\uc77c \uc0c1\ub300 \uac15\ub3c4 ${ret}%\uc640 \uc139\ud130 \uad11\ubc94\uc704 \ud655\uc0b0\uc774 \ud655\uc778\ub418\ub294 \uad6c\uac04\uc785\ub2c8\ub2e4. \ubcc0\ub3d9\uc131 \ucc38\uace0\uce58\ub294 ${vol}% \uc218\uc900\uc785\ub2c8\ub2e4.`;
  }
  return `20\uc77c \uc0c1\ub300 \uac15\ub3c4 ${ret}%\ub85c \ub4b7\ucc98\uc9c0\uace0 \uc788\uc73c\uba70 \ubcc0\ub3d9\uc131 \ucc38\uace0\uce58\ub294 ${vol}% \uc218\uc900\uc785\ub2c8\ub2e4.`;
}


function sectorLogicBadges(sector) {
  const mapping = {
    '반도체': ['수출/환율 민감형', '글로벌 수요형'],
    '인터넷': ['금리 민감형', '성장주 민감형'],
    '2차전지·화학': ['정책 수혜형', '원자재 민감형'],
    '바이오': ['정책/규제 민감형', '성장주 민감형'],
    '자동차': ['수출/환율 민감형', '경기 민감형'],
    '조선': ['글로벌 사이클형', '후행 수주형'],
    '철강': ['원자재 민감형', '경기 민감형'],
    '건설': ['금리 민감형', '정책 수혜형'],
    '전력·에너지': ['원자재 민감형', '방어형'],
    '증권': ['금리 민감형', '시장 회전율 민감형'],
  };
  return mapping[String(sector || '')] || ['시장 민감형'];
}

function deriveMarketRegimeContext(data) {
  const macroRows = data.global_macro_pressure || [];
  const strong = data.strong_sectors || [];
  const weak = data.weak_sectors || [];
  const reps = data.representative_symbols || [];
  const positiveReps = reps.filter((row) => Number(row.ret20_pct || 0) > 0).length;
  const risingRatio = reps.length ? positiveReps / reps.length : 0;
  const avgRet = average(reps.map((row) => Number(row.ret20_pct || 0)));
  const avgVol = average(reps.map((row) => Number(row.vol20_pct || 0)));
  const macroScores = macroRows.map((row) => Number(row.surprise_std || 0));
  const positiveMacro = macroRows.filter((row) => Number(row.surprise_std || 0) > 0).sort((a, b) => Math.abs(Number(b.surprise_std || 0)) - Math.abs(Number(a.surprise_std || 0)));
  const negativeMacro = macroRows.filter((row) => Number(row.surprise_std || 0) <= 0).sort((a, b) => Math.abs(Number(b.surprise_std || 0)) - Math.abs(Number(a.surprise_std || 0)));
  const breadthDelta = strong.length - weak.length;
  const decomposition = {
    total: clampValue(50 + Number(data.regime_score || 0) * 6),
    priceTrend: clampValue(50 + avgRet * 3.2 + breadthDelta * 4),
    volatility: clampValue(100 - avgVol * 4.5),
    liquidityRate: clampValue(55 - average(macroScores) * 10),
    policySupport: clampValue(48 + (data.strategy_hints?.length || 0) * 3),
    globalRisk: clampValue(50 + average(macroScores.map((value) => Math.abs(value))) * 10),
    breadth: clampValue(risingRatio * 100),
  };
  const positiveDrivers = [
    ...strong.slice(0, 3).map((row) => ({
      title: `${row.sector} \uc8fc\ub3c4`,
      direction: '\uc0c1\ubc29',
      strength: Number(row.score || 0).toFixed(1),
      horizon: '\uc2a4\uc719',
      note: sectorReason(row, 'strong'),
    })),
    ...positiveMacro.slice(0, 2).map((row) => ({
      title: String(row.indicator_name || row.country || '\uac70\uc2dc \uc9c0\ud45c'),
      direction: macroDriverDirection(row),
      strength: macroDriverStrength(row),
      horizon: '\ub2e8\uae30',
      note: `\uc2e4\uc81c\uac12 ${row.actual ?? '-'} / \uc11c\ud504\ub77c\uc774\uc988 ${row.surprise_std ?? '-'}`,
    })),
  ].slice(0, 5);
  const negativeDrivers = [
    ...weak.slice(0, 3).map((row) => ({
      title: `${row.sector} \uc81c\uc57d`,
      direction: '\ud558\ubc29',
      strength: Number(row.score || 0).toFixed(1),
      horizon: '\uc2a4\uc719',
      note: sectorReason(row, 'weak'),
    })),
    ...negativeMacro.slice(0, 2).map((row) => ({
      title: String(row.indicator_name || row.country || '\uac70\uc2dc \uc9c0\ud45c'),
      direction: macroDriverDirection(row),
      strength: macroDriverStrength(row),
      horizon: '\ub2e8\uae30',
      note: `\uc2e4\uc81c\uac12 ${row.actual ?? '-'} / \uc11c\ud504\ub77c\uc774\uc988 ${row.surprise_std ?? '-'}`,
    })),
  ].slice(0, 5);
  const sensitiveMacro = [...macroRows]
    .sort((a, b) => Math.abs(Number(b.surprise_std || 0)) - Math.abs(Number(a.surprise_std || 0)))
    .slice(0, 3)
    .map((row) => `${row.indicator_name || row.country || '\uac70\uc2dc \uc9c0\ud45c'}: \uc11c\ud504\ub77c\uc774\uc988 ${row.surprise_std ?? '-'}`);

  const regime = String(data.regime || '');
  const actionGuide = regime === '\uc704\ud5d8\uc120\ud638'
    ? {
        favorable: '\ucd94\uc138 \ucd94\uc885 + \uc120\ub3c4 \uc139\ud130 \uc120\ubcc4 \uc811\uadfc',
        avoid: '\uc9c0\uc218 \ubb34\ucc28\ubcc4 \ucd94\uaca9\ub9e4\uc218',
        stockType: '\ub300\ud615 \uc131\uc7a5\uc8fc / \uc815\ucc45 \uc218\ud61c\uc8fc / \uc2e4\uc801 \uac00\uc2dc\uc131 \uc885\ubaa9',
        cashHint: '\ud604\uae08 \ube44\uc911\uc740 \uc911\ub9bd \uc774\ud558\ub85c \uc6b4\uc601\ud558\ub418, \ub2e8\uae30 \uacfc\uc5f4 \uc139\ud130\ub294 \ubd84\ud560 \uc9c4\uc785\uc774 \uc720\ub9ac\ud569\ub2c8\ub2e4.',
      }
    : regime === '\uc704\ud5d8\ud68c\ud53c'
      ? {
          favorable: '\uad00\ub9dd / \ubc29\uc5b4\ud615 \ud3ec\uc9c0\uc154\ub2dd / \ubcf4\uc720 \uad00\ub9ac \uc6b0\uc120',
          avoid: '\ub808\ubc84\ub9ac\uc9c0 \ucd94\uaca9\uacfc \uc800\ud488\uc9c8 \ud14c\ub9c8\uc8fc \uc811\uadfc',
          stockType: '\ubc30\ub2f9\uc8fc / \ud604\uae08\ud750\ub984 \uc548\uc815\uc8fc / \ubc29\uc5b4\uc8fc',
          cashHint: '\ud604\uae08 \ube44\uc911 \ud655\ub300\uac00 \uc720\ud6a8\ud558\uba70, \uc2e0\uaddc \uc9c4\uc785\ubcf4\ub2e4 \ubb34\ud6a8\ud654 \uc870\uac74 \uad00\ub9ac\uac00 \uc911\uc694\ud569\ub2c8\ub2e4.',
        }
      : {
          favorable: '\ub20c\ub9bc\ubaa9 \uc120\ubcc4 \uc811\uadfc / \uc2dc\uc7a5 \ub300\ube44 \uc0c1\ub300 \uac15\ub3c4 \uc139\ud130 \uc704\uc8fc',
          avoid: '\uc9c0\uc218 \ucd94\uaca9 \ub9e4\ub9e4',
          stockType: '\uc2e4\uc801 \uac00\uc2dc\uc131 \uc885\ubaa9 / \uc120\ub3c4 \uc139\ud130 \uc8fc\ub3c4\uc8fc',
          cashHint: '\ubd84\ud560 \uc9c4\uc785 \uad8c\uace0 \uad6c\uac04\uc73c\ub85c, \uc2e0\uaddc \uc9c4\uc785\ubcf4\ub2e4 \uc9c4\uc785 \uadfc\uac70 \ud655\uc778\uc774 \uc911\uc694\ud569\ub2c8\ub2e4.',
        };

  return {
    risingRatio,
    avgRet,
    avgVol,
    confidenceLabel: regimeConfidenceLabel(data.regime_score, risingRatio),
    directionLabel: regimeDirectionLabel(data.regime_score),
    decomposition,
    positiveDrivers,
    negativeDrivers,
    sensitiveMacro,
    actionGuide,
    invalidation: [
      '\uae08\ub9ac \uc11c\ud504\ub77c\uc774\uc988 \ud655\ub300',
      '\ud658\uc728 \uae09\ub4f1 \ub610\ub294 \ubcc0\ub3d9\uc131 \ud655\ub300',
      '\uc815\ucc45 \uae30\ub300 \ud6c4\ud1f4 \ub610\ub294 \uacf5\uc2dc \uc2e4\ub9dd',
    ],
    scheduledSignals: sensitiveMacro.length ? sensitiveMacro : ['\uc8fc\uc694 \uac70\uc2dc \uc9c0\ud45c \uc7ac\ud655\uc778 \ud544\uc694'],
    limitations: [
      '\ud604\uc7ac breadth\ub294 \ub300\ud45c \uc885\ubaa9 \uad70 \uae30\uc900 \ud504\ub85d\uc2dc\uc785\ub2c8\ub2e4.',
      '\uc139\ud130 \ud310\ub2e8\uc740 \uc804\uccb4 \uc720\ub2c8\ubc84\uc2a4\uac00 \uc544\ub2c8\ub77c \ud604\uc7ac \uc218\uc9d1 \uac00\ub2a5\ud55c \ub300\ud45c \uc885\ubaa9 \uae30\uc900\uc73c\ub85c \uacc4\uc0b0\ub429\ub2c8\ub2e4.',
    ],
  };
}

function renderCollapsibleSection(title, subtitle, body, open = false) {
  return `
    <details class="report-disclosure" ${open ? 'open' : ''}>
      <summary>
        <div>
          <strong>${escapeHtml(title)}</strong>
          ${subtitle ? `<span>${escapeHtml(subtitle)}</span>` : ''}
        </div>
        <b class="report-disclosure-arrow">+</b>
      </summary>
      <div class="report-disclosure-body">${body}</div>
    </details>`;
}

function renderDriverGrid(items) {
  if (!items || items.length === 0) {
    return '<p class="section-copy">\ud45c\uc2dc\ud560 \ud575\uc2ec \uc6d0\uc778\uc774 \uc5c6\uc2b5\ub2c8\ub2e4.</p>';
  }
  return `<div class="driver-grid">${items.map((item) => `
    <article class="timeline-card">
      <div class="timeline-meta">
        <span class="timeline-chip">${escapeHtml(item.direction)}</span>
        <span class="timeline-chip">\uac15\ub3c4 ${escapeHtml(item.strength)}</span>
        <span class="timeline-chip">${escapeHtml(item.horizon)}</span>
      </div>
      <h5>${escapeHtml(item.title)}</h5>
      <p>${escapeHtml(item.note)}</p>
    </article>`).join('')}</div>`;
}

function renderSectorInsightGrid(items, tone) {
  if (!items || items.length === 0) {
    return '<p class="section-copy">\ud45c\uc2dc\ud560 \uc139\ud130 \ub370\uc774\ud130\uac00 \uc5c6\uc2b5\ub2c8\ub2e4.</p>';
  }
  return `<div class="driver-grid">${items.map((row) => `
    <article class="timeline-card">
      <div class="timeline-meta">
        <span class="timeline-chip">${escapeHtml(row.sector)}</span>
        <span class="timeline-chip">\uc810\uc218 ${Number(row.score || 0).toFixed(1)}</span>
      </div>
      <h5>${escapeHtml(tone === 'strong' ? '\uac15\uc138 \uc139\ud130' : '\uc57d\uc138 \uc139\ud130')}</h5>
      <p>${escapeHtml(sectorReason(row, tone))}</p>
    </article>`).join('')}</div>`;
}

function renderHeadlineImpactGrid(items) {
  if (!items || items.length === 0) {
    return '<p class="section-copy">최근 5일 헤드라인 배치 데이터가 아직 없습니다.</p>';
  }
  return `<div class="driver-grid">${items.map((item, index) => {
    const detailId = `headline-brief-${index}-${String(item.section_key || 'section').replace(/[^a-z0-9_-]/gi, '')}`;
    headlineBriefStore.set(detailId, item);
    return `
    <article class="timeline-card">
      <div class="timeline-meta">
        <span class="timeline-chip">${escapeHtml(item.section_label || item.section_key || '-')}</span>
        <span class="timeline-chip">${escapeHtml(item.impact_direction || '-')}</span>
        <span class="timeline-chip">기사 ${Number(item.headline_count || 0)}건</span>
      </div>
      <h5>${escapeHtml(item.focus || '시장 영향')}</h5>
      <p>${escapeHtml(item.market_impact || '')}</p>
      <p class="data-footnote">주요 헤드라인: ${escapeHtml((item.top_headlines || []).slice(0, 3).join(' / ') || '-')}</p>
      <button class="btn tertiary" type="button" data-headline-brief-id="${escapeHtml(detailId)}">상세 보기</button>
    </article>`;
  }).join('')}</div>`;
}

function renderHeadlineBriefDetail(item) {
  const articles = item?.top_articles || [];
  return `
    <div class="report-section">
      <h4>${escapeHtml(item.section_label || item.section_key || '헤드라인')}</h4>
      <div>${renderMetricPairs([
        { label: '기사 수', value: `${Number(item.headline_count || 0)}건` },
        { label: '영향 방향', value: item.impact_direction || '-' },
        { label: '영향 초점', value: item.focus || '-' },
        { label: '최신 시각', value: formatKstDateTime(item.latest_published_at_utc) },
      ])}</div>
      <p class="section-copy" style="margin-top:14px;">${escapeHtml(item.market_impact || '')}</p>
    </div>
    <div class="report-section" style="margin-top:16px;">
      <h4>통합 요약</h4>
      ${renderList((item.summary_points || []).map((row) => row))}
    </div>
    <div class="report-section" style="margin-top:16px;">
      <h4>원문 기사</h4>
      <div class="timeline-list">${articles.map((article) => `
        <article class="timeline-card">
          <div class="timeline-meta">
            <span class="timeline-chip">${escapeHtml(item.section_label || '-')}</span>
            <span class="timeline-chip">${escapeHtml(formatKstDateTime(article.published_at_utc))}</span>
          </div>
          <h5>${escapeHtml(article.title || '')}</h5>
          <p>${escapeHtml(article.summary || '')}</p>
          <a class="btn tertiary" href="${escapeHtml(article.url || '#')}" target="_blank" rel="noreferrer">원문 열기</a>
        </article>`).join('')}</div>
    </div>`;
}

function marketSummaryText(data, context) {
  const leader = data.strong_sectors?.[0]?.sector || '\uac15\uc138 \uc139\ud130';
  if (data.regime === '\uc704\ud5d8\uc120\ud638') {
    return `\ud604\uc7ac \uc2dc\uc7a5\uc740 \uc704\ud5d8\uc120\ud638 \uad6d\uba74\uc785\ub2c8\ub2e4. ${leader} \uc911\uc2ec\uc758 \uc120\ubcc4 \uc811\uadfc\uc774 \uc720\ub9ac\ud558\uba70 \ud655\uc2e0\ub3c4\ub294 ${context.confidenceLabel}\uc785\ub2c8\ub2e4.`;
  }
  if (data.regime === '\uc704\ud5d8\ud68c\ud53c') {
    return `\ud604\uc7ac \uc2dc\uc7a5\uc740 \uc704\ud5d8\ud68c\ud53c \uad6d\uba74\uc785\ub2c8\ub2e4. \uacf5\uaca9\uc801 \uc2e0\uaddc \uc9c4\uc785\ubcf4\ub2e4 \ubc29\uc5b4 \uc6b4\uc601\uc774 \uc6b0\uc120\uc785\ub2c8\ub2e4.`;
  }
  return `\ud604\uc7ac \uc2dc\uc7a5\uc740 \uc911\ub9bd \uad6c\uac04\uc785\ub2c8\ub2e4. ${leader} \ub4f1 \uc0c1\ub300 \uac15\ub3c4\uac00 \ub192\uc740 \uc601\uc5ed\ub9cc \uc120\ubcc4\uc801\uc73c\ub85c \ubcf4\ub294 \uc811\uadfc\uc774 \uc801\uc808\ud569\ub2c8\ub2e4.`;
}

function renderMarketReport(data) {
  const macroRows = data.global_macro_pressure || [];
  const strong = data.strong_sectors || [];
  const weak = data.weak_sectors || [];
  const reps = data.representative_symbols || [];
  const context = deriveMarketRegimeContext(data);
  const summary = marketSummaryText(data, context);
  const topConclusion = renderCollapsibleSection(
    '\uc0c1\ub2e8 \ud575\uc2ec \uacb0\ub860',
    '\ud604\uc7ac \uc2dc\uc7a5 \uccb4\uc81c\uc640 \ud574\uc11d \uae30\uc900 \uc2dc\uc810',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\uc2dc\uc7a5 \ucd5c\uc885 \uccb4\uc81c</h4>
        <div>${renderMetricPairs([
          { label: '\uccb4\uc81c', value: String(data.regime || '-') },
          { label: '\ud55c \uc904 \uacb0\ub860', value: summary },
          { label: '\uccb4\uc81c \uae30\uc6b8\uae30', value: context.directionLabel },
          { label: '\ud604\uc7ac \ud655\uc2e0\ub3c4', value: context.confidenceLabel },
        ])}</div>
      </section>
      <section class="report-section">
        <h4>\ud574\uc11d \uae30\uc900 \uc2dc\uc810</h4>
        <div>${renderMetricPairs([
          { label: '\uae30\uc900\uc77c', value: String(data.as_of_date || '-') },
          { label: '\ub370\uc774\ud130 \ubc18\uc601 \uc2dc\uac01', value: formatKstDateTime(data.generated_at_utc) },
          { label: '\uc2dc\uc7a5 \uad6c\uac04', value: marketSessionLabel(data.generated_at_utc) },
          { label: '\uc751\ub2f5 \uacbd\ub85c', value: sourceLabel(data.pipeline_status?.response_source) },
        ])}</div>
      </section>
    </div>`,
    true
  );

  const decompositionSection = renderCollapsibleSection(
    '\uc2dc\uc7a5 \uccb4\uc81c \ubd84\ud574',
    '\uac00\uaca9, \ubcc0\ub3d9\uc131, breadth, \uac70\uc2dc \uc555\ub825 \ud504\ub85d\uc2dc',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\uccb4\uc81c \uc810\uc218 \ubd84\ud574</h4>
        ${renderScoreRows([
          { label: '\uc885\ud569 \uccb4\uc81c', value: context.decomposition.total },
          { label: '\uac00\uaca9/\ucd94\uc138', value: context.decomposition.priceTrend },
          { label: '\ubcc0\ub3d9\uc131', value: context.decomposition.volatility },
          { label: '\uc720\ub3d9\uc131/\uae08\ub9ac \uc555\ub825', value: context.decomposition.liquidityRate },
          { label: '\uc815\ucc45 \uc6b0\ud638\ub3c4', value: context.decomposition.policySupport },
          { label: '\uae00\ub85c\ubc8c \ub9ac\uc2a4\ud06c', value: context.decomposition.globalRisk },
          { label: '\uc2dc\uc7a5 breadth', value: context.decomposition.breadth },
        ])}
      </section>
      <section class="report-section">
        <h4>breadth \uc694\uc57d</h4>
        <div>${renderMetricPairs([
          { label: '\uc0c1\uc2b9 \ub300\ud45c \uc885\ubaa9 \ube44\uc911', value: `${(context.risingRatio * 100).toFixed(1)}%` },
          { label: '\uac15\uc138 / \uc57d\uc138 \uc139\ud130', value: `${strong.length} / ${weak.length}` },
          { label: '\ub300\ud45c \uc885\ubaa9 \ud3c9\uade0 20\uc77c \uc218\uc775\ub960', value: `${context.avgRet.toFixed(2)}%` },
          { label: '\ub300\ud45c \uc885\ubaa9 \ud3c9\uade0 \ubcc0\ub3d9\uc131', value: `${context.avgVol.toFixed(2)}%` },
        ])}</div>
      </section>
    </div>`,
    true
  );

  const driversSection = renderCollapsibleSection(
    '\ud604\uc7ac \uc2dc\uc7a5\uc744 \uc6c0\uc9c1\uc774\ub294 \ud575\uc2ec \uc6d0\uc778 Top 5',
    '\uc0c1\uc2b9 \ub3d9\uc778, \uc81c\uc57d \ub3d9\uc778, \ubbfc\uac10 \uac70\uc2dc \ubcc0\uc218',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\ud575\uc2ec \uc0c1\uc2b9 \ub3d9\uc778</h4>
        ${renderDriverGrid(context.positiveDrivers)}
      </section>
      <section class="report-section">
        <h4>\ud575\uc2ec \ud558\ub77d/\uc81c\uc57d \ub3d9\uc778</h4>
        ${renderDriverGrid(context.negativeDrivers)}
      </section>
      <section class="report-section">
        <h4>\uac00\uc7a5 \ubbfc\uac10\ud55c \uac70\uc2dc \ubcc0\uc218 3\uac1c</h4>
        ${renderList(context.sensitiveMacro)}
      </section>
      <section class="report-section">
        <h4>\ucd5c\uadfc \uccb4\uc81c \ud574\uc11d \ud575\uc2ec</h4>
        ${renderList((data.strategy_hints || []).slice(0, 5))}
      </section>
    </div>`,
    true
  );

  const headlineSection = renderCollapsibleSection(
    '최근 5일 섹션별 헤드라인 영향',
    '정치, 경제, IT/과학, 세계 헤드라인을 시장 영향 관점으로 통합',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>섹션별 영향 요약</h4>
        ${renderHeadlineImpactGrid(data.headline_news_briefs || [])}
      </section>
      <section class="report-section">
        <h4>헤드라인 통합 해석</h4>
        ${renderList((data.headline_news_briefs || []).slice(0, 6).map((item) => `${item.section_label}: ${item.market_impact}`))}
      </section>
    </div>`,
    true
  );

  const sectorsSection = renderCollapsibleSection(
    '\uc139\ud130 \ud310\ub2e8',
    '\uac15\uc138/\uc57d\uc138 \uc139\ud130\uc640 \ub300\ud45c \uc885\ubaa9 \uadfc\uac70',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\uac15\uc138 \uc139\ud130 Top N</h4>
        ${renderSectorInsightGrid(strong, 'strong')}
      </section>
      <section class="report-section">
        <h4>\uc57d\uc138 \uc139\ud130 Bottom N</h4>
        ${renderSectorInsightGrid(weak, 'weak')}
      </section>
      <section class="report-section">
        <h4>\uc139\ud130 \ubcc4 \uacbd\uacc4 \ud3ec\uc778\ud2b8</h4>
        ${renderList([
          strong[0] ? `${strong[0].sector}: \uac15\ud558\uc9c0\ub9cc \ub2e8\uae30 \uacfc\uc5f4 \uc5ec\ubd80\ub97c \ud655\uc778\ud560 \ud544\uc694\uac00 \uc788\uc2b5\ub2c8\ub2e4.` : '\uacfc\uc5f4 \uac10\uc2dc \uc139\ud130 \uc815\ubcf4 \uc5c6\uc74c',
          weak[0] ? `${weak[0].sector}: \uc57d\ud558\uc9c0\ub9cc \uc815\ucc45/\uc2e4\uc801 \ucd09\ub9e4\uc5d0 \ub530\ub77c \ubc18\ub4f1 \uac00\ub2a5\uc131\uc744 \ubcf4\uc544\uc57c \ud569\ub2c8\ub2e4.` : '\ubc18\ub4f1 \ud6c4\ubcf4 \uc139\ud130 \uc815\ubcf4 \uc5c6\uc74c',
        ])}
      </section>
      <section class="report-section">
        <h4>\ub300\ud45c \uc885\ubaa9 \uadfc\uac70</h4>
        ${renderList(reps.map((row) => `${formatInstrumentLabel(row)}: 20\uc77c \uc218\uc775\ub960 ${Number(row.ret20_pct || 0).toFixed(2)}%, \ubcc0\ub3d9\uc131 ${Number(row.vol20_pct || 0).toFixed(2)}%`))}
      </section>
    </div>`,
    true
  );

  const actionSection = renderCollapsibleSection(
    '\ud22c\uc790\uc790 \ud589\ub3d9 \uc5f0\uacb0',
    '\uc9c0\uae08 \uc720\ub9ac\ud55c \uc811\uadfc, \ud53c\ud574\uc57c \ud560 \uc811\uadfc, \uae30\uac04\ubcc4 \ud78c\ud2b8',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\uc9c0\uae08 \uc720\ub9ac\ud55c \uc811\uadfc</h4>
        <p class="section-copy">${escapeHtml(context.actionGuide.favorable)}</p>
        <h4 style="margin-top:14px;">\ud53c\ud574\uc57c \ud560 \uc811\uadfc</h4>
        <p class="section-copy">${escapeHtml(context.actionGuide.avoid)}</p>
      </section>
      <section class="report-section">
        <h4>\uc801\ud569 \uc885\ubaa9 \uc720\ud615</h4>
        <p class="section-copy">${escapeHtml(context.actionGuide.stockType)}</p>
        <h4 style="margin-top:14px;">\ud3ec\uc9c0\uc158 \uc6b4\uc601 \ud78c\ud2b8</h4>
        <p class="section-copy">${escapeHtml(context.actionGuide.cashHint)}</p>
      </section>
      <section class="report-section">
        <h4>\ud22c\uc790 \uae30\uac04\ubcc4 \uc804\ub7b5 \ud78c\ud2b8</h4>
        ${renderList([
          '\ub2e8\uae30: \uc815\ucc45/\uac70\uc2dc \ud45c\ubcf8 \ubc1c\ud45c \uc804\ud6c4 \ubcc0\ub3d9\uc131\uc744 \uc6b0\uc120 \uad00\ub9ac\ud569\ub2c8\ub2e4.',
          '\uc2a4\uc719: \uac15\uc138 \uc139\ud130 \uc8fc\ub3c4\uc8fc \uc911\uc2ec \ubd84\ud560 \uc811\uadfc\uc774 \uc801\ud569\ud569\ub2c8\ub2e4.',
          '\uc911\uae30: \uc2e4\uc801 \uac00\uc2dc\uc131\uacfc \uc815\ucc45 \uc9c0\uc18d\uc131\uc744 \ud568\uaed8 \ubcf4\ub294 \uc811\uadfc\uc774 \ud544\uc694\ud569\ub2c8\ub2e4.',
        ])}
      </section>
    </div>`,
    false
  );

  const invalidationSection = renderCollapsibleSection(
    '\ubc18\uc99d \uc870\uac74',
    '\ud604\uc7ac \uccb4\uc81c \ud310\ub2e8\uc758 \ubb34\ud6a8\ud654 \uc870\uac74\uacfc \uc804\ud658 \uc2e0\ud638',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\ubb34\ud6a8\ud654 \uc870\uac74</h4>
        ${renderList(context.invalidation)}
      </section>
      <section class="report-section">
        <h4>\uc8fc\uc758\ud574\uc57c \ud560 \uac70\uc2dc \uc7ac\ud655\uc778 \ud56d\ubaa9</h4>
        ${renderList(context.scheduledSignals)}
      </section>
      <section class="report-section">
        <h4>\uccb4\uc81c \uc804\ud658 \uac00\ub2a5\uc131 \uc2e0\ud638</h4>
        ${renderList([
          '\uac15\uc138 \uc139\ud130 \uc218\uac00 \uc904\uace0 \uc57d\uc138 \uc139\ud130\uac00 \ub3d9\uc2dc \ud655\ub300\ub418\ub294\uc9c0 \ud655\uc778\ud569\ub2c8\ub2e4.',
          '\uc11c\ud504\ub77c\uc774\uc988 \ud06c\uae30\uac00 \ud070 \uac70\uc2dc \uc9c0\ud45c\uac00 \uc5f0\uc18d\ub418\uba74 \uccb4\uc81c \uc810\uc218 \uc804\ud658 \uc2e0\ud638\ub85c \ubd05\ub2c8\ub2e4.',
          '\ub300\ud45c \uc885\ubaa9 \uc0c1\uc2b9 \ube44\uc911\uc774 \uae09\uac10\ud558\uba74 breadth \uc57d\ud654\ub85c \ud574\uc11d\ud569\ub2c8\ub2e4.',
        ])}
      </section>
    </div>`,
    false
  );

  const trustSection = renderCollapsibleSection(
    '\uc2e0\ub8b0\ub3c4 \ubc0f \ub370\uc774\ud130 \uc124\uba85',
    '\ud65c\uc6a9 \uc18c\uc2a4, \uc751\ub2f5 \uacbd\ub85c, \uc2e0\uc120\ub3c4, \ud55c\uacc4',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\ub370\uc774\ud130 \ubc18\uc601 \ubc94\uc704 \uc694\uc57d</h4>
        <div>${renderMetricPairs([
          { label: '\uac00\uaca9', value: `KIS \ub300\ud45c \uc885\ubaa9 ${reps.length}\uac74 \ubc18\uc601` },
          { label: '\uac70\uc2dc', value: `\uad6d\ub0b4\uc678 \uac70\uc2dc \uc9c0\ud45c ${macroRows.length}\uac74 \ubc18\uc601` },
          { label: '\uc815\ucc45/\ubb38\uc11c', value: `${data.strategy_hints?.length || 0}\uac74 \ud78c\ud2b8 \ubc18\uc601` },
          { label: '\uc751\ub2f5 \uacbd\ub85c', value: sourceLabel(data.pipeline_status?.response_source) },
        ])}</div>
      </section>
      <section class="report-section">
        <h4>\uc2e0\uc120\ub3c4 / \ucd5c\uc885 \uc5c5\ub370\uc774\ud2b8</h4>
        <div>${renderMetricPairs([
          { label: '\uc0dd\uc131 \uc2dc\uac01', value: formatKstDateTime(data.generated_at_utc) },
          { label: '\ub370\uc774\ud130 \uc2e0\uc120\ub3c4', value: freshnessLabel(data.generated_at_utc) },
          { label: '\ud30c\uc774\ud504\ub77c\uc778 \uc0c1\ud0dc', value: sourceLabel(data.pipeline_status?.response_source) },
          { label: '\uc6f9 \ub9ac\ud3ec\ud2b8 \uae30\uc900', value: marketSessionLabel(data.generated_at_utc) },
        ])}</div>
      </section>
      <section class="report-section">
        <h4>\ud310\ub2e8 \ud55c\uacc4</h4>
        ${renderList(context.limitations)}
      </section>
      <section class="report-section">
        <h4>\uadfc\uac70 \ub370\uc774\ud130 \ucd9c\ucc98</h4>
        <p class="data-footnote">KIS \uc77c\ubd09, BOK/KOSIS/OECD/FRED/BLS/BEA/Fiscal Data/World Bank/IMF/Eurostat \uac70\uc2dc \ub370\uc774\ud130, \uc815\ucc45\ube0c\ub9ac\ud551\u00b7\ud55c\uad6d\uc740\ud589\u00b7\uae00\ub85c\ubc8c \uac70\uc2dc \ube0c\ub9ac\ud551 \ubc30\uce58 \ubb38\uc11c\ub97c \ud568\uaed8 \uc0ac\uc6a9\ud588\uc2b5\ub2c8\ub2e4.</p>
      </section>
    </div>`,
    false
  );

  return reportShell({
    badges: ['Market Regime \ub9ac\ud3ec\ud2b8', data.regime, `\uc810\uc218 ${Number(data.regime_score || 0).toFixed(1)}`, `\ud655\uc2e0\ub3c4 ${context.confidenceLabel}`],
    title: summary,
    summary: `${data.market_one_line} \uc2dc\uc7a5 \uccb4\uc81c, \ud575\uc2ec \ub3d9\uc778, \uc139\ud130 \ud310\ub2e8, \ud22c\uc790\uc790 \ud589\ub3d9 \ud78c\ud2b8\ub97c \uc601\uc5ed\ubcc4\ub85c \uc815\ub9ac\ud588\uc2b5\ub2c8\ub2e4.`,
    statusHtml: renderStatus(data.pipeline_status),
    body: `
      ${renderSummaryGrid([
        { label: '\uc2dc\uc7a5 \uccb4\uc81c \uc810\uc218', value: Number(data.regime_score || 0).toFixed(1), tone: toneClassByScore(data.regime_score) },
        { label: '\uccb4\uc81c \uae30\uc6b8\uae30', value: context.directionLabel },
        { label: '\ud604\uc7ac \ud655\uc2e0\ub3c4', value: context.confidenceLabel },
        { label: '\ub300\ud45c \uc885\ubaa9 \uc0c1\uc2b9 \ube44\uc911', value: `${(context.risingRatio * 100).toFixed(1)}%` },
      ])}
      ${topConclusion}
      ${decompositionSection}
      ${driversSection}
      ${headlineSection}
      ${sectorsSection}
      ${actionSection}
      ${invalidationSection}
      ${trustSection}`,
  });
}

function dominantStockHorizon(data) {
  const horizonRows = [
    { key: '\ub2e8\uae30', value: Number(data.short_term_score || 0) },
    { key: '\uc2a4\uc719', value: Number(data.swing_score || 0) },
    { key: '\uc911\uae30', value: Number(data.midterm_score || 0) },
  ].sort((a, b) => b.value - a.value);
  return horizonRows[0]?.key || '\uc2a4\uc719';
}

function stockValidityWindow(data) {
  const dominant = dominantStockHorizon(data);
  if (dominant === '\ub2e8\uae30') return '1~3\uac70\ub798\uc77c';
  if (dominant === '\uc2a4\uc719') return '1~3\uc8fc';
  return '1~3\uac1c\uc6d4';
}

function stockConflictSignals(features, signal) {
  const conflicts = [];
  if (Number(features.return_20d || 0) > 0.08 && Number(features.financing_risk_score || 0) >= 0.4) {
    conflicts.push('\ucd94\uc138\ub294 \uac15\ud558\uc9c0\ub9cc \uc790\uae08\uc870\ub2ec \ub9ac\uc2a4\ud06c\uac00 \ub0a8\uc544 \uc788\uc2b5\ub2c8\ub2e4.');
  }
  if (Number(features.rsi_14 || 0) >= 72 && Number(features.revenue_growth_yoy || 0) > 0.05) {
    conflicts.push('\uc7ac\ubb34\ub294 \uc591\ud638\ud558\uc9c0\ub9cc \ub2e8\uae30 \uacfc\uc5f4 \uc2e0\ud638\uac00 \ub3d9\uc2dc\uc5d0 \uc874\uc7ac\ud569\ub2c8\ub2e4.');
  }
  if (getRiskFlagCodes(signal).includes('EVENT_DAY_VOLATILITY_MODE')) {
    conflicts.push('\ud575\uc2ec \uc774\ubca4\ud2b8\uac00 \uc788\uc5b4 \uc77c\ubc18 \uc608\uce21\ubcf4\ub2e4 \uc7a5\uc911 \ud655\uc778\uc774 \ub354 \uc911\uc694\ud569\ub2c8\ub2e4.');
  }
  return conflicts;
}

function stockChangedVariables(data, features, signal) {
  const candidates = [
    {
      title: '\uc139\ud130 \uc790\uae08 \uc720\uc785',
      direction: Number(features.sector_fund_flow_score || 0) >= 0.5 ? '\uc0c1\ubc29' : '\uc81c\uc57d',
      strength: Number(features.sector_fund_flow_score || 0).toFixed(2),
      horizon: '\uc2a4\uc719',
      note: `\uc139\ud130 \uc790\uae08 \uc720\uc785 \uac15\ub3c4 ${Number(features.sector_fund_flow_score || 0).toFixed(2)}`,
      score: Math.abs(Number(features.sector_fund_flow_score || 0) - 0.5),
    },
    {
      title: '\uacf5\uc2dc \uc21c\ud6a8\uacfc',
      direction: Number(features.disclosure_net_score || 0) >= 0 ? '\uc0c1\ubc29' : '\ud558\ubc29',
      strength: Number(Math.abs(features.disclosure_net_score || 0)).toFixed(2),
      horizon: '\ub2e8\uae30',
      note: `\uacf5\uc2dc \uc21c\ud6a8\uacfc ${Number(features.disclosure_net_score || 0).toFixed(2)}`,
      score: Math.abs(Number(features.disclosure_net_score || 0)),
    },
    {
      title: '\uc7ac\ubb34 \uccb4\ub825',
      direction: Number(features.revenue_growth_yoy || 0) >= 0 ? '\uc0c1\ubc29' : '\ud558\ubc29',
      strength: Number(Math.abs(features.revenue_growth_yoy || 0)).toFixed(2),
      horizon: '\uc911\uae30',
      note: `\ub9e4\ucd9c \uc131\uc7a5\ub960 ${((Number(features.revenue_growth_yoy || 0)) * 100).toFixed(1)}% / \uc601\uc5c5\uc774\uc775\ub960 ${((Number(features.operating_margin || 0)) * 100).toFixed(1)}%`,
      score: Math.abs(Number(features.revenue_growth_yoy || 0)) + Math.abs(Number(features.operating_margin || 0)),
    },
    {
      title: '\uac70\uc2dc \uc555\ub825',
      direction: Number(features.macro_pressure_score || 0) >= 0.4 ? '\ud558\ubc29' : '\uc911\ub9bd',
      strength: Number(features.macro_pressure_score || 0).toFixed(2),
      horizon: '\uc911\uae30',
      note: `\uac70\uc2dc \uc555\ub825 ${Number(features.macro_pressure_score || 0).toFixed(2)} / \uc9c0\uc6d0 ${Number(features.macro_support_score || 0).toFixed(2)}`,
      score: Math.abs(Number(features.macro_pressure_score || 0)),
    },
    {
      title: '\uac00\uaca9 \ubaa8\uba58\ud140',
      direction: Number(features.return_20d || 0) >= 0 ? '\uc0c1\ubc29' : '\ud558\ubc29',
      strength: Math.abs(Number(features.return_20d || 0) * 100).toFixed(1),
      horizon: '\ub2e8\uae30',
      note: `20\uc77c \uc218\uc775\ub960 ${((Number(features.return_20d || 0)) * 100).toFixed(1)}% / RSI ${Number(features.rsi_14 || 0).toFixed(1)}`,
      score: Math.abs(Number(features.return_20d || 0)),
    },
  ];
  return candidates.sort((a, b) => b.score - a.score).slice(0, 3);
}

function stockPeriodNarratives(data, features) {
  return {
    short: `\ub2e8\uae30\ub294 \ub274\uc2a4/\uacf5\uc2dc/\ubcc0\ub3d9\uc131\uc758 \uc601\ud5a5\uc774 \ud06c\uba70, RSI ${Number(features.rsi_14 || 0).toFixed(1)} / \uac70\ub798\ub7c9 ${Number(features.rel_volume || 0).toFixed(2)}\ubc30 \uc218\uc900\uc744 \ud568\uaed8 \ubcf4\uace0 \uc788\uc2b5\ub2c8\ub2e4.`,
    swing: `\uc2a4\uc719\uc740 \uc139\ud130 \uc790\uae08 \uc720\uc785 ${Number(features.sector_fund_flow_score || 0).toFixed(2)}\uc640 20\uc77c \uc218\uc775\ub960 ${((Number(features.return_20d || 0)) * 100).toFixed(1)}%\ub97c \uc911\uc2ec\uc73c\ub85c \ubcf4\ub294 \uad6c\uc870\uc785\ub2c8\ub2e4.`,
    mid: `\uc911\uae30\ub294 \ub9e4\ucd9c \uc131\uc7a5\ub960 ${((Number(features.revenue_growth_yoy || 0)) * 100).toFixed(1)}%, \uc601\uc5c5\uc774\uc775\ub960 ${((Number(features.operating_margin || 0)) * 100).toFixed(1)}%, \uac70\uc2dc \uc555\ub825 ${Number(features.macro_pressure_score || 0).toFixed(2)}\ub97c \uc911\uc2ec\uc73c\ub85c \ud574\uc11d\ud569\ub2c8\ub2e4.`,
    gap: `\uae30\uac04\ubcc4\ub85c \ubcf4\uba74 ${dominantStockHorizon(data)} \uad00\uc810\uc774 \uac00\uc7a5 \uac15\ud558\uba70, \ub2e8\uae30\uc640 \uc911\uae30\uac00 \ub2e4\ub974\uba74 \uacfc\uc5f4/\uc2e4\uc801 \uac04 \uac04\uadf9\uc744 \uc758\ubbf8\ud569\ub2c8\ub2e4.`,
  };
}

function stockLayerNarratives(data, features) {
  return [
    `\uc2dc\uc7a5 \uc601\ud5a5 \uc810\uc218 ${Number(data.market_score || 0).toFixed(1)}\ub85c, \ud604\uc7ac \uc2dc\uc7a5 \uccb4\uc81c\uac00 \uc885\ubaa9\uc5d0 \ubbf8\uce58\ub294 \uc601\ud5a5\uc744 \ubc18\uc601\ud569\ub2c8\ub2e4.`,
    `\uc139\ud130 \uc601\ud5a5 \uc810\uc218 ${Number(data.sector_score || 0).toFixed(1)}\uc640 \uc0c1\ub300 \uac15\ub3c4 ${Number(data.sector_relative_strength || 0).toFixed(1)}\ub97c \ud568\uaed8 \ubcf4\uace0 \uc788\uc2b5\ub2c8\ub2e4.`,
    `\uc885\ubaa9 \uace0\uc720 \uc810\uc218 ${Number(data.stock_specific_score || 0).toFixed(1)}\ub294 \uc7ac\ubb34, \uc2e4\uc801, \uacf5\uc2dc, \ud68c\uc0ac \uace0\uc720 \uc774\uc288\ub97c \uc758\ubbf8\ud569\ub2c8\ub2e4.`,
    `\uc774\ubca4\ud2b8 \uc601\ud5a5 \uc810\uc218 ${Number(data.event_score || 0).toFixed(1)}\ub294 \ucd5c\uadfc \ub274\uc2a4/\uacf5\uc2dc\uac00 \ud604\uc7ac \uc8fc\uac00 \uac00\uc124\uc744 \uc5bc\ub9c8\ub098 \ubc14\uafb8\uace0 \uc788\ub294\uc9c0\ub97c \ubcf4\uc5ec\uc90d\ub2c8\ub2e4.`,
  ];
}

function stockTechnicalWarnings(features) {
  const flags = [];
  if (Number(features.rsi_14 || 0) >= 75) flags.push('\ub2e8\uae30 \uacfc\uc5f4 \uad6c\uac04\uc785\ub2c8\ub2e4.');
  if (Number(features.rel_volume || 0) < 0.7) flags.push('\uac70\ub798\ub7c9\uc774 \ub450\ud130\uc6cc\uc9c0\uc9c0 \uc54a\uc544 \ucd94\uc138 \uc2e0\ub8b0\ub3c4\uac00 \ub0ae\uc744 \uc218 \uc788\uc2b5\ub2c8\ub2e4.');
  if (Number(features.volatility_20d || 0) >= 0.08) flags.push('\ubcc0\ub3d9\uc131\uc774 \ud070 \uad6c\uac04\uc774\uc5b4\uc11c \ubd84\ud560 \ub300\uc751\uc774 \ud544\uc694\ud569\ub2c8\ub2e4.');
  if (Number(features.intraday_range_pct || 0) >= 0.05) flags.push('\uc7a5\uc911 \ubcc0\ub3d9\ud3ed\uc774 \ucee4 \ub2e8\uae30 \uc774\uc0c1\uc9d5\ud6c4\ub97c \uc810\uac80\ud560 \ud544\uc694\uac00 \uc788\uc2b5\ub2c8\ub2e4.');
  return flags;
}

function stockMacroSensitivity(data, features) {
  const sectorName = String(data.sector_name || '');
  const notes = [];
  if (['\ubc18\ub3c4\uccb4', '\uc790\ub3d9\ucc28'].includes(sectorName)) notes.push('\ud658\uc728\uacfc \uae00\ub85c\ubc8c \uc218\uc694 \ubcc0\ud654\uc5d0 \ubbfc\uac10\ud55c \uad6c\uc870\uc785\ub2c8\ub2e4.');
  if (['\uc778\ud130\ub137', '\ubc14\uc774\uc624'].includes(sectorName)) notes.push('\uae08\ub9ac \ubcc0\ud654\uac00 \uc131\uc7a5\uc8fc \ubc38\ub958\uc5d0\uc774\uc158 \ud574\uc11d\uc744 \ud070 \ud3ed\uc73c\ub85c \ubc14\uafc9\ub2c8\ub2e4.');
  if (['2\ucc28\uc804\uc9c0\u00b7\ud654\ud559', '\uc804\ub825\u00b7\uc5d0\ub108\uc9c0'].includes(sectorName)) notes.push('\uc6d0\uc790\uc7ac \uac00\uaca9\uacfc \uc815\ucc45 \ud750\ub984\uc5d0 \ub3d9\uc2dc \uc5f0\ub3d9\ub429\ub2c8\ub2e4.');
  notes.push(`\ud604\uc7ac \uac70\uc2dc \uc555\ub825 ${Number(features.macro_pressure_score || 0).toFixed(2)}, \uae00\ub85c\ubc8c \uc810\uc218 ${Number(features.macro_global_score || 0).toFixed(2)}\ub97c \ud568\uaed8 \ubc18\uc601\ud55c \uc0c1\ud0dc\uc785\ub2c8\ub2e4.`);
  return notes;
}

function splitDocumentSummaries(explanation) {
  const items = explanation?.document_summaries || [];
  return {
    news: items.filter((item) => String(item.source || '') === 'news').slice(0, 4),
    disclosures: items.filter((item) => String(item.source || '') === 'disclosure').slice(0, 4),
  };
}

function deriveStockDecisionContext(data) {
  const features = data.source_analysis?.features || {};
  const signal = data.source_analysis?.signal || {};
  const explanation = data.source_analysis?.explanation || {};
  const documents = data.recent_timeline || [];
  const documentSplit = splitDocumentSummaries(explanation);
  const horizon = dominantStockHorizon(data);
  const riskPressure = clampValue(
    Number(features.financing_risk_score || 0) * 35
      + Number(features.macro_pressure_score || 0) * 25
      + Number(features.event_volatility_score || 0) * 20
      + (signal.risk_flags || []).length * 4
  );
  const financialScore = clampValue(
    50
      + Number(features.revenue_growth_yoy || 0) * 35
      + Number(features.operating_margin || 0) * 80
      + Number(features.operating_cashflow_margin || 0) * 50
      - Math.max(Number(features.debt_ratio || 0) - 1, 0) * 12
  );
  const valuationBurden = clampValue(
    40
      + Math.max(Number(features.return_20d || 0), 0) * 120
      + Math.max(Number(features.rsi_14 || 0) - 60, 0) * 1.5
      - Number(features.operating_margin || 0) * 20
  );
  return {
    horizon,
    validityWindow: stockValidityWindow(data),
    riskPressure: riskPressure.toFixed(1),
    financialScore: financialScore.toFixed(1),
    valuationBurden: valuationBurden.toFixed(1),
    changedVariables: stockChangedVariables(data, features, signal),
    newEvidence: documents.slice(0, 3).map((item) => `${item.title} (${item.event_type})`),
    weakenedEvidence: [...(data.bearish_factors || []), ...(signal.risk_flags || [])].slice(0, 4),
    conflicts: stockConflictSignals(features, signal),
    periods: stockPeriodNarratives(data, features),
    layers: stockLayerNarratives(data, features),
    technicalWarnings: stockTechnicalWarnings(features),
    macroSensitivity: stockMacroSensitivity(data, features),
    documentSplit,
  };
}

function renderStockReport(data) {
  const features = data.source_analysis?.features || {};
  const signal = data.source_analysis?.signal || {};
  const explanation = data.source_analysis?.explanation || {};
  const documents = data.recent_timeline || [];
  const context = deriveStockDecisionContext(data);
  const summary = `${data.instrument_name}(${data.ticker})\uc740 \ud604\uc7ac ${data.conclusion} \uad00\uc810\uc774\uba70, \uc0c1\ud0dc\ub294 ${data.state_label}\uc785\ub2c8\ub2e4.`;

  const topConclusion = renderCollapsibleSection(
    '\uc0c1\ub2e8 \ud575\uc2ec \uacb0\ub860',
    '\ucd5c\uc885 \uc885\ubaa9 \ud310\ub2e8\uacfc \ud574\uc11d \uae30\uc900 \uc2dc\uc810',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\ucd5c\uc885 \uc885\ubaa9 \ud310\ub2e8</h4>
        <div>${renderMetricPairs([
          { label: '\uc885\ubaa9', value: `${data.instrument_name}(${data.ticker})` },
          { label: '\ud55c \uc904 \ud22c\uc790 \ud310\ub2e8', value: summary },
          { label: '\ud604\uc7ac \uc0c1\ud0dc \ub77c\ubca8', value: String(data.state_label || '-') },
          { label: '\ud310\ub2e8 \ud655\uc2e0\ub3c4', value: Number(data.confidence_score || 0).toFixed(1) },
          { label: '\ud310\ub2e8 \uc720\ud6a8 \uae30\uac04', value: context.validityWindow },
          { label: '\uc8fc\ub3c4 \ud574\uc11d \uae30\uac04', value: context.horizon },
        ])}</div>
      </section>
      <section class="report-section">
        <h4>\uae30\uc900 \uc2dc\uc810 \ubc0f \ub370\uc774\ud130 \uc2dc\uac04</h4>
        <div>${renderMetricPairs([
          { label: '\uae30\uc900\uc77c', value: String(data.as_of_date || '-') },
          { label: '\uc0dd\uc131 \uc2dc\uac01', value: formatKstDateTime(data.generated_at_utc) },
          { label: '\ub370\uc774\ud130 \uc2e0\uc120\ub3c4', value: freshnessLabel(data.generated_at_utc) },
          { label: '\uc751\ub2f5 \uacbd\ub85c', value: sourceLabel(data.pipeline_status?.response_source) },
        ])}</div>
      </section>
    </div>`,
    true
  );

  const scoreSection = renderCollapsibleSection(
    '\ud310\ub2e8 \uc810\uc218 \uad6c\uc870 \ubd84\ud574',
    '\uc885\ud569 \ud310\ub2e8, \uae30\uac04\ubcc4 \uc810\uc218, \uc601\ud5a5 \uacc4\uce35',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\uc885\ud569 \uc810\uc218</h4>
        ${renderSummaryGrid([
          { label: '\ud310\ub2e8 \uc810\uc218', value: Number(data.confidence_score || 0).toFixed(1), tone: toneClassByScore(data.confidence_score) },
          { label: '\ud488\uc9c8 \uc810\uc218', value: Number(data.quality_score || 0).toFixed(1), tone: toneClassByScore(data.quality_score) },
          { label: '\uc2dc\uadf8\ub110 \uc810\uc218', value: Number(signal.score || 0).toFixed(1) },
          { label: '\ubb38\uc11c \uadfc\uac70 \uc218', value: String(documents.length) },
        ])}
      </section>
      <section class="report-section">
        <h4>\uae30\uac04\ubcc4 / \uc601\ud5a5 \uc810\uc218</h4>
        ${renderScoreRows([
          { label: '\ub2e8\uae30', value: data.short_term_score },
          { label: '\uc2a4\uc719', value: data.swing_score },
          { label: '\uc911\uae30', value: data.midterm_score },
          { label: '\uc2dc\uc7a5 \uc601\ud5a5', value: data.market_score },
          { label: '\uc139\ud130 \uc601\ud5a5', value: data.sector_score },
          { label: '\uc885\ubaa9 \uace0\uc720', value: data.stock_specific_score },
          { label: '\uc774\ubca4\ud2b8 \uc601\ud5a5', value: data.event_score },
          { label: '\ubc38\ub958\uc5d0\uc774\uc158', value: data.valuation_score },
          { label: '\uc7ac\ubb34/\uc2e4\uc801 \ud504\ub85d\uc2dc', value: context.financialScore },
          { label: '\ubc38\ub958\uc5d0\uc774\uc158 \ubd80\ub2f4', value: context.valuationBurden },
          { label: '\ub9ac\uc2a4\ud06c \uc555\ub825', value: context.riskPressure },
        ])}
      </section>
    </div>`,
    true
  );

  const evidenceSection = renderCollapsibleSection(
    '\uc65c \uc774\ub7f0 \uacb0\ub860\uc774 \ub098\uc654\ub294\uc9c0',
    '\uc0c1\uc2b9/\ud558\ub77d \uadfc\uac70, \ud575\uc2ec \ubcc0\uc218, \uc0c1\ucda9 \uc2e0\ud638',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\uc0c1\uc2b9 \uadfc\uac70 Top 5</h4>
        ${renderList(data.bullish_factors || [])}
      </section>
      <section class="report-section">
        <h4>\ud558\ub77d \uadfc\uac70 Top 5</h4>
        ${renderList(data.bearish_factors || [])}
      </section>
      <section class="report-section">
        <h4>\ud310\ub2e8\uc744 \uac00\uc7a5 \ub9ce\uc774 \ubc14\uafbc \ubcc0\uc218 3\uac1c</h4>
        ${renderDriverGrid(context.changedVariables)}
      </section>
      <section class="report-section">
        <h4>\uc0c8\ub86d\uac8c \ucd94\uac00\ub41c \ud575\uc2ec \uadfc\uac70</h4>
        ${renderList(context.newEvidence)}
      </section>
      <section class="report-section">
        <h4>\uc57d\ud574\uc9c4 \uadfc\uac70</h4>
        ${renderList(context.weakenedEvidence)}
      </section>
      <section class="report-section">
        <h4>\uc0c1\ucda9\ud558\ub294 \uc2e0\ud638</h4>
        ${renderList(context.conflicts.length ? context.conflicts : ['\ud2b9\ubcc4\ud788 \ud070 \uc0c1\ucda9 \uc2e0\ud638\ub294 \ud655\uc778\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.'])}
      </section>
    </div>`,
    true
  );

  const periodSection = renderCollapsibleSection(
    '\uae30\uac04\ubcc4 \ud574\uc11d',
    '\ub2e8\uae30, \uc2a4\uc719, \uc911\uae30 \uad00\uc810 \ucc28\uc774',
    `<div class="evidence-grid">
      <section class="report-section"><h4>\ub2e8\uae30 \ud574\uc11d</h4><p class="section-copy">${escapeHtml(context.periods.short)}</p></section>
      <section class="report-section"><h4>\uc2a4\uc719 \ud574\uc11d</h4><p class="section-copy">${escapeHtml(context.periods.swing)}</p></section>
      <section class="report-section"><h4>\uc911\uae30 \ud574\uc11d</h4><p class="section-copy">${escapeHtml(context.periods.mid)}</p></section>
      <section class="report-section"><h4>\uae30\uac04\ubcc4 \uacb0\ub860 \ucc28\uc774</h4><p class="section-copy">${escapeHtml(context.periods.gap)}</p></section>
    </div>`,
    true
  );

  const layerSection = renderCollapsibleSection(
    '\uc2dc\uc7a5-\uc139\ud130-\uc885\ubaa9 \uacc4\uce35 \ubd84\uc11d',
    '\uc2dc\uc7a5, \uc139\ud130, \ud68c\uc0ac \uace0\uc720 \uc601\ud5a5\uc744 \uad6c\ubd84',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\uacc4\uce35 \ud574\uc11d</h4>
        ${renderList(context.layers)}
      </section>
      <section class="report-section">
        <h4>\uc139\ud130 \ubaa8\uba58\ud140 / peer \uadfc\uac70</h4>
        ${renderSignalChips(data.sector_momentum_summary || [])}
        <div style="margin-top:12px;">${renderPeerTable(data.sector_peer_snapshot || [])}</div>
      </section>
    </div>`,
    true
  );

  const technicalSection = renderCollapsibleSection(
    '\uac00\uaca9/\uc218\uae09/\uae30\uc220 \ud574\uc11d',
    'MA, \uac70\ub798\ub7c9, \ubcc0\ub3d9\uc131, RSI, \uc774\uc0c1\uc9d5\ud6c4',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\ud604\uc7ac \uac00\uaca9 \uc704\uce58</h4>
        <div>${renderMetricPairs([
          { label: '\uc885\uac00', value: String(features.close ?? '-') },
          { label: 'MA20 / MA60', value: `${features.ma_20 ?? '-'} / ${features.ma_60 ?? '-'}` },
          { label: '\uac00\uaca9 vs MA20', value: `${((Number(features.price_vs_ma20 || 0)) * 100).toFixed(1)}%` },
          { label: '\uac00\uaca9 vs MA60', value: `${((Number(features.price_vs_ma60 || 0)) * 100).toFixed(1)}%` },
          { label: '\uac70\ub798\ub7c9', value: `${Number(features.rel_volume || 0).toFixed(2)}\ubc30` },
          { label: 'RSI', value: Number(features.rsi_14 || 0).toFixed(1) },
        ])}</div>
      </section>
      <section class="report-section">
        <h4>\ubcc0\ub3d9\uc131 / \uacbd\uacc4 \uad6c\uac04</h4>
        ${renderList([
          `20\uc77c \ubcc0\ub3d9\uc131 ${((Number(features.volatility_20d || 0)) * 100).toFixed(1)}%`,
          `ATR ${((Number(features.atr_14_pct || 0)) * 100).toFixed(1)}%`,
          `\uc7a5\uc911 \ubcc0\ub3d9\ud3ed ${((Number(features.intraday_range_pct || 0)) * 100).toFixed(1)}%`,
          ...context.technicalWarnings,
        ])}
      </section>
    </div>`,
    false
  );

  const eventSection = renderCollapsibleSection(
    '\uc774\ubca4\ud2b8\u00b7\ub274\uc2a4\u00b7\uacf5\uc2dc \ud574\uc11d',
    '\ud0c0\uc784\ub77c\uc778, \uacf5\uc2dc \uc694\uc57d, \ub274\uc2a4 \uc694\uc57d',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\ucd5c\uadfc \uc774\ubca4\ud2b8 \ud0c0\uc784\ub77c\uc778</h4>
        ${renderTimeline(documents)}
      </section>
      <section class="report-section">
        <h4>\ucd5c\uadfc \uacf5\uc2dc \ud575\uc2ec \uc694\uc57d</h4>
        ${renderDisclosureCards(explanation.material_disclosures || [])}
      </section>
      <section class="report-section">
        <h4>\ucd5c\uadfc \ub274\uc2a4 \ud575\uc2ec \uc694\uc57d</h4>
        ${renderList(context.documentSplit.news.map((item) => `${item.title}: ${item.summary}`))}
      </section>
      <section class="report-section">
        <h4>\uacf5\uc2dc \ub610\ub294 \ub274\uc2a4 \uc774\ubca4\ud2b8 \uc6b0\uc120\uc21c\uc704</h4>
        ${renderList((explanation.material_disclosures || []).map((item) => `${item.event_label || '\uacf5\uc2dc'} / \uc21c\ud6a8\uacfc ${Number(item.net_score || 0).toFixed(2)} / ${item.title || ''}`))}
      </section>
    </div>`,
    false
  );

  const financeSection = renderCollapsibleSection(
    '\uc7ac\ubb34/\uc2e4\uc801/\uac00\uce58 \ud310\ub2e8',
    '\uc2e4\uc801 \ud750\ub984, \ud604\uae08\ud750\ub984, \uc790\uae08\uc870\ub2ec, \uac70\ubc84\ub10c\uc2a4',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\ucd5c\uadfc \uc2e4\uc801 \ud750\ub984</h4>
        ${renderSignalChips(data.financial_summary || [])}
      </section>
      <section class="report-section">
        <h4>\uc774\uc775 \uccb4\ub825 / \uc7ac\ubb34 \uc548\uc815\uc131</h4>
        ${renderList([
          `\ub9e4\ucd9c \uc131\uc7a5\ub960 ${((Number(features.revenue_growth_yoy || 0)) * 100).toFixed(1)}%`,
          `\uc601\uc5c5\uc774\uc775\ub960 ${((Number(features.operating_margin || 0)) * 100).toFixed(1)}%`,
          `\uc601\uc5c5\ud604\uae08\ud750\ub984 \ub9c8\uc9c4 ${((Number(features.operating_cashflow_margin || 0)) * 100).toFixed(1)}%`,
          `\ubd80\ucc44\ube44\uc728 ${Number(features.debt_ratio || 0).toFixed(2)} / \uc720\ub3d9\ube44\uc728 ${Number(features.current_ratio || 0).toFixed(2)}`,
        ])}
      </section>
      <section class="report-section">
        <h4>\uc790\uae08\uc870\ub2ec / \uc8fc\uc8fc\ud658\uc6d0 / \uac70\ubc84\ub10c\uc2a4</h4>
        ${renderList([
          `\uc790\uae08\uc870\ub2ec \ub9ac\uc2a4\ud06c ${Number(features.financing_risk_score || 0).toFixed(2)}`,
          `\uc8fc\uc8fc\ud658\uc6d0 \uc2e0\ud638 ${Number(features.shareholder_return_score || 0).toFixed(2)}`,
          `\uac70\ubc84\ub10c\uc2a4 \uc2e0\ud638 ${Number(features.governance_score || 0).toFixed(2)}`,
          `\ubc38\ub958\uc5d0\uc774\uc158 \ubd80\ub2f4 \ud504\ub85d\uc2dc ${context.valuationBurden}`,
        ])}
      </section>
    </div>`,
    false
  );

  const macroSection = renderCollapsibleSection(
    '\uac70\uc2dc/\uc815\ucc45 \uc601\ud5a5',
    '\uc774 \uc885\ubaa9\uc5d0 \uc911\uc694\ud55c \uac70\uc2dc \ubcc0\uc218 \ud574\uc11d',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\uc911\uc694 \uac70\uc2dc \ubcc0\uc218</h4>
        ${renderList(context.macroSensitivity)}
      </section>
      <section class="report-section">
        <h4>\uac70\uc2dc\u00b7\uc815\ucc45 \uadfc\uac70</h4>
        ${renderList(data.policy_macro_summary || [])}
      </section>
      <section class="report-section">
        <h4>\uac70\uc2dc\uac00 \ubc14\ub00c\uba74 \ud754\ub4e4\ub9b4 \ub17c\ub9ac</h4>
        ${renderList([
          '\uae08\ub9ac \uc11c\ud504\ub77c\uc774\uc988\uac00 \ud06c\uba74 \uc131\uc7a5\uc8fc \ud3c9\uac00\uac00 \ud754\ub4e4\ub9b4 \uc218 \uc788\uc2b5\ub2c8\ub2e4.',
          '\ud658\uc728 \uae09\ub4f1/\uae09\ub77d\uc740 \uc218\ucd9c\uc8fc \uac00\uc124\uc744 \ube60\ub974\uac8c \ubc14\uafc0 \uc218 \uc788\uc2b5\ub2c8\ub2e4.',
          '\uc815\ucc45 \uae30\ub300\uac00 \ud6c4\ud1f4\ub418\uba74 \uc139\ud130 \uc0c1\ub300\uac15\ub3c4\uac00 \uc57d\ud654\ub420 \uc218 \uc788\uc2b5\ub2c8\ub2e4.',
        ])}
      </section>
    </div>`,
    false
  );

  const checkpointSection = renderCollapsibleSection(
    '\uccb4\ud06c\ud3ec\uc778\ud2b8 \ubc0f \ubc18\uc99d \uc870\uac74',
    '\ud655\uc778 \ud544\uc218 \ud56d\ubaa9, \ubb34\ud6a8\ud654/\uc0c1\ud5a5/\ud558\ud5a5 \uc7ac\ud3c9\uac00 \uc870\uac74',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\uc9c0\uae08 \ud655\uc778\ud560 \uccb4\ud06c\ud3ec\uc778\ud2b8</h4>
        ${renderList(data.change_triggers || [])}
      </section>
      <section class="report-section">
        <h4>\uc774 \ud310\ub2e8\uc774 \ud2c0\ub9b4 \uc218 \uc788\ub294 \uc774\uc720</h4>
        ${renderList((signal.risk_flags || []).length ? signal.risk_flags : ['\ub300\ud615 \ub9ac\uc2a4\ud06c \ud50c\ub798\uadf8\ub294 \ud655\uc778\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.'])}
      </section>
      <section class="report-section">
        <h4>\ubb34\ud6a8\ud654 / \uc0c1\ud5a5 / \ud558\ud5a5 \uc7ac\ud3c9\uac00 \uc870\uac74</h4>
        ${renderList([
          `\ubb34\ud6a8\ud654: ${data.change_triggers?.[0] || '\uc0c8 \uc545\uc7ac \ubc1c\uc0dd'}`,
          `\uc0c1\ud5a5 \uc7ac\ud3c9\uac00: ${data.bullish_factors?.[0] || '\uc0c1\uc2b9 \uadfc\uac70 \uac15\ud654'}`,
          `\ud558\ud5a5 \uc7ac\ud3c9\uac00: ${data.bearish_factors?.[0] || '\ud558\ub77d \uadfc\uac70 \ud655\ub300'}`,
        ])}
      </section>
      <section class="report-section">
        <h4>\ub2e4\uc74c \ud655\uc778 \uc608\uc815 \uc774\ubca4\ud2b8</h4>
        ${renderList((documents || []).slice(0, 4).map((item) => `${item.event_type}: ${item.title}`))}
      </section>
    </div>`,
    false
  );

  const trustSection = renderCollapsibleSection(
    '\ub370\uc774\ud130 \uc2e0\ub8b0 \ubc0f \uc124\uba85 \uac00\ub2a5\uc131',
    '\uc0ac\uc6a9 \ub370\uc774\ud130, \uc2e0\ud638 \ud488\uc9c8, \ud574\uc11d \uc81c\uc57d',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>\uc0ac\uc6a9 \ub370\uc774\ud130 \uc694\uc57d</h4>
        <div>${renderMetricPairs([
          { label: '\uc0ac\uc6a9 \ubb38\uc11c/\uacf5\uc2dc/\ub274\uc2a4', value: `${documents.length}\uac74` },
          { label: '\uacf5\uc2dc \uc810\uc218 \ub370\uc774\ud130', value: `${(explanation.material_disclosures || []).length}\uac74` },
          { label: '\uc751\ub2f5 \uacbd\ub85c', value: sourceLabel(data.pipeline_status?.response_source) },
          { label: '\uc2e0\ud638 \ud488\uc9c8', value: Number(data.quality_score || 0).toFixed(1) },
        ])}</div>
      </section>
      <section class="report-section">
        <h4>\ub370\uc774\ud130 \ucd5c\uc2e0\uc131</h4>
        <div>${renderMetricPairs([
          { label: '\uc0dd\uc131 \uc2dc\uac01', value: formatKstDateTime(data.generated_at_utc) },
          { label: '\ub370\uc774\ud130 \uc2e0\uc120\ub3c4', value: freshnessLabel(data.generated_at_utc) },
          { label: '\ud30c\uc774\ud504\ub77c\uc778 \uc0c1\ud0dc', value: sourceLabel(data.pipeline_status?.response_source) },
          { label: '\ubb38\uc11c \uadfc\uac70 \uc218', value: String(documents.length) },
        ])}</div>
      </section>
      <section class="report-section">
        <h4>\ud574\uc11d \uc81c\uc57d \uc870\uac74</h4>
        ${renderList([
          '\ubc38\ub958\uc5d0\uc774\uc158 \ubd80\ub2f4\uc740 \uc2e4\uc81c PER/PBR\uac00 \uc544\ub2c8\ub77c \ud604\uc7ac \uc2e4\uc801\u00b7\uac00\uaca9 \uad00\uacc4\ub97c \ubcf8 \ud504\ub85d\uc2dc \uc9c0\ud45c\uc785\ub2c8\ub2e4.',
          '\uc2dc\uc7a5-\uc139\ud130 \uc601\ud5a5\uc740 \ub300\ud45c \uc885\ubaa9 \uae30\uc900 \uc0c1\ub300\uac15\ub3c4\ub97c \ud65c\uc6a9\ud55c \ud574\uc11d\uc785\ub2c8\ub2e4.',
          '\uc774\ubca4\ud2b8 \ud574\uc11d\uc740 \ucd5c\uc2e0 \ubb38\uc11c \uc694\uc57d\uacfc \uacf5\uc2dc \uc810\uc218\ud654 \uacb0\uacfc\ub97c \ud568\uaed8 \ubcf4\ub294 \uad6c\uc870\uc785\ub2c8\ub2e4.',
        ])}
      </section>
      <section class="report-section">
        <h4>\ub370\uc774\ud130 \ucd9c\ucc98</h4>
        <p class="data-footnote">KIS \uc2dc\uc138, NAVER/NewsAPI \ub274\uc2a4, OpenDART \uc7ac\ubb34\uc81c\ud45c\u00b7\uacf5\uc2dc, KIND \uacf5\uc2dc, \uad6d\ub0b4\uc678 \uac70\uc2dc \ub370\uc774\ud130, \uc815\ucc45\ube0c\ub9ac\ud551/\ud55c\uad6d\uc740\ud589 \ubc30\uce58 \ubb38\uc11c\ub97c \ud568\uaed8 \uc0ac\uc6a9\ud588\uc2b5\ub2c8\ub2e4.</p>
      </section>
    </div>`,
    false
  );

  return reportShell({
    badges: ['Stock Decision \ub9ac\ud3ec\ud2b8', data.market_regime, `\ud310\ub2e8 ${Number(data.confidence_score || 0).toFixed(1)}`, `\uc8fc\ub3c4 ${context.horizon}`],
    title: summary,
    summary: `\uc885\ubaa9 \ud22c\uc790 \uac00\uc124\uc744 \uac80\uc99d\ud558\ub294 \uad00\uc810\uc5d0\uc11c \uc810\uc218, \uadfc\uac70, \uae30\uac04\ubcc4 \ud574\uc11d, \uacc4\uce35 \uc601\ud5a5, \ubc18\uc99d \uc870\uac74\uc744 \uc601\uc5ed\ubcc4\ub85c \uc815\ub9ac\ud588\uc2b5\ub2c8\ub2e4.`,
    statusHtml: renderStatus(data.pipeline_status),
    body: `
      ${renderSummaryGrid([
        { label: '\ud310\ub2e8 \uc810\uc218', value: Number(data.confidence_score || 0).toFixed(1), tone: toneClassByScore(data.confidence_score) },
        { label: '\ud488\uc9c8 \uc810\uc218', value: Number(data.quality_score || 0).toFixed(1), tone: toneClassByScore(data.quality_score) },
        { label: '\uc2dc\uadf8\ub110 \uc810\uc218', value: Number(signal.score || 0).toFixed(1) },
        { label: '\ubb38\uc11c \uadfc\uac70 \uc218', value: String(documents.length) },
      ])}
      ${topConclusion}
      ${scoreSection}
      ${evidenceSection}
      ${periodSection}
      ${layerSection}
      ${technicalSection}
      ${eventSection}
      ${financeSection}
      ${macroSection}
      ${checkpointSection}
      ${trustSection}`,
  });
}


function actionHorizonLabel(value) {
  return {
    short_term: '단기',
    swing: '스윙',
    midterm: '중기',
  }[String(value || '')] || '스윙';
}

function actionRiskProfileLabel(value) {
  return {
    conservative: '보수형',
    balanced: '균형형',
    aggressive: '공격형',
  }[String(value || '')] || '균형형';
}

function actionObjectiveLabel(value) {
  return {
    new_entry: '신규 진입',
    add: '추가 매수',
    buy_hold: '보유 유지',
    partial_take: '부분 차익',
    full_exit: '전량 정리',
  }[String(value || '')] || '신규 진입';
}

function actionProfileParams(value) {
  if (value === 'conservative') return { buyPct: 0.04, invalidPct: 0.05, targetPct: 0.08 };
  if (value === 'aggressive') return { buyPct: 0.02, invalidPct: 0.07, targetPct: 0.14 };
  return { buyPct: 0.03, invalidPct: 0.06, targetPct: 0.10 };
}

function parseZoneNumbers(value) {
  return String(value || '')
    .split('~')
    .map((item) => Number(String(item).replace(/[^0-9.]/g, '').trim()))
    .filter((item) => Number.isFinite(item));
}

function formatPrice(value) {
  if (!Number.isFinite(Number(value))) return '-';
  return new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(Number(value));
}

function zoneDistanceText(current, low, high = low) {
  if (!Number.isFinite(current) || !Number.isFinite(low)) return '계산 불가';
  const target = Number.isFinite(high) ? (low + high) / 2 : low;
  const pct = ((target / current) - 1) * 100;
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
}

function actionRiskProfileSummary(profile, decision) {
  const risk = actionRiskProfileLabel(profile);
  const quality = Number(decision?.quality_score || 0);
  if (profile === 'conservative') {
    return `${risk} 기준으로 무효화 구간을 상대적으로 좁게 보고, 확인 이후 진입을 우선합니다. 품질 점수 ${quality.toFixed(1)} 이상에서만 공격적 행동을 정당화합니다.`;
  }
  if (profile === 'aggressive') {
    return `${risk} 기준으로 눌림 이후 빠른 재진입을 허용하지만, 변동성 확대 구간에서는 손절 기준을 명확히 두는 전제가 필요합니다.`;
  }
  return `${risk} 기준으로 추세와 이벤트를 함께 보되, 추가 확인 전 과도한 추격은 제한하는 접근입니다.`;
}

function deriveActionContext(data) {
  const decision = data.source_decision || {};
  const analysis = decision.source_analysis || {};
  const features = analysis.features || {};
  const signal = analysis.signal || {};
  const explanation = analysis.explanation || {};
  const profile = String(data.risk_profile || 'balanced');
  const params = actionProfileParams(profile);
  const close = Number(features.close || 0);
  const buyLow = close * (1 - params.buyPct);
  const buyHigh = close * (1 + params.buyPct * 0.35);
  const waitLow = close * (1 - params.buyPct * 0.35);
  const waitHigh = close * (1 + params.buyPct * 0.15);
  const chaseLow = buyHigh;
  const chaseHigh = close * (1 + Math.max(params.targetPct * 0.45, params.buyPct * 0.8));
  const invalidPrice = close * (1 - params.invalidPct);
  const target1Low = close * (1 + params.targetPct * 0.55);
  const target1High = close * (1 + params.targetPct);
  const target2Low = close * (1 + params.targetPct);
  const target2High = close * (1 + params.targetPct * 1.35);
  const riskPerShare = Math.max(close - invalidPrice, 1);
  const rewardPerShare = Math.max(((target1Low + target1High) / 2) - close, 0);
  const rewardRisk = rewardPerShare / riskPerShare;
  const bullish = decision.bullish_factors || [];
  const bearish = decision.bearish_factors || [];
  const triggers = decision.change_triggers || [];
  const timeline = decision.recent_timeline || [];
  const currentPnL = Number.isFinite(Number(data.avg_buy_price)) && Number(data.avg_buy_price) > 0
    ? ((close / Number(data.avg_buy_price)) - 1) * 100
    : null;

  const coreAssumptions = [
    `시장 체제 ${decision.market_regime || '-'}가 단기간 급격히 악화되지 않는다는 가정`,
    `${decision.sector_name || '해당 섹터'} 자금 흐름과 대장주 연동이 급격히 꺾이지 않는다는 가정`,
    `최근 공시/이벤트 해석이 ${decision.conclusion || '현재 판단'}을 뒤집을 정도로 악화되지 않는다는 가정`,
  ];
  const requiredConditions = [...(data.preconditions || [])].slice(0, 3);
  const supportingConditions = [
    bullish[0] || '추세와 수급이 동시에 유지될 것',
    decision.sector_momentum_summary?.[0] || '섹터 모멘텀이 유지될 것',
    decision.policy_macro_summary?.[0] || '거시 변수의 급격한 악화가 없을 것',
  ].filter(Boolean);
  const unconfirmedVariables = [
    triggers[0] || '신규 이벤트 발생 여부',
    timeline[0] ? `${timeline[0].event_type}: ${timeline[0].title}` : '최신 이벤트 후속 확인',
    decision.policy_macro_summary?.[1] || '거시 변수 추가 확인',
  ].filter(Boolean);
  const avoidNowReasons = [
    bearish[0] || '즉시 추격 시 손익비가 나빠질 수 있음',
    signal.risk_flags?.[0] || '리스크 플래그 존재',
    Number(features.event_volatility_score || 0) >= 0.65 ? '이벤트 당일 변동성 주의 모드' : '확인 전 성급한 진입 회피',
  ].filter(Boolean);

  const immediateAction = data.recommended_action.includes('진입') || data.recommended_action.includes('매수')
    ? `현재가 ${formatPrice(close)} 기준으로 매수 관심 구간 접근 여부를 먼저 확인합니다.`
    : data.recommended_action.includes('축소')
      ? `현재 보유 비중과 무효화 가격 ${formatPrice(invalidPrice)} 이탈 여부를 가장 먼저 점검합니다.`
      : `지금은 실행보다 확인이 우선입니다. 최근 이벤트와 거래대금 변화를 먼저 점검합니다.`;

  const step1 = requiredConditions[0] || '핵심 전제 조건을 먼저 확인합니다.';
  const step2 = requiredConditions[1] || '구간 접근 여부와 거래량을 함께 확인합니다.';
  const followIfReady = data.recommended_action.includes('매수') || data.recommended_action.includes('진입')
    ? '조건이 충족되면 한 번에 진입하지 말고 분할로 접근합니다.'
    : '조건이 충족되더라도 바로 방향 전환하지 말고 후속 확인 후 행동합니다.';
  const followIfNotReady = '조건이 미충족이면 관찰 유지로 전환하고, 다음 체크 시점까지 계획을 보류합니다.';
  const reviewTiming = [
    `기본 유효 기간: ${data.plan_validity_window || '-'}`,
    timeline[0] ? `다음 재점검: ${timeline[0].event_type} 후속 확인 시점` : '다음 재점검: 1~3거래일 내 재평가',
    Number(features.event_volatility_score || 0) >= 0.65 ? '이벤트 당일에는 장중보다 종가 기준 재점검을 우선합니다.' : '장중 급변이 없으면 종가 기준으로 재평가합니다.',
  ];

  const noPositionBullets = [
    data.no_position_plan || '미보유자는 무리한 추격보다 조건 충족 후 진입이 우선입니다.',
    `진입 조건: ${requiredConditions[0] || '추세 및 이벤트 확인'}`,
    `대기 조건: ${avoidNowReasons[0] || '손익비 재확인 필요'}`,
    `포기 조건: ${data.invalidation_zone || '무효화 구간 진입 시 보류'}`,
  ];
  const holdingBullets = [
    data.holding_plan || '보유자는 보유 지속 조건과 축소 조건을 동시에 관리해야 합니다.',
    `유지 조건: ${supportingConditions[0] || '상승 근거 유지'}`,
    `추가매수 조건: ${data.buy_interest_zone}`,
    `축소 조건: ${data.invalidation_zone}`,
  ];
  if (currentPnL !== null) {
    holdingBullets.push(`평균단가 ${formatPrice(data.avg_buy_price)} 기준 현재 손익은 ${currentPnL >= 0 ? '+' : ''}${currentPnL.toFixed(1)}%입니다.`);
  }

  const pnlRules = [
    '수익 중: 1차 목표 구간에서 일부 이익 실현 여부를 점검합니다.',
    '본전 근처: 거래량 약화나 이벤트 악화가 보이면 방어를 우선합니다.',
    '손실 중: 무효화 조건을 넘기면 미련 없이 계획을 재설정합니다.',
  ];

  const horizonPlans = [
    `단기: ${Number(decision.short_term_score || 0).toFixed(1)}점 기준으로 이벤트와 거래대금 확인이 핵심입니다.`,
    `스윙: ${Number(decision.swing_score || 0).toFixed(1)}점 기준으로 섹터 자금 유입과 추세 확인이 핵심입니다.`,
    `중기: ${Number(decision.midterm_score || 0).toFixed(1)}점 기준으로 실적 지속성과 거시 부담을 함께 봅니다.`,
  ];
  const horizonGap = [
    `주도 기간은 ${actionHorizonLabel(data.investment_horizon)}이며, 플랜 유효 기간은 ${data.plan_validity_window || '-'}입니다.`,
    '단기는 빠른 재평가, 스윙은 구간 대응, 중기는 조건 유지 여부 확인 중심으로 읽어야 합니다.',
    '기간이 길수록 구간 폭은 넓어지고, 손절/재평가 기준은 상대적으로 느슨해집니다.',
  ];

  const riskCustomization = [
    `보수형: 확인 후 진입, 무효화 구간 엄격 적용`,
    `균형형: 추세와 이벤트를 함께 확인하며 분할 접근`,
    `공격형: 눌림 이후 빠른 재진입 허용, 대신 손절 기준 명확화`,
    actionRiskProfileSummary(profile, decision),
    `현재 위험 성향 ${actionRiskProfileLabel(profile)} 기준 손실 허용 폭은 약 ${(params.invalidPct * 100).toFixed(1)}% 내외로 설계되어 있습니다.`,
  ];

  const scenarioBias = data.recommended_action.includes('축소')
    ? '하방 시나리오 우세'
    : data.recommended_action.includes('진입') || data.recommended_action.includes('매수')
      ? '상방 시나리오 우세'
      : '중립 시나리오 우세';
  const scenarioNotes = (data.scenarios || []).map((item, index) => `${item.scenario}: ${item.trigger} / ${item.action} / ${item.expected_path} / 감시 포인트 ${triggers[index] || '추세와 거래량 확인'}`);

  const rationaleTop = [
    ...(bullish.slice(0, 3)),
    ...(decision.sector_momentum_summary || []).slice(0, 1),
    ...(decision.policy_macro_summary || []).slice(0, 1),
  ].filter(Boolean).slice(0, 5);
  const contraryTop = [...bearish].filter(Boolean).slice(0, 3);
  const inheritedPoints = [
    `종목 판단 결론: ${decision.conclusion || '-'}`,
    `현재 상태: ${decision.state_label || '-'}`,
    `섹터 요약: ${(decision.sector_momentum_summary || [])[0] || '섹터 정보 없음'}`,
    `거시 요약: ${(decision.policy_macro_summary || [])[0] || '거시 요약 없음'}`,
  ];
  const marketSectorImpact = [
    `시장 체제 ${decision.market_regime || '-'}가 행동 계획의 기본 방향을 결정합니다.`,
    `섹터 점수 ${Number(decision.sector_score || 0).toFixed(1)}와 상대강도 ${Number(decision.sector_relative_strength || 0).toFixed(1)}가 진입 적극성을 조절합니다.`,
    `이벤트 점수 ${Number(decision.event_score || 0).toFixed(1)}와 품질 점수 ${Number(decision.quality_score || 0).toFixed(1)}가 실행 속도를 조절합니다.`,
  ];

  const checklist = [
    `실적 일정 확인 필요: ${timeline.some((item) => String(item.event_type || '').includes('실적')) ? '예' : '권장'}`,
    `공시 일정 확인 필요: ${timeline.some((item) => String(item.event_type || '').includes('공시')) ? '예' : '권장'}`,
    `거시 이벤트 확인 필요: ${decision.policy_macro_summary?.length ? '예' : '권장'}`,
    `거래량/변동성 확인 필요: ${Number(features.rel_volume || 0) < 1 || Number(features.volatility_20d || 0) > 0.08 ? '예' : '기본 확인'}`,
    '분할 매수 시에는 첫 진입 후 거래량 유지 여부를 다시 점검합니다.',
    `진입 후 관리 포인트: ${triggers[0] || '최신 이벤트와 무효화 가격을 같이 확인'}`,
  ];

  const invalidation = [
    `가격 기반 무효화: ${data.invalidation_zone}`,
    `이벤트 기반 무효화: ${bearish[0] || '새 악재 공시 또는 이벤트 악화'}`,
    `거시 기반 무효화: ${decision.policy_macro_summary?.[0] || '거시 환경 급변'}`,
    `실적/공시 기반 무효화: ${triggers[0] || '핵심 가정 붕괴 시 계획 재설정'}`,
    '무효화 시 대체 행동: 관찰 유지 또는 비중 축소로 전환',
  ];

  return {
    close,
    buyZone: { low: buyLow, high: buyHigh, label: `${formatPrice(buyLow)} ~ ${formatPrice(buyHigh)}` },
    waitZone: { low: waitLow, high: waitHigh, label: `${formatPrice(waitLow)} ~ ${formatPrice(waitHigh)}` },
    chaseZone: { low: chaseLow, high: chaseHigh, label: `${formatPrice(chaseLow)} ~ ${formatPrice(chaseHigh)}` },
    invalidZone: { low: invalidPrice, label: formatPrice(invalidPrice) },
    target1: { low: target1Low, high: target1High, label: `${formatPrice(target1Low)} ~ ${formatPrice(target1High)}` },
    target2: { low: target2Low, high: target2High, label: `${formatPrice(target2Low)} ~ ${formatPrice(target2High)}` },
    rewardRisk,
    immediateAction,
    coreAssumptions,
    requiredConditions,
    supportingConditions,
    unconfirmedVariables,
    avoidNowReasons,
    step1,
    step2,
    followIfReady,
    followIfNotReady,
    reviewTiming,
    noPositionBullets,
    holdingBullets,
    pnlRules,
    horizonPlans,
    horizonGap,
    riskCustomization,
    scenarioBias,
    scenarioNotes,
    rationaleTop,
    contraryTop,
    inheritedPoints,
    marketSectorImpact,
    checklist,
    invalidation,
  };
}

function renderActionReport(data) {
  const decision = data.source_decision || {};
  const analysis = decision.source_analysis || {};
  const signal = analysis.signal || {};
  const context = deriveActionContext(data);
  const summary = `${data.instrument_name}(${data.ticker})의 현재 실행 권고는 ${data.recommended_action}입니다.`;

  const topConclusion = renderCollapsibleSection(
    '상단 행동 결론',
    '누가, 언제, 어떤 강도로 움직여야 하는지에 대한 요약',
    `<div class="evidence-grid">
      <section class="report-section">
        <h4>최종 행동 권고</h4>
        <div>${renderMetricPairs([
          { label: '종목', value: `${data.instrument_name}(${data.ticker})` },
          { label: '최종 권고', value: data.recommended_action || '-' },
          { label: '행동 한 줄 요약', value: summary },
          { label: '행동 확신도', value: Number(data.action_score || 0).toFixed(1) },
          { label: '유효 투자 기간', value: data.plan_validity_window || '-' },
          { label: '위험 성향 반영', value: actionRiskProfileLabel(data.risk_profile) },
        ])}</div>
      </section>
      <section class="report-section">
        <h4>종목 판단 연결 요약</h4>
        ${renderList([
          `기반 종목 판단: ${decision.conclusion || '-'} / 상태 ${decision.state_label || '-'}`,
          `시장 체제: ${decision.market_regime || '-'} / 품질 점수 ${Number(decision.quality_score || 0).toFixed(1)}`,
          data.action_reason || '행동 이유 없음',
          actionRiskProfileSummary(data.risk_profile, decision),
        ])}
      </section>
    </div>`,
    true
  );

  const premiseSection = renderCollapsibleSection(
    '행동 판단의 전제 조건',
    '이 플랜이 성립하는 가정과 지금 바로 실행을 미뤄야 하는 이유',
    `<div class="evidence-grid">
      <section class="report-section"><h4>핵심 가정 3개</h4>${renderList(context.coreAssumptions)}</section>
      <section class="report-section"><h4>반드시 충족되어야 하는 조건</h4>${renderList(context.requiredConditions)}</section>
      <section class="report-section"><h4>충족되면 유리한 보조 조건</h4>${renderList(context.supportingConditions)}</section>
      <section class="report-section"><h4>아직 확인되지 않은 변수</h4>${renderList(context.unconfirmedVariables)}</section>
      <section class="report-section"><h4>지금 바로 실행하지 말아야 하는 이유</h4>${renderList(context.avoidNowReasons)}</section>
    </div>`,
    true
  );

  const zoneSection = renderCollapsibleSection(
    '가격 구간 설계',
    '매수 관심, 대기, 추격 경계, 무효화, 목표 구간을 구분',
    `<div>
      <div class="zone-grid">
        <article class="zone-card"><span>매수 관심 구간</span><strong>${escapeHtml(context.buyZone.label)}</strong></article>
        <article class="zone-card"><span>최적 대기 구간</span><strong>${escapeHtml(context.waitZone.label)}</strong></article>
        <article class="zone-card"><span>추격 매수 경계</span><strong>${escapeHtml(context.chaseZone.label)}</strong></article>
        <article class="zone-card"><span>무효화 구간</span><strong>${escapeHtml(context.invalidZone.label)} 하회</strong></article>
        <article class="zone-card"><span>1차 목표 구간</span><strong>${escapeHtml(context.target1.label)}</strong></article>
        <article class="zone-card"><span>2차 목표 구간</span><strong>${escapeHtml(context.target2.label)}</strong></article>
      </div>
      <div class="evidence-grid" style="margin-top:16px;">
        <section class="report-section">
          <h4>구간별 의미</h4>
          ${renderList([
            `가치 구간: ${context.buyZone.label}에서 손익비가 가장 우호적입니다.`,
            `확인 구간: ${context.waitZone.label}에서는 조건 충족 여부를 다시 확인합니다.`,
            `과열 경계 구간: ${context.chaseZone.label}부터는 추격 리스크가 커집니다.`,
            `무효화 기준: ${context.invalidZone.label} 하회 시 현재 플랜을 재설정합니다.`,
          ])}
        </section>
        <section class="report-section">
          <h4>현재가와 각 구간 사이 거리</h4>
          ${renderList([
            `현재가 -> 매수 관심 구간 중심: ${zoneDistanceText(context.close, context.buyZone.low, context.buyZone.high)}`,
            `현재가 -> 1차 목표 중심: ${zoneDistanceText(context.close, context.target1.low, context.target1.high)}`,
            `현재가 -> 2차 목표 중심: ${zoneDistanceText(context.close, context.target2.low, context.target2.high)}`,
            `현재가 -> 무효화 가격: ${zoneDistanceText(context.close, context.invalidZone.low)}`,
          ])}
        </section>
        <section class="report-section">
          <h4>위험 대비 기대보상 비율</h4>
          ${renderList([
            `1차 목표 기준 위험 대비 기대보상 비율은 ${Number(context.rewardRisk || 0).toFixed(2)}배입니다.`,
            Number(context.rewardRisk || 0) >= 1 ? '보상 구간이 손실 허용 폭보다 넓은 편입니다.' : '보상 구간이 손실 허용 폭보다 좁아 보수적 접근이 필요합니다.',
          ])}
        </section>
      </div>
    </div>`,
    true
  );

  const roadmapSection = renderCollapsibleSection(
    '실행 로드맵',
    '지금 해야 할 행동과 조건 충족 여부에 따른 후속 계획',
    `<div class="evidence-grid">
      <section class="report-section"><h4>지금 해야 할 1순위 행동</h4><p class="section-copy">${escapeHtml(context.immediateAction)}</p></section>
      <section class="report-section"><h4>1차 실행 단계</h4>${renderList([context.step1, context.step2])}</section>
      <section class="report-section"><h4>조건 충족 시 후속 행동</h4>${renderList([context.followIfReady])}</section>
      <section class="report-section"><h4>조건 미충족 시 대안 행동</h4>${renderList([context.followIfNotReady])}</section>
      <section class="report-section"><h4>재검토 시점</h4>${renderList(context.reviewTiming)}</section>
    </div>`,
    true
  );

  const holdingSection = renderCollapsibleSection(
    '보유 여부별 분리 계획',
    '미보유자와 보유자의 행동 기준을 분리',
    `<div class="evidence-grid">
      <section class="report-section"><h4>미보유자 계획</h4>${renderList(context.noPositionBullets)}</section>
      <section class="report-section"><h4>보유자 계획</h4>${renderList(context.holdingBullets)}</section>
      <section class="report-section"><h4>손익 구간별 대응 원칙</h4>${renderList(context.pnlRules)}</section>
    </div>`,
    false
  );

  const horizonSection = renderCollapsibleSection(
    '투자 기간별 계획',
    '단기, 스윙, 중기 계획과 허용 리스크 차이',
    `<div class="evidence-grid">
      <section class="report-section"><h4>기간별 실행 관점</h4>${renderList(context.horizonPlans)}</section>
      <section class="report-section"><h4>기간별 구간 및 리스크 차이</h4>${renderList(context.horizonGap)}</section>
    </div>`,
    false
  );

  const profileSection = renderCollapsibleSection(
    '위험 성향별 커스터마이즈',
    '같은 종목이라도 위험 성향에 따라 행동 계획이 어떻게 달라지는지 설명',
    `<div class="evidence-grid">
      <section class="report-section"><h4>위험 성향 반영 결과</h4>${renderList(context.riskCustomization)}</section>
      <section class="report-section"><h4>입력 파라미터 요약</h4><div>${renderMetricPairs([
        { label: '투자 기간', value: actionHorizonLabel(data.investment_horizon) },
        { label: '위험 성향', value: actionRiskProfileLabel(data.risk_profile) },
        { label: '투자 목적', value: actionObjectiveLabel(data.objective) },
        { label: '현재 보유 여부', value: data.has_position ? '보유 중' : '미보유' },
        { label: '평균단가', value: Number.isFinite(Number(data.avg_buy_price)) && Number(data.avg_buy_price) > 0 ? formatPrice(data.avg_buy_price) : '입력 없음' },
      ])}</div></section>
    </div>`,
    false
  );

  const scenarioSection = renderCollapsibleSection(
    '시나리오별 실행 전략',
    '상방, 중립, 하방 시나리오와 감시 포인트',
    `<div class="evidence-grid">
      <section class="report-section"><h4>시나리오 우세도</h4>${renderList([context.scenarioBias])}</section>
      <section class="report-section"><h4>시나리오별 실행 요약</h4>${renderList(context.scenarioNotes)}</section>
    </div>`,
    false
  );

  const rationaleSection = renderCollapsibleSection(
    '행동 근거 설명',
    '왜 이런 행동 권고가 나왔는지, 무엇이 계획을 지지하고 무엇이 반대하는지 설명',
    `<div class="evidence-grid">
      <section class="report-section"><h4>핵심 근거 Top 5</h4>${renderList(context.rationaleTop)}</section>
      <section class="report-section"><h4>반대 근거 Top 3</h4>${renderList(context.contraryTop.length ? context.contraryTop : ['뚜렷한 반대 근거는 제한적입니다.'])}</section>
      <section class="report-section"><h4>종목 판단에서 이어받은 포인트</h4>${renderList(context.inheritedPoints)}</section>
      <section class="report-section"><h4>시장/섹터 환경 영향</h4>${renderList(context.marketSectorImpact)}</section>
    </div>`,
    false
  );

  const checklistSection = renderCollapsibleSection(
    '실행 전 체크리스트 및 무효화 조건',
    '실행 전 점검 항목과 플랜을 버려야 하는 조건',
    `<div class="evidence-grid">
      <section class="report-section"><h4>실행 전 체크리스트</h4>${renderList(context.checklist)}</section>
      <section class="report-section"><h4>플랜 무효화 조건</h4>${renderList(context.invalidation)}</section>
      <section class="report-section"><h4>신뢰도 / 출처</h4>${renderList([
        `원천 분석 리포트 참조: ${decision.instrument_name || '-'} Stock Decision 기반`,
        `행동 계획 생성 기준: ${decision.market_regime || '-'} / 판단 점수 ${Number(decision.confidence_score || 0).toFixed(1)} / 행동 점수 ${Number(data.action_score || 0).toFixed(1)}`,
        `데이터 최신성: ${freshnessLabel(data.generated_at_utc)}`,
        `판단 한계: Action Planner는 Stock Decision 결과를 실행 언어로 재구성한 계획이며 자동매매 지시가 아닙니다.`,
        '데이터 출처: KIS, NAVER/NewsAPI, OpenDART, KIND, 국내외 거시 데이터, 정책/문서 배치 데이터',
      ])}</section>
    </div>`,
    false
  );

  return reportShell({
    badges: ['Action Planner 리포트', data.recommended_action, actionHorizonLabel(data.investment_horizon), actionRiskProfileLabel(data.risk_profile)],
    title: summary,
    summary: `${data.action_reason} 이 리포트는 종목 판단 결과를 실제 실행 가능한 계획으로 변환해, 전제 조건과 가격 구간, 후속 행동까지 한 번에 정리합니다.`,
    statusHtml: renderStatus(data.pipeline_status),
    body: `
      ${renderSummaryGrid([
        { label: '최종 행동', value: data.recommended_action || '-' },
        { label: '행동 점수', value: Number(data.action_score || 0).toFixed(1), tone: toneClassByScore(data.action_score) },
        { label: '기반 종목 판단', value: decision.conclusion || '-' },
        { label: '유효 기간', value: data.plan_validity_window || '-' },
      ])}
      ${topConclusion}
      ${premiseSection}
      ${zoneSection}
      ${roadmapSection}
      ${holdingSection}
      ${horizonSection}
      ${profileSection}
      ${scenarioSection}
      ${rationaleSection}
      ${checklistSection}`,
  });
}

function renderWatchReport(data) {
  const signal = data.source_signal || {};
  const summary = data.should_alert_now
    ? `${data.instrument_name}은 현재 즉시 점검이 필요한 상태입니다.`
    : `${data.instrument_name}은 현재 즉시 대응보다 관찰 유지가 우선입니다.`;

  return reportShell({
    badges: ['Watchlist Alerts 리포트', data.monitoring_state, data.should_alert_now ? '즉시 점검' : '관찰 유지'],
    title: summary,
    summary: `${data.alert_preview} 알림 리포트는 현재 시점의 이벤트와 리스크를 다시 점검해 생성됩니다.`,
    statusHtml: renderStatus(data.pipeline_status),
    body: `
      ${renderSummaryGrid([
        { label: '즉시 알림 여부', value: data.should_alert_now ? '예' : '아니오', tone: data.should_alert_now ? 'report-tone-negative' : 'report-tone-neutral' },
        { label: '모니터링 상태', value: data.monitoring_state },
        { label: '시그널 점수', value: Number(signal.score || 0).toFixed(1), tone: toneClassByScore(signal.score) },
        { label: '리스크 플래그 수', value: String((data.risk_flags || []).length) },
      ])}
      <div class="evidence-grid">
        <section class="report-section">
          <h4>즉시 확인할 트리거</h4>
          ${renderList(data.key_triggers || [])}
        </section>
        <section class="report-section">
          <h4>리스크 플래그</h4>
          ${renderList(data.risk_flags || [])}
        </section>
        <section class="report-section">
          <h4>관찰 촉매</h4>
          ${renderList(data.catalyst_watchlist || [])}
        </section>
        <section class="report-section">
          <h4>활용 데이터 요약</h4>
          <div>${renderMetricPairs([
            { label: '알림 판단', value: data.should_alert_now ? '즉시 대응 필요' : '관찰 유지' },
            { label: '이벤트 근거', value: `${data.source_analysis?.explanation?.document_summaries?.length || 0}건 반영` },
            { label: '시그널 유형', value: signal.signal_type || '-' },
            { label: '시그널 방향', value: signal.direction || '-' },
          ])}</div>
        </section>
      </div>
      <section class="report-section">
        <h4>알림 메시지 미리보기</h4>
        <p class="section-copy">${escapeHtml(data.alert_preview)}</p>
      </section>
      <section class="report-section">
        <h4>근거 데이터 출처</h4>
        <p class="data-footnote">Watchlist Alerts는 시세, 뉴스, 공시, 재무제표, 정책/거시 데이터와 알림 채널 설정을 결합해 현재 시점의 대응 필요 여부를 계산합니다.</p>
      </section>`,
  });
}

function renderSubscriptions(items) {
  const target = qs('#subscription-list');
  if (!target) return;
  if (!items || items.length === 0) {
    target.innerHTML = `<div class="report-empty">${T.noSubs}</div>`;
    return;
  }
  target.innerHTML = items
    .map(
      (item) => `
      <article class="subscription-card">
        <div>
          <div class="signal-chip-row">
            <span class="signal-chip">${escapeHtml(item.channel)}</span>
            <span class="signal-chip">저장형 워치리스트</span>
          </div>
          <h4>${escapeHtml(item.instrument_name)} (${escapeHtml(item.ticker)})</h4>
          <p>${escapeHtml(item.notes || '메모 없음')}</p>
          <p class="subscription-note">생성 시각: ${escapeHtml(formatDate(item.created_at_utc))}</p>
        </div>
        <button class="btn tertiary subscription-delete" data-ticker="${escapeHtml(item.ticker)}" type="button">삭제</button>
      </article>`
    )
    .join('');

  [...target.querySelectorAll('.subscription-delete')].forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        await request('DELETE', `/api/v1/watchlist-alerts/subscriptions/${encodeURIComponent(button.dataset.ticker)}?channel=telegram`);
        qs('#subscription-output').textContent = `${button.dataset.ticker} 워치리스트를 삭제했습니다.`;
        await refreshSubscriptions();
      } catch (err) {
        qs('#subscription-output').textContent = formatError(err);
      }
    });
  });
}

async function refreshHealth() {
  const target = qs('#health-status');
  try {
    const data = await request('GET', '/api/v1/health');
    target.textContent = `${T.ok} | ${formatDate(data.time_utc)}`;
  } catch (err) {
    target.textContent = `${T.error} | ${formatError(err)}`;
  }
}

async function refreshSubscriptions() {
  const data = await request('GET', '/api/v1/watchlist-alerts/subscriptions');
  renderSubscriptions(data);
}

function openSheet({ kicker, title, templateId, submitLabel, onSubmit }) {
  const backdrop = qs('#sheet-backdrop');
  const sheet = qs('#sheet');
  const body = qs('#sheet-body');
  qs('#sheet-kicker').textContent = kicker;
  qs('#sheet-title').textContent = title;
  const template = qs(templateId);
  const fragment = template.content.cloneNode(true);
  const form = fragment.querySelector('form');
  const submitButton = fragment.querySelector('button[type="submit"]');
  if (submitButton && submitLabel) {
    submitButton.textContent = submitLabel;
  }
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await onSubmit(form);
      closeSheet();
    } catch (err) {
      const feedback = document.createElement('p');
      feedback.className = 'section-copy';
      feedback.textContent = formatError(err);
      const old = body.querySelector('.section-copy');
      if (old) old.remove();
      body.appendChild(feedback);
    }
  });
  body.innerHTML = '';
  body.appendChild(fragment);
  backdrop.classList.remove('hidden');
  sheet.classList.remove('hidden');
  sheet.setAttribute('aria-hidden', 'false');
}

function closeSheet() {
  qs('#sheet-backdrop').classList.add('hidden');
  qs('#sheet').classList.add('hidden');
  qs('#sheet').setAttribute('aria-hidden', 'true');
  qs('#sheet-body').innerHTML = '';
}

function openHtmlSheet({ kicker, title, html }) {
  const backdrop = qs('#sheet-backdrop');
  const sheet = qs('#sheet');
  const body = qs('#sheet-body');
  qs('#sheet-kicker').textContent = kicker;
  qs('#sheet-title').textContent = title;
  body.innerHTML = html;
  backdrop.classList.remove('hidden');
  sheet.classList.remove('hidden');
  sheet.setAttribute('aria-hidden', 'false');
}

function readRequired(form, name) {
  const value = String(new FormData(form).get(name) || '').trim();
  if (!value) {
    throw new Error(T.inputRequired);
  }
  return value;
}

async function runMarket() {
  mountLoading('market');
  try {
    const data = await request('GET', '/api/v1/market-regime/overview');
    mountReport('market', renderMarketReport(data));
  } catch (err) {
    mountError('market', err);
  }
}

async function runStock(form) {
  mountLoading('stock');
  const formData = new FormData(form);
  const ticker = readRequired(form, 'ticker');
  const params = new URLSearchParams();
  if (formData.get('as_of_date')) params.set('as_of_date', String(formData.get('as_of_date')));
  if (formData.get('lookback_days')) params.set('lookback_days', String(formData.get('lookback_days')));
  const url = `/api/v1/stock-decision/${encodeURIComponent(ticker)}${params.size ? `?${params.toString()}` : ''}`;
  try {
    const data = await request('GET', url);
    mountReport('stock', renderStockReport(data));
  } catch (err) {
    mountError('stock', err);
    throw err;
  }
}

async function runAction(form) {
  mountLoading('action');
  const formData = new FormData(form);
  const avgBuyRaw = String(formData.get('avg_buy_price') || '').trim();
  const body = {
    ticker_or_name: readRequired(form, 'ticker_or_name'),
    investment_horizon: String(formData.get('investment_horizon') || 'swing'),
    risk_profile: String(formData.get('risk_profile') || 'balanced'),
    objective: String(formData.get('objective') || 'new_entry'),
    has_position: formData.get('has_position') === 'on',
    avg_buy_price: avgBuyRaw ? Number(avgBuyRaw) : null,
  };
  try {
    const data = await request('POST', '/api/v1/action-planner/analyze', body);
    mountReport('action', renderActionReport(data));
  } catch (err) {
    mountError('action', err);
    throw err;
  }
}

async function runWatch(form) {
  mountLoading('watch');
  const formData = new FormData(form);
  const body = {
    ticker_or_name: readRequired(form, 'ticker_or_name'),
    notify: formData.get('notify') === 'on',
    force_send: formData.get('force_send') === 'on',
  };
  try {
    const data = await request('POST', '/api/v1/watchlist-alerts/check', body);
    mountReport('watch', renderWatchReport(data));
  } catch (err) {
    mountError('watch', err);
    throw err;
  }
}

async function runSubscription(form) {
  const formData = new FormData(form);
  const body = {
    ticker_or_name: readRequired(form, 'ticker_or_name'),
    notes: String(formData.get('notes') || '').trim(),
    channel: 'telegram',
  };
  const data = await request('POST', '/api/v1/watchlist-alerts/subscriptions', body);
  qs('#subscription-output').textContent = `${data.instrument_name} (${data.ticker}) 워치리스트 저장이 완료되었습니다.`;
  await refreshSubscriptions();
}

async function runPreview(form) {
  const formData = new FormData(form);
  const data = await request('POST', '/api/v1/ingestion/crawl/preview', {
    source_id: String(formData.get('source_id') || ''),
    max_chars: 6000,
  });
  qs('#preview-output').textContent = JSON.stringify(data, null, 2);
}

async function runBatch(url, body) {
  const output = qs('#batch-output');
  output.textContent = '배치를 실행하는 중입니다...';
  try {
    const data = await request('POST', url, body);
    output.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    output.textContent = formatError(err);
  }
}

function bindLaunchers() {
  qs('#launch-market').addEventListener('click', runMarket);
  qs('#launch-stock').addEventListener('click', () =>
    openSheet({
      kicker: 'Stock Decision',
      title: '종목 판단 파라미터 입력',
      templateId: '#tpl-stock-form',
      submitLabel: '종목 판단 리포트 생성',
      onSubmit: runStock,
    })
  );
  qs('#launch-action').addEventListener('click', () =>
    openSheet({
      kicker: 'Action Planner',
      title: '행동 계획 파라미터 입력',
      templateId: '#tpl-action-form',
      submitLabel: '행동 계획 리포트 생성',
      onSubmit: runAction,
    })
  );
  qs('#launch-watch').addEventListener('click', () =>
    openSheet({
      kicker: 'Watchlist Alerts',
      title: '관찰 알림 점검 조건 입력',
      templateId: '#tpl-watch-form',
      submitLabel: '관찰 알림 리포트 생성',
      onSubmit: runWatch,
    })
  );
  qs('#launch-subscription').addEventListener('click', () =>
    openSheet({
      kicker: '저장형 워치리스트',
      title: '관찰 종목 저장',
      templateId: '#tpl-subscription-form',
      submitLabel: '워치리스트 저장',
      onSubmit: runSubscription,
    })
  );
  qs('#launch-preview').addEventListener('click', () =>
    openSheet({
      kicker: 'Source Preview',
      title: '소스 미리보기 파라미터 입력',
      templateId: '#tpl-preview-form',
      submitLabel: '소스 미리보기 실행',
      onSubmit: runPreview,
    })
  );
}

function bindOperators() {
  qs('#refresh-health').addEventListener('click', refreshHealth);
  qs('#refresh-subscriptions').addEventListener('click', refreshSubscriptions);
  qs('#toggle-admin').addEventListener('click', () => qs('#admin-body').classList.toggle('hidden'));
  qs('#sheet-close').addEventListener('click', closeSheet);
  qs('#sheet-backdrop').addEventListener('click', closeSheet);
  qs('#run-kind').addEventListener('click', () => runBatch('/api/v1/batch/kind/disclosures', { ticker_or_name: '005930', max_items: 3 }));
  qs('#run-policy').addEventListener('click', () => runBatch('/api/v1/batch/policy-briefing', { max_items: 3 }));
  qs('#run-bok').addEventListener('click', () => runBatch('/api/v1/batch/bok/publications', { max_items: 3 }));
  qs('#run-naver-headlines').addEventListener('click', () => runBatch('/api/v1/batch/naver/headlines', { max_items: 10 }));
  qs('#run-market-snapshot').addEventListener('click', () => runBatch('/api/v1/batch/market-regime-snapshot', { max_items: 1 }));
  document.addEventListener('click', (event) => {
    const trigger = event.target instanceof Element ? event.target.closest('[data-headline-brief-id]') : null;
    if (!trigger) return;
    const detailId = trigger.getAttribute('data-headline-brief-id');
    if (!detailId) return;
    const item = headlineBriefStore.get(detailId);
    if (!item) return;
    openHtmlSheet({
      kicker: 'Market Regime 헤드라인 상세',
      title: `${item.section_label || item.section_key || '헤드라인'} 영향 상세`,
      html: renderHeadlineBriefDetail(item),
    });
  });
}

function boot() {
  bindLaunchers();
  bindOperators();
  refreshHealth();
  refreshSubscriptions();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot, { once: true });
} else {
  boot();
}
