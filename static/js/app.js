/* ============================================
   Docxtract — Application Logic
   ============================================ */

'use strict';

const API = '/api';

// ---- State ----
let currentView = 'upload';
let documents = [];
let currentDocData = null;
let selectedFile = null;
let selectedDocType = null;
let currentFilter = 'all';
let isUploading = false;

// ---- DOM refs (resolved after DOMContentLoaded) ----
let views, navLinks, uploadZone, fileInput, docTypeSelector, typeChips;
let uploadBtn, cancelUploadBtn, selectedFileInfo, documentsGrid, emptyState;
let recentSection, recentList, filterChips, loadingOverlay, loadingText, toastContainer;

// ---- Lookup tables (declared once) ----
const TYPE_ICONS = Object.freeze({
    business_card: '🪪',
    resume: '📄',
    medical_report: '🏥',
});

const TYPE_LABELS = Object.freeze({
    business_card: 'Business Card',
    resume: 'Resume',
    medical_report: 'Medical Report',
});

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
    // Resolve DOM references once the page is loaded
    views = {
        upload: document.getElementById('view-upload'),
        documents: document.getElementById('view-documents'),
        review: document.getElementById('view-review'),
        detail: document.getElementById('view-detail'),
    };
    navLinks = document.querySelectorAll('.nav-link');
    uploadZone = document.getElementById('upload-zone');
    fileInput = document.getElementById('file-input');
    docTypeSelector = document.getElementById('doc-type-selector');
    typeChips = document.querySelectorAll('.type-chip');
    uploadBtn = document.getElementById('upload-btn');
    cancelUploadBtn = document.getElementById('cancel-upload-btn');
    selectedFileInfo = document.getElementById('selected-file-info');
    documentsGrid = document.getElementById('documents-grid');
    emptyState = document.getElementById('empty-state');
    recentSection = document.getElementById('recent-section');
    recentList = document.getElementById('recent-list');
    filterChips = document.querySelectorAll('.filter-chip');
    loadingOverlay = document.getElementById('loading-overlay');
    loadingText = document.getElementById('loading-text');
    toastContainer = document.getElementById('toast-container');

    initRouter();
    initUploadZone();
    initTypeChips();
    initFilterChips();
    initButtons();
    loadDocuments();
});

// ====================================================================
// Router
// ====================================================================

function initRouter() {
    window.addEventListener('hashchange', handleRoute);
    handleRoute();
}

function handleRoute() {
    const hash = window.location.hash.replace('#', '') || 'upload';

    // Handle detail view: #detail/123
    if (hash.startsWith('detail/')) {
        const docId = parseInt(hash.split('/')[1], 10);
        if (Number.isNaN(docId) || docId <= 0) {
            showToast('Invalid document ID.', 'error');
            window.location.hash = '#documents';
            return;
        }
        switchView('detail');
        loadDocumentDetail(docId);
        return;
    }

    if (views[hash]) {
        switchView(hash);
        if (hash === 'documents') loadDocuments();
        if (hash === 'upload') loadDocuments(); // refresh recent list
        if (hash === 'review') loadReviewQueue();
    } else {
        switchView('upload');
    }
}

function switchView(name) {
    currentView = name;
    Object.values(views).forEach(v => v.classList.remove('active'));
    if (views[name]) views[name].classList.add('active');
    navLinks.forEach(link => {
        link.classList.toggle('active', link.dataset.view === name);
    });
}

// ====================================================================
// Upload Zone
// ====================================================================

function initUploadZone() {
    uploadZone.addEventListener('click', () => fileInput.click());

    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('drag-over');
    });

    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('drag-over');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length > 0) handleFileSelected(e.dataTransfer.files[0]);
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) handleFileSelected(e.target.files[0]);
    });
}

function handleFileSelected(file) {
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    const allowedExts = ['pdf', 'txt', 'docx', 'doc', 'png', 'jpg', 'jpeg', 'tiff', 'bmp', 'webp'];

    if (!allowedExts.includes(ext)) {
        showToast('Unsupported file format. Use PDF, DOCX, TXT, or an image.', 'error');
        return;
    }

    // Client-side size guard (20 MB default, matches server)
    const MAX_MB = 20;
    if (file.size > MAX_MB * 1024 * 1024) {
        showToast(`File is too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Max: ${MAX_MB} MB.`, 'error');
        return;
    }

    selectedFile = file;
    selectedDocType = null;

    // Show type selector, hide drop zone
    docTypeSelector.style.display = 'block';
    uploadZone.style.display = 'none';

    // Reset chips
    typeChips.forEach(c => c.classList.remove('selected'));
    uploadBtn.disabled = true;

    // Show file info
    const sizeKB = (file.size / 1024).toFixed(1);
    selectedFileInfo.textContent = `${file.name} (${sizeKB} KB)`;
}

// ====================================================================
// Type Chips
// ====================================================================

function initTypeChips() {
    typeChips.forEach(chip => {
        chip.addEventListener('click', () => {
            typeChips.forEach(c => c.classList.remove('selected'));
            chip.classList.add('selected');
            selectedDocType = chip.dataset.type;
            uploadBtn.disabled = false;
        });
    });
}

// ====================================================================
// Filter Chips
// ====================================================================

function initFilterChips() {
    filterChips.forEach(chip => {
        chip.addEventListener('click', () => {
            filterChips.forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            currentFilter = chip.dataset.filter;
            renderDocuments();
        });
    });
}

// ====================================================================
// Buttons
// ====================================================================

function initButtons() {
    uploadBtn.addEventListener('click', handleUpload);
    cancelUploadBtn.addEventListener('click', resetUploadState);
    document.getElementById('back-btn').addEventListener('click', () => {
        window.location.hash = '#documents';
    });

    // Detail-view actions — handlers are bound once and read currentDocId
    document.getElementById('export-json-btn').addEventListener('click', () => {
        if (currentDocId) downloadExport(currentDocId, 'json');
    });
    document.getElementById('export-csv-btn').addEventListener('click', () => {
        if (currentDocId) downloadExport(currentDocId, 'csv');
    });
    document.getElementById('approve-btn').addEventListener('click', () => {
        if (currentDocId) approveDocument(currentDocId);
    });
}

let currentDocId = null;

function resetUploadState() {
    selectedFile = null;
    selectedDocType = null;
    docTypeSelector.style.display = 'none';
    uploadZone.style.display = 'block';
    fileInput.value = '';
    typeChips.forEach(c => c.classList.remove('selected'));
    uploadBtn.disabled = true;
}

// ====================================================================
// API Calls
// ====================================================================

async function handleUpload() {
    if (!selectedFile || !selectedDocType || isUploading) return;
    isUploading = true;
    uploadBtn.disabled = true;

    showLoading('Uploading document…');

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('doc_type', selectedDocType);

    let docId = null;

    try {
        const res = await fetch(`${API}/documents/upload`, {
            method: 'POST',
            body: formData,
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `Upload failed (${res.status})`);
        }

        const doc = await res.json();
        docId = doc.id;

        // Switch from generic spinner → pipeline tracker
        hideLoading();
        showPipelineTracker(doc.filename);

        // Open SSE stream for real-time progress
        const ssePromise = openProgressStream(doc.id);

        // Trigger processing
        const processRes = await fetch(`${API}/documents/${doc.id}/process`, {
            method: 'POST',
        });

        if (!processRes.ok) {
            const err = await processRes.json().catch(() => ({}));
            throw new Error(err.detail || `Processing failed (${processRes.status})`);
        }

        // Wait for SSE to finish (the "done" event)
        await ssePromise;

        showToast('Document processed!', 'success');
        resetUploadState();
        await loadDocuments();

        // Brief pause so the user sees all steps completed, then navigate
        await sleep(800);
        hidePipelineTracker();
        window.location.hash = `#detail/${doc.id}`;

    } catch (err) {
        showToast(err.message, 'error');
        hidePipelineTracker();
    } finally {
        isUploading = false;
        hideLoading();
    }
}

// ====================================================================
// Pipeline Tracker
// ====================================================================

const PIPELINE_PHASES = ['upload', 'ingestion', 'preprocessing', 'extraction', 'mapping', 'validation'];

let pipelineOverlay, pipelineSteps, pipelineFilename, pipelineStatusDetail, pipelineProgressDot;
let activeEventSource = null;

function _initTrackerRefs() {
    if (pipelineOverlay) return;
    pipelineOverlay = document.getElementById('pipeline-overlay');
    pipelineSteps = document.getElementById('pipeline-steps');
    pipelineFilename = document.getElementById('pipeline-filename');
    pipelineStatusDetail = document.getElementById('pipeline-status-detail');
    pipelineProgressDot = document.getElementById('pipeline-progress-dot');
}

function showPipelineTracker(filename) {
    _initTrackerRefs();
    pipelineFilename.textContent = filename;
    pipelineStatusDetail.textContent = 'Preparing…';

    // Reset all steps to pending
    const steps = pipelineSteps.querySelectorAll('.pipeline-step');
    steps.forEach(step => {
        step.classList.remove('completed', 'active', 'failed');
        step.classList.add('pending');
    });

    pipelineOverlay.style.display = 'flex';

    // Trigger entry animation
    requestAnimationFrame(() => {
        pipelineOverlay.classList.add('visible');
    });
}

function hidePipelineTracker() {
    _initTrackerRefs();
    pipelineOverlay.classList.remove('visible');
    setTimeout(() => {
        pipelineOverlay.style.display = 'none';
    }, 400);

    if (activeEventSource) {
        activeEventSource.close();
        activeEventSource = null;
    }
}

function updatePipelineStep(phase, status, detail) {
    _initTrackerRefs();
    const phaseIndex = PIPELINE_PHASES.indexOf(phase);
    if (phaseIndex === -1 && phase !== 'done') return;

    const steps = pipelineSteps.querySelectorAll('.pipeline-step');

    if (phase === 'done') {
        // Mark all steps completed
        steps.forEach(step => {
            step.classList.remove('active', 'pending', 'failed');
            step.classList.add('completed');
        });
        pipelineStatusDetail.textContent = 'Complete!';
        pipelineProgressDot.className = 'pipeline-status-dot completed';
        return;
    }

    steps.forEach((step, i) => {
        step.classList.remove('active', 'pending', 'completed', 'failed');
        if (i < phaseIndex) {
            step.classList.add('completed');
        } else if (i === phaseIndex) {
            step.classList.add(status === 'failed' ? 'failed' : 'active');
        } else {
            step.classList.add('pending');
        }
    });

    // Update status bar
    if (detail) {
        pipelineStatusDetail.textContent = detail;
    }
    pipelineProgressDot.className = `pipeline-status-dot ${status === 'failed' ? 'failed' : 'active'}`;
}

function openProgressStream(docId) {
    return new Promise((resolve) => {
        // Small delay to ensure the SSE endpoint is ready
        setTimeout(() => {
            const es = new EventSource(`${API}/documents/${docId}/progress`);
            activeEventSource = es;

            es.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    updatePipelineStep(data.phase, data.status, data.detail);

                    if (data.phase === 'done' || data.status === 'failed') {
                        es.close();
                        activeEventSource = null;
                        resolve(data);
                    }
                } catch { /* ignore parse errors */ }
            };

            es.onerror = () => {
                es.close();
                activeEventSource = null;
                resolve({ phase: 'done', status: 'completed' });
            };
        }, 100);
    });
}

function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
}

async function loadDocuments() {
    try {
        const res = await fetch(`${API}/documents`);
        if (!res.ok) throw new Error('Failed to load documents');
        const data = await res.json();
        documents = data.documents || [];
        renderDocuments();
        renderRecentUploads();
        updateReviewBadge(documents.filter(d => d.status === 'needs_review').length);
    } catch {
        // Silently fail on first load (API may not be ready yet)
        documents = [];
        renderDocuments();
    }
}

async function loadDocumentDetail(docId) {
    showLoading('Loading document…');
    try {
        const res = await fetch(`${API}/documents/${docId}`);
        if (!res.ok) throw new Error('Document not found');
        const doc = await res.json();
        renderDetail(doc);
    } catch (err) {
        showToast(err.message, 'error');
        window.location.hash = '#documents';
    } finally {
        hideLoading();
    }
}

async function deleteDocument(docId) {
    if (!confirm('Delete this document? This cannot be undone.')) return;

    try {
        const res = await fetch(`${API}/documents/${docId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Delete failed');
        showToast('Document deleted', 'info');
        await loadDocuments();
        if (currentView === 'detail') window.location.hash = '#documents';
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ====================================================================
// Render Functions
// ====================================================================

function renderDocuments() {
    const filtered = currentFilter === 'all'
        ? documents
        : documents.filter(d => d.doc_type === currentFilter);

    if (filtered.length === 0) {
        documentsGrid.innerHTML = '';
        documentsGrid.appendChild(emptyState);
        emptyState.style.display = 'block';
        return;
    }

    emptyState.style.display = 'none';

    documentsGrid.innerHTML = filtered.map(doc => `
        <div class="doc-card" onclick="window.location.hash='#detail/${doc.id}'">
            <div class="doc-card-header">
                <div>
                    <div class="doc-card-name">${escapeHtml(doc.filename)}</div>
                    <div class="doc-card-type">${TYPE_LABELS[doc.doc_type] || doc.doc_type}</div>
                </div>
                <div class="doc-card-icon ${escapeHtml(doc.doc_type)}">
                    ${TYPE_ICONS[doc.doc_type] || '📋'}
                </div>
            </div>
            <div class="doc-card-footer">
                <span class="doc-card-date">${formatDate(doc.created_at)}</span>
                <span class="status-badge ${escapeHtml(doc.status)}">${escapeHtml(doc.status)}</span>
            </div>
        </div>
    `).join('');
}

function renderRecentUploads() {
    const recent = documents.slice(0, 3);
    if (recent.length === 0) {
        recentSection.style.display = 'none';
        return;
    }

    recentSection.style.display = 'block';

    recentList.innerHTML = recent.map(doc => `
        <div class="doc-card" onclick="window.location.hash='#detail/${doc.id}'" style="padding: 14px 18px;">
            <div class="doc-card-header" style="margin-bottom: 0;">
                <div>
                    <div class="doc-card-name">${escapeHtml(doc.filename)}</div>
                    <div class="doc-card-type">${TYPE_LABELS[doc.doc_type] || doc.doc_type} &middot; ${formatDate(doc.created_at)}</div>
                </div>
                <span class="status-badge ${escapeHtml(doc.status)}">${escapeHtml(doc.status)}</span>
            </div>
        </div>
    `).join('');
}

function renderDetail(doc) {
    currentDocId = doc.id;
    document.getElementById('detail-filename').textContent = doc.filename;

    const statusBadge = document.getElementById('detail-status');
    statusBadge.textContent = doc.status;
    statusBadge.className = `status-badge ${doc.status}`;

    document.getElementById('detail-meta').innerHTML = `
        <span>${TYPE_LABELS[doc.doc_type] || escapeHtml(doc.doc_type)}</span>
        <span>Uploaded ${formatDate(doc.created_at)}</span>
        ${doc.processed_at ? `<span>Processed ${formatDate(doc.processed_at)}</span>` : ''}
        <span style="margin-left:auto;">
            <button class="btn btn-danger btn-sm" onclick="deleteDocument(${doc.id})">Delete</button>
        </span>
    `;

    // Raw text
    const rawTextEl = document.getElementById('detail-raw-text');
    rawTextEl.textContent = doc.raw_text || 'No text extracted yet.';

    // Extracted data
    const dataEl = document.getElementById('detail-extracted-data');
    const editBtn = document.getElementById('btn-edit-data');
    if (doc.extracted_data && Object.keys(doc.extracted_data).length > 0) {
        currentDocData = doc.extracted_data;
        dataEl.innerHTML = renderExtractedData(doc.extracted_data, doc.confidence_scores);
        editBtn.style.display = 'inline-block';
    } else {
        currentDocData = {};
        dataEl.innerHTML = '<p class="text-muted">No structured data extracted yet.</p>';
        editBtn.style.display = 'inline-block';
    }

    // Approve button — only shown for needs_review docs
    const approveBtn = document.getElementById('approve-btn');
    approveBtn.style.display = (doc.status === 'needs_review') ? 'inline-flex' : 'none';

    // Issues banner
    const banner = document.getElementById('issues-banner');
    const issues = doc.issues || [];
    const missing = doc.missing_required || [];
    if (issues.length || missing.length) {
        let html = '<h4>This document needs review</h4><ul>';
        for (const m of missing) html += `<li>Missing required field: <strong>${escapeHtml(m)}</strong></li>`;
        for (const i of issues) html += `<li>${escapeHtml(i)}</li>`;
        html += '</ul>';
        banner.innerHTML = html;
        banner.style.display = 'block';
    } else {
        banner.style.display = 'none';
    }
}

// ====================================================================
// Review queue
// ====================================================================

async function loadReviewQueue() {
    try {
        const res = await fetch(`${API}/review-queue`);
        if (!res.ok) throw new Error('Failed to load review queue');
        const data = await res.json();
        renderReviewQueue(data.items || []);
        updateReviewBadge(data.total || 0);
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function renderReviewQueue(items) {
    const grid = document.getElementById('review-grid');
    const empty = document.getElementById('review-empty');

    if (items.length === 0) {
        grid.innerHTML = '';
        grid.appendChild(empty);
        empty.style.display = 'block';
        return;
    }

    empty.style.display = 'none';
    grid.innerHTML = items.map(item => {
        const missingHtml = (item.missing_required || []).map(m =>
            `<span class="status-badge needs_review">missing: ${escapeHtml(m)}</span>`
        ).join(' ');
        return `
            <div class="doc-card" onclick="window.location.hash='#detail/${item.id}'">
                <div class="doc-card-header">
                    <div>
                        <div class="doc-card-name">${escapeHtml(item.filename)}</div>
                        <div class="doc-card-type">${TYPE_LABELS[item.doc_type] || item.doc_type}</div>
                    </div>
                    <div class="doc-card-icon ${escapeHtml(item.doc_type)}">
                        ${TYPE_ICONS[item.doc_type] || '📋'}
                    </div>
                </div>
                <div class="doc-card-footer" style="flex-wrap:wrap;gap:6px;">
                    ${missingHtml || '<span class="status-badge needs_review">low confidence</span>'}
                </div>
            </div>
        `;
    }).join('');
}

function updateReviewBadge(count) {
    const badge = document.getElementById('review-badge');
    if (!badge) return;
    if (count > 0) {
        badge.textContent = String(count);
        badge.style.display = 'inline-block';
    } else {
        badge.style.display = 'none';
    }
}

async function approveDocument(docId) {
    try {
        const res = await fetch(`${API}/documents/${docId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),  // approve as-is
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Approve failed');
        }
        showToast('Document approved', 'success');
        await loadDocumentDetail(docId);
        await loadReviewQueue();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function downloadExport(docId, format) {
    try {
        const res = await fetch(`${API}/documents/${docId}/export?format=${format}`);
        if (!res.ok) throw new Error(`Failed to export as ${format.toUpperCase()}`);
        
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        
        // Extract filename from Content-Disposition if available, or fallback
        let filename = `export_${docId}.${format}`;
        const cd = res.headers.get('Content-Disposition');
        if (cd && cd.includes('filename=')) {
            const matches = /filename="([^"]+)"/.exec(cd);
            if (matches && matches[1]) {
                filename = matches[1];
            }
        } else {
            // Fallback: try to grab from the DOM
            const domName = document.getElementById('detail-filename')?.textContent;
            if (domName) {
                filename = `${domName}.${format}`;
            }
        }
        
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        
        // Cleanup
        window.URL.revokeObjectURL(url);
        a.remove();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function renderExtractedData(data, confidences) {
    if (data._note) {
        return `<p class="text-muted">${escapeHtml(data._note)}</p>`;
    }

    let html = '<table class="data-table">';

    for (const [key, value] of Object.entries(data)) {
        if (key.startsWith('_')) continue;

        const label = key.replace(/_/g, ' ');
        let displayValue;

        if (Array.isArray(value)) {
            displayValue = value.map(v => {
                if (typeof v === 'object' && v !== null) {
                    return '<pre style="margin:0;font-size:0.82rem;">' +
                        escapeHtml(JSON.stringify(v, null, 2)) + '</pre>';
                }
                const strV = String(v);
                if (strV.startsWith('http://') || strV.startsWith('https://') || strV.startsWith('www.')) {
                    const href = strV.startsWith('www.') ? 'https://' + strV : strV;
                    return `<a href="${escapeHtml(href)}" target="_blank" rel="noopener">${escapeHtml(strV)}</a>`;
                }
                return escapeHtml(strV);
            }).join('<br>');
        } else if (typeof value === 'object' && value !== null) {
            displayValue = '<pre style="margin:0;font-size:0.82rem;">' +
                escapeHtml(JSON.stringify(value, null, 2)) + '</pre>';
        } else {
            const strV = String(value ?? '—');
            if (strV.startsWith('http://') || strV.startsWith('https://') || strV.startsWith('www.')) {
                const href = strV.startsWith('www.') ? 'https://' + strV : strV;
                displayValue = `<a href="${escapeHtml(href)}" target="_blank" rel="noopener">${escapeHtml(strV)}</a>`;
            } else {
                displayValue = escapeHtml(strV);
            }
        }

        // Confidence bar
        let confBar = '';
        if (confidences && confidences[key] !== undefined) {
            const pct = Math.round(confidences[key] * 100);
            const color = pct >= 80 ? 'var(--success)' : pct >= 50 ? 'var(--warning)' : 'var(--error)';
            confBar = `<span class="confidence-bar"><span class="confidence-bar-fill" style="width:${pct}%;background:${color}"></span></span>`;
        }

        html += `<tr>
            <td>${escapeHtml(label)}</td>
            <td>${displayValue} ${confBar}</td>
        </tr>`;
    }

    html += '</table>';
    return html;
}

// ====================================================================
// Edit Data
// ====================================================================

function openEditModal() {
    if (!currentDocData) return;
    const textarea = document.getElementById('edit-json-textarea');
    textarea.value = JSON.stringify(currentDocData, null, 2);
    document.getElementById('edit-modal').style.display = 'flex';
}

function closeEditModal() {
    document.getElementById('edit-modal').style.display = 'none';
}

async function saveEditedData() {
    const textarea = document.getElementById('edit-json-textarea');
    let newData;
    try {
        newData = JSON.parse(textarea.value);
    } catch (e) {
        showToast('Invalid JSON format. Please check for errors.', 'error');
        return;
    }

    try {
        const res = await fetch(`${API}/documents/${currentDocId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                extracted_data: newData,
                approve: true  // Saving edits automatically approves it
            })
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to save changes');
        }

        showToast('Data updated successfully', 'success');
        closeEditModal();
        await loadDocumentDetail(currentDocId);
        await loadReviewQueue();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// ====================================================================
// Helpers
// ====================================================================

function formatDate(dateStr) {
    if (!dateStr) return '';
    // Server returns UTC timestamps — ensure the browser knows they're UTC
    if (dateStr && !dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
        dateStr = dateStr + 'Z';
    }
    const d = new Date(dateStr);
    if (Number.isNaN(d.getTime())) return '';

    const now = new Date();
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHrs = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHrs < 24) return `${diffHrs}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icons = { success: '✓', error: '✕', info: 'ℹ' };
    toast.innerHTML = `<span>${icons[type] || ''}</span><span>${escapeHtml(message)}</span>`;
    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('removing');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function showLoading(text = 'Processing…') {
    loadingText.textContent = text;
    loadingOverlay.style.display = 'flex';
}

function hideLoading() {
    loadingOverlay.style.display = 'none';
}
