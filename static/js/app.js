/* ============================================
   Docxtract — Application Logic
   ============================================ */

'use strict';

const API = '/api';

// ---- State ----
let currentView = 'upload';
let documents = [];
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
    const allowedExts = ['pdf', 'txt', 'docx', 'doc'];

    if (!allowedExts.includes(ext)) {
        showToast('Unsupported file format. Please use PDF, DOCX, or TXT.', 'error');
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
}

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
        showToast(`"${doc.filename}" uploaded successfully`, 'success');

        // Auto-process
        hideLoading();
        showLoading('Running extraction pipeline…');

        const processRes = await fetch(`${API}/documents/${doc.id}/process`, {
            method: 'POST',
        });

        if (!processRes.ok) {
            const err = await processRes.json().catch(() => ({}));
            throw new Error(err.detail || `Processing failed (${processRes.status})`);
        }

        showToast('Document processed!', 'success');
        resetUploadState();
        await loadDocuments();

        // Navigate to detail
        window.location.hash = `#detail/${doc.id}`;

    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        isUploading = false;
        hideLoading();
    }
}

async function loadDocuments() {
    try {
        const res = await fetch(`${API}/documents`);
        if (!res.ok) throw new Error('Failed to load documents');
        const data = await res.json();
        documents = data.documents || [];
        renderDocuments();
        renderRecentUploads();
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
    if (doc.extracted_data && Object.keys(doc.extracted_data).length > 0) {
        dataEl.innerHTML = renderExtractedData(doc.extracted_data, doc.confidence_scores);
    } else {
        dataEl.innerHTML = '<p class="text-muted">No structured data extracted yet.</p>';
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
                return escapeHtml(String(v));
            }).join('<br>');
        } else if (typeof value === 'object' && value !== null) {
            displayValue = '<pre style="margin:0;font-size:0.82rem;">' +
                escapeHtml(JSON.stringify(value, null, 2)) + '</pre>';
        } else {
            displayValue = escapeHtml(String(value ?? '—'));
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
// Helpers
// ====================================================================

function formatDate(dateStr) {
    if (!dateStr) return '';
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
