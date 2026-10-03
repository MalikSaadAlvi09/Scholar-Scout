/**
 * ScholarScout - Main Frontend Application Controller
 * Provides interactive dashboard logic for all 10 academic intelligence screens,
 * real-time research job monitoring, funding & faculty discovery, shortlisting,
 * personal notes persistence, outreach email management, and settings diagnostics.
 */

// Global Application State
const State = {
  activeTab: 'tab-overview',
  activeJobId: null,
  activeJobPollInterval: null,
  profile: null,
  profileVersions: [],
  settings: null,
  overviewData: null,
  
  // Data Catalogs
  universities: [],
  scholarships: [],
  professors: [],
  drafts: [],
  jobs: [],
  shortlist: {
    universities: [],
    scholarships: [],
    professors: [],
    total_count: 0
  },
  
  // Controlled Sending & Outreach State
  sendingSettings: { sending_master_enabled: false },
  emailAccounts: [],
  selectedAccountId: 1,
  outreachSubview: 'viewDraftsEditor',
  outboundQueue: [],
  doNotContactList: [],
  emailAuditLogs: [],
  selectedDraftIds: new Set(),
  outreachSettings: null,
  activeDraftId: null,
  activeDraft: null,
  draftsStatusFilter: 'all',

  // Pagination States
  pagination: {
    universities: { page: 1, pageSize: 10, total: 0 },
    scholarships: { page: 1, pageSize: 8, total: 0 },
    professors: { page: 1, pageSize: 8, total: 0 }
  },
  
  // Active Filter Sets
  filters: {
    jobs: { status: 'all', type: 'all', search: '' },
    universities: { country: 'all', search: '', shortlistedOnly: false, sortBy: 'name' },
    scholarships: { minFitScore: 80, category: 'all', eligibility: 'all', opportunityStatus: 'all', country: 'all', degreeLevel: 'all', search: '', shortlistedOnly: false, sortBy: 'fit_score' },
    professors: { minMatchScore: 80, recruitment: 'all', email: 'all', department: '', search: '', shortlistedOnly: false, sortBy: 'match_score' },
    drafts: { search: '', type: 'all' },
    shortlist: { subTab: 'all' }
  },
  
  // Research Setup State
  researchMode: 'discovery', // 'discovery' | 'single' | 'batch'
  discoveryQueries: [],
  discoveredLeads: [],
  globalCountries: [],
  
  // Fact extraction from CV
  extractedFacts: {}
};

// ============================================================================
// 1. INITIALIZATION & ROUTING
// ============================================================================

document.addEventListener('DOMContentLoaded', async () => {
  setupNavigation();
  setupModals();
  setupResearchSetupModeSwitcher();
  setupEventListeners();
  setupFiltersAndSearch();
  setupCountryRibbon();
  setupCvUpload();
  setupControlledSending();
  setupNvidiaMultiKeyAndModelSelector();
  setupGatheringAgent();
  
  // Initial health, countries, profile, and settings load
  await checkHealth();
  await loadGlobalCountries();
  await loadProfile();
  await loadSettings();
  await loadSendingSettings();
  await loadEmailAccounts();
  await refreshAllData();
  await loadScheduledRechecks();
  await loadDbBackups();
  
  // Global periodic background job poller (every 6 seconds)
  setInterval(async () => {
    if (State.activeTab === 'tab-overview' || State.activeTab === 'tab-jobs') {
      await refreshJobsData();
    }
  }, 6000);
});

// Setup sidebar navigation and mobile toggle
function setupNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const targetTab = item.getAttribute('data-tab');
      switchTab(targetTab);
    });
    // Keyboard navigation (Enter / Space)
    item.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        const targetTab = item.getAttribute('data-tab');
        switchTab(targetTab);
      }
    });
  });

  // Header profile badge click
  document.getElementById('headerProfileBadge')?.addEventListener('click', () => {
    switchTab('tab-profile');
  });

  // Mobile menu drawer toggle
  const mobileToggle = document.getElementById('mobileNavToggle');
  const sidebar = document.getElementById('appSidebar');
  if (mobileToggle && sidebar) {
    mobileToggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
    });
  }

  // Overview quick action cards
  document.getElementById('metricCardJobs')?.addEventListener('click', () => switchTab('tab-jobs'));
  document.getElementById('metricCardUnivs')?.addEventListener('click', () => switchTab('tab-universities'));
  document.getElementById('metricCardAwards')?.addEventListener('click', () => switchTab('tab-scholarships'));
  document.getElementById('metricCardProfessors')?.addEventListener('click', () => switchTab('tab-professors'));
  document.getElementById('metricCardShortlist')?.addEventListener('click', () => switchTab('tab-shortlist'));
  document.getElementById('metricCardDrafts')?.addEventListener('click', () => switchTab('tab-drafts'));

  document.getElementById('overviewNewResearchBtn')?.addEventListener('click', () => switchTab('tab-research'));
  document.getElementById('ovEmptyLaunchBtn')?.addEventListener('click', () => switchTab('tab-research'));
  document.getElementById('ovViewAllJobsBtn')?.addEventListener('click', () => switchTab('tab-jobs'));
  document.getElementById('ovViewAllFundingBtn')?.addEventListener('click', () => switchTab('tab-scholarships'));
  document.getElementById('ovViewAllFacultyBtn')?.addEventListener('click', () => switchTab('tab-professors'));
  document.getElementById('jobsNewRunBtn')?.addEventListener('click', () => switchTab('tab-research'));
  document.getElementById('jobsEmptyStartBtn')?.addEventListener('click', () => switchTab('tab-research'));
}

function switchTab(tabId) {
  if (!tabId) return;
  State.activeTab = tabId;

  // Close mobile sidebar on navigation
  document.getElementById('appSidebar')?.classList.remove('open');

  // Update nav-item active states
  document.querySelectorAll('.nav-item').forEach(el => {
    const isTarget = el.getAttribute('data-tab') === tabId;
    el.classList.toggle('active', isTarget);
    el.setAttribute('aria-selected', isTarget ? 'true' : 'false');
  });

  // Show selected tab content section
  document.querySelectorAll('.tab-content').forEach(el => {
    const isTarget = el.id === tabId;
    el.classList.toggle('active', isTarget);
  });

  // Scroll to top of content area
  const mainContent = document.getElementById('mainContent');
  if (mainContent) mainContent.scrollTop = 0;

  // Trigger screen-specific refresh
  if (tabId === 'tab-overview') loadOverview();
  if (tabId === 'tab-jobs') loadJobs();
  if (tabId === 'tab-universities') loadUniversities();
  if (tabId === 'tab-scholarships') loadScholarships();
  if (tabId === 'tab-professors') loadProfessors();
  if (tabId === 'tab-shortlist') loadShortlist();
  if (tabId === 'tab-drafts') {
    loadDrafts();
    loadOutreachSettings();
  }
  if (tabId === 'tab-settings') {
    loadSettings();
    loadScheduledRechecks();
    loadDbBackups();
  }
}

// Refresh all application data
async function refreshAllData() {
  await Promise.allSettled([
    loadOverview(),
    loadJobs(),
    loadUniversities(),
    loadScholarships(),
    loadProfessors(),
    loadShortlist(),
    loadDrafts(),
    loadOutreachSettings()
  ]);
}

// ============================================================================
// 2. HEALTH & SYSTEM DIAGNOSTICS
// ============================================================================

async function checkHealth() {
  try {
    const res = await fetch('/api/health');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    
    // LLM Status Pill
    const llmDot = document.getElementById('llmDot');
    const llmText = document.getElementById('llmStatusText');
    if (data.llm_configured) {
      if (llmDot) llmDot.className = 'status-dot healthy';
      if (llmText) llmText.innerText = `AI: ${data.model_name.split('/').pop() || 'Configured'}`;
    } else {
      if (llmDot) llmDot.className = 'status-dot warning';
      if (llmText) llmText.innerText = 'AI: Unconfigured';
    }

    // Search Provider Pill
    const searchDot = document.getElementById('searchDot');
    const searchText = document.getElementById('searchStatusText');
    if (data.search_configured) {
      if (searchDot) searchDot.className = 'status-dot healthy';
      if (searchText) searchText.innerText = `Search: ${capitalize(data.search_provider)}`;
    } else {
      if (searchDot) searchDot.className = 'status-dot active';
      if (searchText) searchText.innerText = 'Search: Direct';
    }

    // System platform info
    const sysPlatform = document.getElementById('sysPlatform');
    if (sysPlatform) sysPlatform.innerText = data.platform || 'Server Platform';

    // Provider badges in setup
    updateProviderBadgesInSetup(data.search_provider, data.search_configured);
  } catch (err) {
    const healthDot = document.getElementById('healthDot');
    const healthText = document.getElementById('healthStatusText');
    if (healthDot) healthDot.className = 'status-dot error';
    if (healthText) healthText.innerText = 'Backend Offline';
  }
}

function updateProviderBadgesInSetup(providerName, isConfigured) {
  const titleEl = document.getElementById('providerDisplayTitle');
  const subtitleEl = document.getElementById('providerDisplaySubtitle');
  const badgeEl = document.getElementById('discoveryProviderBadge');
  const alertEl = document.getElementById('unconfiguredProviderAlert');

  const names = {
    tavily: 'Tavily Search API (AI-Optimized)',
    serpapi: 'SerpAPI (Google Search)',
    brave: 'Brave Search API',
    null: 'Direct University URL Mode Only'
  };

  const displayName = names[providerName] || capitalize(providerName || 'Search');

  if (titleEl) titleEl.innerText = `Search Provider: ${displayName}`;
  if (badgeEl) {
    badgeEl.innerText = isConfigured ? `${displayName} (Active)` : `${displayName} (Unconfigured)`;
    badgeEl.className = isConfigured ? 'badge badge-primary' : 'badge badge-warning';
  }
  if (alertEl) {
    alertEl.classList.toggle('hidden', isConfigured || providerName === 'null');
  }
}

// ============================================================================
// 3. SCREEN 1: EXECUTIVE OVERVIEW
// ============================================================================

async function loadOverview() {
  try {
    const res = await fetch('/api/overview');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    State.overviewData = data;

    // 1. Update Top Metric Cards (Actual Database Data)
    const stats = data.stats || {};
    setText('ovStatTotalJobs', stats.jobs_count || 0);
    setText('ovStatActiveJobs', `${stats.active_jobs || 0} active in queue`);
    
    setText('ovStatTotalUnivs', data.total_universities_tracked || 0);
    setText('ovStatTotalAwards', stats.scholarships_count || 0);
    setText('ovStatHighFitAwards', `${stats.top_scholarships || 0} high-fit (≥80%)`);
    
    setText('ovStatTotalFaculty', stats.professors_count || 0);
    setText('ovStatVerifiedEmails', `${data.verified_emails_count || 0} verified emails`);
    
    const sl = data.shortlist_counts || {};
    setText('ovStatTotalShortlist', sl.total || 0);
    setText('ovStatTotalDrafts', stats.drafts_count || 0);

    // Telemetry Box
    setText('ovStatTokens', Number(stats.total_llm_tokens || 0).toLocaleString());
    setText('ovStatLlmReqs', Number(stats.total_llm_requests || 0).toLocaleString());
    
    if (State.profile) {
      setText('ovStatProfileName', `${State.profile.name || State.profile.full_name || 'Candidate'} (v${State.profile.version || 1})`);
    }

    // 2. Render Recent Jobs Table
    renderOverviewRecentJobs(data.recent_jobs || []);

    // 3. Render Top Funding Opportunities Spotlight
    renderOverviewTopScholarships(data.top_scholarships || []);

    // 4. Render Top Faculty Matches Spotlight
    renderOverviewTopFaculty(data.top_professors || []);

  } catch (err) {
    console.error('Failed to load overview:', err);
  }
}

function renderOverviewRecentJobs(jobs) {
  const tbody = document.getElementById('ovRecentJobsTableBody');
  const emptyState = document.getElementById('ovJobsEmptyState');
  const table = document.getElementById('ovRecentJobsTable');
  if (!tbody) return;

  if (!jobs || jobs.length === 0) {
    tbody.innerHTML = '';
    table?.classList.add('hidden');
    emptyState?.classList.remove('hidden');
    return;
  }

  table?.classList.remove('hidden');
  emptyState?.classList.add('hidden');

  tbody.innerHTML = jobs.map(job => {
    const statusBadge = getJobStatusBadge(job.status);
    const targetDisplay = job.job_type === 'discovery_job' 
      ? `<strong>✨ Autonomous Discovery</strong><br><span class="text-xs text-muted">${job.university_name || 'Search Provider'}</span>`
      : `<strong>${escapeHtml(job.university_name || 'University')}</strong><br><span class="text-xs font-mono text-muted">${escapeHtml(truncate(job.university_url, 35))}</span>`;

    return `
      <tr>
        <td class="font-mono">#${job.id}</td>
        <td>${targetDisplay}</td>
        <td><span class="badge badge-navy">${escapeHtml(capitalize(job.scope || 'all'))}</span></td>
        <td>${statusBadge}</td>
        <td class="font-mono">${job.pages_crawled || 0}</td>
        <td class="font-mono text-teal font-semibold">${job.scholarships_count || 0}</td>
        <td class="font-mono font-semibold">${job.professors_count || 0}</td>
        <td>
          <button type="button" class="btn btn-sm btn-secondary" onclick="viewJobCoverageModal(${job.id})">📊 Report</button>
        </td>
      </tr>
    `;
  }).join('');
}

function renderOverviewTopScholarships(awards) {
  const container = document.getElementById('ovTopAwardsList');
  const emptyState = document.getElementById('ovFundingEmptyState');
  if (!container) return;

  if (!awards || awards.length === 0) {
    container.innerHTML = '';
    emptyState?.classList.remove('hidden');
    return;
  }

  emptyState?.classList.add('hidden');

  container.innerHTML = awards.map(s => {
    const fitBadge = getFitScoreBadge(s.fit_score);
    const catBadge = getFundingCategoryBadge(s.funding_category);
    const isShortlisted = Boolean(s.is_shortlisted);

    return `
      <div class="scholarship-card mb-2">
        <div class="scholarship-header-row">
          <div class="scholarship-title-group">
            <h4>${escapeHtml(s.title)}</h4>
            <div class="scholarship-univ-meta">
              <span>🏛️ ${escapeHtml(s.university || 'University')}</span>
              <span>📍 ${escapeHtml(s.country || 'Unknown')}</span>
              <span>🎓 ${escapeHtml(s.degree_level || 'Ph.D.')}</span>
            </div>
          </div>
          <div class="action-btn-group">
            <button type="button" class="star-btn ${isShortlisted ? 'active' : ''}" onclick="toggleScholarshipShortlist(${s.id})" title="${isShortlisted ? 'Remove from Shortlist' : 'Add to Shortlist'}">
              ${isShortlisted ? '⭐ Shortlisted' : '☆ Shortlist'}
            </button>
          </div>
        </div>

        <div class="scholarship-badges-row">
          ${fitBadge}
          ${catBadge}
          <span class="badge badge-neutral">💰 ${escapeHtml(s.amount || 'Funding Available')}</span>
        </div>

        ${s.fit_reason ? `<div class="fit-reason-box">💡 <strong>Fit Reason:</strong> ${escapeHtml(s.fit_reason)}</div>` : ''}

        <div class="scholarship-footer-actions">
          <button type="button" class="btn btn-link btn-sm p-0" onclick="openEvidenceModal('${escapeJsString(s.title)}', '${escapeJsString(s.source_url)}', '${escapeJsString(s.evidence_snippet)}', ${escapeJsObject(s.claims_evidence)})">
            🔍 View Evidence Snippet
          </button>
          <a href="${escapeHtml(s.official_url || s.source_url)}" target="_blank" rel="noopener" class="btn btn-sm btn-secondary">
            🌐 Official Source ↗
          </a>
        </div>
      </div>
    `;
  }).join('');
}

function renderOverviewTopFaculty(faculty) {
  const container = document.getElementById('ovTopFacultyList');
  const emptyState = document.getElementById('ovFacultyEmptyState');
  if (!container) return;

  if (!faculty || faculty.length === 0) {
    container.innerHTML = '';
    emptyState?.classList.remove('hidden');
    return;
  }

  emptyState?.classList.add('hidden');

  container.innerHTML = faculty.map(p => {
    const matchBadge = getMatchScoreBadge(p.match_score);
    const recBadge = getRecruitmentBadge(p.recruitment_status);
    const hasEmail = p.email && p.email.includes('@') && !['Not found', 'Unknown', 'None'].includes(p.email);
    const isShortlisted = Boolean(p.is_shortlisted);

    return `
      <div class="professor-card mb-2">
        <div class="professor-header-row">
          <div class="professor-name-group">
            <h4>${escapeHtml(p.name)}</h4>
            <div class="professor-dept-univ">
              ${escapeHtml(p.title || 'Faculty Member')} • ${escapeHtml(p.university || 'University')}
            </div>
          </div>
          <button type="button" class="star-btn ${isShortlisted ? 'active' : ''}" onclick="toggleProfessorShortlist(${p.id})">
            ${isShortlisted ? '⭐' : '☆'}
          </button>
        </div>

        <div class="rubric-score-pills">
          ${matchBadge}
          ${recBadge}
          ${hasEmail ? `<span class="badge badge-teal">📧 ${escapeHtml(p.email)}</span>` : '<span class="badge badge-neutral">Email unlisted</span>'}
        </div>

        <div class="text-xs text-muted mb-2">
          <strong>Research Interests:</strong> ${escapeHtml(truncate(p.research_interests, 95))}
        </div>

        <div class="scholarship-footer-actions">
          <button type="button" class="btn btn-sm btn-secondary" onclick="openEvidenceModal('${escapeJsString(p.name)}', '${escapeJsString(p.source_url)}', '${escapeJsString(p.evidence_snippet)}', {})">
            🔍 Evidence
          </button>
          <button type="button" class="btn btn-sm btn-primary" onclick="initEmailDraftForProfessor(${p.id}, '${escapeJsString(p.name)}', '${escapeJsString(p.email)}', '${escapeJsString(p.university)}', '${escapeJsString(p.research_interests)}')">
            ✉️ Draft Inquiry
          </button>
        </div>
      </div>
    `;
  }).join('');
}

// ============================================================================
// 4. SCREEN 2: ACADEMIC PROFILE & CV EXTRACTION
// ============================================================================

async function loadProfile() {
  try {
    const res = await fetch('/api/profile');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const p = await res.json();
    State.profile = p;

    // Update Header Pill and Profile Version Badge
    const displayName = p.name || p.full_name || 'Candidate';
    setText('headerProfileName', displayName);
    setText('currentVersionBadge', `v${p.version || 1} Active`);
    setText('navProfileVersion', `v${p.version || 1}`);

    // Populate Form Inputs
    setInputValue('prof_name', displayName);
    setInputValue('prof_nationality', p.nationality || '');
    setInputValue('prof_country_of_origin', p.country_of_origin || p.nationality || '');
    setInputValue('prof_current_residence', p.current_residence || '');

    setInputValue('prof_current_degree', p.current_degree || '');
    setInputValue('prof_current_institution', p.current_institution || '');
    setInputValue('prof_current_major', p.current_major || '');
    setInputValue('prof_gpa', p.gpa || '');
    setInputValue('prof_graduation_date', p.graduation_date || '');

    setInputValue('prof_target_degree', p.target_degree || 'Ph.D.');
    setInputValue('prof_broad_subject', p.broad_subject || p.current_major || '');
    setInputValue('prof_target_field', p.target_field || p.broad_subject || '');
    setInputValue('prof_intended_intake', p.intended_intake || '');
    setInputValue('prof_research_interests', p.specific_interests || p.research_interests || '');

    const prefCountries = Array.isArray(p.preferred_countries) ? p.preferred_countries.join(', ') : (p.preferred_countries || '');
    const exclCountries = Array.isArray(p.excluded_countries) ? p.excluded_countries.join(', ') : (p.excluded_countries || '');
    setInputValue('prof_preferred_countries', prefCountries);
    setInputValue('prof_excluded_countries', exclCountries);

    setInputValue('prof_english_tests', p.english_tests || '');
    setInputValue('prof_technical_skills', p.technical_skills || '');
    setInputValue('prof_publications', p.publications || '');
    setInputValue('prof_research_experience', p.research_experience || '');
    setInputValue('prof_funding_notes', p.funding_notes || '');

    setInputValue('prof_portfolio_url', p.portfolio_url || '');
    setInputValue('prof_github_url', p.github_url || '');
    setInputValue('prof_website_url', p.website_url || '');

    // Funding needs checkboxes
    const fundingNeeds = Array.isArray(p.funding_needs) ? p.funding_needs : [];
    setChecked('fund_need_tuition', fundingNeeds.includes('full_tuition'));
    setChecked('fund_need_stipend', fundingNeeds.includes('living_stipend'));
    setChecked('fund_need_insurance', fundingNeeds.includes('health_insurance'));
    setChecked('fund_need_travel', fundingNeeds.includes('travel_grant'));

    // Update completeness meter
    updateProfileCompletenessUI();

    // Update setup mode summary pills
    updateDiscoverySummaryPills(p);

    // Load version history
    await loadVersionHistory();

  } catch (err) {
    console.error('Failed to load profile:', err);
  }
}

function updateProfileCompletenessUI() {
  const p = State.profile;
  if (!p) return;

  const checks = [
    { label: 'Full Legal Name', done: Boolean(p.name || p.full_name) },
    { label: 'Target Degree Level', done: Boolean(p.target_degree) },
    { label: 'Major & Academic GPA', done: Boolean(p.current_major && p.gpa && p.gpa !== 'Unknown') },
    { label: 'Specific Research Interests', done: Boolean((p.specific_interests || p.research_interests) && (p.specific_interests || p.research_interests).length > 10) },
    { label: 'Preferred Destination Countries', done: Boolean(p.preferred_countries && p.preferred_countries.length > 0) },
    { label: 'English / Standardized Test Scores', done: Boolean(p.english_tests && p.english_tests !== 'Unknown') },
    { label: 'Research Experience or Publications', done: Boolean((p.research_experience || p.publications) && (p.research_experience || p.publications).length > 15) }
  ];

  const completedCount = checks.filter(c => c.done).length;
  const pct = Math.round((completedCount / checks.length) * 100);

  const bar = document.getElementById('profileProgressBar');
  const badge = document.getElementById('profileCompletenessBadge');
  const list = document.getElementById('profileChecklist');

  if (bar) bar.style.width = `${pct}%`;
  if (badge) badge.innerText = `${pct}% Complete`;

  if (list) {
    list.innerHTML = checks.map(c => `
      <li class="checklist-item ${c.done ? 'done' : ''}">
        <span>${c.done ? '✅' : '⚪'}</span>
        <span>${escapeHtml(c.label)}</span>
      </li>
    `).join('');
  }
}

function updateDiscoverySummaryPills(p) {
  setText('discProfDegree', `Degree: ${p.target_degree || 'Ph.D.'}`);
  setText('discProfSubject', `Subject: ${p.broad_subject || p.current_major || 'Computer Science'}`);
  const countries = Array.isArray(p.preferred_countries) ? p.preferred_countries.join(', ') : (p.preferred_countries || 'Global');
  setText('discProfCountries', `Countries: ${truncate(countries, 30)}`);
  setText('discProfIntake', `Intake: ${p.intended_intake || 'Upcoming'}`);
}

async function loadVersionHistory() {
  try {
    const res = await fetch('/api/profile/versions');
    if (!res.ok) return;
    const versions = await res.json();
    State.profileVersions = versions;

    const listEl = document.getElementById('profileVersionHistoryList');
    if (listEl) {
      if (!versions || versions.length === 0) {
        listEl.innerHTML = '<span class="text-xs text-muted">Initial version v1</span>';
      } else {
        listEl.innerHTML = versions.slice(0, 5).map(v => `
          <div class="version-row text-xs py-1 border-b flex-row-between">
            <strong>Snapshot Version #${v.version}</strong>
            <span class="text-muted">${formatDate(v.created_at)}</span>
          </div>
        `).join('');
      }
    }
  } catch (err) {
    console.error('Failed to load version history:', err);
  }
}

// Save Profile Form Submission
document.getElementById('academicProfileForm')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const statusEl = document.getElementById('profileSaveStatusText');
  const btn = document.getElementById('saveProfileSubmitBtn');
  if (btn) btn.disabled = true;
  if (statusEl) statusEl.innerText = 'Saving profile version...';

  try {
    const preferredCountries = (getInputValue('prof_preferred_countries') || '')
      .split(',')
      .map(s => s.trim())
      .filter(Boolean);

    const excludedCountries = (getInputValue('prof_excluded_countries') || '')
      .split(',')
      .map(s => s.trim())
      .filter(Boolean);

    const fundingNeeds = [];
    if (getChecked('fund_need_tuition')) fundingNeeds.push('full_tuition');
    if (getChecked('fund_need_stipend')) fundingNeeds.push('living_stipend');
    if (getChecked('fund_need_insurance')) fundingNeeds.push('health_insurance');
    if (getChecked('fund_need_travel')) fundingNeeds.push('travel_grant');

    const payload = {
      name: getInputValue('prof_name'),
      full_name: getInputValue('prof_name'),
      nationality: getInputValue('prof_nationality'),
      country_of_origin: getInputValue('prof_country_of_origin'),
      current_residence: getInputValue('prof_current_residence'),

      current_degree: getInputValue('prof_current_degree'),
      current_institution: getInputValue('prof_current_institution'),
      current_major: getInputValue('prof_current_major'),
      gpa: getInputValue('prof_gpa'),
      graduation_date: getInputValue('prof_graduation_date'),

      target_degree: getInputValue('prof_target_degree'),
      broad_subject: getInputValue('prof_broad_subject'),
      target_field: getInputValue('prof_target_field'),
      specific_interests: getInputValue('prof_research_interests'),
      research_interests: getInputValue('prof_research_interests'),
      intended_intake: getInputValue('prof_intended_intake'),

      preferred_countries: preferredCountries,
      excluded_countries: excludedCountries,

      english_tests: getInputValue('prof_english_tests'),
      technical_skills: getInputValue('prof_technical_skills'),
      publications: getInputValue('prof_publications'),
      research_experience: getInputValue('prof_research_experience'),

      funding_needs: fundingNeeds,
      funding_notes: getInputValue('prof_funding_notes'),

      portfolio_url: getInputValue('prof_portfolio_url'),
      github_url: getInputValue('prof_github_url'),
      website_url: getInputValue('prof_website_url')
    };

    const res = await fetch('/api/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const result = await res.json();
    
    showToast(`Profile saved successfully! Snapshot Version #${result.version || 1} created.`, 'success');
    if (statusEl) statusEl.innerText = `Saved (v${result.version || 1})`;
    
    await loadProfile();
  } catch (err) {
    showToast(`Failed to save profile: ${err.message}`, 'error');
    if (statusEl) statusEl.innerText = 'Save failed';
  } finally {
    if (btn) btn.disabled = false;
  }
});

// Quick Save Button in Header
document.getElementById('saveProfileBtn')?.addEventListener('click', () => {
  document.getElementById('saveProfileSubmitBtn')?.click();
});

// CV Drag and Drop Upload Setup
function setupCvUpload() {
  const dropZone = document.getElementById('cvDropZone');
  const fileInput = document.getElementById('cvFileInput');
  const selectBtn = document.getElementById('cvSelectFileBtn');
  const uploadBtn = document.getElementById('cvUploadAndParseBtn');
  const label = document.getElementById('cvFileNameLabel');
  const status = document.getElementById('cvUploadStatus');

  let selectedFile = null;

  selectBtn?.addEventListener('click', () => fileInput?.click());
  dropZone?.addEventListener('click', () => fileInput?.click());

  dropZone?.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });

  dropZone?.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

  dropZone?.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  });

  fileInput?.addEventListener('change', () => {
    if (fileInput.files && fileInput.files.length > 0) {
      handleFileSelected(fileInput.files[0]);
    }
  });

  function handleFileSelected(file) {
    selectedFile = file;
    if (label) label.innerText = `Selected: ${file.name} (${Math.round(file.size / 1024)} KB)`;
    if (uploadBtn) uploadBtn.disabled = false;
    if (status) status.innerText = '';
  }

  uploadBtn?.addEventListener('click', async () => {
    if (!selectedFile) return;
    uploadBtn.disabled = true;
    if (status) status.innerText = 'Parsing document and extracting candidate facts...';

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const res = await fetch('/api/profile/upload-cv', {
        method: 'POST',
        body: formData
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (data.success === false) {
        throw new Error(data.message || 'Extraction failed');
      }

      State.extractedFacts = data.proposed_facts || {};
      openCvExtractModal(data.proposed_facts || {});
      if (status) status.innerText = 'Facts extracted successfully!';
    } catch (err) {
      if (status) status.innerText = `Extraction failed: ${err.message}`;
      showToast(`CV Extraction Error: ${err.message}`, 'error');
    } finally {
      uploadBtn.disabled = false;
    }
  });
}

function openCvExtractModal(facts) {
  const modal = document.getElementById('cvExtractModalBackdrop');
  const container = document.getElementById('cvExtractedFactsContent');
  if (!modal || !container) return;

  const entries = Object.entries(facts).filter(([k, v]) => v && String(v).trim().length > 0);

  if (entries.length === 0) {
    container.innerHTML = '<p class="text-sm text-muted">No structured facts could be extracted from this document.</p>';
  } else {
    container.innerHTML = `
      <div class="extracted-facts-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 40px;">Merge</th>
              <th>Field</th>
              <th>Extracted Fact Value</th>
            </tr>
          </thead>
          <tbody>
            ${entries.map(([key, val], idx) => `
              <tr>
                <td>
                  <input type="checkbox" id="merge_fact_${idx}" data-field="${escapeHtml(key)}" value="${escapeHtml(typeof val === 'object' ? JSON.stringify(val) : String(val))}" checked>
                </td>
                <td><strong>${escapeHtml(formatFieldName(key))}</strong></td>
                <td class="font-sans text-xs">${escapeHtml(typeof val === 'object' ? JSON.stringify(val) : String(val))}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  modal.classList.remove('hidden');
}

document.getElementById('confirmCvMergeBtn')?.addEventListener('click', () => {
  const checkboxes = document.querySelectorAll('#cvExtractedFactsContent input[type="checkbox"]:checked');
  let mergedCount = 0;

  checkboxes.forEach(cb => {
    const field = cb.getAttribute('data-field');
    const val = cb.value;
    
    // Map extracted fields to form inputs
    const fieldMap = {
      name: 'prof_name',
      full_name: 'prof_name',
      current_degree: 'prof_current_degree',
      current_institution: 'prof_current_institution',
      current_major: 'prof_current_major',
      major: 'prof_current_major',
      gpa: 'prof_gpa',
      graduation_date: 'prof_graduation_date',
      target_degree: 'prof_target_degree',
      broad_subject: 'prof_broad_subject',
      target_field: 'prof_target_field',
      specific_interests: 'prof_research_interests',
      research_interests: 'prof_research_interests',
      technical_skills: 'prof_technical_skills',
      publications: 'prof_publications',
      research_experience: 'prof_research_experience',
      english_tests: 'prof_english_tests'
    };

    const inputId = fieldMap[field];
    if (inputId) {
      setInputValue(inputId, val);
      mergedCount++;
    }
  });

  document.getElementById('cvExtractModalBackdrop')?.classList.add('hidden');
  showToast(`Merged ${mergedCount} candidate facts into profile form. Click Save Profile to apply.`, 'success');
});

document.getElementById('cancelCvMergeBtn')?.addEventListener('click', () => {
  document.getElementById('cvExtractModalBackdrop')?.classList.add('hidden');
});
document.getElementById('closeCvExtractModalBtn')?.addEventListener('click', () => {
  document.getElementById('cvExtractModalBackdrop')?.classList.add('hidden');
});

// AI Privacy Preview Modal
document.getElementById('viewPrivacyPreviewBtn')?.addEventListener('click', async () => {
  try {
    const res = await fetch('/api/profile/privacy-preview');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const container = document.getElementById('privacyTasksContent');
    const modal = document.getElementById('privacyModalBackdrop');
    if (container && modal) {
      container.innerHTML = Object.entries(data).map(([taskName, fields]) => `
        <div class="privacy-task-card card mb-3">
          <div class="card-header py-2">
            <strong>Task: ${formatFieldName(taskName)}</strong>
            <span class="badge badge-teal">${Object.keys(fields || {}).length} fields shared</span>
          </div>
          <div class="card-body py-2 text-xs font-mono bg-subtle">
            <pre>${escapeHtml(JSON.stringify(fields, null, 2))}</pre>
          </div>
        </div>
      `).join('');
      modal.classList.remove('hidden');
    }
  } catch (err) {
    showToast(`Failed to load privacy preview: ${err.message}`, 'error');
  }
});

document.getElementById('dismissPrivacyModalBtn')?.addEventListener('click', () => {
  document.getElementById('privacyModalBackdrop')?.classList.add('hidden');
});
document.getElementById('closePrivacyModalBtn')?.addEventListener('click', () => {
  document.getElementById('privacyModalBackdrop')?.classList.add('hidden');
});

// ============================================================================
// 5. SCREEN 3: RESEARCH SETUP & AUTONOMOUS DISCOVERY
// ============================================================================

function setupResearchSetupModeSwitcher() {
  const discoveryBtn = document.getElementById('discoveryModeBtn');
  const singleBtn = document.getElementById('singleUrlModeBtn');
  const batchBtn = document.getElementById('multiUrlModeBtn');

  const discoveryGroup = document.getElementById('discoveryModeGroup');
  const singleGroup = document.getElementById('singleUrlGroup');
  const batchGroup = document.getElementById('multiUrlGroup');
  const crawlScope = document.getElementById('crawlScopeControls');

  function setMode(mode) {
    State.researchMode = mode;

    discoveryBtn?.classList.toggle('active', mode === 'discovery');
    singleBtn?.classList.toggle('active', mode === 'single');
    batchBtn?.classList.toggle('active', mode === 'batch');

    discoveryGroup?.classList.toggle('hidden', mode !== 'discovery');
    singleGroup?.classList.toggle('hidden', mode !== 'single');
    batchGroup?.classList.toggle('hidden', mode !== 'batch');
    crawlScope?.classList.toggle('hidden', mode === 'discovery');
  }

  discoveryBtn?.addEventListener('click', () => setMode('discovery'));
  singleBtn?.addEventListener('click', () => setMode('single'));
  batchBtn?.addEventListener('click', () => setMode('batch'));

  // Go to settings button in provider card
  document.getElementById('configureSearchInSettingsBtn')?.addEventListener('click', () => {
    switchTab('tab-settings');
  });

  // Generate Focused Queries
  document.getElementById('generateQueriesBtn')?.addEventListener('click', async () => {
    const btn = document.getElementById('generateQueriesBtn');
    if (btn) btn.disabled = true;
    
    try {
      const customKw = getInputValue('customKeywordsInput');
      const maxQ = parseInt(getInputValue('maxQueriesInput') || '5', 10);

      const res = await fetch('/api/discovery/generate-queries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          max_queries: maxQ,
          custom_keywords: customKw
        })
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      State.discoveryQueries = data.queries || [];

      renderGeneratedQueries(data.queries || []);
      const previewBtn = document.getElementById('previewLeadsBtn');
      if (previewBtn) previewBtn.disabled = (data.queries || []).length === 0;

      showToast(`Generated ${data.total_generated || 0} precision discovery queries.`, 'success');
    } catch (err) {
      showToast(`Query generation failed: ${err.message}`, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  // Preview Search Leads (Search Test)
  document.getElementById('previewLeadsBtn')?.addEventListener('click', async () => {
    const btn = document.getElementById('previewLeadsBtn');
    if (btn) btn.disabled = true;

    try {
      showToast('Executing search query preview across provider...', 'info');
      const maxUnivs = parseInt(getInputValue('maxDiscoveryUniversitiesInput') || '10', 10);

      const res = await fetch('/api/discovery/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          queries: State.discoveryQueries,
          max_universities: maxUnivs
        })
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      State.discoveredLeads = data.discovered_institutions || [];
      renderDiscoveryLeads(data.discovered_institutions || []);
      showToast(`Discovered ${data.total_discovered || 0} official university domains.`, 'success');
    } catch (err) {
      showToast(`Lead preview failed: ${err.message}`, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  // Launch Autonomous Discovery Run
  document.getElementById('startDiscoveryJobBtn')?.addEventListener('click', async () => {
    const btn = document.getElementById('startDiscoveryJobBtn');
    if (btn) btn.disabled = true;

    try {
      const maxUnivs = parseInt(getInputValue('maxDiscoveryUniversitiesInput') || '10', 10);
      const customKw = getInputValue('customKeywordsInput');

      const res = await fetch('/api/discovery/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          queries: State.discoveryQueries.length > 0 ? State.discoveryQueries : undefined,
          custom_keywords: customKw,
          max_universities: maxUnivs,
          scope: 'all'
        })
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      showToast(`Discovery Job #${data.job_id} successfully queued!`, 'success');
      
      // Switch to Research Jobs tab and refresh
      switchTab('tab-jobs');
    } catch (err) {
      showToast(`Discovery start failed: ${err.message}`, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  // Launch Direct URL Research Run (Single or Batch)
  document.getElementById('launchUrlResearchBtn')?.addEventListener('click', async () => {
    const btn = document.getElementById('launchUrlResearchBtn');
    if (btn) btn.disabled = true;

    try {
      let payload = {
        scope: getInputValue('researchScopeSelect') || 'all',
        max_pages: parseInt(getInputValue('maxPagesPerUniv') || '15', 10),
        time_limit_seconds: parseInt(getInputValue('crawlTimeLimit') || '120', 10)
      };

      if (State.researchMode === 'single') {
        const url = getInputValue('targetUniversityUrl');
        if (!url) throw new Error('Please enter a target university URL.');
        payload.university_url = url;
        payload.university_name = getInputValue('targetUniversityName');
      } else if (State.researchMode === 'batch') {
        const rawUrls = getInputValue('batchUniversityUrls');
        if (!rawUrls) throw new Error('Please enter one or more university URLs.');
        payload.university_urls = rawUrls;
      }

      const res = await fetch('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      showToast(data.message || 'Research run(s) enqueued successfully!', 'success');
      
      // Clear inputs
      setInputValue('targetUniversityUrl', '');
      setInputValue('batchUniversityUrls', '');

      switchTab('tab-jobs');
    } catch (err) {
      showToast(`Launch failed: ${err.message}`, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  });
}

function renderGeneratedQueries(queries) {
  const container = document.getElementById('generatedQueriesContainer');
  const list = document.getElementById('queriesList');
  const badge = document.getElementById('queriesCountBadge');
  if (!container || !list) return;

  if (!queries || queries.length === 0) {
    container.classList.add('hidden');
    return;
  }

  if (badge) badge.innerText = `${queries.length} queries`;

  list.innerHTML = queries.map((q, idx) => `
    <div class="query-item-card">
      <div class="flex-1">
        <div class="query-item-text">🔍 "${escapeHtml(q.query || q)}"</div>
        <div class="query-item-rationale">Focus: ${escapeHtml(q.rationale || q.focus_aspect || 'Target Degree & Funding Intent')}</div>
      </div>
      <span class="badge badge-neutral text-xs">#${idx + 1}</span>
    </div>
  `).join('');

  container.classList.remove('hidden');
}

function renderDiscoveryLeads(leads) {
  const container = document.getElementById('leadsPreviewContainer');
  const tbody = document.getElementById('leadsPreviewTableBody');
  const badge = document.getElementById('leadsCountBadge');
  if (!container || !tbody) return;

  if (!leads || leads.length === 0) {
    container.classList.add('hidden');
    return;
  }

  if (badge) badge.innerText = `${leads.length} leads`;

  tbody.innerHTML = leads.map(lead => `
    <tr>
      <td><strong>${escapeHtml(lead.name || 'University')}</strong></td>
      <td class="font-mono">${escapeHtml(lead.domain || '')}</td>
      <td>${escapeHtml(lead.country || 'Unknown')}</td>
      <td class="text-xs text-muted font-mono">${escapeHtml(truncate(lead.discovered_via_query, 35))}</td>
      <td>
        <a href="${escapeHtml(lead.lead_url)}" target="_blank" rel="noopener" class="text-xs">
          ${escapeHtml(truncate(lead.lead_url, 30))} ↗
        </a>
      </td>
    </tr>
  `).join('');

  container.classList.remove('hidden');
}

// ============================================================================
// 6. SCREEN 4: RESEARCH JOBS & QUEUE MONITOR
// ============================================================================

async function loadJobs() {
  try {
    const res = await fetch('/api/jobs');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const jobs = await res.json();
    State.jobs = jobs;

    setText('navJobsCount', jobs.length);
    renderJobsTable();
  } catch (err) {
    console.error('Failed to load jobs:', err);
  }
}

async function refreshJobsData() {
  await loadJobs();
}

function renderJobsTable() {
  const tbody = document.getElementById('allJobsTableBody');
  const emptyState = document.getElementById('jobsEmptyState');
  const table = document.getElementById('allJobsTable');
  if (!tbody) return;

  let filtered = [...State.jobs];

  // Apply filters
  const statusFilter = State.filters.jobs.status;
  if (statusFilter && statusFilter !== 'all') {
    filtered = filtered.filter(j => j.status === statusFilter);
  }

  const typeFilter = State.filters.jobs.type;
  if (typeFilter && typeFilter !== 'all') {
    filtered = filtered.filter(j => j.job_type === typeFilter);
  }

  const searchTerm = (State.filters.jobs.search || '').trim().toLowerCase();
  if (searchTerm) {
    filtered = filtered.filter(j => 
      (j.university_name || '').toLowerCase().includes(searchTerm) ||
      (j.university_url || '').toLowerCase().includes(searchTerm) ||
      String(j.id).includes(searchTerm)
    );
  }

  if (filtered.length === 0) {
    tbody.innerHTML = '';
    table?.classList.add('hidden');
    emptyState?.classList.remove('hidden');
    return;
  }

  table?.classList.remove('hidden');
  emptyState?.classList.add('hidden');

  tbody.innerHTML = filtered.map(job => {
    const statusBadge = getJobStatusBadge(job.status);
    const targetDisplay = job.job_type === 'discovery_job'
      ? `<strong>✨ Autonomous Discovery</strong><br><span class="text-xs text-muted font-mono">${escapeHtml(job.university_name || 'Search Interface')}</span>`
      : `<strong>${escapeHtml(job.university_name || 'Target University')}</strong><br><a href="${escapeHtml(job.university_url)}" target="_blank" rel="noopener" class="text-xs font-mono text-muted">${escapeHtml(truncate(job.university_url, 35))} ↗</a>`;

    const isRunning = job.status === 'running' || job.status === 'queued';
    const isPaused = job.status === 'paused';
    const stopReasonHtml = job.stop_reason ? `<br><span class="stop-reason-pill mt-1" title="${escapeHtml(job.stop_reason)}">🛑 ${escapeHtml(truncate(job.stop_reason, 26))}</span>` : '';
    const checkpointHtml = job.checkpoint_page_count ? `<br><span class="checkpoint-tag mt-1" title="Checkpoint saved after page ${job.checkpoint_page_count}">💾 Chkpt: ${job.checkpoint_page_count}p</span>` : '';

    return `
      <tr>
        <td class="font-mono">#${job.id}</td>
        <td>${targetDisplay}</td>
        <td>
          <span class="badge badge-navy">${escapeHtml(capitalize(job.job_type === 'discovery_job' ? 'Discovery' : 'Crawl'))}</span><br>
          <span class="text-xs text-muted">Scope: ${escapeHtml(job.scope || 'all')}</span>
        </td>
        <td><span class="badge badge-teal">v${job.profile_version || 1}</span></td>
        <td>
          ${statusBadge}
          ${stopReasonHtml}
          ${checkpointHtml}<br>
          <span class="text-xs text-muted">${escapeHtml(truncate(job.current_step || 'In queue', 28))}</span>
        </td>
        <td class="font-mono">${job.pages_crawled || 0}</td>
        <td class="font-mono text-teal font-semibold">${job.scholarships_count || 0}</td>
        <td class="font-mono font-semibold">${job.professors_count || 0}</td>
        <td class="font-mono text-xs">${Number(job.llm_total_tokens || 0).toLocaleString()}</td>
        <td class="text-xs text-muted">${formatDate(job.created_at)}</td>
        <td>
          <div class="action-btn-group">
            <button type="button" class="icon-btn" onclick="viewJobCoverageModal(${job.id})" title="View Institutional Coverage Report">📊 Report</button>
            <button type="button" class="icon-btn" onclick="viewJobCrawlPagesModal(${job.id})" title="View Visited Webpages Log">📑 Pages</button>
            ${isRunning ? `
              <button type="button" class="icon-btn" onclick="pauseJob(${job.id})" title="Pause Job">⏸️</button>
              <button type="button" class="icon-btn" onclick="cancelJob(${job.id})" title="Cancel Job">🛑</button>
            ` : ''}
            ${isPaused ? `
              <button type="button" class="icon-btn" onclick="resumeJob(${job.id})" title="Resume Job">▶️</button>
            ` : ''}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

// Job Controls: Pause, Resume, Cancel
async function pauseJob(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/pause`, { method: 'POST' });
    if (res.ok) {
      showToast(`Job #${jobId} paused.`, 'info');
      await loadJobs();
    }
  } catch (err) {
    showToast(`Pause failed: ${err.message}`, 'error');
  }
}

async function resumeJob(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/resume`, { method: 'POST' });
    if (res.ok) {
      showToast(`Job #${jobId} resumed.`, 'info');
      await loadJobs();
    }
  } catch (err) {
    showToast(`Resume failed: ${err.message}`, 'error');
  }
}

async function cancelJob(jobId) {
  if (!confirm(`Cancel Research Job #${jobId}?`)) return;
  try {
    const res = await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
    if (res.ok) {
      showToast(`Job #${jobId} cancelled.`, 'info');
      await loadJobs();
    }
  } catch (err) {
    showToast(`Cancel failed: ${err.message}`, 'error');
  }
}

// ============================================================================
// 7. SCREEN 5: TRACKED UNIVERSITIES & REAL-TIME DIRECTORY
// ============================================================================

async function loadUniversities(forceRandomize = false) {
  try {
    const f = State.filters.universities;
    const params = new URLSearchParams();

    if (f.search) params.append('search', f.search);

    const isRandomMode = forceRandomize || f.country === 'random' || f.sortBy === 'random' || f.randomize;

    if (isRandomMode) {
      params.append('randomize', 'true');
      params.append('sort_by', 'random');
    } else {
      if (f.country && f.country !== 'all') params.append('country', f.country);
      if (f.sortBy) params.append('sort_by', f.sortBy);
    }

    if (f.shortlistedOnly) params.append('shortlisted_only', 'true');

    const res = await fetch(`/api/universities?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    State.universities = data;

    setText('navUniversitiesCount', data.length);
    populateCountryDropdown('univCountryFilter', data.map(u => u.country));

    // Update active country display label in ribbon card
    const labelEl = document.getElementById('activeCountryDisplayLabel');
    if (labelEl) {
      if (isRandomMode) {
        labelEl.innerText = `Showing: 🎲 Random Global Sample (${data.length} Institutions)`;
      } else if (!f.country || f.country === 'all') {
        labelEl.innerText = `Showing: 🌐 All Countries (${data.length} Institutions)`;
      } else {
        labelEl.innerText = `Showing: 📍 ${f.country} (${data.length} Institutions)`;
      }
    }

    renderUniversitiesTable();
  } catch (err) {
    console.error('Failed to load universities:', err);
  }
}

function renderUniversitiesTable() {
  const tbody = document.getElementById('universitiesTableBody');
  const emptyState = document.getElementById('univEmptyState');
  const table = document.getElementById('universitiesTable');
  const pageInfo = document.getElementById('univPaginationInfo');
  const prevBtn = document.getElementById('univPrevPageBtn');
  const nextBtn = document.getElementById('univNextPageBtn');
  const pageNumEl = document.getElementById('univPageNum');
  if (!tbody) return;

  const items = State.universities;
  const pg = State.pagination.universities;
  pg.total = items.length;

  if (items.length === 0) {
    tbody.innerHTML = '';
    table?.classList.add('hidden');
    emptyState?.classList.remove('hidden');
    if (pageInfo) pageInfo.innerText = 'Showing 0 of 0 universities';
    if (prevBtn) prevBtn.disabled = true;
    if (nextBtn) nextBtn.disabled = true;
    return;
  }

  table?.classList.remove('hidden');
  emptyState?.classList.add('hidden');

  const startIdx = (pg.page - 1) * pg.pageSize;
  const endIdx = startIdx + pg.pageSize;
  const pageItems = items.slice(startIdx, endIdx);

  if (pageInfo) pageInfo.innerText = `Showing ${startIdx + 1}–${Math.min(endIdx, items.length)} of ${items.length} universities`;
  if (pageNumEl) pageNumEl.innerText = `Page ${pg.page} of ${Math.ceil(items.length / pg.pageSize) || 1}`;
  if (prevBtn) prevBtn.disabled = pg.page <= 1;
  if (nextBtn) nextBtn.disabled = endIdx >= items.length;

  tbody.innerHTML = pageItems.map(u => {
    const isShortlisted = Boolean(u.is_shortlisted);
    const hasNotes = Boolean(u.notes && u.notes.trim().length > 0);
    const leadUrl = u.lead_url || `https://${u.domain}`;

    return `
      <tr>
        <td>
          <button type="button" class="star-btn ${isShortlisted ? 'active' : ''}" onclick="toggleUniversityShortlist('${escapeJsString(u.domain)}', '${escapeJsString(u.university_name)}', '${escapeJsString(u.country)}', '${escapeJsString(leadUrl)}')" title="${isShortlisted ? 'Remove from Shortlist' : 'Add to Shortlist'}">
            ${isShortlisted ? '⭐' : '☆'}
          </button>
        </td>
        <td>
          <strong>${escapeHtml(u.university_name)}</strong><br>
          <a href="${escapeHtml(leadUrl)}" target="_blank" rel="noopener" class="text-xs font-mono text-muted">${escapeHtml(u.domain)} ↗</a>
        </td>
        <td><span class="badge badge-navy">${escapeHtml(u.country || 'Unknown')}</span></td>
        <td class="font-mono">${u.pages_crawled || 0}</td>
        <td class="font-mono text-teal font-semibold">${u.scholarships_count || 0}</td>
        <td class="font-mono font-semibold">${u.professors_count || 0}</td>
        <td class="text-xs text-muted">${u.last_checked ? formatDate(u.last_checked) : 'Cataloged'}</td>
        <td>
          <button type="button" class="btn btn-sm ${hasNotes ? 'btn-primary' : 'btn-secondary'}" onclick="openNotesModal('university', '${escapeJsString(u.domain)}', '${escapeJsString(u.notes || '')}', { university_name: '${escapeJsString(u.university_name)}', country: '${escapeJsString(u.country)}', lead_url: '${escapeJsString(leadUrl)}' })">
            ${hasNotes ? '📝 Notes' : '+ Note'}
          </button>
        </td>
        <td>
          <div class="action-btn-group">
            <button type="button" class="btn btn-sm btn-primary action-quick-launch" onclick="quickLaunchUniversityResearch('${escapeJsString(u.domain)}', '${escapeJsString(u.university_name)}', '${escapeJsString(leadUrl)}')" title="1-Click Launch Research Crawl on ${escapeHtml(u.university_name)}">
              🚀 Crawl
            </button>
            <button type="button" class="btn btn-sm btn-secondary" onclick="openEditUniversityModal('${escapeJsString(u.domain)}', '${escapeJsString(u.university_name)}', '${escapeJsString(u.country)}', '${escapeJsString(leadUrl)}', '${escapeJsString(u.notes || '')}', ${isShortlisted})" title="Edit University Information">
              ✏️
            </button>
            <button type="button" class="btn btn-sm btn-secondary" onclick="deleteUniversity('${escapeJsString(u.domain)}', '${escapeJsString(u.university_name)}')" title="Remove / Untrack University">
              🗑️
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

// Country Explorer Ribbon Setup & Handlers
function setupCountryRibbon() {
  const ribbon = document.getElementById('countryPillsRibbon');
  if (!ribbon) return;

  ribbon.querySelectorAll('.country-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      const country = pill.getAttribute('data-country');
      filterUniversitiesByCountry(country);
    });
  });

  // Shuffle Random Sample Button in Header
  document.getElementById('shuffleUnivsBtn')?.addEventListener('click', () => {
    filterUniversitiesByCountry('random');
  });

  // Open Add Custom University Modal Button
  document.getElementById('openAddUnivModalBtn')?.addEventListener('click', () => {
    openAddUniversityModal();
  });
}

function filterUniversitiesByCountry(country) {
  State.filters.universities.country = country;
  State.pagination.universities.page = 1;

  if (country === 'random') {
    State.filters.universities.randomize = true;
    State.filters.universities.sortBy = 'random';
    setInputValue('univSortBy', 'random');
    setInputValue('univCountryFilter', 'all');
  } else if (country === 'all') {
    State.filters.universities.randomize = false;
    State.filters.universities.sortBy = 'name';
    setInputValue('univCountryFilter', 'all');
    setInputValue('univSortBy', 'name');
  } else {
    State.filters.universities.randomize = false;
    setInputValue('univCountryFilter', country);
  }

  // Update Ribbon Pills Active Class
  updateActiveCountryRibbonUI(country);

  loadUniversities(country === 'random');
}

function updateActiveCountryRibbonUI(selectedCountry) {
  const ribbon = document.getElementById('countryPillsRibbon');
  if (!ribbon) return;

  const target = selectedCountry || 'all';
  ribbon.querySelectorAll('.country-pill').forEach(pill => {
    const pCountry = pill.getAttribute('data-country');
    const isActive = (pCountry === target) || (target === 'all' && pCountry === 'all') || (target === 'random' && pCountry === 'random');
    pill.classList.toggle('active', isActive);
  });
}

// 1-Click Launch University Research Crawl
async function quickLaunchUniversityResearch(domain, name, leadUrl) {
  showToast(`Initiating research crawl for ${name || domain}...`, 'info', 2500);
  try {
    const res = await fetch(`/api/universities/${encodeURIComponent(domain)}/launch-research`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    showToast(`🚀 Research Job #${data.job_id} launched for ${name || domain}!`, 'success', 4000);

    await loadJobs();
    await loadOverview();
    await loadUniversities();
  } catch (err) {
    showToast(`Failed to launch research: ${err.message}`, 'error');
  }
}

// Add / Edit Custom University Modal Management
function openAddUniversityModal() {
  const modal = document.getElementById('univModalBackdrop');
  if (!modal) return;

  setInputValue('univModalMode', 'create');
  setText('univModalTitle', '🏛️ Add Custom University');
  setInputValue('univModalName', '');
  setInputValue('univModalLeadUrl', '');
  setInputValue('univModalDomain', '');
  setInputValue('univModalNotes', '');
  setChecked('univModalShortlist', false);

  // Pre-fill country dropdown if filtered
  const activeCountry = State.filters.universities.country;
  if (activeCountry && activeCountry !== 'all' && activeCountry !== 'random') {
    setInputValue('univModalCountry', activeCountry);
  }

  modal.classList.remove('hidden');
  document.getElementById('univModalName')?.focus();
}

function openEditUniversityModal(domain, name, country, leadUrl, notes, isShortlisted) {
  const modal = document.getElementById('univModalBackdrop');
  if (!modal) return;

  setInputValue('univModalMode', 'edit');
  setText('univModalTitle', `✏️ Edit University: ${name}`);
  setInputValue('univModalName', name);
  setInputValue('univModalLeadUrl', leadUrl || `https://${domain}`);
  setInputValue('univModalDomain', domain);
  setInputValue('univModalCountry', country || 'United States');
  setInputValue('univModalNotes', notes || '');
  setChecked('univModalShortlist', Boolean(isShortlisted));

  modal.classList.remove('hidden');
  document.getElementById('univModalName')?.focus();
}

async function saveUniversityModal() {
  const mode = getInputValue('univModalMode');
  const name = getInputValue('univModalName').trim();
  const leadUrl = getInputValue('univModalLeadUrl').trim();
  const domain = getInputValue('univModalDomain').trim();
  const country = getInputValue('univModalCountry');
  const notes = getInputValue('univModalNotes').trim();
  const isShortlisted = getChecked('univModalShortlist');

  if (!name || !leadUrl) {
    showToast('University name and official website URL are required.', 'warning');
    return;
  }

  try {
    let url = '/api/universities';
    let method = 'POST';

    if (mode === 'edit') {
      const targetDomain = domain || extractDomainFromUrl(leadUrl);
      url = `/api/universities/${encodeURIComponent(targetDomain)}`;
      method = 'PUT';
    }

    const payload = {
      university_name: name,
      lead_url: leadUrl,
      domain: domain,
      country: country,
      notes: notes,
      is_shortlisted: isShortlisted
    };

    const res = await fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    showToast(data.message || `${name} saved successfully!`, 'success');
    document.getElementById('univModalBackdrop')?.classList.add('hidden');

    await loadUniversities();
    await loadOverview();
    if (isShortlisted) await loadShortlist();
  } catch (err) {
    showToast(`Failed to save university: ${err.message}`, 'error');
  }
}

async function deleteUniversity(domain, name) {
  if (!confirm(`Are you sure you want to remove "${name || domain}" from tracked universities?`)) return;

  try {
    const res = await fetch(`/api/universities/${encodeURIComponent(domain)}`, {
      method: 'DELETE'
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast(`Removed "${name || domain}" from directory.`, 'info');

    await loadUniversities();
    await loadOverview();
    await loadShortlist();
  } catch (err) {
    showToast(`Failed to delete university: ${err.message}`, 'error');
  }
}

// Quick target research from University directory
function targetResearchUniversity(url, name) {
  switchTab('tab-research');
  const singleBtn = document.getElementById('singleUrlModeBtn');
  singleBtn?.click();
  setInputValue('targetUniversityUrl', url);
  setInputValue('targetUniversityName', name);
}

// Toggle University Shortlist
async function toggleUniversityShortlist(domain, name, country, leadUrl) {
  try {
    const res = await fetch(`/api/universities/${encodeURIComponent(domain)}/shortlist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        university_name: name,
        country: country,
        lead_url: leadUrl
      })
    });

    if (res.ok) {
      await loadUniversities();
      await loadOverview();
      await loadShortlist();
    }
  } catch (err) {
    showToast(`Shortlist update failed: ${err.message}`, 'error');
  }
}

// ============================================================================
// 8. SCREEN 6: FUNDING OPPORTUNITIES CATALOG
// ============================================================================

async function loadScholarships() {
  try {
    const f = State.filters.scholarships;
    const params = new URLSearchParams();
    if (f.minFitScore) params.append('min_fit_score', f.minFitScore);
    if (f.category && f.category !== 'all') params.append('funding_category', f.category);
    if (f.eligibility && f.eligibility !== 'all') params.append('eligibility_status', f.eligibility);
    if (f.opportunityStatus && f.opportunityStatus !== 'all') params.append('opportunity_status', f.opportunityStatus);
    if (f.country && f.country !== 'all') params.append('country', f.country);
    if (f.degreeLevel && f.degreeLevel !== 'all') params.append('degree_level', f.degreeLevel);
    if (f.shortlistedOnly) params.append('is_shortlisted', 'true');
    if (f.search) params.append('search', f.search);
    if (f.sortBy) params.append('sort_by', f.sortBy);

    const res = await fetch(`/api/scholarships?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    State.scholarships = data;

    setText('scholarshipsCount', data.length);
    populateCountryDropdown('fundingCountryFilter', data.map(s => s.country));
    renderScholarshipsCatalog();
  } catch (err) {
    console.error('Failed to load scholarships:', err);
  }
}

function renderScholarshipsCatalog() {
  const container = document.getElementById('scholarshipsCatalogList');
  const emptyState = document.getElementById('fundingCatalogEmptyState');
  const pageInfo = document.getElementById('fundingPaginationInfo');
  const prevBtn = document.getElementById('fundingPrevPageBtn');
  const nextBtn = document.getElementById('fundingNextPageBtn');
  const pageNumEl = document.getElementById('fundingPageNum');
  if (!container) return;

  const items = State.scholarships;
  const pg = State.pagination.scholarships;
  pg.total = items.length;

  if (items.length === 0) {
    container.innerHTML = '';
    emptyState?.classList.remove('hidden');
    if (pageInfo) pageInfo.innerText = 'Showing 0 of 0 opportunities';
    if (prevBtn) prevBtn.disabled = true;
    if (nextBtn) nextBtn.disabled = true;
    return;
  }

  emptyState?.classList.add('hidden');

  const startIdx = (pg.page - 1) * pg.pageSize;
  const endIdx = startIdx + pg.pageSize;
  const pageItems = items.slice(startIdx, endIdx);

  if (pageInfo) pageInfo.innerText = `Showing ${startIdx + 1}–${Math.min(endIdx, items.length)} of ${items.length} opportunities`;
  if (pageNumEl) pageNumEl.innerText = `Page ${pg.page} of ${Math.ceil(items.length / pg.pageSize) || 1}`;
  if (prevBtn) prevBtn.disabled = pg.page <= 1;
  if (nextBtn) nextBtn.disabled = endIdx >= items.length;

  container.innerHTML = pageItems.map(s => {
    const fitBadge = getFitScoreBadge(s.fit_score);
    const catBadge = getFundingCategoryBadge(s.funding_category);
    const eligBadge = getEligibilityBadge(s.eligibility_status);
    const isShortlisted = Boolean(s.is_shortlisted);
    const hasNotes = Boolean(s.notes && s.notes.trim().length > 0);

    return `
      <div class="scholarship-card">
        <div class="scholarship-header-row">
          <div class="scholarship-title-group">
            <h4>${escapeHtml(s.title)}</h4>
            <div class="scholarship-univ-meta">
              <span>🏛️ <strong>${escapeHtml(s.university || 'University')}</strong></span>
              <span>📍 ${escapeHtml(s.country || 'Unknown')}</span>
              <span>🎓 ${escapeHtml(s.degree_level || 'Ph.D.')}</span>
              ${s.department && s.department !== 'Unknown' ? `<span>🏢 ${escapeHtml(s.department)}</span>` : ''}
            </div>
          </div>
          <div class="action-btn-group">
            <button type="button" class="star-btn ${isShortlisted ? 'active' : ''}" onclick="toggleScholarshipShortlist(${s.id})">
              ${isShortlisted ? '⭐ Shortlisted' : '☆ Shortlist'}
            </button>
            <button type="button" class="btn btn-sm ${hasNotes ? 'btn-primary' : 'btn-secondary'}" onclick="openNotesModal('scholarship', ${s.id}, '${escapeJsString(s.notes || '')}', { title: '${escapeJsString(s.title)}' })">
              ${hasNotes ? '📝 Notes' : '+ Note'}
            </button>
          </div>
        </div>

        <div class="scholarship-badges-row">
          ${fitBadge}
          ${catBadge}
          ${eligBadge}
          <span class="badge badge-neutral">💰 ${escapeHtml(s.amount || 'Funding Provided')}</span>
          <span class="badge badge-neutral">📅 Deadline: ${escapeHtml(s.deadline || s.deadline_date || 'Check official link')}</span>
          <span class="badge badge-teal">Profile v${s.profile_version || 1}</span>
        </div>

        <div class="scholarship-details-grid">
          <div class="detail-item">
            <strong>Tuition Coverage</strong>
            <span>${escapeHtml(s.tuition_coverage || 'Unknown')}</span>
          </div>
          <div class="detail-item">
            <strong>Stipend Support</strong>
            <span>${escapeHtml(s.stipend_amount || s.amount || 'Unknown')} ${escapeHtml(s.stipend_currency || '')}</span>
          </div>
          <div class="detail-item">
            <strong>Duration & Terms</strong>
            <span>${escapeHtml(s.funding_duration || 'Standard Degree Duration')}</span>
          </div>
          <div class="detail-item">
            <strong>Intake / Year</strong>
            <span>${escapeHtml(s.intake_and_year || 'Upcoming Term')}</span>
          </div>
        </div>

        ${s.fit_reason ? `<div class="fit-reason-box">💡 <strong>Fit Assessment:</strong> ${escapeHtml(s.fit_reason)}</div>` : ''}

        <div class="evidence-toggle-wrap">
          <button type="button" class="evidence-toggle-btn" onclick="toggleEvidencePanel('ev_panel_${s.id}')">
            <span>🔍 Expand Source Citation & Evidence</span>
          </button>
          <div id="ev_panel_${s.id}" class="evidence-panel hidden">
            <div class="verbatim-quote">"${escapeHtml(s.evidence_snippet || 'Verified against institutional web text.')}"</div>
            <div class="text-xs text-muted mt-1">
              <strong>Source URL:</strong> <a href="${escapeHtml(s.source_url)}" target="_blank" rel="noopener" class="font-mono">${escapeHtml(s.source_url)} ↗</a>
              <span class="ml-2">• Verified fact ground truth from official portal</span>
            </div>
          </div>
        </div>

        <div class="scholarship-footer-actions">
          <div class="text-xs text-muted">
            Last checked: ${formatDate(s.created_at)} ${s.discovered_via_query ? `• Query: <code class="text-xs font-mono">${escapeHtml(truncate(s.discovered_via_query, 30))}</code>` : ''}
          </div>
          <div class="action-btn-group">
            <button type="button" class="btn btn-sm btn-secondary" onclick="openEvidenceModal('${escapeJsString(s.title)}', '${escapeJsString(s.source_url)}', '${escapeJsString(s.evidence_snippet)}', ${escapeJsObject(s.claims_evidence)})">
              🔍 Evidence
            </button>
            <button type="button" class="btn btn-sm btn-secondary" onclick="openEvidenceHistory('scholarship', ${s.id}, '${escapeJsString(s.title)}')">
              📜 History
            </button>
            <button type="button" class="btn btn-sm btn-primary" onclick="initEmailDraftForScholarship(${s.id}, '${escapeJsString(s.title)}', '${escapeJsString(s.university)}')">
              ✉️ Draft Inquiry
            </button>
            <a href="${escapeHtml(s.official_url || s.source_url)}" target="_blank" rel="noopener" class="btn btn-sm btn-secondary">
              🌐 Official Source ↗
            </a>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

async function toggleScholarshipShortlist(id) {
  try {
    const res = await fetch(`/api/scholarships/${id}/shortlist`, { method: 'POST' });
    if (res.ok) {
      await loadScholarships();
      await loadOverview();
      await loadShortlist();
    }
  } catch (err) {
    showToast(`Shortlist toggle failed: ${err.message}`, 'error');
  }
}

// ============================================================================
// 9. SCREEN 7: PROFESSORS & FACULTY DIRECTORY
// ============================================================================

async function loadProfessors() {
  try {
    const f = State.filters.professors;
    const params = new URLSearchParams();
    if (f.minMatchScore) params.append('min_match_score', f.minMatchScore);
    if (f.recruitment && f.recruitment !== 'all') params.append('recruitment_status', f.recruitment);
    if (f.email === 'has_email') params.append('has_email', 'true');
    if (f.email === 'no_email') params.append('has_email', 'false');
    if (f.department) params.append('department', f.department);
    if (f.shortlistedOnly) params.append('is_shortlisted', 'true');
    if (f.search) params.append('search', f.search);
    if (f.sortBy) params.append('sort_by', f.sortBy);

    const res = await fetch(`/api/professors?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    State.professors = data;

    setText('professorsCount', data.length);
    renderProfessorsCatalog();
  } catch (err) {
    console.error('Failed to load professors:', err);
  }
}

function renderProfessorsCatalog() {
  const container = document.getElementById('professorsCatalogList');
  const emptyState = document.getElementById('professorsCatalogEmptyState');
  const pageInfo = document.getElementById('profPaginationInfo');
  const prevBtn = document.getElementById('profPrevPageBtn');
  const nextBtn = document.getElementById('profNextPageBtn');
  const pageNumEl = document.getElementById('profPageNum');
  if (!container) return;

  const items = State.professors;
  const pg = State.pagination.professors;
  pg.total = items.length;

  if (items.length === 0) {
    container.innerHTML = '';
    emptyState?.classList.remove('hidden');
    if (pageInfo) pageInfo.innerText = 'Showing 0 of 0 faculty members';
    if (prevBtn) prevBtn.disabled = true;
    if (nextBtn) nextBtn.disabled = true;
    return;
  }

  emptyState?.classList.add('hidden');

  const startIdx = (pg.page - 1) * pg.pageSize;
  const endIdx = startIdx + pg.pageSize;
  const pageItems = items.slice(startIdx, endIdx);

  if (pageInfo) pageInfo.innerText = `Showing ${startIdx + 1}–${Math.min(endIdx, items.length)} of ${items.length} faculty members`;
  if (pageNumEl) pageNumEl.innerText = `Page ${pg.page} of ${Math.ceil(items.length / pg.pageSize) || 1}`;
  if (prevBtn) prevBtn.disabled = pg.page <= 1;
  if (nextBtn) nextBtn.disabled = endIdx >= items.length;

  container.innerHTML = pageItems.map(p => {
    const matchBadge = getMatchScoreBadge(p.match_score);
    const recBadge = getRecruitmentBadge(p.recruitment_status);
    const hasEmail = p.email && p.email.includes('@') && !['Not found', 'Unknown', 'None'].includes(p.email);
    const isShortlisted = Boolean(p.is_shortlisted);
    const hasNotes = Boolean(p.notes && p.notes.trim().length > 0);

    const interestsTags = (p.research_interests || '')
      .split(',')
      .map(t => t.trim())
      .filter(Boolean);

    return `
      <div class="professor-card">
        <div class="professor-header-row">
          <div class="professor-name-group">
            <h4>${escapeHtml(p.name)}</h4>
            <div class="professor-dept-univ">
              <span>🏛️ <strong>${escapeHtml(p.university || 'University')}</strong></span>
              <span>🏢 ${escapeHtml(p.department || 'Department')}</span>
              ${p.title && p.title !== 'Unknown' ? `<span>• ${escapeHtml(p.title)}</span>` : ''}
              ${p.lab_group && p.lab_group !== 'Unknown' ? `<span>• 🔬 ${escapeHtml(p.lab_group)}</span>` : ''}
            </div>
          </div>
          <div class="action-btn-group">
            <button type="button" class="star-btn ${isShortlisted ? 'active' : ''}" onclick="toggleProfessorShortlist(${p.id})">
              ${isShortlisted ? '⭐ Shortlisted' : '☆ Shortlist'}
            </button>
            <button type="button" class="btn btn-sm ${hasNotes ? 'btn-primary' : 'btn-secondary'}" onclick="openNotesModal('professor', ${p.id}, '${escapeJsString(p.notes || '')}', { name: '${escapeJsString(p.name)}' })">
              ${hasNotes ? '📝 Notes' : '+ Note'}
            </button>
          </div>
        </div>

        <div class="rubric-score-pills">
          ${matchBadge}
          ${recBadge}
          ${hasEmail ? `<span class="badge badge-teal">📧 ${escapeHtml(p.email)}</span>` : '<span class="badge badge-neutral">Email unlisted in source</span>'}
          <span class="rubric-pill">Research Overlap: ${p.research_overlap_score || 0}/40</span>
          <span class="rubric-pill">Experience Fit: ${p.experience_fit_score || 0}/30</span>
          <span class="rubric-pill">Recruitment: ${p.recruitment_fit_score || 0}/20</span>
        </div>

        ${interestsTags.length > 0 ? `
          <div class="professor-interests-tags">
            <strong class="text-xs text-muted">Focus Areas:</strong>
            ${interestsTags.map(t => `<span class="interest-tag">${escapeHtml(t)}</span>`).join('')}
          </div>
        ` : ''}

        ${p.match_reason ? `<div class="fit-reason-box">💡 <strong>Heuristic Fit Rationale:</strong> ${escapeHtml(p.match_reason)}</div>` : ''}

        <div class="evidence-toggle-wrap">
          <button type="button" class="evidence-toggle-btn" onclick="toggleEvidencePanel('prof_ev_${p.id}')">
            <span>🔍 Expand Source Recruitment Evidence</span>
          </button>
          <div id="prof_ev_${p.id}" class="evidence-panel hidden">
            <div class="verbatim-quote">"${escapeHtml(p.evidence_snippet || p.recruitment_evidence || 'Verified against institutional faculty directory text.')}"</div>
            <div class="text-xs text-muted mt-1">
              <strong>Official Profile:</strong> <a href="${escapeHtml(p.official_profile_url || p.source_url)}" target="_blank" rel="noopener" class="font-mono">${escapeHtml(p.official_profile_url || p.source_url)} ↗</a>
              ${hasEmail && p.email_date_observed ? `<span class="ml-2">• Email observed: ${formatDate(p.email_date_observed)}</span>` : ''}
            </div>
          </div>
        </div>

        <div class="scholarship-footer-actions">
          <div class="text-xs text-muted">
            Last checked: ${formatDate(p.created_at)}
          </div>
          <div class="action-btn-group">
            <button type="button" class="btn btn-sm btn-secondary" onclick="openEvidenceModal('${escapeJsString(p.name)}', '${escapeJsString(p.source_url)}', '${escapeJsString(p.evidence_snippet)}', {})">
              🔍 Evidence
            </button>
            <button type="button" class="btn btn-sm btn-secondary" onclick="openEvidenceHistory('professor', ${p.id}, '${escapeJsString(p.name)}')">
              📜 History
            </button>
            <button type="button" class="btn btn-sm btn-primary" onclick="initEmailDraftForProfessor(${p.id}, '${escapeJsString(p.name)}', '${escapeJsString(p.email)}', '${escapeJsString(p.university)}', '${escapeJsString(p.research_interests)}')">
              ✉️ Generate Inquiry Draft
            </button>
            <a href="${escapeHtml(p.official_profile_url || p.source_url)}" target="_blank" rel="noopener" class="btn btn-sm btn-secondary">
              🌐 Faculty Page ↗
            </a>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

async function toggleProfessorShortlist(id) {
  try {
    const res = await fetch(`/api/professors/${id}/shortlist`, { method: 'POST' });
    if (res.ok) {
      await loadProfessors();
      await loadOverview();
      await loadShortlist();
    }
  } catch (err) {
    showToast(`Shortlist toggle failed: ${err.message}`, 'error');
  }
}

// ============================================================================
// 10. SCREEN 8: SHORTLIST WORKSPACE
// ============================================================================

async function loadShortlist() {
  try {
    const res = await fetch('/api/shortlist');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    State.shortlist = data;

    setText('navShortlistCount', data.total_count || 0);
    setText('slCountAll', data.total_count || 0);
    setText('slCountUniv', (data.universities || []).length);
    setText('slCountAwards', (data.scholarships || []).length);
    setText('slCountFaculty', (data.professors || []).length);

    setText('slUnivCountBadge', `${(data.universities || []).length} bookmarked`);
    setText('slAwardsCountBadge', `${(data.scholarships || []).length} bookmarked`);
    setText('slFacultyCountBadge', `${(data.professors || []).length} bookmarked`);

    renderShortlist();
  } catch (err) {
    console.error('Failed to load shortlist:', err);
  }
}

function renderShortlist() {
  const data = State.shortlist;
  const subTab = State.filters.shortlist.subTab;

  const univSec = document.getElementById('slUnivSection');
  const awardsSec = document.getElementById('slAwardsSection');
  const facultySec = document.getElementById('slFacultySection');
  const emptyState = document.getElementById('slUniversalEmptyState');

  if (data.total_count === 0) {
    univSec?.classList.add('hidden');
    awardsSec?.classList.add('hidden');
    facultySec?.classList.add('hidden');
    emptyState?.classList.remove('hidden');
    return;
  }

  emptyState?.classList.add('hidden');

  univSec?.classList.toggle('hidden', subTab !== 'all' && subTab !== 'univ');
  awardsSec?.classList.toggle('hidden', subTab !== 'all' && subTab !== 'awards');
  facultySec?.classList.toggle('hidden', subTab !== 'all' && subTab !== 'faculty');

  // Render Universities
  const uTbody = document.getElementById('slUnivTableBody');
  if (uTbody) {
    if ((data.universities || []).length === 0) {
      uTbody.innerHTML = '<tr><td colspan="6" class="text-center py-3 text-muted">No universities shortlisted yet.</td></tr>';
    } else {
      uTbody.innerHTML = data.universities.map(u => `
        <tr>
          <td><strong>${escapeHtml(u.university_name)}</strong><br><span class="text-xs font-mono text-muted">${escapeHtml(u.domain)}</span></td>
          <td><span class="badge badge-navy">${escapeHtml(u.country || 'Unknown')}</span></td>
          <td class="font-mono text-teal">${u.scholarships_count || 0}</td>
          <td class="font-mono">${u.professors_count || 0}</td>
          <td>
            <button type="button" class="btn btn-sm ${u.notes ? 'btn-primary' : 'btn-secondary'}" onclick="openNotesModal('university', '${escapeJsString(u.domain)}', '${escapeJsString(u.notes || '')}', { university_name: '${escapeJsString(u.university_name)}' })">
              ${u.notes ? '📝 ' + escapeHtml(truncate(u.notes, 20)) : '+ Add Note'}
            </button>
          </td>
          <td>
            <button type="button" class="btn btn-sm btn-danger-outline" onclick="toggleUniversityShortlist('${escapeJsString(u.domain)}')">✕ Remove</button>
          </td>
        </tr>
      `).join('');
    }
  }

  // Render Awards
  const aList = document.getElementById('slAwardsList');
  if (aList) {
    if ((data.scholarships || []).length === 0) {
      aList.innerHTML = '<p class="text-sm text-muted text-center py-3">No funding opportunities shortlisted yet.</p>';
    } else {
      aList.innerHTML = data.scholarships.map(s => `
        <div class="scholarship-card mb-2">
          <div class="scholarship-header-row">
            <div class="scholarship-title-group">
              <h4>${escapeHtml(s.title)}</h4>
              <div class="scholarship-univ-meta">🏛️ ${escapeHtml(s.university)} • 📍 ${escapeHtml(s.country)} • 💰 ${escapeHtml(s.amount)}</div>
            </div>
            <div class="action-btn-group">
              <button type="button" class="btn btn-sm btn-primary" onclick="openNotesModal('scholarship', ${s.id}, '${escapeJsString(s.notes || '')}', { title: '${escapeJsString(s.title)}' })">
                📝 Notes
              </button>
              <button type="button" class="btn btn-sm btn-danger-outline" onclick="toggleScholarshipShortlist(${s.id})">✕ Unstar</button>
            </div>
          </div>
          ${s.notes ? `<div class="fit-reason-box mb-2"><strong>Personal Note:</strong> ${escapeHtml(s.notes)}</div>` : ''}
          <div class="flex-row-between text-xs">
            <a href="${escapeHtml(s.official_url || s.source_url)}" target="_blank" rel="noopener">🌐 Open Official Portal ↗</a>
            <button type="button" class="btn btn-sm btn-secondary" onclick="initEmailDraftForScholarship(${s.id}, '${escapeJsString(s.title)}', '${escapeJsString(s.university)}')">✉️ Draft Inquiry</button>
          </div>
        </div>
      `).join('');
    }
  }

  // Render Faculty
  const fList = document.getElementById('slFacultyList');
  if (fList) {
    if ((data.professors || []).length === 0) {
      fList.innerHTML = '<p class="text-sm text-muted text-center py-3">No professors shortlisted yet.</p>';
    } else {
      fList.innerHTML = data.professors.map(p => `
        <div class="professor-card mb-2">
          <div class="professor-header-row">
            <div class="professor-name-group">
              <h4>${escapeHtml(p.name)}</h4>
              <div class="professor-dept-univ">🏛️ ${escapeHtml(p.university)} • 🏢 ${escapeHtml(p.department)}</div>
            </div>
            <div class="action-btn-group">
              <button type="button" class="btn btn-sm btn-primary" onclick="openNotesModal('professor', ${p.id}, '${escapeJsString(p.notes || '')}', { name: '${escapeJsString(p.name)}' })">
                📝 Notes
              </button>
              <button type="button" class="btn btn-sm btn-danger-outline" onclick="toggleProfessorShortlist(${p.id})">✕ Unstar</button>
            </div>
          </div>
          ${p.notes ? `<div class="fit-reason-box mb-2"><strong>Personal Note:</strong> ${escapeHtml(p.notes)}</div>` : ''}
          <div class="flex-row-between text-xs">
            <span>${p.email && p.email.includes('@') ? `📧 ${escapeHtml(p.email)}` : 'Email unlisted'}</span>
            <button type="button" class="btn btn-sm btn-primary" onclick="initEmailDraftForProfessor(${p.id}, '${escapeJsString(p.name)}', '${escapeJsString(p.email)}', '${escapeJsString(p.university)}', '${escapeJsString(p.research_interests)}')">✉️ Draft Inquiry</button>
          </div>
        </div>
      `).join('');
    }
  }
}

// Shortlist Sub-Tabs
document.getElementById('slTabAllBtn')?.addEventListener('click', () => setShortlistSubTab('all'));
document.getElementById('slTabUnivBtn')?.addEventListener('click', () => setShortlistSubTab('univ'));
document.getElementById('slTabAwardsBtn')?.addEventListener('click', () => setShortlistSubTab('awards'));
document.getElementById('slTabFacultyBtn')?.addEventListener('click', () => setShortlistSubTab('faculty'));

function setShortlistSubTab(subTab) {
  State.filters.shortlist.subTab = subTab;
  document.getElementById('slTabAllBtn')?.classList.toggle('active', subTab === 'all');
  document.getElementById('slTabUnivBtn')?.classList.toggle('active', subTab === 'univ');
  document.getElementById('slTabAwardsBtn')?.classList.toggle('active', subTab === 'awards');
  document.getElementById('slTabFacultyBtn')?.classList.toggle('active', subTab === 'faculty');
  renderShortlist();
}

// Shortlist Exports (Markdown / JSON)
document.getElementById('exportShortlistMdBtn')?.addEventListener('click', () => {
  const data = State.shortlist;
  let md = `# ScholarScout Academic Shortlist Report\nGenerated: ${new Date().toISOString()}\n\n`;

  md += `## 1. Shortlisted Universities (${(data.universities || []).length})\n`;
  (data.universities || []).forEach(u => {
    md += `- **${u.university_name}** (${u.domain}) - ${u.country}\n  - Lead URL: ${u.lead_url || 'N/A'}\n  - Personal Notes: ${u.notes || 'None'}\n`;
  });

  md += `\n## 2. Shortlisted Funding Opportunities (${(data.scholarships || []).length})\n`;
  (data.scholarships || []).forEach(s => {
    md += `- **${s.title}** - ${s.university} (${s.country})\n  - Amount: ${s.amount}\n  - Deadline: ${s.deadline || s.deadline_date}\n  - Official Link: ${s.official_url || s.source_url}\n  - Notes: ${s.notes || 'None'}\n`;
  });

  md += `\n## 3. Shortlisted Faculty & Mentors (${(data.professors || []).length})\n`;
  (data.professors || []).forEach(p => {
    md += `- **${p.name}** (${p.title || 'Faculty'}) - ${p.university} (${p.department})\n  - Email: ${p.email}\n  - Focus: ${p.research_interests}\n  - Notes: ${p.notes || 'None'}\n`;
  });

  downloadFile(md, 'scholarscout_shortlist.md', 'text/markdown');
  showToast('Shortlist exported as Markdown!', 'success');
});

document.getElementById('exportShortlistJsonBtn')?.addEventListener('click', () => {
  const jsonStr = JSON.stringify(State.shortlist, null, 2);
  downloadFile(jsonStr, 'scholarscout_shortlist.json', 'application/json');
  showToast('Shortlist exported as JSON!', 'success');
});

// ============================================================
// 11. SCREEN 9: EMAIL-DRAFTING & CONTROLLED SENDING WORKSPACE
// ============================================================

// Initialize Controlled Sending & Subviews
function setupControlledSending() {
  // Master sending toggle
  document.getElementById('toggleMasterSendingBtn')?.addEventListener('click', toggleMasterSending);
  
  // Account picker
  document.getElementById('activeAccountSelect')?.addEventListener('change', (e) => {
    State.selectedAccountId = parseInt(e.target.value, 10) || 1;
    showToast(`Active sender account switched to Account #${State.selectedAccountId}`, 'info');
  });

  // Sync replies button
  document.getElementById('syncRepliesHeaderBtn')?.addEventListener('click', syncReplies);

  // Sub-view tab switching
  setupEmailWorkspaceSubviews();

  // Approve & Pre-Send buttons
  document.getElementById('editorApproveBtn')?.addEventListener('click', approveCurrentDraft);
  document.getElementById('editorPreSendInspectBtn')?.addEventListener('click', () => {
    if (State.activeDraftId) openPreSendInspectionModal(State.activeDraftId);
  });

  // Batch Approval
  document.getElementById('selectAllDraftsCheckbox')?.addEventListener('change', (e) => {
    toggleSelectAllDrafts(e.target.checked);
  });
  document.getElementById('batchApproveSelectedBtn')?.addEventListener('click', batchApproveSelectedDrafts);

  // Queue Action buttons
  document.getElementById('refreshQueueBtn')?.addEventListener('click', loadOutboundQueue);
  document.getElementById('processQueueBatchBtn')?.addEventListener('click', processQueueBatch);

  // DNC Form
  document.getElementById('addDncForm')?.addEventListener('submit', submitDncForm);

  // Audit Log refresh
  document.getElementById('refreshAuditLogBtn')?.addEventListener('click', loadEmailAuditLogs);

  // General workspace view refresh button
  document.getElementById('refreshCurrentWorkspaceViewBtn')?.addEventListener('click', refreshActiveEmailSubview);
}

function setupEmailWorkspaceSubviews() {
  const tabBtns = document.querySelectorAll('.subviews-tab-list .subview-tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const subview = btn.dataset.subview;
      switchEmailSubview(subview);
    });
  });
}

function switchEmailSubview(subviewId) {
  if (!subviewId) return;
  State.outreachSubview = subviewId;

  // Update tab buttons
  document.querySelectorAll('.subviews-tab-list .subview-tab-btn').forEach(btn => {
    const isTarget = btn.dataset.subview === subviewId;
    btn.classList.toggle('active', isTarget);
    btn.setAttribute('aria-selected', isTarget ? 'true' : 'false');
  });

  // Hide all subview containers and show target
  const subviews = ['viewDraftsEditor', 'viewOutboundQueue', 'viewDoNotContact', 'viewAuditLogs'];
  subviews.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      if (id === subviewId) {
        el.classList.remove('hidden');
      } else {
        el.classList.add('hidden');
      }
    }
  });

  // Refresh relevant subview data
  if (subviewId === 'viewDraftsEditor') loadDrafts();
  if (subviewId === 'viewOutboundQueue') loadOutboundQueue();
  if (subviewId === 'viewDoNotContact') loadDoNotContact();
  if (subviewId === 'viewAuditLogs') loadEmailAuditLogs();
}

function refreshActiveEmailSubview() {
  switchEmailSubview(State.outreachSubview || 'viewDraftsEditor');
}

// Load Sending Master Settings & Update Banner
async function loadSendingSettings() {
  try {
    const res = await fetch('/api/emails/settings');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    State.sendingSettings = data;
    updateSendingBannerUI(data.sending_master_enabled);
  } catch (err) {
    console.error('Failed to load sending settings:', err);
  }
}

function updateSendingBannerUI(isEnabled) {
  const banner = document.getElementById('masterSendingBanner');
  const icon = document.getElementById('sendingStatusIcon');
  const title = document.getElementById('sendingBannerTitle');
  const desc = document.getElementById('sendingBannerDesc');
  const btn = document.getElementById('toggleMasterSendingBtn');

  if (!banner) return;

  if (isEnabled) {
    banner.className = 'sending-banner active-sending';
    if (icon) icon.innerText = '🚀';
    if (title) title.innerText = 'Sending Status: CONTROLLED SENDING ACTIVE';
    if (desc) desc.innerText = 'Approved messages in the outbound queue can be dispatched according to rate limits and hourly quotas.';
    if (btn) {
      btn.innerText = '⏸️ Pause Sending';
      btn.className = 'btn btn-sm btn-warning';
    }
  } else {
    banner.className = 'sending-banner safety-mode';
    if (icon) icon.innerText = '🛡️';
    if (title) title.innerText = 'Sending Status: SAFETY MODE (Outbound Dispatch Disabled)';
    if (desc) desc.innerText = 'Messages remain safely in draft or queued state until an account is connected and you explicitly enable controlled sending.';
    if (btn) {
      btn.innerText = '⚡ Enable Sending';
      btn.className = 'btn btn-sm btn-secondary';
    }
  }
}

async function toggleMasterSending() {
  const current = State.sendingSettings?.sending_master_enabled;
  const nextState = !current;
  
  if (nextState) {
    const ok = confirm('⚠️ Activate Controlled Email Sending?\n\nMessages in the outbound queue will be eligible for controlled dispatch through your selected provider.\n\nAre you sure you want to proceed?');
    if (!ok) return;
  }

  try {
    const res = await fetch('/api/emails/settings/toggle-sending', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        enabled: nextState,
        confirmation_ack: true,
        reason: 'User dashboard toggle'
      })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    State.sendingSettings.sending_master_enabled = data.sending_master_enabled;
    updateSendingBannerUI(data.sending_master_enabled);
    showToast(data.message, nextState ? 'warning' : 'info');
  } catch (err) {
    showToast(`Could not toggle sending: ${err.message}`, 'error');
  }
}

// Load Connected Email Accounts
async function loadEmailAccounts() {
  try {
    const res = await fetch('/api/emails/accounts');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const accounts = await res.json();
    State.emailAccounts = accounts;

    const select = document.getElementById('activeAccountSelect');
    if (select) {
      if (accounts.length === 0) {
        select.innerHTML = '<option value="1">Mock Sandbox (Safe Offline Testing)</option>';
      } else {
        select.innerHTML = accounts.map(a => `
          <option value="${a.id}" ${a.id === State.selectedAccountId ? 'selected' : ''}>
            ${escapeHtml(a.name)} (${escapeHtml(a.email_address)}) • ${escapeHtml(a.provider_type)}
          </option>
        `).join('');
      }
    }
  } catch (err) {
    console.error('Failed to load email accounts:', err);
  }
}

// Sync Provider Replies
async function syncReplies() {
  const accId = State.selectedAccountId || 1;
  const btn = document.getElementById('syncRepliesHeaderBtn');
  if (btn) btn.disabled = true;

  try {
    showToast(`Scanning account #${accId} for replies...`, 'info', 2000);
    const res = await fetch(`/api/emails/accounts/${accId}/sync-replies`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showToast(data.message || `Sync complete: ${data.replies_found || 0} reply detected.`, 'success');
    await loadDrafts();
    await loadOutboundQueue();
  } catch (err) {
    showToast(`Reply sync failed: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// Load Outreach Instructions & Template Settings
async function loadOutreachSettings() {
  try {
    const res = await fetch('/api/outreach-settings');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    State.outreachSettings = data;

    setInputValue('setting_purpose', data.purpose || '');
    setInputValue('setting_degree_intake', data.target_degree_intake || '');
    setInputValue('setting_tone_length', data.tone_and_length || '');
    setInputValue('setting_specific_request', data.specific_request || '');
    setInputValue('setting_background_emphasis', data.background_to_emphasize || '');
    setInputValue('setting_attachments', data.proposed_attachments || '');
    setInputValue('setting_wording_preferences', data.optional_wording_preferences || '');
    setInputValue('setting_signature', data.signature || '');
  } catch (err) {
    console.error('Failed to load outreach settings:', err);
  }
}

// Save Outreach Instructions
document.getElementById('saveOutreachSettingsBtn')?.addEventListener('click', async () => {
  try {
    const payload = {
      purpose: getInputValue('setting_purpose'),
      target_degree_intake: getInputValue('setting_degree_intake'),
      tone_and_length: getInputValue('setting_tone_length'),
      specific_request: getInputValue('setting_specific_request'),
      background_to_emphasize: getInputValue('setting_background_emphasis'),
      proposed_attachments: getInputValue('setting_attachments'),
      optional_wording_preferences: getInputValue('setting_wording_preferences'),
      signature: getInputValue('setting_signature')
    };

    const res = await fetch('/api/outreach-settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    State.outreachSettings = data.settings;
    showToast('Outreach instructions saved! Applied to all new drafts.', 'success');
    document.getElementById('outreachSettingsPanel')?.classList.add('hidden');
  } catch (err) {
    showToast(`Failed to save outreach instructions: ${err.message}`, 'error');
  }
});

// Reset Outreach Settings
document.getElementById('resetOutreachSettingsBtn')?.addEventListener('click', () => {
  setInputValue('setting_purpose', 'PhD Advisorship & Research Assistantship Inquiry');
  setInputValue('setting_degree_intake', `Ph.D. in ${State.profile?.target_field || 'Computer Science'} (Fall 2026)`);
  setInputValue('setting_tone_length', 'Professional, concise, scholarly; strictly under 200 words');
  setInputValue('setting_specific_request', 'Request a brief 15-minute introductory video call to discuss potential research synergy and prospective Ph.D. positions.');
  setInputValue('setting_background_emphasis', `${State.profile?.background_summary || 'Strong foundation in AI/ML research, 3.95 GPA, hands-on PyTorch engineering.'}`);
  setInputValue('setting_attachments', 'Academic CV (PDF), Unofficial Transcript, 1-page Research Summary');
  setInputValue('setting_wording_preferences', 'Focus strictly on specific lab publications and neuro-symbolic research; avoid generic flattery or assumptions about guaranteed funding.');
  setInputValue('setting_signature', `Sincerely,\n${State.profile?.name || '[Candidate Name]'}\nApplicant, Graduate Research\nEmail: ${State.profile?.email || 'candidate@alumni.univ.edu'}\nPortfolio: ${State.profile?.portfolio_url || 'https://github.com/scholarscout-candidate'}`);
  showToast('Restored default outreach template instructions.', 'info');
});

// Toggle Outreach Settings Card
document.getElementById('toggleOutreachSettingsBtn')?.addEventListener('click', () => {
  const panel = document.getElementById('outreachSettingsPanel');
  if (panel) {
    panel.classList.toggle('hidden');
    if (!panel.classList.contains('hidden')) {
      loadOutreachSettings();
      panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }
});

document.getElementById('hideOutreachSettingsBtn')?.addEventListener('click', () => {
  document.getElementById('outreachSettingsPanel')?.classList.add('hidden');
});

// Load and Render Drafts Catalog
async function loadDrafts(selectDraftId = null) {
  try {
    const res = await fetch('/api/emails');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const drafts = await res.json();
    State.drafts = drafts;

    setText('draftsCount', drafts.length);
    setText('subviewDraftsBadge', drafts.length);

    // Update status count pills
    const countAll = drafts.length;
    const countDraft = drafts.filter(d => (d.approval_status === 'draft' || !d.approval_status) && d.status !== 'verified_ready').length;
    const countApproved = drafts.filter(d => d.approval_status === 'approved' || d.status === 'verified_ready').length;
    const countQueued = drafts.filter(d => d.approval_status === 'queued' || d.status === 'queued').length;
    const countAccepted = drafts.filter(d => d.approval_status === 'provider-accepted' || d.status === 'sent' || d.status === 'provider-accepted').length;
    const countUncertain = drafts.filter(d => d.approval_status === 'uncertain' || d.status === 'uncertain').length;

    setText('countDraftsAll', countAll);
    setText('countDraftsDraft', countDraft);
    setText('countDraftsApproved', countApproved);
    setText('countDraftsQueued', countQueued);
    setText('countDraftsAccepted', countAccepted);
    setText('countDraftsUncertain', countUncertain);

    renderWorkspaceDraftsList();

    // Auto-select draft
    if (selectDraftId) {
      selectWorkspaceDraft(selectDraftId);
    } else if (State.activeDraftId && drafts.some(d => d.id === State.activeDraftId)) {
      selectWorkspaceDraft(State.activeDraftId);
    } else if (drafts.length > 0) {
      selectWorkspaceDraft(drafts[0].id);
    } else {
      State.activeDraftId = null;
      State.activeDraft = null;
      document.getElementById('editorUnselectedState')?.classList.remove('hidden');
      document.getElementById('editorActiveContent')?.classList.add('hidden');
    }
  } catch (err) {
    console.error('Failed to load drafts:', err);
  }
}

// Render Left Column Draft Cards
function renderWorkspaceDraftsList() {
  const container = document.getElementById('workspaceDraftsList');
  const emptyState = document.getElementById('workspaceDraftsEmpty');
  if (!container) return;

  let filtered = [...State.drafts];

  // Apply Status Filter
  const statusFilter = State.draftsStatusFilter || 'all';
  if (statusFilter === 'draft') {
    filtered = filtered.filter(d => (d.approval_status === 'draft' || !d.approval_status) && d.status !== 'verified_ready');
  } else if (statusFilter === 'approved') {
    filtered = filtered.filter(d => d.approval_status === 'approved' || d.status === 'verified_ready');
  } else if (statusFilter === 'queued') {
    filtered = filtered.filter(d => d.approval_status === 'queued' || d.status === 'queued');
  } else if (statusFilter === 'provider-accepted') {
    filtered = filtered.filter(d => d.approval_status === 'provider-accepted' || d.status === 'sent' || d.status === 'provider-accepted');
  } else if (statusFilter === 'uncertain') {
    filtered = filtered.filter(d => d.approval_status === 'uncertain' || d.status === 'uncertain');
  }

  // Apply Search Filter
  const searchTerm = (document.getElementById('draftSearchInput')?.value || '').trim().toLowerCase();
  if (searchTerm) {
    filtered = filtered.filter(d =>
      (d.recipient_name || '').toLowerCase().includes(searchTerm) ||
      (d.recipient_email || '').toLowerCase().includes(searchTerm) ||
      (d.subject || '').toLowerCase().includes(searchTerm) ||
      (d.body_text || '').toLowerCase().includes(searchTerm) ||
      (d.prof_university || '').toLowerCase().includes(searchTerm) ||
      (d.university_name || '').toLowerCase().includes(searchTerm)
    );
  }

  if (filtered.length === 0) {
    container.innerHTML = '';
    emptyState?.classList.remove('hidden');
    return;
  }

  emptyState?.classList.add('hidden');

  container.innerHTML = filtered.map(d => {
    const isActive = d.id === State.activeDraftId;
    const isSelected = State.selectedDraftIds.has(d.id);
    const isFlagged = d.unsupported_claims_flag == 1 || d.status === 'needs_review';
    const isDiscouraged = d.status === 'flagged_discouraged' || d.contact_instructions_flag === 'discouraged' || d.contact_instructions_flag === 'portal_required';
    const isApproved = d.approval_status === 'approved' || d.status === 'verified_ready';
    const isQueued = d.approval_status === 'queued';
    const isAccepted = d.approval_status === 'provider-accepted' || d.status === 'sent';
    const isUncertain = d.approval_status === 'uncertain';

    let cardClasses = 'draft-card-item';
    if (isActive) cardClasses += ' active';
    if (isDiscouraged) cardClasses += ' discouraged';
    else if (isFlagged) cardClasses += ' flagged';

    let statusBadge = '<span class="badge badge-teal">Draft</span>';
    if (isAccepted) {
      statusBadge = '<span class="badge badge-success">🚀 Sent</span>';
    } else if (isQueued) {
      statusBadge = '<span class="badge badge-primary">📬 Queued</span>';
    } else if (isApproved) {
      statusBadge = '<span class="badge badge-teal">✅ Approved</span>';
    } else if (isUncertain) {
      statusBadge = '<span class="badge badge-warning">⚠️ Uncertain</span>';
    } else if (isDiscouraged) {
      statusBadge = '<span class="badge badge-danger">🛑 Discouraged</span>';
    } else if (isFlagged) {
      statusBadge = '<span class="badge badge-warning">⚠️ Review</span>';
    }

    const recipientInst = d.prof_university || d.university_name || 'Academic Institution';

    return `
      <div class="${cardClasses}" onclick="selectWorkspaceDraft(${d.id})" id="draft-card-${d.id}">
        <div class="draft-card-top">
          <div class="flex-row-between gap-2 align-center">
            <input type="checkbox" class="draft-checkbox" value="${d.id}" ${isSelected ? 'checked' : ''} onclick="event.stopPropagation(); toggleDraftSelection(${d.id}, this.checked)" aria-label="Select draft #${d.id}">
            <div class="draft-card-name">${escapeHtml(d.recipient_name)}</div>
          </div>
          ${statusBadge}
        </div>
        <div class="draft-card-univ">${escapeHtml(recipientInst)}</div>
        <div class="draft-card-subject">${escapeHtml(d.subject || 'No Subject')}</div>
        <div class="draft-card-meta-row">
          <span>v${d.profile_version || 1} • ${formatDate(d.created_at)}</span>
          <span class="text-xs font-mono text-muted">#${d.id}</span>
        </div>
      </div>
    `;
  }).join('');
}

// Draft Selection & Batch Approval Handlers
function toggleDraftSelection(draftId, isChecked) {
  if (isChecked) {
    State.selectedDraftIds.add(draftId);
  } else {
    State.selectedDraftIds.delete(draftId);
  }
  updateBatchApprovalBar();
}

function toggleSelectAllDrafts(isChecked) {
  if (isChecked) {
    State.drafts.forEach(d => State.selectedDraftIds.add(d.id));
  } else {
    State.selectedDraftIds.clear();
  }
  renderWorkspaceDraftsList();
  updateBatchApprovalBar();
}

function updateBatchApprovalBar() {
  const count = State.selectedDraftIds.size;
  setText('selectedDraftsCount', count);
  const btn = document.getElementById('batchApproveSelectedBtn');
  if (btn) btn.disabled = count === 0;
}

async function batchApproveSelectedDrafts() {
  const ids = Array.from(State.selectedDraftIds);
  if (ids.length === 0) return;

  const btn = document.getElementById('batchApproveSelectedBtn');
  if (btn) btn.disabled = true;

  try {
    showToast(`Approving exact content versions for ${ids.length} draft(s)...`, 'info', 2000);
    const res = await fetch('/api/emails/drafts/batch-approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ draft_ids: ids })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showToast(data.message || `Batch approval completed (${data.approved_count} approved)!`, 'success');
    State.selectedDraftIds.clear();
    updateBatchApprovalBar();
    await loadDrafts(State.activeDraftId);
  } catch (err) {
    showToast(`Batch approval failed: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// Select and Display Draft in Master-Detail Editor
async function selectWorkspaceDraft(draftId) {
  State.activeDraftId = draftId;

  // Update active state styling in left list
  document.querySelectorAll('.draft-card-item').forEach(el => el.classList.remove('active'));
  document.getElementById(`draft-card-${draftId}`)?.classList.add('active');

  try {
    const res = await fetch(`/api/emails/${draftId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const draft = await res.json();
    State.activeDraft = draft;

    document.getElementById('editorUnselectedState')?.classList.add('hidden');
    document.getElementById('editorActiveContent')?.classList.remove('hidden');

    // Populate Recipient Header
    setText('editorRecipientName', draft.recipient_name || 'Faculty Member');
    const subtitle = [draft.prof_dept, draft.prof_university || draft.university_name].filter(Boolean).join(' • ');
    setText('editorRecipientSubtitle', subtitle || draft.recipient_role || 'Academic Inquiry');
    setText('editorRecipientEmail', draft.recipient_email || 'No email on record');

    const mailtoLink = document.getElementById('editorMailtoLink');
    if (mailtoLink) {
      mailtoLink.href = `mailto:${encodeURIComponent(draft.recipient_email || '')}?subject=${encodeURIComponent(draft.subject || '')}&body=${encodeURIComponent(draft.body_text || '')}`;
    }

    // Cryptographic Version Hash Pill
    const hashPill = document.getElementById('editorHashPill');
    if (hashPill) {
      if (draft.content_hash) {
        hashPill.innerText = `SHA256: ${draft.content_hash.slice(0, 10)}...`;
        hashPill.title = `Full Version Hash: ${draft.content_hash}`;
      } else {
        hashPill.innerText = 'SHA256: -';
      }
    }

    // Status Badge
    const statusBadge = document.getElementById('editorStatusBadge');
    if (statusBadge) {
      const isApproved = draft.approval_status === 'approved' || draft.status === 'verified_ready';
      const isQueued = draft.approval_status === 'queued';
      const isAccepted = draft.approval_status === 'provider-accepted' || draft.status === 'sent';
      const isUncertain = draft.approval_status === 'uncertain';

      if (isAccepted) {
        statusBadge.className = 'badge badge-success';
        statusBadge.innerText = '🚀 Sent / Accepted';
      } else if (isQueued) {
        statusBadge.className = 'badge badge-primary';
        statusBadge.innerText = '📬 In Outbound Queue';
      } else if (isApproved) {
        statusBadge.className = 'badge badge-success';
        statusBadge.innerText = '✅ Version Approved';
      } else if (isUncertain) {
        statusBadge.className = 'badge badge-warning';
        statusBadge.innerText = '⚠️ Uncertain Status';
      } else if (draft.status === 'flagged_discouraged' || draft.contact_instructions_flag === 'discouraged' || draft.contact_instructions_flag === 'portal_required') {
        statusBadge.className = 'badge badge-danger';
        statusBadge.innerText = '🛑 Outreach Discouraged';
      } else if (draft.unsupported_claims_flag == 1 || draft.status === 'needs_review') {
        statusBadge.className = 'badge badge-warning';
        statusBadge.innerText = '⚠️ Needs Review / Unsupported Claims';
      } else {
        statusBadge.className = 'badge badge-teal';
        statusBadge.innerText = 'Draft (Unapproved)';
      }
    }

    // Policy Notice & Grounding Warning Banner
    renderPolicyAlertBanner(draft);

    // Form inputs
    setInputValue('editorSubjectInput', draft.subject || '');
    setInputValue('editorBodyInput', draft.body_text || '');
    updateEditorWordCount(draft.body_text || '');

    // Proposed Attachments
    renderAttachmentsList(draft.attachments || ['Academic CV (PDF)']);

    // Metadata Bar
    setText('editorProfileVersion', `v${draft.profile_version || 1}`);
    setText('editorGeneratedDate', formatDate(draft.created_at));
    setText('editorDraftId', draft.id);

    const approvedMeta = document.getElementById('editorApprovedAtMeta');
    if (approvedMeta) {
      approvedMeta.innerHTML = draft.approved_at 
        ? `<span class="meta-item">🔒 Approved: <strong>${formatDate(draft.approved_at)}</strong></span>`
        : '';
    }

    // Side-by-Side Evidence Inspector
    renderEvidenceInspector(draft.evidence_used || {});

  } catch (err) {
    console.error('Failed to select draft:', err);
    showToast(`Error loading draft details: ${err.message}`, 'error');
  }
}

// Single Draft Exact Version Approval
async function approveCurrentDraft() {
  if (!State.activeDraftId) return;
  const btn = document.getElementById('editorApproveBtn');
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`/api/emails/drafts/${State.activeDraftId}/approve`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    showToast(data.message || 'Exact version approved and locked!', 'success');
    await loadDrafts(State.activeDraftId);
  } catch (err) {
    showToast(`Approval failed: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// Pre-Send Inspection Modal
async function openPreSendInspectionModal(draftId) {
  const modal = document.getElementById('preSendModalBackdrop');
  const content = document.getElementById('preSendModalContent');
  const confirmBtn = document.getElementById('confirmPreSendQueueBtn');
  if (!modal || !content) return;

  modal.classList.remove('hidden');
  content.innerHTML = '<div class="text-center py-4 text-muted"><span class="loading-spinner"></span> Performing pre-send safety verification...</div>';
  if (confirmBtn) confirmBtn.disabled = true;

  try {
    const accId = State.selectedAccountId || 1;
    const res = await fetch(`/api/emails/drafts/${draftId}/pre-send-preview?account_id=${accId}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const p = await res.json();

    const dncBadge = p.safety_checks?.do_not_contact_suppressed
      ? '<span class="badge badge-danger">🛑 SUPPRESSED (On Do-Not-Contact List)</span>'
      : '<span class="badge badge-success">✓ Passed (Not Suppressed)</span>';

    const dupBadge = p.safety_checks?.duplicate_prior_send
      ? `<span class="badge badge-warning">⚠️ Already Sent on ${formatDate(p.safety_checks?.prior_send_date)}</span>`
      : '<span class="badge badge-success">✓ Passed (No Prior Sends)</span>';

    const hashMatchBadge = p.version_hash_matches_approved
      ? '<span class="badge badge-success">✓ Exact Approved Version Match</span>'
      : (p.approval_status === 'approved' ? '<span class="badge badge-danger">✕ Content Modified Since Approval</span>' : '<span class="badge badge-warning">⚠️ Unapproved Version</span>');

    const canQueue = p.can_queue !== false && !p.safety_checks?.do_not_contact_suppressed;
    if (confirmBtn) confirmBtn.disabled = !canQueue;

    content.innerHTML = `
      <div class="presend-summary-grid">
        <div class="card p-3 mb-3">
          <div class="flex-row-between align-center mb-2">
            <div>
              <strong>Recipient:</strong> ${escapeHtml(p.recipient_name)} &lt;<span class="font-mono">${escapeHtml(p.recipient_email)}</span>&gt;
            </div>
            <div>
              ${dncBadge}
            </div>
          </div>
          <div class="flex-row-between align-center mb-2">
            <div>
              <strong>Account:</strong> ${escapeHtml(p.account?.name || 'Mock Sandbox')} (${escapeHtml(p.account?.email_address || 'sandbox@scholarscout.local')})
            </div>
            <div>
              ${dupBadge}
            </div>
          </div>
          <div class="flex-row-between align-center">
            <div class="font-mono text-xs">
              <strong>Hash:</strong> ${escapeHtml((p.content_hash || '').slice(0, 16))}...
            </div>
            <div>
              ${hashMatchBadge}
            </div>
          </div>
        </div>

        <div class="card p-3 mb-3">
          <div class="text-sm font-semibold mb-1">Subject Line</div>
          <div class="font-semibold text-teal mb-2">${escapeHtml(p.subject)}</div>
          <div class="text-sm font-semibold mb-1">Validated Attachments</div>
          <div class="text-xs font-mono text-muted mb-2">
            ${(p.attachments && p.attachments.length > 0) ? p.attachments.map(a => `<div>📄 ${escapeHtml(a.filename || a)} (${a.size_bytes ? Math.round(a.size_bytes/1024) + ' KB' : 'verified'})</div>`).join('') : 'None'}
          </div>
          <div class="text-sm font-semibold mb-1">Message Body Preview</div>
          <div class="presend-body-box font-sans text-xs p-2 bg-subtle rounded" style="max-height: 180px; overflow-y: auto; white-space: pre-wrap;">${escapeHtml(p.body_text)}</div>
        </div>
      </div>
    `;
  } catch (err) {
    content.innerHTML = `<div class="alert alert-danger">Failed to generate pre-send preview: ${escapeHtml(err.message)}</div>`;
  }
}

async function confirmPreSendQueue() {
  if (!State.activeDraftId) return;
  const btn = document.getElementById('confirmPreSendQueueBtn');
  if (btn) btn.disabled = true;

  try {
    const accId = State.selectedAccountId || 1;
    const res = await fetch(`/api/emails/drafts/${State.activeDraftId}/queue?account_id=${accId}`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    showToast(data.message || 'Draft enqueued into outbound dispatch queue!', 'success');
    document.getElementById('preSendModalBackdrop')?.classList.add('hidden');
    switchEmailSubview('viewOutboundQueue');
  } catch (err) {
    showToast(`Queue failed: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ============================================================
// OUTBOUND QUEUE CONTROLLER
// ============================================================

async function loadOutboundQueue() {
  const tbody = document.getElementById('outboundQueueTableBody');
  if (!tbody) return;

  try {
    const res = await fetch('/api/emails/queue');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const queue = await res.json();
    State.outboundQueue = queue;

    setText('subviewQueueBadge', queue.filter(q => q.status === 'queued').length);

    if (queue.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="text-center py-4 text-muted">Outbound queue is currently empty. Approve and enqueue drafts from the live editor above.</td></tr>';
      return;
    }

    tbody.innerHTML = queue.map(q => {
      let statusBadge = '<span class="badge badge-primary">⏳ Queued</span>';
      if (q.status === 'provider-accepted' || q.status === 'sent') {
        statusBadge = '<span class="badge badge-success">🚀 Accepted</span>';
      } else if (q.status === 'uncertain') {
        statusBadge = '<span class="badge badge-warning">⚠️ Uncertain Timeout</span>';
      } else if (q.status === 'failed') {
        statusBadge = '<span class="badge badge-danger">❌ Failed</span>';
      } else if (q.status === 'cancelled') {
        statusBadge = '<span class="badge badge-neutral">🛑 Cancelled</span>';
      }

      let actions = '';
      if (q.status === 'queued' || q.status === 'failed') {
        actions += `<button type="button" class="btn btn-xs btn-primary mr-1" onclick="processQueueItem(${q.id})">🚀 Send</button>`;
        actions += `<button type="button" class="btn btn-xs btn-danger" onclick="cancelQueueItem(${q.id})">🗑️</button>`;
      } else if (q.status === 'uncertain') {
        actions += `<button type="button" class="btn btn-xs btn-warning mr-1" onclick="reconcileQueueItem(${q.id})">🔄 Reconcile</button>`;
        actions += `<button type="button" class="btn btn-xs btn-danger" onclick="cancelQueueItem(${q.id})">🗑️</button>`;
      } else if (q.status === 'provider-accepted' || q.status === 'sent') {
        actions += `<button type="button" class="btn btn-xs btn-secondary" onclick="generateFollowupForDraft(${q.draft_id})">✉️ Follow-up</button>`;
      }

      return `
        <tr>
          <td class="font-mono text-xs">#${q.id}</td>
          <td><strong>${escapeHtml(q.recipient_email)}</strong></td>
          <td class="text-xs">${escapeHtml(truncate(q.subject, 30))}</td>
          <td class="text-xs text-muted">${escapeHtml(q.account_name || 'Sandbox')}</td>
          <td class="font-mono text-xs text-muted">${escapeHtml((q.content_hash || '').slice(0, 8))}...</td>
          <td>${statusBadge}</td>
          <td class="font-mono text-xs">${q.attempts || 0}</td>
          <td class="font-mono text-xs text-muted">${escapeHtml(q.provider_message_id || '-')}</td>
          <td>${actions}</td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to load outbound queue:', err);
  }
}

async function processQueueBatch() {
  const btn = document.getElementById('processQueueBatchBtn');
  if (btn) btn.disabled = true;

  try {
    showToast('Dispatching pending queue items...', 'info', 2000);
    const res = await fetch('/api/emails/queue/process-batch?limit=10', { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showToast(`Batch processed: ${data.dispatched_count || 0} dispatched, ${data.failed_count || 0} failed.`, 'success');
    await loadOutboundQueue();
    await loadDrafts();
  } catch (err) {
    showToast(`Batch dispatch failed: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function processQueueItem(queueId) {
  try {
    showToast(`Dispatching queue item #${queueId}...`, 'info', 1500);
    const res = await fetch(`/api/emails/queue/${queueId}/process`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    showToast(data.message || 'Queue item dispatched!', 'success');
    await loadOutboundQueue();
    await loadDrafts();
  } catch (err) {
    showToast(`Dispatch failed: ${err.message}`, 'error');
  }
}

async function cancelQueueItem(queueId) {
  if (!confirm(`Cancel queued message #${queueId}?`)) return;
  try {
    const res = await fetch(`/api/emails/queue/${queueId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast('Queued message cancelled.', 'info');
    await loadOutboundQueue();
  } catch (err) {
    showToast(`Cancel failed: ${err.message}`, 'error');
  }
}

async function reconcileQueueItem(queueId) {
  try {
    showToast(`Reconciling timeout status for item #${queueId}...`, 'info', 2000);
    const res = await fetch(`/api/emails/queue/${queueId}/reconcile`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showToast(data.message || 'Item reconciled.', 'success');
    await loadOutboundQueue();
  } catch (err) {
    showToast(`Reconciliation failed: ${err.message}`, 'error');
  }
}

async function generateFollowupForDraft(draftId) {
  try {
    showToast('Generating respectful follow-up draft...', 'info', 2000);
    const res = await fetch(`/api/emails/drafts/${draftId}/generate-followup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ days_elapsed: 7 })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    showToast(data.message || 'Follow-up draft created!', 'success');
    switchEmailSubview('viewDraftsEditor');
    await loadDrafts(data.followup_draft_id);
  } catch (err) {
    showToast(`Could not generate follow-up: ${err.message}`, 'error');
  }
}

// ============================================================
// DO-NOT-CONTACT LIST CONTROLLER
// ============================================================

async function loadDoNotContact() {
  const tbody = document.getElementById('dncTableBody');
  if (!tbody) return;

  try {
    const res = await fetch('/api/emails/dnc');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const list = await res.json();
    State.doNotContactList = list;

    setText('dncListCount', list.length);
    setText('subviewDncBadge', list.length);

    if (list.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-muted">No active suppression patterns. Use the form above to suppress specific emails or whole university domains.</td></tr>';
      return;
    }

    tbody.innerHTML = list.map(item => `
      <tr>
        <td class="font-mono text-xs"><strong>${escapeHtml(item.pattern)}</strong></td>
        <td class="text-xs text-muted">${escapeHtml(item.reason || 'Manual suppression')}</td>
        <td><span class="badge badge-neutral">${escapeHtml(item.source || 'user')}</span></td>
        <td class="text-xs text-muted">${formatDate(item.created_at)}</td>
        <td>
          <button type="button" class="btn btn-xs btn-danger" onclick="removeDncRule(${item.id})" title="Remove Suppression">🗑️</button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('Failed to load DNC list:', err);
  }
}

async function submitDncForm(e) {
  e.preventDefault();
  const pattern = (document.getElementById('dncPatternInput')?.value || '').trim();
  const reason = (document.getElementById('dncReasonInput')?.value || '').trim();

  if (!pattern) return;

  try {
    const res = await fetch('/api/emails/dnc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pattern: pattern, reason: reason })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    showToast(`Suppression pattern "${pattern}" registered!`, 'success');
    setInputValue('dncPatternInput', '');
    setInputValue('dncReasonInput', '');
    await loadDoNotContact();
  } catch (err) {
    showToast(`Failed to add suppression: ${err.message}`, 'error');
  }
}

async function removeDncRule(id) {
  if (!confirm(`Remove suppression rule #${id}?`)) return;
  try {
    const res = await fetch(`/api/emails/dnc/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast('Suppression rule removed.', 'info');
    await loadDoNotContact();
  } catch (err) {
    showToast(`Failed to remove rule: ${err.message}`, 'error');
  }
}

// ============================================================
// OUTBOUND SENDING AUDIT LOG CONTROLLER
// ============================================================

async function loadEmailAuditLogs() {
  const tbody = document.getElementById('auditLogTableBody');
  if (!tbody) return;

  try {
    const res = await fetch('/api/emails/audit-logs?limit=50');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const logs = await res.json();
    State.emailAuditLogs = logs;

    setText('subviewAuditBadge', logs.length);

    if (logs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No audit log entries recorded yet.</td></tr>';
      return;
    }

    tbody.innerHTML = logs.map(l => {
      let actionBadge = `<span class="badge badge-neutral">${escapeHtml(l.action)}</span>`;
      if (l.action.includes('approved')) actionBadge = '<span class="badge badge-teal">Approved</span>';
      if (l.action.includes('dispatched') || l.action.includes('accepted')) actionBadge = '<span class="badge badge-success">Accepted</span>';
      if (l.action.includes('failed') || l.action.includes('timeout')) actionBadge = '<span class="badge badge-danger">Failure/Timeout</span>';
      if (l.action.includes('suppressed')) actionBadge = '<span class="badge badge-danger">Suppressed</span>';

      return `
        <tr>
          <td class="text-xs text-muted font-mono">${formatDate(l.created_at)}</td>
          <td>${actionBadge}</td>
          <td class="text-xs"><strong>${escapeHtml(l.recipient_email || '-')}</strong></td>
          <td class="text-xs text-muted">${escapeHtml(l.account_name || 'Sandbox')}</td>
          <td class="font-mono text-xs text-muted">${escapeHtml(l.provider_message_id || '-')}</td>
          <td class="text-xs text-muted">${escapeHtml(l.details || '')}</td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to load audit logs:', err);
  }
}

// Status Filter Pills in Workspace
document.getElementById('draftStatusFilterPills')?.addEventListener('click', (e) => {
  const btn = e.target.closest('.status-pill-btn');
  if (!btn) return;

  document.querySelectorAll('#draftStatusFilterPills .status-pill-btn').forEach(el => el.classList.remove('active'));
  btn.classList.add('active');
  State.draftsStatusFilter = btn.dataset.status || 'all';
  renderWorkspaceDraftsList();
});

// Search Input in Workspace
document.getElementById('draftSearchInput')?.addEventListener('input', () => {
  renderWorkspaceDraftsList();
});

// ============================================================
// BATCH DRAFT GENERATION MODAL CONTROLLER
// ============================================================

document.getElementById('openBatchDraftModalBtn')?.addEventListener('click', async () => {
  const modal = document.getElementById('batchDraftModalBackdrop');
  if (!modal) return;

  modal.classList.remove('hidden');
  document.getElementById('batchGenProgressBox')?.classList.add('hidden');

  try {
    const res = await fetch('/api/professors');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const professors = await res.json();
    renderBatchProfessorsTable(professors);
  } catch (err) {
    showToast(`Failed to load faculty: ${err.message}`, 'error');
  }
});

document.getElementById('closeBatchDraftModalBtn')?.addEventListener('click', () => {
  document.getElementById('batchDraftModalBackdrop')?.classList.add('hidden');
});

document.getElementById('cancelBatchDraftBtn')?.addEventListener('click', () => {
  document.getElementById('batchDraftModalBackdrop')?.classList.add('hidden');
});

function renderBatchProfessorsTable(professors) {
  const tbody = document.getElementById('batchProfessorsTableBody');
  if (!tbody) return;

  if (professors.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">No faculty discovered yet. Run university research first.</td></tr>';
    return;
  }

  tbody.innerHTML = professors.map(p => {
    const isShortlisted = p.is_shortlisted ? '⭐ ' : '';
    const isDiscouraged = (p.contact_instructions || '').toLowerCase().includes('do not email') || (p.recruitment_status || '').toLowerCase().includes('portal only');
    const policyBadge = isDiscouraged
      ? '<span class="badge badge-danger">🛑 Discouraged</span>'
      : '<span class="badge badge-teal">Standard</span>';

    return `
      <tr>
        <td><input type="checkbox" class="batch-prof-checkbox" value="${p.id}" data-shortlisted="${p.is_shortlisted ? '1' : '0'}"></td>
        <td><strong>${isShortlisted}${escapeHtml(p.name)}</strong><br><span class="text-xs font-mono text-muted">${escapeHtml(p.email || 'No email')}</span></td>
        <td>${escapeHtml(p.university)}<br><span class="text-xs text-muted">${escapeHtml(p.department || '')}</span></td>
        <td><span class="text-xs">${escapeHtml(p.research_interests || p.areas_of_interest || 'Faculty research')}</span></td>
        <td>${policyBadge}<br><span class="text-xs text-muted">${escapeHtml(p.recruitment_status || 'Unstated')}</span></td>
      </tr>
    `;
  }).join('');

  updateBatchSelectedCount();

  // Attach change listeners
  document.querySelectorAll('.batch-prof-checkbox').forEach(cb => {
    cb.addEventListener('change', updateBatchSelectedCount);
  });
}

function updateBatchSelectedCount() {
  const checked = document.querySelectorAll('.batch-prof-checkbox:checked');
  const count = checked.length;
  setText('batchSelectedCount', count);
  setText('batchConfirmCount', count);
}

document.getElementById('batchMasterCheckbox')?.addEventListener('change', (e) => {
  const isChecked = e.target.checked;
  document.querySelectorAll('.batch-prof-checkbox').forEach(cb => {
    cb.checked = isChecked;
  });
  updateBatchSelectedCount();
});

document.getElementById('batchSelectAllBtn')?.addEventListener('click', () => {
  document.querySelectorAll('.batch-prof-checkbox').forEach(cb => { cb.checked = true; });
  updateBatchSelectedCount();
});

document.getElementById('batchDeselectAllBtn')?.addEventListener('click', () => {
  document.querySelectorAll('.batch-prof-checkbox').forEach(cb => { cb.checked = false; });
  updateBatchSelectedCount();
});

document.getElementById('batchSelectShortlistedBtn')?.addEventListener('click', () => {
  document.querySelectorAll('.batch-prof-checkbox').forEach(cb => {
    cb.checked = cb.dataset.shortlisted === '1';
  });
  updateBatchSelectedCount();
});

document.getElementById('confirmBatchDraftBtn')?.addEventListener('click', async () => {
  const checked = Array.from(document.querySelectorAll('.batch-prof-checkbox:checked')).map(cb => parseInt(cb.value, 10));
  if (checked.length === 0) {
    showToast('Please select at least one faculty member.', 'warning');
    return;
  }

  const btn = document.getElementById('confirmBatchDraftBtn');
  const progressBox = document.getElementById('batchGenProgressBox');
  const progressBar = document.getElementById('batchGenProgressBar');
  const progressText = document.getElementById('batchGenProgressText');

  if (btn) btn.disabled = true;
  if (progressBox) progressBox.classList.remove('hidden');
  if (progressBar) progressBar.style.width = '40%';
  if (progressText) progressText.innerText = `Generating personalized inquiries for ${checked.length} selected faculty...`;

  try {
    const res = await fetch('/api/emails/generate-batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ professor_ids: checked })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (progressBar) progressBar.style.width = '100%';
    showToast(`Successfully generated ${data.count} personalized outreach drafts!`, 'success');

    setTimeout(async () => {
      document.getElementById('batchDraftModalBackdrop')?.classList.add('hidden');
      if (btn) btn.disabled = false;
      const firstId = data.drafts?.[0]?.id;
      await loadDrafts(firstId);
      await loadOverview();
    }, 600);

  } catch (err) {
    if (progressText) progressText.innerText = `Error: ${err.message}`;
    showToast(`Batch draft generation failed: ${err.message}`, 'error');
    if (btn) btn.disabled = false;
  }
});

// Single Draft Creator Modal Handlers (for Custom Drafts)
function openEmailDraftEditor(draftId = null) {
  const modal = document.getElementById('emailDraftModalBackdrop');
  if (!modal) return;

  setInputValue('draft_id', '');
  setInputValue('draft_recipient_name', '');
  setInputValue('draft_recipient_email', '');
  setInputValue('draft_recipient_role', 'Faculty / PI');
  setInputValue('draft_type', 'Professor Research Inquiry');
  setInputValue('draft_subject', `Prospective Ph.D. Student Inquiry - ${State.profile?.name || 'Applicant'}`);
  setInputValue('draft_body_text', '');
  setInputValue('draft_context_title', '');
  setInputValue('draft_context_details', '');

  modal.classList.remove('hidden');
}

document.getElementById('createNewDraftBtn')?.addEventListener('click', () => openEmailDraftEditor());
document.getElementById('emptyWorkspaceCreateBtn')?.addEventListener('click', () => openEmailDraftEditor());
document.getElementById('closeEmailDraftModalBtn')?.addEventListener('click', () => {
  document.getElementById('emailDraftModalBackdrop')?.classList.add('hidden');
});
document.getElementById('cancelDraftBtn')?.addEventListener('click', () => {
  document.getElementById('emailDraftModalBackdrop')?.classList.add('hidden');
});

// Cross-Screen Direct Triggers
async function initEmailDraftForProfessor(profId, name, email, university, researchInterests) {
  try {
    showToast(`Generating grounded outreach inquiry for ${name}...`, 'info');
    const res = await fetch('/api/emails/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        professor_id: profId,
        recipient_name: name,
        recipient_email: (email && email.includes('@') && !['Not found', 'Unknown'].includes(email)) ? email : 'unknown@university.edu',
        recipient_role: 'Faculty / PI',
        draft_type: 'Professor Research Inquiry',
        context_title: researchInterests || 'Faculty Research',
        context_details: `Affiliation: ${university}. Research interests: ${researchInterests}.`
      })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showToast(`Inquiry draft generated for ${name}!`, 'success');

    // Switch to Email Drafts tab and select draft
    switchTab('tab-drafts');
    await loadDrafts(data.draft.id);
  } catch (err) {
    showToast(`Could not generate draft: ${err.message}`, 'error');
  }
}

async function initEmailDraftForScholarship(scholId, title, university) {
  try {
    showToast(`Generating inquiry for ${title}...`, 'info');
    const res = await fetch('/api/emails/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scholarship_id: scholId,
        recipient_name: 'Scholarship Committee / Admissions Office',
        recipient_email: 'admissions@university.edu',
        recipient_role: 'Scholarship Committee',
        draft_type: 'Scholarship Funding Inquiry',
        context_title: title,
        context_details: `Inquiry regarding funding guidelines, stipend details, and timeline for ${title} at ${university}.`
      })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showToast(`Inquiry draft generated for ${title}!`, 'success');

    switchTab('tab-drafts');
    await loadDrafts(data.draft.id);
  } catch (err) {
    showToast(`Could not generate draft: ${err.message}`, 'error');
  }
}
document.getElementById('cancelDraftBtn')?.addEventListener('click', () => document.getElementById('emailDraftModalBackdrop')?.classList.add('hidden'));
document.getElementById('closeEmailDraftModalBtn')?.addEventListener('click', () => document.getElementById('emailDraftModalBackdrop')?.classList.add('hidden'));

// ============================================================================
// 12. SCREEN 10: SETTINGS & PROVIDER CONFIGURATION
// ============================================================================

async function loadSettings() {
  try {
    const res = await fetch('/api/settings');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const s = await res.json();
    State.settings = s;

    setInputValue('setting_api_base_url', s.api_base_url || '');
    setInputValue('setting_llm_timeout', s.llm_timeout || 45);
    setInputValue('setting_llm_max_concurrency', s.llm_max_concurrency || 3);
    setInputValue('setting_job_max_llm_requests', s.job_max_llm_requests || 20);
    setInputValue('setting_job_max_llm_tokens', s.job_max_llm_tokens || 60000);

    setInputValue('setting_search_provider', s.search_provider || 'tavily');
    setInputValue('setting_search_max_queries', s.search_max_queries || 5);
    setInputValue('setting_search_max_results', s.search_max_results || 8);
    setInputValue('setting_discovery_max_universities', s.discovery_max_universities || 10);
    setInputValue('setting_crawl_max_pages', s.crawl_max_pages || 15);

    // Multi-key and Model Population
    const keyCount = s.api_keys_count || (s.is_llm_configured ? 1 : 0);
    setText('settingsKeyPoolCountBadge', `${keyCount} Active Key${keyCount === 1 ? '' : 's'}`);
    setText('settingsKeysCounterText', `${keyCount} key${keyCount === 1 ? '' : 's'} configured in pool`);

    const modelSelect = document.getElementById('setting_model_select');
    const customGroup = document.getElementById('customModelInputGroup');
    const customInput = document.getElementById('setting_model_name');

    if (modelSelect && s.model_name) {
      const options = Array.from(modelSelect.options).map(o => o.value);
      if (options.includes(s.model_name)) {
        modelSelect.value = s.model_name;
        if (customGroup) customGroup.classList.add('hidden');
        if (customInput) customInput.value = s.model_name;
      } else {
        modelSelect.value = 'custom';
        if (customGroup) customGroup.classList.remove('hidden');
        if (customInput) customInput.value = s.model_name;
      }
    }

    // AI Status Badge
    const aiBadge = document.getElementById('settingsAiStatusBadge');
    if (aiBadge) {
      aiBadge.innerText = s.is_llm_configured ? `NVIDIA Active (${keyCount} key${keyCount === 1 ? '' : 's'})` : 'Unconfigured';
      aiBadge.className = s.is_llm_configured ? 'badge badge-teal' : 'badge badge-warning';
    }

    // Search Status Badge
    const searchBadge = document.getElementById('settingsSearchStatusBadge');
    if (searchBadge) {
      searchBadge.innerText = s.is_search_configured ? `${capitalize(s.search_provider)} Active` : `${capitalize(s.search_provider)} (No Key)`;
      searchBadge.className = s.is_search_configured ? 'badge badge-primary' : 'badge badge-warning';
    }

    // Load Scheduled Rechecks and Backups in Settings
    await loadScheduledRechecks();
    await loadDbBackups();

  } catch (err) {
    console.error('Failed to load settings:', err);
  }
}

// Save All Settings
document.getElementById('saveAllSettingsBtn')?.addEventListener('click', async () => {
  const btn = document.getElementById('saveAllSettingsBtn');
  if (btn) btn.disabled = true;

  try {
    const apiKeysText = getInputValue('setting_api_keys');
    const searchKey = getInputValue('setting_search_api_key');

    const modelSelect = document.getElementById('setting_model_select');
    let selectedModel = modelSelect ? modelSelect.value : '';
    if (selectedModel === 'custom' || !selectedModel) {
      selectedModel = getInputValue('setting_model_name');
    }

    const payload = {
      api_base_url: getInputValue('setting_api_base_url'),
      model_name: selectedModel,
      llm_timeout: parseFloat(getInputValue('setting_llm_timeout') || '45'),
      llm_max_concurrency: parseInt(getInputValue('setting_llm_max_concurrency') || '3', 10),
      job_max_llm_requests: parseInt(getInputValue('setting_job_max_llm_requests') || '20', 10),
      job_max_llm_tokens: parseInt(getInputValue('setting_job_max_llm_tokens') || '60000', 10),

      search_provider: getInputValue('setting_search_provider'),
      search_max_queries: parseInt(getInputValue('setting_search_max_queries') || '5', 10),
      search_max_results: parseInt(getInputValue('setting_search_max_results') || '8', 10),
      discovery_max_universities: parseInt(getInputValue('setting_discovery_max_universities') || '10', 10),
      crawl_max_pages: parseInt(getInputValue('setting_crawl_max_pages') || '15', 10)
    };

    if (apiKeysText && apiKeysText.trim()) {
      payload.api_keys = apiKeysText.trim();
      const firstKey = apiKeysText.trim().split(/[\n,]+/)[0].trim();
      if (firstKey) payload.api_key = firstKey;
    }
    if (searchKey) payload.search_api_key = searchKey;

    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    showToast('Settings saved successfully! NVIDIA key pool updated.', 'success');
    await checkHealth();
    await loadSettings();
  } catch (err) {
    showToast(`Failed to save settings: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
});

// Setup NVIDIA Multi-Key and Model Selector
function setupNvidiaMultiKeyAndModelSelector() {
  const modelSelect = document.getElementById('setting_model_select');
  const customGroup = document.getElementById('customModelInputGroup');
  const customInput = document.getElementById('setting_model_name');
  const keysTextarea = document.getElementById('setting_api_keys');
  const keysCounter = document.getElementById('settingsKeysCounterText');
  const testAllKeysBtn = document.getElementById('testAllKeysBtn');
  const allKeysBox = document.getElementById('allKeysTestResultsBox');

  if (modelSelect) {
    modelSelect.addEventListener('change', () => {
      if (modelSelect.value === 'custom') {
        if (customGroup) customGroup.classList.remove('hidden');
        if (customInput) customInput.focus();
      } else {
        if (customGroup) customGroup.classList.add('hidden');
        if (customInput) customInput.value = modelSelect.value;
      }
    });
  }

  if (keysTextarea && keysCounter) {
    keysTextarea.addEventListener('input', () => {
      const text = keysTextarea.value.trim();
      if (!text) {
        keysCounter.innerText = '0 keys entered';
        return;
      }
      const keys = text.split(/[\n,]+/).map(k => k.trim()).filter(k => k.length > 0);
      keysCounter.innerText = `${keys.length} key${keys.length === 1 ? '' : 's'} entered`;
    });
  }

  if (testAllKeysBtn) {
    testAllKeysBtn.addEventListener('click', async () => {
      testAllKeysBtn.disabled = true;
      showToast('Testing all keys in the pool against NVIDIA NIM...', 'info', 3000);
      try {
        const res = await fetch('/api/settings/test-all-keys', { method: 'POST' });
        const data = await res.json();
        
        if (allKeysBox) {
          allKeysBox.classList.remove('hidden');
          const keys = data.results || [];
          allKeysBox.innerHTML = `
            <div class="p-3">
              <div class="flex-row-between align-center mb-2">
                <strong>🔑 NVIDIA Key Pool Diagnostics (${data.valid_keys}/${data.total_keys} Operational)</strong>
                <span class="badge ${data.all_valid ? 'badge-success' : 'badge-warning'}">${data.all_valid ? 'All Keys Operational' : 'Degraded / Issues Found'}</span>
              </div>
              <div class="key-results-list flex-col gap-2">
                ${keys.map(k => `
                  <div class="key-test-item p-2 rounded ${k.valid ? 'bg-success-subtle' : 'bg-danger-subtle'} flex-row-between align-center text-xs">
                    <div>
                      <span class="font-mono font-bold">${escapeHtml(k.masked_key)}</span>
                      <span class="text-muted ml-2">${k.valid ? `⚡ ${k.latency_ms}ms (${escapeHtml(k.model || '')})` : `❌ ${escapeHtml(k.error || 'Failed')}`}</span>
                    </div>
                    <span class="badge ${k.valid ? 'badge-success' : 'badge-danger'}">${k.valid ? 'Valid & Ready' : (k.error_type || 'Error')}</span>
                  </div>
                `).join('')}
              </div>
            </div>
          `;
        }
        
        if (data.all_valid) {
          showToast(`All ${data.total_keys} NVIDIA API keys verified operational!`, 'success');
        } else {
          showToast(`${data.valid_keys}/${data.total_keys} keys operational. Check diagnostics.`, 'warning');
        }
      } catch (err) {
        showToast(`Test all keys failed: ${err.message}`, 'error');
      } finally {
        testAllKeysBtn.disabled = false;
      }
    });
  }
}

// Setup Scholarship Outreach Autonomous Gathering Agent Controller
let gatheringJobPollInterval = null;
let activeGatheringJobId = null;

function setupGatheringAgent() {
  const headerBtn = document.getElementById('headerStartAgentBtn');
  const startModal = document.getElementById('agentStartModalBackdrop');
  const closeStartBtn = document.getElementById('closeAgentStartModalBtn');
  const cancelStartBtn = document.getElementById('cancelAgentStartBtn');
  const quickForm = document.getElementById('agentStartQuickForm');
  
  const progressModal = document.getElementById('agentProgressModalBackdrop');
  const closeProgressBtn = document.getElementById('closeAgentProgressModalBtn');
  const pauseBtn = document.getElementById('agentPauseBtn');
  const resumeBtn = document.getElementById('agentResumeBtn');
  const stopBtn = document.getElementById('agentStopBtn');
  const viewFindingsBtn = document.getElementById('agentViewFindingsBtn');

  // Open Start Modal on Header Button Click
  headerBtn?.addEventListener('click', () => {
    // Pre-populate with profile data if available
    if (State.profile) {
      const subjectInput = document.getElementById('agentSubject');
      if (subjectInput && !subjectInput.value && State.profile.primary_field) {
        subjectInput.value = State.profile.primary_field;
      }
      const countriesInput = document.getElementById('agentCountries');
      if (countriesInput && !countriesInput.value && State.profile.target_countries) {
        const countries = Array.isArray(State.profile.target_countries) ? State.profile.target_countries.join(', ') : State.profile.target_countries;
        countriesInput.value = countries;
      }
    }
    startModal?.classList.remove('hidden');
  });

  closeStartBtn?.addEventListener('click', () => startModal?.classList.add('hidden'));
  cancelStartBtn?.addEventListener('click', () => startModal?.classList.add('hidden'));

  // Close progress modal
  closeProgressBtn?.addEventListener('click', () => {
    progressModal?.classList.add('hidden');
  });

  viewFindingsBtn?.addEventListener('click', () => {
    progressModal?.classList.add('hidden');
    switchTab('tab-overview');
    refreshAllData();
  });

  // Launch Agent Form Submit
  quickForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const degreeCheckboxes = document.querySelectorAll('input[name="agentDegrees"]:checked');
    const degrees = Array.from(degreeCheckboxes).map(cb => cb.value);
    
    if (degrees.length === 0) {
      showToast('Please select at least one degree level (e.g. MS, PhD).', 'warning');
      return;
    }

    const subject = getInputValue('agentSubject').trim();
    if (!subject) {
      showToast('Please enter your subject or field of study.', 'warning');
      return;
    }

    const countriesRaw = getInputValue('agentCountries').trim();
    const countries = countriesRaw ? countriesRaw.split(',').map(c => c.trim()).filter(Boolean) : [];
    const maxUniv = parseInt(getInputValue('agentMaxUniversities') || '8', 10);

    const launchBtn = document.getElementById('launchAgentBtn');
    if (launchBtn) launchBtn.disabled = true;

    try {
      showToast('Launching Scholarship Outreach Agent pipeline...', 'info', 2500);
      const res = await fetch('/api/agent/start-gathering', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          degree_levels: degrees,
          subject: subject,
          target_countries: countries,
          max_universities: maxUniv
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      activeGatheringJobId = data.job_id;
      State.activeJobId = data.job_id;

      // Close start modal & open progress modal
      startModal?.classList.add('hidden');
      openGatheringProgressModal(data.job_id, subject, degrees);
      
      showToast(`Agent gathering pipeline started! (Job #${data.job_id})`, 'success');
      
      // Start polling
      startGatheringJobPolling(data.job_id);

    } catch (err) {
      showToast(`Failed to launch agent: ${err.message}`, 'error');
    } finally {
      if (launchBtn) launchBtn.disabled = false;
    }
  });

  // Pause Button
  pauseBtn?.addEventListener('click', async () => {
    if (!activeGatheringJobId) return;
    try {
      pauseBtn.disabled = true;
      const res = await fetch(`/api/agent/pause/${activeGatheringJobId}`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast('Agent gathering paused.', 'warning');
      pauseBtn.classList.add('hidden');
      resumeBtn?.classList.remove('hidden');
    } catch (err) {
      showToast(`Failed to pause: ${err.message}`, 'error');
    } finally {
      pauseBtn.disabled = false;
    }
  });

  // Resume Button
  resumeBtn?.addEventListener('click', async () => {
    if (!activeGatheringJobId) return;
    try {
      resumeBtn.disabled = true;
      const res = await fetch(`/api/agent/resume/${activeGatheringJobId}`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast('Agent gathering resumed.', 'info');
      resumeBtn.classList.add('hidden');
      pauseBtn?.classList.remove('hidden');
    } catch (err) {
      showToast(`Failed to resume: ${err.message}`, 'error');
    } finally {
      resumeBtn.disabled = false;
    }
  });

  // Stop Button
  stopBtn?.addEventListener('click', async () => {
    if (!activeGatheringJobId) return;
    if (!confirm('Are you sure you want to stop the gathering agent? Collected data will be retained.')) return;
    try {
      stopBtn.disabled = true;
      const res = await fetch(`/api/agent/stop/${activeGatheringJobId}`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast('Agent gathering stopped.', 'info');
      stopGatheringJobPolling();
      await updateGatheringProgressUI(activeGatheringJobId);
    } catch (err) {
      showToast(`Failed to stop: ${err.message}`, 'error');
    } finally {
      stopBtn.disabled = false;
    }
  });

  // Export Buttons
  document.getElementById('agentDownloadExcelBtn')?.addEventListener('click', () => {
    if (activeGatheringJobId) {
      window.location.href = `/api/agent/export/${activeGatheringJobId}/excel`;
    }
  });

  document.getElementById('agentDownloadCsvBtn')?.addEventListener('click', () => {
    if (activeGatheringJobId) {
      window.location.href = `/api/agent/export/${activeGatheringJobId}/csv`;
    }
  });
}

function openGatheringProgressModal(jobId, subject, degrees) {
  const modal = document.getElementById('agentProgressModalBackdrop');
  if (!modal) return;

  setText('agentProgressSubjectBadge', `📚 Field: ${subject}`);
  setText('agentProgressDegreeBadge', `🎓 Degrees: ${Array.isArray(degrees) ? degrees.join(', ') : degrees}`);
  setText('agentProgressStatusText', 'Initializing autonomous gathering pipeline...');
  setText('agentActiveStepText', 'Searching Universities Worldwide...');
  setText('agentActiveUnivText', 'Preparing search queries...');
  setText('agentCountUnivs', '0');
  setText('agentCountSchols', '0');
  setText('agentCountProfs', '0');

  const progressBar = document.getElementById('agentProgressBar');
  if (progressBar) progressBar.style.width = '5%';

  const terminal = document.getElementById('agentLiveTerminal');
  if (terminal) {
    terminal.innerHTML = `
      <div class="terminal-line"><span class="term-time">[${new Date().toLocaleTimeString()}]</span> <span class="term-phase">[INIT]</span> Initializing ScholarScout Outreach Agent pipeline for ${escapeHtml(subject)} (${Array.isArray(degrees) ? escapeHtml(degrees.join(', ')) : escapeHtml(degrees)})...</div>
      <div class="terminal-line"><span class="term-time">[${new Date().toLocaleTimeString()}]</span> <span class="term-phase">[CONFIG]</span> Querying NVIDIA NIM key pool and preparing web scrapers...</div>
    `;
  }

  // Reset export actions
  const exportActions = document.getElementById('agentExportActions');
  if (exportActions) exportActions.classList.add('hidden');

  const pauseBtn = document.getElementById('agentPauseBtn');
  const resumeBtn = document.getElementById('agentResumeBtn');
  const stopBtn = document.getElementById('agentStopBtn');
  if (pauseBtn) {
    pauseBtn.classList.remove('hidden');
    pauseBtn.disabled = false;
  }
  if (resumeBtn) resumeBtn.classList.add('hidden');
  if (stopBtn) {
    stopBtn.classList.remove('hidden');
    stopBtn.disabled = false;
  }

  modal.classList.remove('hidden');
}

function startGatheringJobPolling(jobId) {
  stopGatheringJobPolling();
  gatheringJobPollInterval = setInterval(async () => {
    await updateGatheringProgressUI(jobId);
  }, 1000);
}

function stopGatheringJobPolling() {
  if (gatheringJobPollInterval) {
    clearInterval(gatheringJobPollInterval);
    gatheringJobPollInterval = null;
  }
}

async function updateGatheringProgressUI(jobId) {
  try {
    const res = await fetch(`/api/agent/status/${jobId}`);
    if (!res.ok) return;
    const data = await res.json();

    setText('agentProgressStatusText', data.message || `Job status: ${data.status}`);
    
    // Counters
    setText('agentCountUnivs', String(data.total_universities_found || 0));
    setText('agentCountSchols', String(data.total_scholarships_found || 0));
    setText('agentCountProfs', String(data.total_professors_found || 0));

    // Current university & step
    if (data.current_university) {
      setText('agentActiveUnivText', data.current_university);
    }
    if (data.current_phase) {
      setText('agentActiveStepText', data.current_phase);
    }

    // Progress bar calculation
    const progressBar = document.getElementById('agentProgressBar');
    if (progressBar) {
      let percent = 10;
      if (data.status === 'completed') percent = 100;
      else if (data.status === 'failed' || data.status === 'cancelled') percent = 100;
      else if (data.current_step && data.total_steps) {
        percent = Math.min(95, Math.max(10, Math.round((data.current_step / data.total_steps) * 100)));
      }
      progressBar.style.width = `${percent}%`;
    }

    // Live terminal log updates
    const terminal = document.getElementById('agentLiveTerminal');
    if (terminal && Array.isArray(data.logs) && data.logs.length > 0) {
      const logsHtml = data.logs.map(log => {
        const timeStr = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
        const levelClass = log.level === 'error' ? 'term-error' : (log.level === 'warning' ? 'term-warn' : (log.level === 'success' ? 'term-success' : ''));
        return `<div class="terminal-line ${levelClass}"><span class="term-time">[${timeStr}]</span> <span class="term-phase">[${escapeHtml(log.phase || 'INFO')}]</span> ${escapeHtml(log.message || '')}</div>`;
      }).join('');
      terminal.innerHTML = logsHtml;
      terminal.scrollTop = terminal.scrollHeight;
    }

    // Check completion or failure
    if (data.status === 'completed') {
      stopGatheringJobPolling();
      const exportActions = document.getElementById('agentExportActions');
      if (exportActions) exportActions.classList.remove('hidden');
      
      const pauseBtn = document.getElementById('agentPauseBtn');
      const resumeBtn = document.getElementById('agentResumeBtn');
      const stopBtn = document.getElementById('agentStopBtn');
      if (pauseBtn) pauseBtn.classList.add('hidden');
      if (resumeBtn) resumeBtn.classList.add('hidden');
      if (stopBtn) stopBtn.classList.add('hidden');

      showToast('🎉 Autonomous gathering completed! Excel & CSV ready for download.', 'success', 5000);
      await refreshAllData();
    } else if (data.status === 'failed' || data.status === 'cancelled') {
      stopGatheringJobPolling();
      const exportActions = document.getElementById('agentExportActions');
      if (exportActions) exportActions.classList.remove('hidden');
      showToast(`Agent pipeline ${data.status}: ${data.error_message || ''}`, 'warning');
    } else if (data.status === 'paused') {
      const pauseBtn = document.getElementById('agentPauseBtn');
      const resumeBtn = document.getElementById('agentResumeBtn');
      if (pauseBtn) pauseBtn.classList.add('hidden');
      if (resumeBtn) resumeBtn.classList.remove('hidden');
    }
  } catch (err) {
    console.error('Error polling agent status:', err);
  }
}

// Test AI Connection Diagnostics
document.getElementById('testAiConnectionBtn')?.addEventListener('click', async () => {
  const btn = document.getElementById('testAiConnectionBtn');
  const status = document.getElementById('aiTestResultStatus');
  const detailsBox = document.getElementById('aiTestDetailsBox');
  if (btn) btn.disabled = true;
  if (status) status.innerText = 'Testing connection to AI provider...';

  try {
    const res = await fetch('/api/settings/test-connection', { method: 'POST' });
    const data = await res.json();

    if (data.success) {
      if (status) status.innerText = `Connected! Latency: ${data.latency_ms || 0}ms`;
      showToast(`AI Connection successful! Model: ${data.model}`, 'success');
    } else {
      if (status) status.innerText = `Connection failed: ${data.error_type || 'Error'}`;
      showToast(`AI Diagnostics Error: ${data.message || data.error}`, 'error');
    }

    if (detailsBox) {
      detailsBox.innerText = JSON.stringify(data, null, 2);
      detailsBox.classList.remove('hidden');
    }
  } catch (err) {
    if (status) status.innerText = `Test error: ${err.message}`;
    showToast(`Test request failed: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
});

// Test Search Provider Credentials
document.getElementById('testSearchCredentialsBtn')?.addEventListener('click', async () => {
  const btn = document.getElementById('testSearchCredentialsBtn');
  const status = document.getElementById('searchTestResultStatus');
  const detailsBox = document.getElementById('searchTestDetailsBox');
  if (btn) btn.disabled = true;
  if (status) status.innerText = 'Validating credentials with search API...';

  try {
    const res = await fetch('/api/settings/test-search', { method: 'POST' });
    const data = await res.json();

    if (data.valid) {
      if (status) status.innerText = `Valid! Latency: ${data.latency_ms || 0}ms (${data.provider_name})`;
      showToast(`Search API credentials valid (${data.provider_name})!`, 'success');
    } else {
      if (status) status.innerText = `Invalid: ${data.message || 'Error'}`;
      showToast(`Search Provider Error: ${data.message}`, 'error');
    }

    if (detailsBox) {
      detailsBox.innerText = JSON.stringify(data, null, 2);
      detailsBox.classList.remove('hidden');
    }
  } catch (err) {
    if (status) status.innerText = `Test error: ${err.message}`;
    showToast(`Search test failed: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
});

// Password Show/Hide Toggles
document.getElementById('toggleApiKeyVisibilityBtn')?.addEventListener('click', () => {
  const input = document.getElementById('setting_api_key');
  const btn = document.getElementById('toggleApiKeyVisibilityBtn');
  if (input && btn) {
    const isPass = input.type === 'password';
    input.type = isPass ? 'text' : 'password';
    btn.innerText = isPass ? 'Hide' : 'Show';
  }
});

document.getElementById('toggleSearchApiKeyVisibilityBtn')?.addEventListener('click', () => {
  const input = document.getElementById('setting_search_api_key');
  const btn = document.getElementById('toggleSearchApiKeyVisibilityBtn');
  if (input && btn) {
    const isPass = input.type === 'password';
    input.type = isPass ? 'text' : 'password';
    btn.innerText = isPass ? 'Hide' : 'Show';
  }
});

// ============================================================================
// 13. UNIVERSAL MODALS & PERSONAL NOTES
// ============================================================================

function setupModals() {
  // Close buttons for all modals on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-backdrop').forEach(m => m.classList.add('hidden'));
    }
  });

  // Notes Modal Close Handlers
  document.getElementById('closeNotesModalBtn')?.addEventListener('click', () => {
    document.getElementById('notesModalBackdrop')?.classList.add('hidden');
  });
  document.getElementById('cancelNotesModalBtn')?.addEventListener('click', () => {
    document.getElementById('notesModalBackdrop')?.classList.add('hidden');
  });

  // Evidence Modal Close Handlers
  document.getElementById('closeEvidenceModalBtn')?.addEventListener('click', () => {
    document.getElementById('evidenceModalBackdrop')?.classList.add('hidden');
  });
  document.getElementById('dismissEvidenceModalBtn')?.addEventListener('click', () => {
    document.getElementById('evidenceModalBackdrop')?.classList.add('hidden');
  });

  // Coverage Modal Close Handlers
  document.getElementById('closeCoverageModalBtn')?.addEventListener('click', () => {
    document.getElementById('coverageModalBackdrop')?.classList.add('hidden');
  });
  document.getElementById('dismissCoverageModalBtn')?.addEventListener('click', () => {
    document.getElementById('coverageModalBackdrop')?.classList.add('hidden');
  });

  // Crawl Pages Modal Close Handlers
  document.getElementById('closeCrawlPagesModalBtn')?.addEventListener('click', () => {
    document.getElementById('crawlPagesModalBackdrop')?.classList.add('hidden');
  });
  document.getElementById('dismissCrawlPagesModalBtn')?.addEventListener('click', () => {
    document.getElementById('crawlPagesModalBackdrop')?.classList.add('hidden');
  });

  // Evidence History Modal Close Handlers
  document.getElementById('closeEvidenceHistoryModalBtn')?.addEventListener('click', () => {
    document.getElementById('evidenceHistoryModalBackdrop')?.classList.add('hidden');
  });
  document.getElementById('dismissEvidenceHistoryModalBtn')?.addEventListener('click', () => {
    document.getElementById('evidenceHistoryModalBackdrop')?.classList.add('hidden');
  });

  // Database Restore Modal Close Handlers
  document.getElementById('closeDbRestoreModalBtn')?.addEventListener('click', () => {
    document.getElementById('dbRestoreModalBackdrop')?.classList.add('hidden');
  });
  document.getElementById('cancelDbRestoreBtn')?.addEventListener('click', () => {
    document.getElementById('dbRestoreModalBackdrop')?.classList.add('hidden');
  });
  document.getElementById('confirmDbRestoreBtn')?.addEventListener('click', () => {
    confirmDbRestore();
  });

  // Pre-Send Modal Handlers
  document.getElementById('closePreSendModalBtn')?.addEventListener('click', () => {
    document.getElementById('preSendModalBackdrop')?.classList.add('hidden');
  });
  document.getElementById('cancelPreSendModalBtn')?.addEventListener('click', () => {
    document.getElementById('preSendModalBackdrop')?.classList.add('hidden');
  });
  document.getElementById('confirmPreSendQueueBtn')?.addEventListener('click', () => {
    confirmPreSendQueue();
  });

  // Add / Edit Custom University Modal Handlers
  document.getElementById('closeUnivModalBtn')?.addEventListener('click', () => {
    document.getElementById('univModalBackdrop')?.classList.add('hidden');
  });
  document.getElementById('cancelUnivModalBtn')?.addEventListener('click', () => {
    document.getElementById('univModalBackdrop')?.classList.add('hidden');
  });
  document.getElementById('saveUnivModalBtn')?.addEventListener('click', () => {
    saveUniversityModal();
  });
  document.getElementById('univManageForm')?.addEventListener('submit', (e) => {
    e.preventDefault();
    saveUniversityModal();
  });
}

// Universal Notes Modal
let activeNotesMeta = {};
function openNotesModal(itemType, itemId, currentNotes = '', meta = {}) {
  const modal = document.getElementById('notesModalBackdrop');
  const title = document.getElementById('notesModalTitle');
  const sub = document.getElementById('notesModalSubtitle');
  const textarea = document.getElementById('notesModalTextarea');
  const typeInput = document.getElementById('notesModalItemType');
  const idInput = document.getElementById('notesModalItemId');
  const status = document.getElementById('notesModalSaveStatus');

  if (!modal) return;

  activeNotesMeta = meta;
  if (typeInput) typeInput.value = itemType;
  if (idInput) idInput.value = itemId;
  if (textarea) textarea.value = currentNotes;
  if (status) status.innerText = '';

  const typeLabels = {
    university: 'University Application Notes',
    scholarship: 'Funding Opportunity Notes',
    professor: 'Professor Outreach Notes'
  };

  if (title) title.innerText = `📝 ${typeLabels[itemType] || 'Personal Notes'}`;
  if (sub) sub.innerText = `Notes for ${meta.university_name || meta.title || meta.name || itemId}:`;

  modal.classList.remove('hidden');
  if (textarea) textarea.focus();
}

document.getElementById('saveNotesModalBtn')?.addEventListener('click', async () => {
  const itemType = getInputValue('notesModalItemType');
  const itemId = getInputValue('notesModalItemId');
  const notes = getInputValue('notesModalTextarea') || '';
  const status = document.getElementById('notesModalSaveStatus');
  if (status) status.innerText = 'Saving notes...';

  try {
    let url = '';
    let payload = { notes: notes };

    if (itemType === 'university') {
      url = `/api/universities/${encodeURIComponent(itemId)}/notes`;
      payload.university_name = activeNotesMeta.university_name;
      payload.country = activeNotesMeta.country;
      payload.lead_url = activeNotesMeta.lead_url;
    } else if (itemType === 'scholarship') {
      url = `/api/scholarships/${itemId}/notes`;
    } else if (itemType === 'professor') {
      url = `/api/professors/${itemId}/notes`;
    }

    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    showToast('Personal notes saved!', 'success');
    document.getElementById('notesModalBackdrop')?.classList.add('hidden');

    // Refresh current tab
    if (State.activeTab === 'tab-universities') await loadUniversities();
    if (State.activeTab === 'tab-scholarships') await loadScholarships();
    if (State.activeTab === 'tab-professors') await loadProfessors();
    if (State.activeTab === 'tab-shortlist') await loadShortlist();
  } catch (err) {
    if (status) status.innerText = `Error: ${err.message}`;
    showToast(`Failed to save notes: ${err.message}`, 'error');
  }
});

// Evidence Citation Modal
function openEvidenceModal(title, sourceUrl, verbatimQuote, claimsEvidence = {}) {
  const modal = document.getElementById('evidenceModalBackdrop');
  if (!modal) return;

  setText('evidenceItemTitle', title);
  setText('evidenceItemSource', sourceUrl || 'N/A');
  setText('evidenceVerbatimQuote', `"${verbatimQuote || 'No verbatim citation available.'}"`);

  const openBtn = document.getElementById('evidenceOpenSourceBtn');
  if (openBtn) openBtn.href = sourceUrl || '#';

  const claimsContainer = document.getElementById('evidenceClaimsList');
  if (claimsContainer) {
    const claims = (claimsEvidence && typeof claimsEvidence === 'object') ? Object.entries(claimsEvidence) : [];
    if (claims.length === 0) {
      claimsContainer.innerHTML = '<p class="text-xs text-muted">No structured claim tags extracted.</p>';
    } else {
      claimsContainer.innerHTML = claims.map(([k, v]) => `
        <div class="claim-item card p-2 mb-1 text-xs">
          <strong>${escapeHtml(formatFieldName(k))}:</strong>
          <span class="text-secondary">${escapeHtml(typeof v === 'object' ? JSON.stringify(v) : String(v))}</span>
        </div>
      `).join('');
    }
  }

  modal.classList.remove('hidden');
}

// Coverage Modal
async function viewJobCoverageModal(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/coverage`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const modal = document.getElementById('coverageModalBackdrop');
    const title = document.getElementById('coverageModalTitle');
    const summary = document.getElementById('coverageSummaryBar');
    const content = document.getElementById('coverageReportContent');

    if (!modal) return;
    if (title) title.innerText = `📊 Institutional Coverage Report (Job #${jobId})`;

    if (summary) {
      summary.innerHTML = `
        <div class="stat-pills-row flex-row-between text-xs font-semibold">
          <span class="badge badge-teal">Status: ${capitalize(data.job_status || 'completed')}</span>
          <span class="badge badge-navy">Institutions Visited: ${data.institutions_visited_count || 0}</span>
          <span class="badge badge-primary">Awards Found: ${data.total_scholarships_found || 0}</span>
          <span class="badge badge-purple">Faculty Discovered: ${data.total_professors_found || 0}</span>
        </div>
      `;
    }

    if (content) {
      const institutions = data.institutions || [];
      if (institutions.length === 0) {
        content.innerHTML = '<p class="text-sm text-muted text-center py-4">No detailed coverage log available for this job.</p>';
      } else {
        content.innerHTML = `
          <div class="table-responsive mt-2">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Institution / Domain</th>
                  <th>Target URL</th>
                  <th>Coverage State</th>
                  <th>Pages</th>
                  <th>Awards</th>
                  <th>Faculty</th>
                </tr>
              </thead>
              <tbody>
                ${institutions.map(inst => `
                  <tr>
                    <td><strong>${escapeHtml(inst.institution_name || inst.domain || 'University')}</strong></td>
                    <td><a href="${escapeHtml(inst.target_url)}" target="_blank" rel="noopener" class="text-xs font-mono">${escapeHtml(truncate(inst.target_url, 30))} ↗</a></td>
                    <td><span class="badge badge-success">${escapeHtml(inst.coverage_state || 'Crawled')}</span></td>
                    <td class="font-mono">${inst.pages_visited_count || 0}</td>
                    <td class="font-mono text-teal">${inst.scholarships_found || 0}</td>
                    <td class="font-mono">${inst.professors_found || 0}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `;
      }
    }

    modal.classList.remove('hidden');
  } catch (err) {
    showToast(`Failed to load coverage report: ${err.message}`, 'error');
  }
}

// Crawled Pages Activity Log Modal
async function viewJobCrawlPagesModal(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/pages`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const pages = await res.json();

    const modal = document.getElementById('crawlPagesModalBackdrop');
    const tbody = document.getElementById('crawlPagesTableBody');
    const title = document.getElementById('crawlPagesModalTitle');

    if (!modal || !tbody) return;
    if (title) title.innerText = `📑 Crawled Webpages Log (Job #${jobId} - ${pages.length} pages)`;

    if (pages.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">No crawled pages recorded for this job.</td></tr>';
    } else {
      tbody.innerHTML = pages.map(p => `
        <tr>
          <td><a href="${escapeHtml(p.url)}" target="_blank" rel="noopener" class="text-xs font-mono">${escapeHtml(truncate(p.url, 40))} ↗</a></td>
          <td>${escapeHtml(truncate(p.page_title || 'Untitled Page', 35))}</td>
          <td><span class="badge badge-navy">${escapeHtml(p.page_type || 'general')}</span></td>
          <td><span class="badge ${p.page_status === 'success' ? 'badge-success' : 'badge-warning'}">${escapeHtml(p.page_status || 'success')}</span></td>
          <td class="font-mono">${p.status_code || 200}</td>
          <td><span class="badge badge-teal">${escapeHtml(p.retrieval_method || 'http')}</span></td>
          <td class="text-xs text-muted">${escapeHtml(truncate(p.selection_reason || '', 40))}</td>
        </tr>
      `).join('');
    }

    modal.classList.remove('hidden');
  } catch (err) {
    showToast(`Failed to load crawl pages: ${err.message}`, 'error');
  }
}

function toggleEvidencePanel(panelId) {
  const panel = document.getElementById(panelId);
  if (panel) panel.classList.toggle('hidden');
}

// ============================================================================
// 14. FILTERS, SEARCH & PAGINATION SETUP
// ============================================================================

function setupFiltersAndSearch() {
  // Jobs Filter
  document.getElementById('jobSearchInput')?.addEventListener('input', (e) => {
    State.filters.jobs.search = e.target.value;
    renderJobsTable();
  });
  document.getElementById('jobStatusFilter')?.addEventListener('change', (e) => {
    State.filters.jobs.status = e.target.value;
    renderJobsTable();
  });
  document.getElementById('jobTypeFilter')?.addEventListener('change', (e) => {
    State.filters.jobs.type = e.target.value;
    renderJobsTable();
  });

  // Universities Filter
  document.getElementById('univSearchInput')?.addEventListener('input', (e) => {
    State.filters.universities.search = e.target.value;
    State.pagination.universities.page = 1;
    loadUniversities();
  });
  document.getElementById('univCountryFilter')?.addEventListener('change', (e) => {
    State.filters.universities.country = e.target.value;
    State.pagination.universities.page = 1;
    State.filters.universities.randomize = false;
    updateActiveCountryRibbonUI(e.target.value);
    loadUniversities();
  });
  document.getElementById('univSortBy')?.addEventListener('change', (e) => {
    State.filters.universities.sortBy = e.target.value;
    State.pagination.universities.page = 1;
    if (e.target.value === 'random') {
      State.filters.universities.randomize = true;
      updateActiveCountryRibbonUI('random');
      loadUniversities(true);
    } else {
      State.filters.universities.randomize = false;
      loadUniversities(false);
    }
  });
  document.getElementById('univShortlistedOnly')?.addEventListener('change', (e) => {
    State.filters.universities.shortlistedOnly = e.target.checked;
    State.pagination.universities.page = 1;
    loadUniversities();
  });

  // Universities Pagination
  document.getElementById('univPrevPageBtn')?.addEventListener('click', () => {
    if (State.pagination.universities.page > 1) {
      State.pagination.universities.page--;
      renderUniversitiesTable();
    }
  });
  document.getElementById('univNextPageBtn')?.addEventListener('click', () => {
    State.pagination.universities.page++;
    renderUniversitiesTable();
  });

  // Funding Filter
  document.getElementById('fundingSearchInput')?.addEventListener('input', (e) => {
    State.filters.scholarships.search = e.target.value;
    State.pagination.scholarships.page = 1;
    loadScholarships();
  });
  document.getElementById('fundingMinFitScore')?.addEventListener('change', (e) => {
    State.filters.scholarships.minFitScore = parseInt(e.target.value, 10);
    State.pagination.scholarships.page = 1;
    loadScholarships();
  });
  document.getElementById('fundingCategoryFilter')?.addEventListener('change', (e) => {
    State.filters.scholarships.category = e.target.value;
    State.pagination.scholarships.page = 1;
    loadScholarships();
  });
  document.getElementById('fundingEligibilityFilter')?.addEventListener('change', (e) => {
    State.filters.scholarships.eligibility = e.target.value;
    State.pagination.scholarships.page = 1;
    loadScholarships();
  });
  document.getElementById('fundingCountryFilter')?.addEventListener('change', (e) => {
    State.filters.scholarships.country = e.target.value;
    State.pagination.scholarships.page = 1;
    loadScholarships();
  });
  document.getElementById('fundingDegreeLevelFilter')?.addEventListener('change', (e) => {
    State.filters.scholarships.degreeLevel = e.target.value;
    State.pagination.scholarships.page = 1;
    loadScholarships();
  });
  document.getElementById('fundingSortBy')?.addEventListener('change', (e) => {
    State.filters.scholarships.sortBy = e.target.value;
    loadScholarships();
  });
  document.getElementById('fundingShortlistedOnly')?.addEventListener('change', (e) => {
    State.filters.scholarships.shortlistedOnly = e.target.checked;
    State.pagination.scholarships.page = 1;
    loadScholarships();
  });

  // Funding Pagination
  document.getElementById('fundingPrevPageBtn')?.addEventListener('click', () => {
    if (State.pagination.scholarships.page > 1) {
      State.pagination.scholarships.page--;
      renderScholarshipsCatalog();
    }
  });
  document.getElementById('fundingNextPageBtn')?.addEventListener('click', () => {
    State.pagination.scholarships.page++;
    renderScholarshipsCatalog();
  });

  // Professors Filter
  document.getElementById('profSearchInput')?.addEventListener('input', (e) => {
    State.filters.professors.search = e.target.value;
    State.pagination.professors.page = 1;
    loadProfessors();
  });
  document.getElementById('profMinMatchScore')?.addEventListener('change', (e) => {
    State.filters.professors.minMatchScore = parseInt(e.target.value, 10);
    State.pagination.professors.page = 1;
    loadProfessors();
  });
  document.getElementById('profRecruitmentFilter')?.addEventListener('change', (e) => {
    State.filters.professors.recruitment = e.target.value;
    State.pagination.professors.page = 1;
    loadProfessors();
  });
  document.getElementById('profEmailFilter')?.addEventListener('change', (e) => {
    State.filters.professors.email = e.target.value;
    State.pagination.professors.page = 1;
    loadProfessors();
  });
  document.getElementById('profDepartmentFilter')?.addEventListener('input', (e) => {
    State.filters.professors.department = e.target.value;
    State.pagination.professors.page = 1;
    loadProfessors();
  });
  document.getElementById('profSortBy')?.addEventListener('change', (e) => {
    State.filters.professors.sortBy = e.target.value;
    loadProfessors();
  });
  document.getElementById('profShortlistedOnly')?.addEventListener('change', (e) => {
    State.filters.professors.shortlistedOnly = e.target.checked;
    State.pagination.professors.page = 1;
    loadProfessors();
  });

  // Professors Pagination
  document.getElementById('profPrevPageBtn')?.addEventListener('click', () => {
    if (State.pagination.professors.page > 1) {
      State.pagination.professors.page--;
      renderProfessorsCatalog();
    }
  });
  document.getElementById('profNextPageBtn')?.addEventListener('click', () => {
    State.pagination.professors.page++;
    renderProfessorsCatalog();
  });

  // Drafts Filter
  document.getElementById('draftSearchInput')?.addEventListener('input', (e) => {
    State.filters.drafts.search = e.target.value;
    renderDrafts();
  });
  document.getElementById('draftTypeFilter')?.addEventListener('change', (e) => {
    State.filters.drafts.type = e.target.value;
    renderDrafts();
  });
}

function setupEventListeners() {
  document.getElementById('overviewRefreshBtn')?.addEventListener('click', () => loadOverview());
  document.getElementById('jobsRefreshBtn')?.addEventListener('click', () => loadJobs());
  document.getElementById('universitiesRefreshBtn')?.addEventListener('click', () => loadUniversities());
  document.getElementById('fundingRefreshBtn')?.addEventListener('click', () => loadScholarships());
  document.getElementById('professorsRefreshBtn')?.addEventListener('click', () => loadProfessors());
  document.getElementById('shortlistRefreshBtn')?.addEventListener('click', () => loadShortlist());

  // Export Buttons
  document.getElementById('exportUnivCsvBtn')?.addEventListener('click', () => downloadExport('universities', 'csv'));
  document.getElementById('exportUnivJsonBtn')?.addEventListener('click', () => downloadExport('universities', 'json'));
  document.getElementById('exportFundingCsvBtn')?.addEventListener('click', () => downloadExport('scholarships', 'csv'));
  document.getElementById('exportFundingJsonBtn')?.addEventListener('click', () => downloadExport('scholarships', 'json'));
  document.getElementById('exportProfCsvBtn')?.addEventListener('click', () => downloadExport('professors', 'csv'));
  document.getElementById('exportProfJsonBtn')?.addEventListener('click', () => downloadExport('professors', 'json'));
  document.getElementById('exportOutreachCsvBtn')?.addEventListener('click', () => downloadExport('outreach', 'csv'));
  document.getElementById('exportOutreachJsonBtn')?.addEventListener('click', () => downloadExport('outreach', 'json'));
  document.getElementById('downloadDiagnosticsBtn')?.addEventListener('click', () => downloadDiagnosticsExport());

  // Scheduled Rechecks & Database Backups
  document.getElementById('runDueRechecksBtn')?.addEventListener('click', () => runDueRechecks());
  document.getElementById('scheduleAllShortlistedBtn')?.addEventListener('click', () => scheduleAllShortlisted());
  document.getElementById('createDbBackupBtn')?.addEventListener('click', () => createDbBackup());
}

// ============================================================================
// 15. UI HELPERS & BADGE FORMATTERS
// ============================================================================

function getJobStatusBadge(status) {
  const s = (status || 'queued').toLowerCase();
  if (s === 'completed') return '<span class="badge badge-success">✅ Completed</span>';
  if (s === 'running') return '<span class="badge badge-teal">⚡ Running</span>';
  if (s === 'queued') return '<span class="badge badge-primary">⏳ Queued</span>';
  if (s === 'paused') return '<span class="badge badge-warning">⏸️ Paused</span>';
  if (s === 'failed') return '<span class="badge badge-danger">❌ Failed</span>';
  if (s === 'cancelled') return '<span class="badge badge-neutral">🛑 Cancelled</span>';
  return `<span class="badge badge-neutral">${escapeHtml(capitalize(s))}</span>`;
}

function getFitScoreBadge(score) {
  const val = Number(score) || 0;
  if (val >= 85) return `<span class="badge badge-success">🎯 ${val}% Fit</span>`;
  if (val >= 65) return `<span class="badge badge-teal">🎯 ${val}% Fit</span>`;
  if (val >= 45) return `<span class="badge badge-warning">🎯 ${val}% Fit</span>`;
  return `<span class="badge badge-neutral">🎯 ${val}% Fit</span>`;
}

function getMatchScoreBadge(score) {
  const val = Number(score) || 0;
  if (val >= 85) return `<span class="badge badge-purple">🔬 ${val}% Match</span>`;
  if (val >= 65) return `<span class="badge badge-teal">🔬 ${val}% Match</span>`;
  if (val >= 45) return `<span class="badge badge-warning">🔬 ${val}% Match</span>`;
  return `<span class="badge badge-neutral">🔬 ${val}% Match</span>`;
}

function getFundingCategoryBadge(cat) {
  const c = cat || 'Unclear funding';
  if (c.includes('Explicit full') || c.includes('Full tuition')) {
    return '<span class="badge badge-teal">🌟 Full Funding + Stipend</span>';
  }
  if (c.includes('Tuition-only')) {
    return '<span class="badge badge-primary">🎓 Tuition Waiver</span>';
  }
  if (c.includes('Partial')) {
    return '<span class="badge badge-warning">💵 Partial Award</span>';
  }
  if (c.includes('assistantship') || c.includes('GRA') || c.includes('GTA')) {
    return '<span class="badge badge-teal">💼 Assistantship (GRA/GTA)</span>';
  }
  return '<span class="badge badge-neutral">❓ Unclear Funding</span>';
}

function getEligibilityBadge(elig) {
  const e = (elig || '').toLowerCase();
  if (e.includes('eligible') && !e.includes('ineligible')) {
    return '<span class="badge badge-success">✓ Appears Eligible</span>';
  }
  if (e.includes('ineligible')) {
    return '<span class="badge badge-danger">✕ Appears Ineligible</span>';
  }
  return '<span class="badge badge-warning">⚠️ Needs Clarification</span>';
}

function getRecruitmentBadge(status) {
  const s = (status || 'unstated').toLowerCase();
  if (s.includes('actively')) {
    return '<span class="badge badge-success">🟢 Actively Recruiting</span>';
  }
  if (s.includes('likely')) {
    return '<span class="badge badge-teal">🔵 Likely Accepting</span>';
  }
  if (s.includes('not accepting')) {
    return '<span class="badge badge-danger">🔴 Not Accepting</span>';
  }
  return '<span class="badge badge-neutral">⚪ Recruitment Unstated</span>';
}

// Country Name Normalizer in Frontend
function normalizeCountryName(country) {
  if (!country) return 'Unknown';
  const c = String(country).trim();
  const lower = c.toLowerCase();
  const map = {
    'usa': 'United States',
    'us': 'United States',
    'united states of america': 'United States',
    'u.s.': 'United States',
    'u.s.a.': 'United States',
    'america': 'United States',
    'uk': 'United Kingdom',
    'u.k.': 'United Kingdom',
    'great britain': 'United Kingdom',
    'britain': 'United Kingdom',
    'england': 'United Kingdom',
    'scotland': 'United Kingdom',
    'wales': 'United Kingdom',
    'uae': 'United Arab Emirates',
    'u.a.e.': 'United Arab Emirates',
    'south korea': 'South Korea',
    'korea, south': 'South Korea',
    'republic of korea': 'South Korea',
    'czechia': 'Czech Republic'
  };
  return map[lower] || c;
}

async function loadGlobalCountries() {
  try {
    const res = await fetch('/api/directory/countries');
    if (res.ok) {
      State.globalCountries = await res.json();
      console.log(`[Directory] Loaded ${State.globalCountries.length} global countries.`);
    }
  } catch (err) {
    console.warn('Could not load global countries directory:', err);
  }
}

function populateCountryDropdown(elementId, countriesList) {
  const select = document.getElementById(elementId);
  if (!select) return;

  const currentVal = select.value;

  let optionsHtml = '<option value="all">🌐 All Countries</option>';

  if (State.globalCountries && State.globalCountries.length > 0) {
    // Featured academic research destinations
    const featuredNames = [
      'United States', 'United Kingdom', 'Canada', 'Germany', 'Australia',
      'Switzerland', 'Singapore', 'Japan', 'France', 'Netherlands',
      'Sweden', 'India', 'South Korea', 'Saudi Arabia', 'United Arab Emirates'
    ];
    const featured = State.globalCountries.filter(c => featuredNames.includes(c.name));
    const allSorted = [...State.globalCountries].sort((a, b) => a.name.localeCompare(b.name));

    if (featured.length > 0) {
      optionsHtml += '<optgroup label="🌟 Featured Research Destinations">';
      featured.forEach(c => {
        optionsHtml += `<option value="${escapeHtml(c.name)}">${c.flag} ${escapeHtml(c.name)}</option>`;
      });
      optionsHtml += '</optgroup>';
    }

    optionsHtml += '<optgroup label="🌍 All World Countries & Territories (A–Z)">';
    allSorted.forEach(c => {
      optionsHtml += `<option value="${escapeHtml(c.name)}">${c.flag} ${escapeHtml(c.name)}</option>`;
    });
    optionsHtml += '</optgroup>';
  } else {
    const unique = Array.from(new Set(
      (countriesList || [])
        .map(c => normalizeCountryName(c))
        .filter(c => c && c !== 'Unknown' && c !== 'all')
    )).sort();

    optionsHtml += unique.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
  }

  select.innerHTML = optionsHtml;

  if (currentVal && currentVal !== 'all') {
    const normVal = normalizeCountryName(currentVal);
    select.value = normVal;
  }
}

// Toast Notifications
function showToast(message, type = 'info', duration = 3800) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
  toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span> <span>${escapeHtml(message)}</span>`;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 250);
  }, duration);
}

// File Downloader
function downloadFile(content, fileName, contentType = 'text/plain') {
  const blob = new Blob([content], { type: contentType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 100);
}

// Utility Helpers
function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = text;
}

function setInputValue(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
}

function getInputValue(id) {
  const el = document.getElementById(id);
  return el ? el.value : '';
}

function setChecked(id, val) {
  const el = document.getElementById(id);
  if (el) el.checked = Boolean(val);
}

function getChecked(id) {
  const el = document.getElementById(id);
  return el ? el.checked : false;
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function escapeJsString(str) {
  if (!str) return '';
  return String(str)
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/"/g, '&quot;')
    .replace(/\n/g, ' ')
    .replace(/\r/g, '');
}

function escapeJsObject(obj) {
  try {
    const jsonStr = JSON.stringify(obj || {});
    return escapeHtml(jsonStr);
  } catch {
    return '{}';
  }
}

function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function truncate(str, maxLen = 40) {
  if (!str) return '';
  if (str.length <= maxLen) return str;
  return str.slice(0, maxLen) + '...';
}

function formatFieldName(name) {
  if (!name) return '';
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatDate(isoStr) {
  if (!isoStr || isoStr === 'Unknown') return 'N/A';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return isoStr;
  }
}

// ============================================================================
// 16. DATA EXPORTS & REDACTED DIAGNOSTICS
// ============================================================================

async function downloadExport(entity, format = 'csv') {
  try {
    showToast(`Preparing ${entity} ${format.toUpperCase()} export...`, 'info', 2000);
    const res = await fetch(`/api/export/${entity}?format=${format}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const dateStr = new Date().toISOString().slice(0, 10);
    if (format === 'csv') {
      const text = await res.text();
      downloadFile(text, `scholarscout_${entity}_${dateStr}.csv`, 'text/csv;charset=utf-8;');
    } else {
      const json = await res.json();
      downloadFile(JSON.stringify(json, null, 2), `scholarscout_${entity}_${dateStr}.json`, 'application/json');
    }
    showToast(`Exported ${entity} as ${format.toUpperCase()}!`, 'success');
  } catch (err) {
    showToast(`Export failed: ${err.message}`, 'error');
  }
}

async function downloadDiagnosticsExport() {
  try {
    showToast('Generating redacted diagnostic bundle...', 'info', 2000);
    const res = await fetch('/api/diagnostics/export');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    const dateStr = new Date().toISOString().slice(0, 10);
    downloadFile(JSON.stringify(json, null, 2), `scholarscout_diagnostics_redacted_${dateStr}.json`, 'application/json');
    showToast('Redacted diagnostics downloaded!', 'success');
  } catch (err) {
    showToast(`Diagnostics export failed: ${err.message}`, 'error');
  }
}

// ============================================================================
// 17. EVIDENCE HISTORY & CHANGE DIFF TIMELINE
// ============================================================================

async function openEvidenceHistory(entityType, entityId, title = 'Item History') {
  const modal = document.getElementById('evidenceHistoryModalBackdrop');
  const titleEl = document.getElementById('historyTargetTitle');
  const timelineEl = document.getElementById('evidenceHistoryTimelineContent');
  if (!modal || !timelineEl) return;

  if (titleEl) titleEl.innerText = `📜 Evidence History: ${title}`;
  timelineEl.innerHTML = '<div class="text-center py-4 text-muted"><span class="loading-spinner"></span> Loading change history...</div>';
  modal.classList.remove('hidden');

  try {
    const res = await fetch(`/api/evidence-history?entity_type=${entityType}&entity_id=${entityId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const records = await res.json();

    if (!records || records.length === 0) {
      timelineEl.innerHTML = `
        <div class="empty-state py-4">
          <div class="empty-icon">📜</div>
          <h4>No Changes Recorded</h4>
          <p class="text-sm text-muted">This ${entityType} is at its baseline discovery state. Any future updates to deadlines, funding, recruitment, or contact info will be tracked here with full diffs.</p>
        </div>
      `;
      return;
    }

    timelineEl.innerHTML = records.map((rec, idx) => {
      let diffHtml = '';
      if (rec.old_value || rec.new_value) {
        diffHtml = `
          <div class="diff-block mt-2">
            ${rec.old_value ? `<div class="diff-line diff-old">− <strong>Previous:</strong> ${escapeHtml(rec.old_value)}</div>` : ''}
            ${rec.new_value ? `<div class="diff-line diff-new">+ <strong>Updated:</strong> ${escapeHtml(rec.new_value)}</div>` : ''}
          </div>
        `;
      }

      return `
        <div class="timeline-diff-item card p-3 mb-3">
          <div class="flex-row-between align-center mb-1">
            <span class="badge badge-teal font-semibold">Change #${records.length - idx}: ${escapeHtml(formatFieldName(rec.field_name || 'Update'))}</span>
            <span class="text-xs text-muted font-mono">${formatDate(rec.changed_at)}</span>
          </div>
          <div class="text-sm"><strong>Reason / Trigger:</strong> ${escapeHtml(rec.change_reason || 'Periodic crawl update')}</div>
          ${diffHtml}
          ${rec.previous_evidence_snippet ? `
            <div class="mt-2 text-xs text-muted">
              <strong>Prior Evidence Quote:</strong> <em>"${escapeHtml(rec.previous_evidence_snippet)}"</em>
            </div>
          ` : ''}
        </div>
      `;
    }).join('');
  } catch (err) {
    timelineEl.innerHTML = `<div class="alert alert-danger">Failed to load evidence history: ${escapeHtml(err.message)}</div>`;
  }
}

// ============================================================================
// 18. SCHEDULED RECHECKS CONTROLLER (SETTINGS)
// ============================================================================

async function loadScheduledRechecks() {
  const tbody = document.getElementById('rechecksTableBody');
  if (!tbody) return;

  try {
    const res = await fetch('/api/rechecks');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = Array.isArray(data) ? data : (data.rechecks || []);

    if (items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center py-4 text-muted">No scheduled rechecks configured. Click "Schedule All Shortlisted Items" above.</td></tr>';
      return;
    }

    tbody.innerHTML = items.map(item => {
      const isStale = Boolean(item.stale_flag || item.is_stale);
      let statusBadge = isStale 
        ? '<span class="badge badge-warning">⚠️ Stale (>30d)</span>' 
        : (item.is_enabled ? '<span class="badge badge-success">Active</span>' : '<span class="badge badge-neutral">Disabled</span>');

      const title = item.target_title || item.item_title || `${item.target_type || item.item_type} #${item.target_id || item.item_id}`;
      const targetType = item.target_type || item.item_type || 'scholarship';
      const lastChecked = formatDate(item.last_checked_at || item.last_run_at);
      const nextDue = formatDate(item.next_check_due || item.next_run_at);

      return `
        <tr>
          <td><strong>${escapeHtml(title)}</strong></td>
          <td><span class="badge badge-navy">${escapeHtml(capitalize(targetType))}</span></td>
          <td>
            <select class="form-control form-control-xs" onchange="updateRecheckFrequency(${item.id}, this.value)">
              <option value="daily" ${item.frequency === 'daily' ? 'selected' : ''}>Daily</option>
              <option value="weekly" ${item.frequency === 'weekly' ? 'selected' : ''}>Weekly</option>
              <option value="monthly" ${item.frequency === 'monthly' ? 'selected' : ''}>Monthly</option>
            </select>
          </td>
          <td>${statusBadge}</td>
          <td class="text-xs text-muted">${lastChecked}</td>
          <td class="text-xs font-mono ${(item.next_check_due && new Date(item.next_check_due) <= new Date()) ? 'text-danger font-semibold' : ''}">${nextDue}</td>
          <td>
            <input type="checkbox" ${item.is_enabled ? 'checked' : ''} onchange="toggleRecheckEnabled(${item.id}, this.checked)" aria-label="Toggle recheck">
          </td>
          <td>
            <button type="button" class="btn btn-xs btn-danger" onclick="deleteRecheck(${item.id})" title="Delete Recheck">🗑️</button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to load scheduled rechecks:', err);
  }
}

async function runDueRechecks() {
  const btn = document.getElementById('runDueRechecksBtn');
  if (btn) btn.disabled = true;
  try {
    showToast('Checking for due rechecks...', 'info', 2000);
    const res = await fetch('/api/rechecks/run-due', { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showToast(data.message || `Processed ${data.executed_count || 0} due recheck(s).`, 'success');
    await loadScheduledRechecks();
  } catch (err) {
    showToast(`Run due rechecks failed: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function scheduleAllShortlisted() {
  const btn = document.getElementById('scheduleAllShortlistedBtn');
  const freq = getInputValue('newRecheckFreqSelect') || 'weekly';
  if (btn) btn.disabled = true;
  try {
    showToast('Scheduling rechecks for all shortlisted opportunities & faculty...', 'info', 2000);
    const res = await fetch(`/api/rechecks/schedule-all-shortlisted?frequency=${freq}`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showToast(data.message || 'Shortlisted items scheduled successfully!', 'success');
    await loadScheduledRechecks();
  } catch (err) {
    showToast(`Scheduling failed: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function toggleRecheckEnabled(id, isEnabled) {
  try {
    await fetch(`/api/rechecks/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_enabled: isEnabled })
    });
    showToast(`Recheck #${id} ${isEnabled ? 'enabled' : 'disabled'}.`, 'info');
    await loadScheduledRechecks();
  } catch (err) {
    showToast(`Update failed: ${err.message}`, 'error');
  }
}

async function updateRecheckFrequency(id, frequency) {
  try {
    await fetch(`/api/rechecks/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ frequency: frequency })
    });
    showToast(`Recheck #${id} frequency updated to ${frequency}.`, 'success');
  } catch (err) {
    showToast(`Update failed: ${err.message}`, 'error');
  }
}

async function deleteRecheck(id) {
  if (!confirm(`Delete scheduled recheck #${id}?`)) return;
  try {
    const res = await fetch(`/api/rechecks/${id}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('Scheduled recheck deleted.', 'info');
      await loadScheduledRechecks();
    }
  } catch (err) {
    showToast(`Delete failed: ${err.message}`, 'error');
  }
}

// ============================================================================
// 19. DATABASE BACKUPS & SAFE ROLLBACK RESTORE (SETTINGS)
// ============================================================================

async function loadDbBackups() {
  const tbody = document.getElementById('dbBackupsTableBody');
  if (!tbody) return;

  try {
    const res = await fetch('/api/database/backups');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const backups = Array.isArray(data) ? data : (data.backups || []);

    if (backups.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-muted">No database backups found. Click "Create New Backup" above.</td></tr>';
      return;
    }

    tbody.innerHTML = backups.map(b => `
      <tr>
        <td class="font-mono text-xs"><strong>${escapeHtml(b.filename)}</strong></td>
        <td class="text-xs text-muted">${formatDate(b.created_at)}</td>
        <td class="font-mono text-xs">${Math.round((b.size_bytes || 0) / 1024)} KB</td>
        <td><span class="badge badge-success">✓ Verified OK</span></td>
        <td>
          <div class="action-btn-group">
            <button type="button" class="btn btn-xs btn-primary" onclick="openDbRestoreModal('${escapeJsString(b.filename)}')">🔄 Restore</button>
            <button type="button" class="btn btn-xs btn-danger" onclick="deleteDbBackup('${escapeJsString(b.filename)}')">🗑️</button>
          </div>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('Failed to load database backups:', err);
  }
}

async function createDbBackup() {
  const btn = document.getElementById('createDbBackupBtn');
  if (btn) btn.disabled = true;
  try {
    showToast('Creating SQLite hot backup...', 'info', 2000);
    const res = await fetch('/api/database/backup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label: 'Manual Snapshot' })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showToast(`Backup created: ${data.filename}`, 'success');
    await loadDbBackups();
  } catch (err) {
    showToast(`Backup failed: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function openDbRestoreModal(filename) {
  const modal = document.getElementById('dbRestoreModalBackdrop');
  const targetLabel = document.getElementById('restoreTargetFilename');
  const targetInput = document.getElementById('restoreTargetFilenameInput');
  if (!modal) return;

  if (targetLabel) targetLabel.innerText = filename;
  if (targetInput) targetInput.value = filename;
  modal.classList.remove('hidden');
}

async function confirmDbRestore() {
  const btn = document.getElementById('confirmDbRestoreBtn');
  const filename = getInputValue('restoreTargetFilenameInput');
  if (!filename) return;

  if (btn) btn.disabled = true;
  try {
    showToast('Restoring database with safety snapshot...', 'info', 3000);
    const res = await fetch('/api/database/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: filename })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    showToast('Database restored successfully from backup!', 'success');
    document.getElementById('dbRestoreModalBackdrop')?.classList.add('hidden');
    await refreshAllData();
    await loadDbBackups();
  } catch (err) {
    showToast(`Restore failed: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function deleteDbBackup(filename) {
  if (!confirm(`Delete backup file "${filename}"?`)) return;
  try {
    const res = await fetch(`/api/database/backups/${encodeURIComponent(filename)}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('Backup deleted.', 'info');
      await loadDbBackups();
    }
  } catch (err) {
    showToast(`Delete failed: ${err.message}`, 'error');
  }
}

