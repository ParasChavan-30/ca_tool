async function safeFetchJson(url, options = {}) {
    const res = await fetch(url, options);
    const text = await res.text();
    try {
        return JSON.parse(text);
    } catch (e) {
        const doc = new DOMParser().parseFromString(text, 'text/html');
        const stripped = doc.body ? doc.body.textContent.trim() : text.replace(/<[^>]*>?/gm, '').trim();
        throw new Error(stripped || `Server returned non-JSON output (Status ${res.status})`);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Navigation Router
    const navButtons = document.querySelectorAll('.nav-item button');
    const viewSections = document.querySelectorAll('.view-section');
    const headerTitle = document.getElementById('pageTitle');

    const titles = {
        'overview': 'Dashboard Overview',
        'sources': 'Manage Sources & Health Matrix',
        'knowledge': 'Knowledge Bank Repository',
        'logs': 'Execution Logs & Detailed Metrics'
    };

    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetView = btn.getAttribute('data-view');
            
            navButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            viewSections.forEach(sec => {
                sec.classList.remove('active');
                if (sec.id === `view-${targetView}`) {
                    sec.classList.add('active');
                }
            });

            headerTitle.textContent = titles[targetView] || 'CA Knowledge Hub';

            // Load view data
            if (targetView === 'overview') loadOverview();
            if (targetView === 'sources') loadSources();
            if (targetView === 'knowledge') loadKnowledgeBank(1);
            if (targetView === 'logs') loadLogs(1);
        });
    });

    // Initial load
    loadOverview();
    checkScraperStatus();

    // Background polling timers
    const overviewInterval = setInterval(loadOverview, 5000);
    const statusInterval = setInterval(checkScraperStatus, 4000);

    window.addEventListener('beforeunload', () => {
        if (overviewInterval) clearInterval(overviewInterval);
        if (statusInterval) clearInterval(statusInterval);
    });

    // Start / Sync All Scraper Action
    const btnStartScraper = document.getElementById('btnStartScraper');
    if (btnStartScraper) {
        btnStartScraper.addEventListener('click', async () => {
            btnStartScraper.disabled = true;
            btnStartScraper.textContent = '⏳ Starting Sync...';

            try {
                const res = await fetch('api/scraper_control.php?action=start');
                const data = await res.json();
                if (data.success) {
                    alert('✅ Scraper sync process started successfully for all active sources!');
                    checkScraperStatus();
                    setTimeout(loadOverview, 1500);
                } else {
                    alert('⚠️ ' + data.error);
                }
            } catch (e) {
                alert('Error connecting to backend: ' + e.message);
            } finally {
                checkScraperStatus();
            }
        });
    }

    // Resume Scraper Action
    const btnResumeScraper = document.getElementById('btnResumeScraper');
    if (btnResumeScraper) {
        btnResumeScraper.addEventListener('click', async () => {
            btnResumeScraper.disabled = true;
            btnResumeScraper.textContent = '⏳ Resuming...';

            try {
                const res = await fetch('api/scraper_control.php?action=resume');
                const data = await res.json();
                if (data.success) {
                    alert('⏯️ Scraper process resumed successfully!');
                    checkScraperStatus();
                    setTimeout(loadOverview, 1500);
                } else {
                    alert('⚠️ ' + data.error);
                }
            } catch (e) {
                alert('Error connecting to backend: ' + e.message);
            } finally {
                checkScraperStatus();
            }
        });
    }

    // Stop Scraper Action
    const btnStopScraper = document.getElementById('btnStopScraper');
    if (btnStopScraper) {
        btnStopScraper.addEventListener('click', async () => {
            if (!confirm('Are you sure you want to STOP the background scraper process?')) return;

            btnStopScraper.disabled = true;
            btnStopScraper.textContent = '⏳ Stopping...';

            try {
                const res = await fetch('api/scraper_control.php?action=stop');
                const data = await res.json();
                if (data.success) {
                    alert('🛑 Scraper process stopped successfully!');
                    checkScraperStatus();
                    setTimeout(loadOverview, 1500);
                } else {
                    alert('⚠️ ' + data.error);
                }
            } catch (e) {
                alert('Error connecting to backend: ' + e.message);
            } finally {
                checkScraperStatus();
            }
        });
    }

    // Run Manual Sync Now (Cron Trigger) Action
    const btnRunCronNow = document.getElementById('btnRunCronNow');
    if (btnRunCronNow) {
        btnRunCronNow.addEventListener('click', async () => {
            if (!confirm('⚡ Trigger daily content update crawl now?\nThis will crawl target CA sites, detect updated articles, and sync changes.')) return;

            btnRunCronNow.disabled = true;
            btnRunCronNow.textContent = '⏳ Triggering Sync...';

            try {
                const res = await fetch('api/cron_trigger.php?force=1');
                const data = await res.json();
                if (data.success) {
                    alert('✅ Scraper update job launched in background!\n' + (data.message || ''));
                    checkScraperStatus();
                    setTimeout(loadOverview, 1500);
                } else {
                    alert('⚠️ Trigger warning: ' + (data.error || data.message));
                }
            } catch (e) {
                alert('Error connecting to cron endpoint: ' + e.message);
            } finally {
                btnRunCronNow.disabled = false;
                btnRunCronNow.textContent = '⚡ Run Manual Sync Now';
                checkScraperStatus();
            }
        });
    }

    // Clear Scraped Data Action
    const btnClearData = document.getElementById('btnClearData');
    if (btnClearData) {
        btnClearData.addEventListener('click', async () => {
            if (!confirm('⚠️ Are you sure you want to DELETE ALL scraped records, sub-pages, attachments & execution logs from the database? This cannot be undone.')) return;

            btnClearData.disabled = true;
            btnClearData.textContent = '⏳ Clearing...';

            try {
                const res = await fetch('api/scraper_control.php?action=clear');
                const data = await res.json();
                if (data.success) {
                    alert('🗑️ All scraped data has been deleted successfully!');
                    loadOverview();
                    if (typeof loadSources === 'function') loadSources();
                    if (typeof loadKnowledgeBank === 'function') loadKnowledgeBank(1);
                    if (typeof loadLogs === 'function') loadLogs(1);
                } else {
                    alert('⚠️ ' + data.error);
                }
            } catch (e) {
                alert('Error clearing data: ' + e.message);
            } finally {
                btnClearData.disabled = false;
                btnClearData.textContent = '🗑️ Clear Data';
            }
        });
    }

    // WordPress Sync Action
    const btnSyncWP = document.getElementById('btnSyncWP');
    if (btnSyncWP) {
        btnSyncWP.addEventListener('click', async () => {
            if (!confirm('🚀 Start WordPress REST API Synchronization?\nThis will upload local PDFs to remote WordPress Media Library and publish items to the Knowledge Bank CPT.')) return;

            btnSyncWP.disabled = true;
            btnSyncWP.textContent = '⏳ Syncing...';

            try {
                const res = await fetch('api/wp_sync.php?action=sync&limit=500');
                const data = await res.json();
                if (data.success && data.synced_count > 0) {
                    alert(`✅ WordPress Sync Complete!\n\nSuccessfully synced ${data.synced_count} item(s) to WordPress.`);
                } else {
                    const errDetail = data.first_error ? `\n\nDiagnostic Info:\n${data.first_error}` : (data.error ? `\n\nError: ${data.error}` : '');
                    alert(`⚠️ WordPress Sync Warning:\nSynced: ${data.synced_count || 0} items | Failed: ${data.failed_count || 0} items${errDetail}`);
                }
                loadOverview();
                if (typeof loadKnowledgeBank === 'function') loadKnowledgeBank(kbCurrentPage);
            } catch (e) {
                alert('Error during WordPress sync: ' + e.message);
            } finally {
                btnSyncWP.disabled = false;
                btnSyncWP.textContent = '🚀 Sync to WordPress';
            }
        });
    }

    // Save Settings Listener
    const btnSaveSettings = document.getElementById('btnSaveSettings');
    if (btnSaveSettings) {
        btnSaveSettings.addEventListener('click', async () => {
            const interval = document.getElementById('cronIntervalSelect').value;
            const retries = document.getElementById('retryLimitsInput').value;
            const timeout = document.getElementById('requestTimeoutInput').value;

            btnSaveSettings.disabled = true;
            btnSaveSettings.textContent = '⏳ Saving...';

            try {
                const res = await fetch('api/cron_settings.php', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        cron_interval_hours: interval,
                        retry_limits: retries,
                        request_timeout: timeout
                    })
                });
                const data = await res.json();
                if (data.success) {
                    alert('✅ Settings saved successfully!');
                    loadOverview();
                } else {
                    alert('⚠️ Error saving settings: ' + data.error);
                }
            } catch (e) {
                alert('Error connecting to backend: ' + e.message);
            } finally {
                btnSaveSettings.disabled = false;
                btnSaveSettings.textContent = '💾 Save Settings';
            }
        });
    }

    // Add Source Modal Opener
    const btnOpenAddSourceModal = document.getElementById('btnOpenAddSourceModal');
    if (btnOpenAddSourceModal) {
        btnOpenAddSourceModal.addEventListener('click', openAddSourceModal);
    }

    // Source Form Submit Handler
    const sourceForm = document.getElementById('sourceForm');
    if (sourceForm) {
        sourceForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const id = document.getElementById('sourceFormId').value;
            const action = id > 0 ? 'edit' : 'add';

            const payload = {
                id: parseInt(id),
                name: document.getElementById('sourceFormName').value,
                domain: document.getElementById('sourceFormDomain').value,
                url: document.getElementById('sourceFormUrl').value,
                failover_priority: parseInt(document.getElementById('sourceFormPriority').value) || 10,
                status: document.getElementById('sourceFormStatus').value,
                is_primary: document.getElementById('sourceFormIsPrimary').checked ? 1 : 0
            };

            try {
                const res = await fetch(`api/sources.php?action=${action}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    alert(`✅ Source ${action === 'add' ? 'added' : 'updated'} successfully!`);
                    closeSourceModal();
                    loadSources();
                    loadOverview();
                } else {
                    alert('⚠️ Error: ' + data.error);
                }
            } catch (err) {
                alert('Failed to save source: ' + err.message);
            }
        });
    }

    // KB Filters Listeners
    const kbSearchInput = document.getElementById('kbSearchInput');
    const kbAuthorityInput = document.getElementById('kbAuthorityInput');

    if (kbSearchInput) {
        kbSearchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); loadKnowledgeBank(1); }
        });
    }
    if (kbAuthorityInput) {
        kbAuthorityInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); loadKnowledgeBank(1); }
        });
    }

    // Modal Viewer Close Logic
    const modalClose = document.getElementById('modalClose');
    if (modalClose) {
        modalClose.addEventListener('click', () => {
            document.getElementById('modalViewer').classList.remove('active');
            document.getElementById('viewerFrame').src = 'about:blank';
        });
    }
});

// Check Live Scraper Status
let isStatusChecking = false;

async function checkScraperStatus() {
    if (isStatusChecking) return;
    isStatusChecking = true;

    try {
        const res = await fetch('api/scraper_control.php?action=status');
        const data = await res.json();
        if (!data.success) return;

        const badge = document.getElementById('scraperStatusBadge');
        const btnStart = document.getElementById('btnStartScraper');
        const btnResume = document.getElementById('btnResumeScraper');
        const btnStop = document.getElementById('btnStopScraper');

        if (data.data.is_running) {
            if (badge) {
                badge.className = 'badge badge-active';
                badge.innerHTML = `🟢 RUNNING (PID ${data.data.pid})`;
            }
            if (btnStart) btnStart.disabled = true;
            if (btnResume) btnResume.disabled = true;
            if (btnStop) btnStop.disabled = false;
        } else {
            if (badge) {
                badge.className = 'badge badge-down';
                badge.innerHTML = `⚪ STOPPED`;
            }
            if (btnStart) btnStart.disabled = false;
            if (btnResume) btnResume.disabled = false;
            if (btnStop) btnStop.disabled = true;
        }
    } catch (e) {
        console.error('Error checking scraper status:', e);
    } finally {
        isStatusChecking = false;
    }
}

// 1. Load Overview View
let isOverviewLoading = false;

async function loadOverview() {
    if (isOverviewLoading) return;
    isOverviewLoading = true;

    try {
        const res = await fetch('api/overview.php');
        const data = await res.json();
        if (!data.success) return;

        const stats = data.data;

        // Total Articles
        const articlesElem = document.getElementById('statTotalArticles');
        if (articlesElem) articlesElem.textContent = (stats.total_articles || 0).toLocaleString();

        // Updates Added Today
        const addedTodayElem = document.getElementById('statAddedToday');
        if (addedTodayElem) addedTodayElem.textContent = (stats.added_today || 0).toLocaleString();

        // Updated Articles
        const updatedElem = document.getElementById('statUpdatedArticles');
        if (updatedElem) updatedElem.textContent = (stats.updated_articles || 0).toLocaleString();

        // Downloaded PDFs
        const pdfsElem = document.getElementById('statTotalPdfs');
        if (pdfsElem) pdfsElem.textContent = (stats.total_pdfs || 0).toLocaleString();

        // Active Sources Count vs Total
        const activeCountElem = document.getElementById('statActiveSourcesCount');
        if (activeCountElem) activeCountElem.textContent = `${stats.active_sources_count || 0} / ${stats.total_sources || 0}`;

        // Failed Sources Count
        const failedCountElem = document.getElementById('statFailedSourcesCount');
        if (failedCountElem) failedCountElem.textContent = stats.failed_sources_count || 0;

        // Cron & Next Sync Schedule
        const cSettings = stats.cron_settings || {};
        const cronLastRunText = document.getElementById('cronLastRunText');
        if (cronLastRunText) cronLastRunText.textContent = stats.last_scraped_at || 'Not yet executed';

        const nextSyncText = document.getElementById('nextSyncText');
        if (nextSyncText) nextSyncText.textContent = stats.next_scheduled_sync || 'Calculated on load';

        const cronIntervalSelect = document.getElementById('cronIntervalSelect');
        if (cronIntervalSelect && cSettings.cron_interval_hours && document.activeElement !== cronIntervalSelect) {
            cronIntervalSelect.value = cSettings.cron_interval_hours;
        }

        const retryLimitsInput = document.getElementById('retryLimitsInput');
        if (retryLimitsInput && cSettings.retry_limits && document.activeElement !== retryLimitsInput) {
            retryLimitsInput.value = cSettings.retry_limits;
        }

        const requestTimeoutInput = document.getElementById('requestTimeoutInput');
        if (requestTimeoutInput && cSettings.request_timeout && document.activeElement !== requestTimeoutInput) {
            requestTimeoutInput.value = cSettings.request_timeout;
        }

        // Category Breakdown
        const catContainer = document.getElementById('categoryDistributionList');
        if (catContainer && stats.category_distribution) {
            const newCatJson = JSON.stringify(stats.category_distribution);
            if (catContainer.dataset.json !== newCatJson) {
                catContainer.dataset.json = newCatJson;
                catContainer.innerHTML = stats.category_distribution.map(cat => `
                    <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.6rem 0; border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <span style="font-weight: 500;">${escapeHtml(cat.category)}</span>
                        <span class="badge badge-category">${cat.count} Items</span>
                    </div>
                `).join('');
            }
        }

        // Recent Activity
        const recentTable = document.getElementById('recentActivityBody');
        if (recentTable && stats.recent_activity) {
            const newActivityJson = JSON.stringify(stats.recent_activity);
            if (recentTable.dataset.json !== newActivityJson) {
                recentTable.dataset.json = newActivityJson;
                recentTable.innerHTML = stats.recent_activity.map(log => `
                    <tr>
                        <td>${log.run_timestamp}</td>
                        <td><strong>${escapeHtml(log.source_domain || 'System')}</strong></td>
                        <td><span class="badge ${log.status === 'SUCCESS' ? 'badge-active' : (log.status === 'FAILOVER' ? 'badge-rotated' : 'badge-down')}">${log.status}</span></td>
                        <td>${log.items_scraped} items ${log.items_updated ? `<span style="color:#38bdf8; font-size:0.8rem;">(${log.items_updated} updated)</span>` : ''}</td>
                    </tr>
                `).join('');
            }
        }

    } catch (e) {
        console.error('Error loading overview:', e);
    } finally {
        isOverviewLoading = false;
    }
}

// 2. Load Sources View & Source Management
let allSourcesList = [];

async function loadSources() {
    try {
        const res = await fetch('api/sources.php');
        const data = await res.json();
        if (!data.success) return;

        allSourcesList = data.data;
        const sourcesTable = document.getElementById('sourcesTableBody');

        if (allSourcesList.length === 0) {
            sourcesTable.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:2rem; color:#94a3b8;">No sources configured yet. Click "Add New Source" to create one.</td></tr>`;
            return;
        }

        sourcesTable.innerHTML = allSourcesList.map((src) => {
            let badgeClass = 'badge-down';
            let statusText = src.status;

            if (src.status === 'ACTIVE') {
                badgeClass = src.is_primary ? 'badge-active' : 'badge-rotated';
                statusText = src.is_primary ? '🟢 ONLINE (PRIMARY)' : '🟢 ACTIVE';
            } else if (src.status === 'DISABLED') {
                badgeClass = 'badge-down';
                statusText = '⚪ DISABLED';
            } else if (src.status === 'FAILED') {
                badgeClass = 'badge-down';
                statusText = '🔴 FAILED';
            }

            const failCount = src.failure_count || 0;
            const failBadge = failCount > 0 
                ? `<span class="badge badge-down" style="font-size:0.75rem;">⚠️ ${failCount} Failures</span>` 
                : `<span style="color:#34d399; font-size:0.85rem;">0</span>`;

            const srcJson = escapeHtml(JSON.stringify(src));

            return `
                <tr>
                    <td>
                        <div style="display:flex; align-items:center; gap:4px;">
                            <strong style="color: #818cf8;">#${src.failover_priority}</strong>
                            <button class="btn btn-outline" style="padding:0.15rem 0.4rem; font-size:0.7rem;" onclick="changePriority(${src.id}, ${src.failover_priority - 1})" title="Move Up">▲</button>
                            <button class="btn btn-outline" style="padding:0.15rem 0.4rem; font-size:0.7rem;" onclick="changePriority(${src.id}, ${src.failover_priority + 1})" title="Move Down">▼</button>
                        </div>
                    </td>
                    <td><strong>${escapeHtml(src.name)}</strong> ${src.is_primary ? '<span style="font-size:0.7rem; color:#10b981; margin-left:4px;">(PRIMARY)</span>' : ''}</td>
                    <td><code>${escapeHtml(src.domain)}</code><br><a href="${src.url}" target="_blank" style="color: #6366f1; font-size:0.78rem; text-decoration: none;">${src.url}</a></td>
                    <td><span class="badge ${badgeClass}">${statusText}</span></td>
                    <td>${failBadge}</td>
                    <td>${src.total_scraped_items || 0} items</td>
                    <td style="font-size:0.8rem; color:#94a3b8;">${src.last_checked || 'Never'}</td>
                    <td>
                        <div style="display:flex; gap:4px; justify-content:center; flex-wrap:wrap;">
                            <button class="btn btn-outline" style="padding:0.3rem 0.6rem; font-size:0.78rem;" onclick="testSource(${src.id})" title="Test connectivity & parser on demand">⚡ Test</button>
                            <button class="btn btn-success" style="padding:0.3rem 0.6rem; font-size:0.78rem;" onclick="runSingleSourceSync(${src.id})" title="Run manual sync for this source only">▶ Sync</button>
                            <button class="btn btn-outline" style="padding:0.3rem 0.6rem; font-size:0.78rem;" onclick='openEditSourceModal(${srcJson})' title="Edit source details">✏️ Edit</button>
                            <button class="btn ${src.status === 'DISABLED' ? 'btn-success' : 'btn-danger'}" style="padding:0.3rem 0.6rem; font-size:0.78rem;" onclick="toggleSourceStatus(${src.id})" title="Enable/Disable source">
                                ${src.status === 'DISABLED' ? 'ENABLE' : 'DISABLE'}
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    } catch (e) {
        console.error('Error loading sources:', e);
    }
}

function openAddSourceModal() {
    document.getElementById('modalSourceFormTitle').textContent = 'Add New Source';
    document.getElementById('sourceFormId').value = '0';
    document.getElementById('sourceFormName').value = '';
    document.getElementById('sourceFormDomain').value = '';
    document.getElementById('sourceFormUrl').value = '';
    document.getElementById('sourceFormPriority').value = '10';
    document.getElementById('sourceFormStatus').value = 'ACTIVE';
    document.getElementById('sourceFormIsPrimary').checked = false;
    document.getElementById('modalSourceForm').classList.add('active');
}

function openEditSourceModal(src) {
    document.getElementById('modalSourceFormTitle').textContent = `Edit Source: ${src.name}`;
    document.getElementById('sourceFormId').value = src.id;
    document.getElementById('sourceFormName').value = src.name;
    document.getElementById('sourceFormDomain').value = src.domain;
    document.getElementById('sourceFormUrl').value = src.url;
    document.getElementById('sourceFormPriority').value = src.failover_priority || 10;
    document.getElementById('sourceFormStatus').value = src.status || 'ACTIVE';
    document.getElementById('sourceFormIsPrimary').checked = src.is_primary ? true : false;
    document.getElementById('modalSourceForm').classList.add('active');
}

function closeSourceModal() {
    document.getElementById('modalSourceForm').classList.remove('active');
}

async function toggleSourceStatus(id) {
    try {
        const res = await fetch(`api/sources.php?action=toggle_status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id })
        });
        const data = await res.json();
        if (data.success) {
            loadSources();
            loadOverview();
        } else {
            alert('⚠️ ' + data.error);
        }
    } catch (e) {
        alert('Failed to toggle status: ' + e.message);
    }
}

async function changePriority(id, newPriority) {
    if (newPriority < 0) return;
    try {
        const res = await fetch(`api/sources.php?action=set_priority`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id, priority: newPriority })
        });
        const data = await res.json();
        if (data.success) {
            loadSources();
        }
    } catch (e) {
        console.error('Priority update error:', e);
    }
}

async function testSource(id) {
    const modal = document.getElementById('modalTestResult');
    const body = document.getElementById('modalTestResultBody');
    modal.classList.add('active');
    body.innerHTML = `
        <div style="text-align:center; padding:2rem;">
            <div style="font-size:2rem; margin-bottom:0.5rem;">⚡</div>
            <p style="color:#38bdf8; font-weight:600;">Testing connection & running parser for Source #${id}...</p>
            <p style="color:#94a3b8; font-size:0.85rem; margin-top:4px;">Connecting to target URL and validating response headers...</p>
        </div>
    `;

    try {
        const res = await fetch(`api/sources.php?action=test_source&id=${id}`);
        const data = await res.json();
        
        if (data.success) {
            const info = data.data;
            body.innerHTML = `
                <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 1.25rem;">
                    <h4 style="color:#34d399; font-size:1.1rem; margin-bottom:0.5rem;">🟢 Connectivity Test PASSED</h4>
                    <p style="margin-bottom:0.75rem;">${escapeHtml(info.message)}</p>
                    <table style="width:100%; font-size:0.88rem; border-spacing:0 4px;">
                        <tr><td style="color:#94a3b8; width:140px;">HTTP Status:</td><td><strong style="color:#34d399;">${info.http_status} OK</strong></td></tr>
                        <tr><td style="color:#94a3b8;">Response Latency:</td><td><strong>${info.latency_ms} ms</strong></td></tr>
                        <tr><td style="color:#94a3b8;">Page Title:</td><td><em>"${escapeHtml(info.page_title)}"</em></td></tr>
                        <tr><td style="color:#94a3b8;">Parsed Links:</td><td><strong>${info.parsed_links_count} links detected</strong></td></tr>
                    </table>
                </div>
            `;
            loadSources();
        } else {
            const err = data.data || {};
            body.innerHTML = `
                <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 1.25rem;">
                    <h4 style="color:#f87171; font-size:1.1rem; margin-bottom:0.5rem;">🔴 Connectivity Test FAILED</h4>
                    <p style="margin-bottom:0.75rem;">${escapeHtml(err.message || data.error)}</p>
                    <table style="width:100%; font-size:0.88rem;">
                        <tr><td style="color:#94a3b8; width:140px;">Target URL:</td><td><code>${escapeHtml(err.url || '')}</code></td></tr>
                        <tr><td style="color:#94a3b8;">Latency:</td><td>${err.latency_ms || 0} ms</td></tr>
                    </table>
                </div>
            `;
            loadSources();
        }
    } catch (e) {
        body.innerHTML = `<div style="color:#f87171; padding:1rem;">Test connection error: ${escapeHtml(e.message)}</div>`;
    }
}

function closeTestModal() {
    document.getElementById('modalTestResult').classList.remove('active');
}

async function runSingleSourceSync(id) {
    if (!confirm(`▶ Trigger manual scraper sync for Source ID #${id}?`)) return;
    try {
        const res = await fetch(`api/scraper_control.php?action=start&source_id=${id}`);
        const data = await res.json();
        if (data.success) {
            alert(`✅ ${data.message}`);
            checkScraperStatus();
            setTimeout(loadOverview, 1500);
        } else {
            alert(`⚠️ ` + data.error);
        }
    } catch (e) {
        alert('Sync trigger error: ' + e.message);
    }
}

// 3. Load Knowledge Bank View
let kbCurrentPage = 1;

async function loadKnowledgeBank(page = 1) {
    kbCurrentPage = page;
    const search = document.getElementById('kbSearchInput')?.value || '';
    const category = document.getElementById('kbCategorySelect')?.value || '';
    const authority = document.getElementById('kbAuthorityInput')?.value || '';
    const dateFrom = document.getElementById('kbDateFromInput')?.value || '';
    const dateTo = document.getElementById('kbDateToInput')?.value || '';

    try {
        const url = `api/knowledge_bank.php?page=${page}&limit=12&search=${encodeURIComponent(search)}&category=${encodeURIComponent(category)}&authority=${encodeURIComponent(authority)}&date_from=${encodeURIComponent(dateFrom)}&date_to=${encodeURIComponent(dateTo)}`;
        const res = await fetch(url);
        const data = await res.json();
        if (!data.success) return;

        // Populate Category select options if empty
        const catSelect = document.getElementById('kbCategorySelect');
        if (catSelect && catSelect.options.length <= 1 && data.categories) {
            data.categories.forEach(cat => {
                const opt = document.createElement('option');
                opt.value = cat;
                opt.textContent = cat;
                catSelect.appendChild(opt);
            });
        }

        const tableBody = document.getElementById('kbTableBody');
        if (data.data.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2.5rem; color: #94a3b8;">🔍 No Knowledge Bank items found for these search filters.</td></tr>`;
            renderKBPagination(1, 0, 0);
            return;
        }

        tableBody.innerHTML = data.data.map(item => {
            let attachmentHTML = `<span style="color: #64748b; font-size:0.8rem;">No PDF</span>`;
            if (item.attachments && item.attachments.length > 0) {
                attachmentHTML = item.attachments.map(att => `
                    <a href="api/serve_pdf.php?file=${encodeURIComponent(att.file_name)}" target="_blank" class="badge badge-primary" style="text-decoration:none; margin-right:4px;">
                        📄 ${escapeHtml(att.file_name.substring(0, 16))}...
                    </a>
                `).join('');
            }

            let wpSyncHTML = `<span class="badge" style="background: rgba(234, 179, 8, 0.15); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.3);">⏳ Pending</span>`;
            if (item.wp_synced_at) {
                const wpIdStr = item.wp_post_id ? ` (#${item.wp_post_id})` : '';
                wpSyncHTML = `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3);" title="Synced on ${item.wp_synced_at}">🟢 Synced${wpIdStr}</span>`;
            } else if (item.wp_post_id) {
                wpSyncHTML = `<span class="badge" style="background: rgba(234, 179, 8, 0.15); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.3);" title="Post created in WP (#${item.wp_post_id}), content modified - re-sync pending">⏳ Re-sync (#${item.wp_post_id})</span>`;
            }

            return `
                <tr>
                    <td style="white-space: nowrap; font-size:0.85rem; color:#94a3b8;">${item.collected_date ? item.collected_date.split(' ')[0] : 'N/A'}</td>
                    <td><strong style="color:#f8fafc; font-size:0.95rem;">${escapeHtml(item.title)}</strong></td>
                    <td><span class="badge badge-category">${escapeHtml(item.authority_category)}</span></td>
                    <td>${attachmentHTML}</td>
                    <td style="white-space: nowrap; font-size:0.85rem; color:#94a3b8;">${item.collected_date || 'N/A'}</td>
                    <td>${wpSyncHTML}</td>
                    <td>
                        <button class="btn btn-primary" style="padding: 0.35rem 0.75rem; font-size: 0.8rem;" onclick="openViewerModal(${item.id})">
                            👁 View Details
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        const pagination = data.pagination;
        renderKBPagination(pagination.current_page, pagination.total_pages, pagination.total_records);
    } catch (e) {
        console.error('Error loading Knowledge Bank:', e);
    }
}

function resetKbFilters() {
    document.getElementById('kbSearchInput').value = '';
    document.getElementById('kbCategorySelect').value = '';
    document.getElementById('kbAuthorityInput').value = '';
    document.getElementById('kbDateFromInput').value = '';
    document.getElementById('kbDateToInput').value = '';
    loadKnowledgeBank(1);
}

function renderKBPagination(currentPage, totalPages, totalRecords) {
    const infoElem = document.getElementById('kbPaginationInfo');
    if (infoElem) {
        infoElem.textContent = `Showing page ${currentPage} of ${totalPages || 1} (${totalRecords} Total Items)`;
    }

    const container = document.getElementById('kbPaginationControls');
    if (!container) return;

    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '';
    const prevDisabled = currentPage <= 1 ? 'disabled' : '';
    const prevOnClick = currentPage > 1 ? `onclick="loadKnowledgeBank(${currentPage - 1})"` : '';
    html += `<button class="btn btn-outline page-btn" ${prevDisabled} ${prevOnClick}>Previous</button>`;

    for (let p = 1; p <= totalPages; p++) {
        if (p === currentPage) {
            html += `<button class="btn btn-primary page-btn active-page">${p}</button>`;
        } else {
            html += `<button class="btn btn-outline page-btn" onclick="loadKnowledgeBank(${p})">${p}</button>`;
        }
    }

    const nextDisabled = currentPage >= totalPages ? 'disabled' : '';
    const nextOnClick = currentPage < totalPages ? `onclick="loadKnowledgeBank(${currentPage + 1})"` : '';
    html += `<button class="btn btn-outline page-btn" ${nextDisabled} ${nextOnClick}>Next</button>`;

    container.innerHTML = html;
}

// 4. Load Execution Logs View
async function loadLogs(page = 1) {
    const statusFilter = document.getElementById('logStatusFilter')?.value || '';
    try {
        const res = await fetch(`api/logs.php?page=${page}&limit=15&status=${encodeURIComponent(statusFilter)}`);
        const data = await res.json();
        if (!data.success) return;

        const tableBody = document.getElementById('logsTableBody');
        if (data.data.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:2rem; color:#94a3b8;">No execution logs recorded yet for this filter.</td></tr>`;
            return;
        }

        tableBody.innerHTML = data.data.map(log => {
            let badgeClass = 'badge-down';
            if (log.status === 'SUCCESS') badgeClass = 'badge-active';
            if (log.status === 'FAILOVER' || log.status === 'RESUMED') badgeClass = 'badge-rotated';
            if (log.status === 'STARTED') badgeClass = 'badge-primary';

            const logContent = escapeHtml(log.log_details || log.error_message || 'No log detail');

            return `
                <tr>
                    <td style="white-space:nowrap; font-size:0.85rem; color:#94a3b8;">${log.run_timestamp}</td>
                    <td><strong>${escapeHtml(log.source_name || 'System / Rotator')}</strong></td>
                    <td><span class="badge ${badgeClass}">${log.status}</span></td>
                    <td><span style="color:#34d399; font-weight:600;">+${log.items_added || 0}</span></td>
                    <td><span style="color:#38bdf8;">${log.items_updated || 0}</span></td>
                    <td><span style="color:#94a3b8;">${log.items_unchanged || 0}</span></td>
                    <td><strong>${log.items_scraped || 0}</strong></td>
                    <td>
                        <button class="btn btn-outline" style="padding:0.25rem 0.6rem; font-size:0.75rem;" onclick='openLogModal(${JSON.stringify(logContent)})'>
                            📜 View Stack & Details
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        const pagination = data.pagination;
        const infoElem = document.getElementById('logPaginationInfo');
        if (infoElem) {
            infoElem.textContent = `Showing page ${pagination.current_page} of ${pagination.total_pages || 1} (${pagination.total_records} Logs)`;
        }
    } catch (e) {
        console.error('Error loading logs:', e);
    }
}

function openLogModal(detailsStr) {
    document.getElementById('logModalContent').textContent = detailsStr;
    document.getElementById('modalLogDetails').classList.add('active');
}

function closeLogModal() {
    document.getElementById('modalLogDetails').classList.remove('active');
}

// Viewer Modal HTML Tab Switcher
async function openViewerModal(itemId) {
    const modal = document.getElementById('modalViewer');
    const modalTitle = document.getElementById('modalViewerTitle');
    const modalCat = document.getElementById('modalViewerCategory');
    const btnLive = document.getElementById('btnLiveWebsite');
    const modalTabs = document.getElementById('modalViewerTabs');
    const iframe = document.getElementById('viewerFrame');

    modal.classList.add('active');
    modalTitle.textContent = 'Loading Knowledge Bank Item...';
    modalTabs.innerHTML = '';
    iframe.src = 'about:blank';

    try {
        const res = await fetch(`api/knowledge_detail.php?id=${itemId}`);
        const data = await res.json();
        if (!data.success) {
            alert('Could not fetch item detail: ' + data.error);
            modal.classList.remove('active');
            return;
        }

        const item = data.data;
        modalTitle.textContent = item.title;
        if (modalCat) modalCat.textContent = item.authority_category;
        if (btnLive) btnLive.href = item.source_url;

        const tabs = [];
        tabs.push({ title: '📄 Main Page HTML', url: `api/render_html.php?id=${item.id}` });

        if (item.sub_pages && item.sub_pages.length > 0) {
            item.sub_pages.forEach((sub, idx) => {
                tabs.push({
                    title: `🔗 Sub-page: ${sub.sub_page_title || 'Page ' + (idx + 1)}`,
                    url: `api/render_html.php?sub_id=${sub.id}`
                });
            });
        }

        if (item.attachments && item.attachments.length > 0) {
            tabs.push({
                title: `📎 PDF Attachments (${item.attachments.length})`,
                url: `api/serve_pdf.php?file=${encodeURIComponent(item.attachments[0].file_name)}`
            });
        }

        modalTabs.innerHTML = tabs.map((tab, idx) => `
            <button class="tab-btn ${idx === 0 ? 'active' : ''}" onclick="switchViewerTab(${idx})">
                ${tab.title}
            </button>
        `).join('');

        window.activeViewerTabs = tabs;
        switchViewerTab(0);

    } catch (e) {
        console.error('Error fetching viewer detail:', e);
    }
}

function switchViewerTab(index) {
    if (!window.activeViewerTabs || !window.activeViewerTabs[index]) return;
    const buttons = document.querySelectorAll('#modalViewerTabs .tab-btn');
    buttons.forEach((b, idx) => b.classList.toggle('active', idx === index));
    document.getElementById('viewerFrame').src = window.activeViewerTabs[index].url;
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
