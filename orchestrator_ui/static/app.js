/* ═══════════════════════════════════════════════════════════════════
   Orchestrator Web UI — Client-Side SPA Logic
   Flow: Hero → Discovery (iframe) → Dashboard (4 cards) → Config → Progress
   ═══════════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    // ── Views ──────────────────────────────────────────────────────
    const views = {
        hero:      document.getElementById('view-hero'),
        discovery: document.getElementById('view-discovery'),
        dashboard: document.getElementById('view-dashboard'),
        config:    document.getElementById('view-config'),
        progress:  document.getElementById('view-progress'),
    };

    let currentWorkflow = null;
    let selectedReports = [];       // Reports selected from Discovery UI
    let sseSource = null;
    let agentTimers = {};
    let agentStepCounts = {};
    let discoveryPollInterval = null;

    // ── Navigation ─────────────────────────────────────────────────

    function showView(name) {
        Object.entries(views).forEach(([key, el]) => {
            el.classList.toggle('active', key === name);
        });
        window.scrollTo(0, 0);
    }

    // ── Hero → Discovery ───────────────────────────────────────────

    document.getElementById('hero-proceed-btn').addEventListener('click', () => {
        startDiscovery();
    });

    // Discovery ← Back to Hero
    document.getElementById('back-to-hero-from-disc').addEventListener('click', () => {
        stopDiscoveryPolling();
        // Unload Discovery iframe to free memory
        document.getElementById('discovery-iframe').src = 'about:blank';
        showView('hero');
    });

    // Dashboard ← Back to Discovery
    document.getElementById('back-to-discovery').addEventListener('click', () => {
        // Unload Discovery iframe to free memory
        document.getElementById('discovery-iframe').src = 'about:blank';
        showView('discovery');
    });

    // Config ← Back to Dashboard
    document.getElementById('back-to-dashboard').addEventListener('click', () => {
        showView('dashboard');
    });

    // Results → Dashboard
    document.getElementById('btn-back-dashboard').addEventListener('click', () => {
        showView('dashboard');
    });

    // ── Discovery Agent Integration ───────────────────────────────

    async function startDiscovery() {
        showView('discovery');
        const loadingEl = document.getElementById('discovery-loading');
        const iframe = document.getElementById('discovery-iframe');

        loadingEl.style.display = '';
        if (iframe.src !== window.location.origin + '/discovery/') {
            iframe.src = '/discovery/';
        }

        // Hide loading screen as soon as iframe loads
        iframe.onload = () => {
            loadingEl.style.display = 'none';
        };

        // Fallback timer to hide loading screen
        setTimeout(() => {
            loadingEl.style.display = 'none';
        }, 3000);

        // Ensure Discovery server is running in background
        fetch('/api/start-discovery', { method: 'POST' }).catch(() => {});

        // Start polling for confirmed reports
        startDiscoveryPolling();
    }

    function startDiscoveryPolling() {
        stopDiscoveryPolling();
        discoveryPollInterval = setInterval(async () => {
            try {
                const res = await fetch('/api/discovery-reports');
                const data = await res.json();
                if (data.reports && data.reports.length > 0) {
                    selectedReports = data.reports;
                    stopDiscoveryPolling();
                    showToast(`${data.reports.length} reports selected!`, 'success');
                    transitionToDashboard();
                }
            } catch (e) { /* Keep polling */ }
        }, 1500);
    }

    function stopDiscoveryPolling() {
        if (discoveryPollInterval) {
            clearInterval(discoveryPollInterval);
            discoveryPollInterval = null;
        }
    }

    function transitionToDashboard() {
        // Show dashboard with selected reports banner
        renderSelectedReportsBanner();
        showView('dashboard');
    }

    function renderSelectedReportsBanner() {
        const container = document.querySelector('.dashboard-container');
        // Remove old banner if any
        const old = document.getElementById('selected-reports-banner');
        if (old) old.remove();

        if (selectedReports.length === 0) return;

        const banner = document.createElement('div');
        banner.id = 'selected-reports-banner';
        banner.className = 'selected-reports-banner';
        banner.innerHTML = `
            <h4>✓ ${selectedReports.length} Reports Selected from Discovery</h4>
            <div class="report-chips">
                ${selectedReports.map(r => `<span class="report-chip">${escapeHtml(r)}</span>`).join('')}
            </div>
        `;
        // Insert after the dashboard-header
        const header = container.querySelector('.dashboard-header');
        header.after(banner);
    }

    // ── Workflow card clicks ───────────────────────────────────────

    document.querySelectorAll('.workflow-card').forEach(card => {
        card.addEventListener('click', () => {
            currentWorkflow = card.dataset.workflow;
            setupConfigForm(currentWorkflow);
            showView('config');
        });
    });

    function setupConfigForm(workflow) {
        const titleEl = document.getElementById('config-title');
        const industryGroup = document.getElementById('fg-industry');
        const itemsLabel = document.getElementById('items-label');
        const itemsHint = document.getElementById('items-hint');
        const discoveryGroup = document.getElementById('fg-discovery');
        const itemsTextarea = document.getElementById('input-items');

        // Reset form
        document.getElementById('config-form').reset();
        industryGroup.style.display = '';
        discoveryGroup.style.display = 'none';

        // Reset Launch button (may still say "Launching…" from a previous run)
        const btn = document.getElementById('btn-launch');
        btn.disabled = false;
        btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Launch Agent';

        // Clear stale hints
        const userHint = document.getElementById('user-hint');
        if (userHint) { userHint.textContent = ''; userHint.style.color = ''; }

        // Pre-populate report names from Discovery selection
        if (selectedReports.length > 0) {
            itemsTextarea.value = selectedReports.join('\n');
        }

        switch (workflow) {
            case 'full':
                titleEl.textContent = 'Full Workflow — Configuration';
                itemsLabel.textContent = 'Report Names';
                itemsHint.textContent = 'Pre-populated from Discovery. Edit if needed.';
                break;
            case 'report_migration':
                titleEl.textContent = 'Report Config Package — Configuration';
                itemsLabel.textContent = 'Report Names';
                itemsHint.textContent = 'Pre-populated from Discovery. Edit if needed.';
                break;
            case 'dashboard_migration':
                titleEl.textContent = 'Dashboard Config Package — Configuration';
                itemsLabel.textContent = 'Dashboard Names';
                itemsHint.textContent = 'Enter one dashboard name per line, or comma-separated.';
                // Clear pre-populated reports for dashboard (different items)
                itemsTextarea.value = '';
                break;
            case 'export':
                titleEl.textContent = 'Export Definitions — Configuration';
                itemsLabel.textContent = 'Report Names';
                itemsHint.textContent = 'Pre-populated from Discovery. Edit if needed.';
                industryGroup.style.display = 'none';
                break;
        }

        fetchEnvStatus();
    }

    async function fetchEnvStatus() {
        try {
            const res = await fetch('/api/env-status');
            const data = await res.json();
            const hint = document.getElementById('user-hint');
            if (data.wd_user) {
                hint.textContent = 'Pre-filled from environment variable.';
                hint.style.color = '#34d399';
            } else {
                hint.textContent = '';
            }
        } catch (e) { /* ignore */ }
    }

    // ── Form submission ────────────────────────────────────────────

    document.getElementById('config-form').addEventListener('submit', async (e) => {
        e.preventDefault();

        const itemsRaw = document.getElementById('input-items').value.trim();
        if (!itemsRaw) {
            showToast('Please enter at least one item name.', 'error');
            return;
        }

        const items = itemsRaw
            .split(/[\n,]+/)
            .map(s => s.trim().replace(/^["'{}]+|["'{}]+$/g, ''))
            .filter(s => s.length > 0);

        const uniqueItems = [...new Set(items)];

        const payload = {
            workflow: currentWorkflow,
            industry: document.getElementById('input-industry')?.value?.trim() || null,
            items: uniqueItems,
            run_export: currentWorkflow === 'full',
            wd_user: document.getElementById('input-user').value.trim(),
            wd_pass: document.getElementById('input-pass').value,
        };

        if ((currentWorkflow !== 'export') && !payload.industry) {
            showToast('Package name is required.', 'error');
            return;
        }

        const btn = document.getElementById('btn-launch');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-sm"></span> Launching…';

        try {
            const res = await fetch('/api/launch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Launch failed');
            }

            resetProgressView();
            showView('progress');
            startSSE();

        } catch (err) {
            showToast(err.message, 'error');
            btn.disabled = false;
            btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Launch Agent';
        }
    });

    // ── SSE Progress Streaming ─────────────────────────────────────

    function startSSE() {
        if (sseSource) sseSource.close();
        sseSource = new EventSource('/api/events');

        sseSource.addEventListener('agent_start', (e) => {
            const data = JSON.parse(e.data);
            createAgentBlock(data.agent, data.total_steps);
        });

        sseSource.addEventListener('step', (e) => {
            const data = JSON.parse(e.data);
            updateAgentStep(data.agent, data.step, data.total, data.label, data.status);
        });

        sseSource.addEventListener('pause', (e) => {
            const data = JSON.parse(e.data);
            showPauseBanner(data.title, data.message);
        });

        sseSource.addEventListener('pause_resolved', () => {
            hidePauseBanner();
        });

        sseSource.addEventListener('agent_done', (e) => {
            const data = JSON.parse(e.data);
            markAgentDone(data.agent, data.exit_code, data.elapsed, data.error);
        });

        sseSource.addEventListener('error_event', (e) => {
            const data = JSON.parse(e.data);
            showToast('Error: ' + data.message, 'error');
        });

        sseSource.addEventListener('all_done', (e) => {
            const data = JSON.parse(e.data);
            showResults(data.results, data.package_name);
            sseSource.close();
        });
    }

    // ── Progress View Helpers ──────────────────────────────────────

    function resetProgressView() {
        document.getElementById('agents-progress').innerHTML = '';
        document.getElementById('pause-banner').classList.add('hidden');
        document.getElementById('results-panel').classList.add('hidden');
        // Show cancel button, hide it when done, reset its content
        const cancelBtn = document.getElementById('btn-cancel-workflow');
        if (cancelBtn) {
            cancelBtn.classList.remove('hidden');
            cancelBtn.disabled = false;
            cancelBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> Cancel Workflow`;
        }
        agentTimers = {};
        agentStepCounts = {};
    }

    function createAgentBlock(agentName, totalSteps) {
        const container = document.getElementById('agents-progress');
        const block = document.createElement('div');
        block.className = 'agent-block';
        block.id = `agent-${slugify(agentName)}`;
        block.innerHTML = `
            <div class="agent-header">
                <span class="agent-name">${escapeHtml(agentName)} Agent</span>
                <div class="agent-meta">
                    <span class="agent-status-badge status-running">Running</span>
                    <span class="agent-timer" id="timer-${slugify(agentName)}">00:00</span>
                </div>
            </div>
            <div class="agent-progress-bar">
                <div class="agent-progress-fill" id="bar-${slugify(agentName)}" style="width: 0%"></div>
            </div>
            <div class="agent-steps" id="steps-${slugify(agentName)}"></div>
        `;
        container.appendChild(block);

        agentStepCounts[agentName] = { done: 0, total: totalSteps };
        const startTime = Date.now();
        agentTimers[agentName] = {
            startTime,
            interval: setInterval(() => {
                const elapsed = Math.floor((Date.now() - startTime) / 1000);
                const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
                const secs = String(elapsed % 60).padStart(2, '0');
                const timerEl = document.getElementById(`timer-${slugify(agentName)}`);
                if (timerEl) timerEl.textContent = `${mins}:${secs}`;
            }, 1000),
        };
    }

    function updateAgentStep(agentName, stepNum, totalSteps, label, status) {
        const slug = slugify(agentName);
        const stepsEl = document.getElementById(`steps-${slug}`);
        const barEl = document.getElementById(`bar-${slug}`);
        if (!stepsEl) return;

        agentStepCounts[agentName] = { done: stepNum, total: totalSteps };
        const pct = Math.round((stepNum / totalSteps) * 100);
        if (barEl) barEl.style.width = pct + '%';

        const stepId = `step-${slug}-${stepNum}`;
        let existing = document.getElementById(stepId);
        if (existing) {
            existing.querySelector('.step-icon').className = `step-icon ${status === 'done' ? 'done' : 'running'}`;
            existing.querySelector('.step-icon').textContent = status === 'done' ? '✓' : '⟳';
        } else {
            const item = document.createElement('div');
            item.className = 'step-item';
            item.id = stepId;
            item.innerHTML = `
                <span class="step-icon ${status === 'done' ? 'done' : 'running'}">${status === 'done' ? '✓' : '⟳'}</span>
                <span class="step-label">Step ${stepNum}/${totalSteps}: ${escapeHtml(label || 'Processing…')}</span>
            `;
            stepsEl.appendChild(item);
            stepsEl.scrollTop = stepsEl.scrollHeight;
        }
    }

    function markAgentDone(agentName, exitCode, elapsed, error) {
        const slug = slugify(agentName);
        if (agentTimers[agentName]) clearInterval(agentTimers[agentName].interval);

        const block = document.getElementById(`agent-${slug}`);
        if (block) {
            const badge = block.querySelector('.agent-status-badge');
            badge.className = `agent-status-badge ${exitCode === 0 ? 'status-done' : 'status-failed'}`;
            badge.textContent = exitCode === 0 ? 'Completed' : 'Failed';

            const bar = document.getElementById(`bar-${slug}`);
            if (bar) {
                bar.style.width = '100%';
                if (exitCode !== 0) bar.style.background = '#ef4444';
            }

            const timerEl = document.getElementById(`timer-${slug}`);
            if (timerEl) {
                if (exitCode === 0) {
                    timerEl.textContent = 'Task completed';
                    timerEl.style.color = '#34d399';
                } else {
                    const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
                    const secs = String(Math.floor(elapsed % 60)).padStart(2, '0');
                    timerEl.textContent = `Failed after ${mins}:${secs}`;
                }
            }

            if (exitCode !== 0 && error) {
                const stepsEl = document.getElementById(`steps-${slug}`);
                if (stepsEl) {
                    const item = document.createElement('div');
                    item.className = 'step-item';
                    item.innerHTML = `
                        <span class="step-icon failed">✕</span>
                        <span class="step-label" style="color: #f87171;">${escapeHtml(error)}</span>
                    `;
                    stepsEl.appendChild(item);
                }
            }
        }
    }

    // ── Pause handling ─────────────────────────────────────────────

    function showPauseBanner(title, message) {
        const banner = document.getElementById('pause-banner');
        document.getElementById('pause-title').textContent = title;
        document.getElementById('pause-message').textContent = message;
        banner.classList.remove('hidden');
    }

    function hidePauseBanner() {
        document.getElementById('pause-banner').classList.add('hidden');
    }

    document.getElementById('btn-pause-resume').addEventListener('click', async () => {
        try {
            await fetch('/api/pause-resolve', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
            hidePauseBanner();
        } catch (e) {
            showToast('Failed to resume: ' + e.message, 'error');
        }
    });

    // ── Cancel workflow ────────────────────────────────────────────

    document.getElementById('btn-cancel-workflow').addEventListener('click', async () => {
        const cancelBtn = document.getElementById('btn-cancel-workflow');
        cancelBtn.disabled = true;
        cancelBtn.textContent = 'Cancelling…';
        try {
            await fetch('/api/cancel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
            showToast('Workflow cancelled.', 'error');
        } catch (e) {
            showToast('Failed to cancel: ' + e.message, 'error');
        }
    });

    // ── Results ────────────────────────────────────────────────────

    function showResults(results, packageName) {
        const panel = document.getElementById('results-panel');
        const banner = document.getElementById('results-banner');
        const details = document.getElementById('results-details');

        // Hide cancel button once results are shown
        const cancelBtn = document.getElementById('btn-cancel-workflow');
        if (cancelBtn) cancelBtn.classList.add('hidden');

        // Stop any remaining timers and mark unfinished agents as failed/cancelled
        Object.keys(agentTimers).forEach(agentName => {
            const slug = slugify(agentName);
            const badge = document.querySelector(`#agent-${slug} .agent-status-badge`);
            if (badge && badge.textContent === 'Running') {
                // If it's still running on the frontend when all_done arrives, mark it failed.
                markAgentDone(agentName, 1, 0, 'Cancelled or interrupted');
            }
        });

        const allOk = results.every(r => r.exit_code === 0);

        banner.className = `results-banner ${allOk ? 'success' : 'failure'}`;
        banner.textContent = allOk
            ? '✓ All agents completed successfully!'
            : '⚠ Some agents failed. Check the details below.';

        let html = '';
        results.forEach(r => {
            const icon = r.exit_code === 0 ? '✓' : '✕';
            const color = r.exit_code === 0 ? '#34d399' : '#f87171';
            html += `<div style="color: ${color}; margin-bottom: 6px;">
                ${icon} <strong>${escapeHtml(r.agent)}</strong> — ${r.elapsed}s
                ${r.error ? `<br><span style="color: var(--text-muted); font-size: 13px; margin-left: 20px;">${escapeHtml(r.error)}</span>` : ''}
            </div>`;
        });

        if (packageName) {
            html += `<div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border);">
                <strong>Config Package:</strong> ${escapeHtml(packageName)}
            </div>`;
        }

        details.innerHTML = html;
        panel.classList.remove('hidden');
    }

    // ── Toast ──────────────────────────────────────────────────────

    function showToast(message, type = '') {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = `toast ${type}`;
        setTimeout(() => { toast.classList.add('hidden'); }, 4000);
    }

    // ── Utilities ──────────────────────────────────────────────────

    function slugify(s) {
        return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ═══════════════════════════════════════════════════════════════════
    // HERO PARTICLE ANIMATION (21st.dev-inspired)
    // ═══════════════════════════════════════════════════════════════════

    (function initParticles() {
        const canvas = document.getElementById('hero-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        let w, h, particles, mouse;

        function resize() {
            w = canvas.width = canvas.offsetWidth;
            h = canvas.height = canvas.offsetHeight;
        }

        mouse = { x: 0, y: 0 };
        document.getElementById('view-hero').addEventListener('mousemove', (e) => {
            mouse.x = e.clientX;
            mouse.y = e.clientY;
        });

        function Particle() {
            this.x = Math.random() * w;
            this.y = Math.random() * h;
            this.vx = (Math.random() - 0.5) * 0.4;
            this.vy = (Math.random() - 0.5) * 0.4;
            this.r = Math.random() * 1.5 + 0.5;
            this.alpha = Math.random() * 0.4 + 0.1;
        }

        function initPoints() {
            particles = [];
            const count = Math.min(Math.floor((w * h) / 12000), 120);
            for (let i = 0; i < count; i++) {
                particles.push(new Particle());
            }
        }

        function draw() {
            ctx.clearRect(0, 0, w, h);

            // Draw connections
            for (let i = 0; i < particles.length; i++) {
                for (let j = i + 1; j < particles.length; j++) {
                    const dx = particles[i].x - particles[j].x;
                    const dy = particles[i].y - particles[j].y;
                    const dist = Math.sqrt(dx * dx + dy * dy);
                    if (dist < 150) {
                        const opacity = (1 - dist / 150) * 0.12;
                        ctx.beginPath();
                        ctx.strokeStyle = `rgba(99, 102, 241, ${opacity})`;
                        ctx.lineWidth = 0.5;
                        ctx.moveTo(particles[i].x, particles[i].y);
                        ctx.lineTo(particles[j].x, particles[j].y);
                        ctx.stroke();
                    }
                }
            }

            // Draw particles & mouse connections
            particles.forEach(p => {
                p.x += p.vx;
                p.y += p.vy;

                if (p.x < 0 || p.x > w) p.vx *= -1;
                if (p.y < 0 || p.y > h) p.vy *= -1;

                // Mouse attraction (subtle)
                const dx = mouse.x - p.x;
                const dy = mouse.y - p.y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 200) {
                    const opacity = (1 - dist / 200) * 0.2;
                    ctx.beginPath();
                    ctx.strokeStyle = `rgba(139, 92, 246, ${opacity})`;
                    ctx.lineWidth = 0.4;
                    ctx.moveTo(p.x, p.y);
                    ctx.lineTo(mouse.x, mouse.y);
                    ctx.stroke();
                }

                ctx.beginPath();
                ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(148, 163, 184, ${p.alpha})`;
                ctx.fill();
            });

            requestAnimationFrame(draw);
        }

        resize();
        initPoints();
        draw();

        window.addEventListener('resize', () => {
            resize();
            initPoints();
        });
    })();

})();
