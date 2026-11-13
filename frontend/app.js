const API_URL = 'http://localhost:8000/api';

const uploadForm = document.getElementById('uploadForm');
const fileInput = document.getElementById('fileInput');
const uploadArea = document.getElementById('uploadArea');
const fileSelected = document.getElementById('fileSelected');
const fileName = document.getElementById('fileName');
const uploadSection = document.getElementById('uploadSection');
const progressSection = document.getElementById('progressSection');
const resultSection = document.getElementById('resultSection');
const errorSection = document.getElementById('errorSection');
const progressBar = document.getElementById('progressBar');
const progressPercent = document.getElementById('progressPercent');
const progressMessage = document.getElementById('progressMessage');
const downloadLink = document.getElementById('downloadLink');
const errorMessage = document.getElementById('errorMessage');
const submitBtn = document.getElementById('submitBtn');
const progressStats = document.getElementById('progressStats');
const cancelBtn = document.getElementById('cancelBtn');
const pauseBtn = document.getElementById('pauseBtn');
const resumeBtn = document.getElementById('resumeBtn');
const errorResumeBtn = document.getElementById('errorResumeBtn');
const resultResumeBtn = document.getElementById('resultResumeBtn');
const resultSummary = document.getElementById('resultSummary');
const tabTranslate = document.getElementById('tabTranslate');
const tabJobs = document.getElementById('tabJobs');
const jobsSection = document.getElementById('jobsSection');
const jobsList = document.getElementById('jobsList');
const jobsEmpty = document.getElementById('jobsEmpty');
const jobsError = document.getElementById('jobsError');
const jobsBadge = document.getElementById('jobsBadge');

const STATUS_LABELS = {
    queued: 'Na fila',
    extracting: 'Extraindo',
    translating: 'Traduzindo',
    pausing: 'Pausando',
    rebuilding: 'Reconstruindo',
    validating: 'Validando',
    paused: 'Pausada',
    cancelled: 'Cancelada',
    done: 'Concluída',
    error: 'Erro'
};

const ACTIVE_STATUSES = ['queued', 'extracting', 'translating', 'pausing', 'rebuilding', 'validating'];
const PAUSABLE_STATUSES = ['queued', 'extracting', 'translating'];
const RESUMABLE_STATUSES = ['paused', 'cancelled', 'error'];

let currentJobId = null;
let pollInterval = null;
let jobsInterval = null;
let currentTab = 'translate';
let currentPanel = 'upload';

function renderVisibility() {
    jobsSection.style.display = currentTab === 'jobs' ? 'block' : 'none';

    const panels = {
        upload: uploadSection,
        progress: progressSection,
        result: resultSection,
        error: errorSection
    };

    Object.entries(panels).forEach(([name, element]) => {
        element.style.display =
            currentTab === 'translate' && name === currentPanel ? 'block' : 'none';
    });
}

function setPanel(name) {
    currentPanel = name;
    renderVisibility();
}

function switchTab(tab) {
    currentTab = tab;

    tabTranslate.classList.toggle('is-active', tab === 'translate');
    tabJobs.classList.toggle('is-active', tab === 'jobs');
    tabTranslate.setAttribute('aria-pressed', String(tab === 'translate'));
    tabJobs.setAttribute('aria-pressed', String(tab === 'jobs'));

    renderVisibility();

    if (tab === 'jobs') {
        loadJobs();
    }
}

tabTranslate.addEventListener('click', () => switchTab('translate'));
tabJobs.addEventListener('click', () => switchTab('jobs'));

// Drag and drop
uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        fileInput.files = files;
        handleFileSelect();
    }
});

// File input change
fileInput.addEventListener('change', handleFileSelect);

function handleFileSelect() {
    const file = fileInput.files[0];
    if (file) {
        const name = file.name.toLowerCase();
        if (!name.endsWith('.epub') && !name.endsWith('.pdf')) {
            alert('Apenas arquivos EPUB ou PDF são permitidos');
            fileInput.value = '';
            return;
        }
        fileName.textContent = file.name;
        document.querySelector('.upload-content').style.display = 'none';
        fileSelected.style.display = 'flex';
    }
}

function removeFile() {
    fileInput.value = '';
    document.querySelector('.upload-content').style.display = 'block';
    fileSelected.style.display = 'none';
}

// Form submit
uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const file = fileInput.files[0];
    if (!file) {
        alert('Selecione um arquivo EPUB ou PDF');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('provider', document.getElementById('provider').value);
    formData.append('model', document.getElementById('model').value);
    formData.append('apiKey', document.getElementById('apiKey').value);
    formData.append('baseUrl', document.getElementById('baseUrl').value);
    
    submitBtn.disabled = true;
    submitBtn.textContent = 'Enviando...';
    
    try {
        const response = await fetch(`${API_URL}/upload`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Erro ao enviar arquivo');
        }
        
        const data = await response.json();
        currentJobId = data.job_id;

        switchTab('translate');
        setPanel('progress');
        startPolling();
    } catch (error) {
        showError(error.message);
        submitBtn.disabled = false;
        submitBtn.textContent = 'Traduzir livro';
    }
});

function setPauseButton(visible, text = 'Pausar', disabled = false) {
    if (!pauseBtn) return;
    pauseBtn.style.display = visible ? 'inline-block' : 'none';
    pauseBtn.textContent = text;
    pauseBtn.disabled = disabled;
}

function setRunningUI() {
    setPauseButton(true);
    cancelBtn.disabled = false;
    cancelBtn.textContent = 'Cancelar';
    cancelBtn.style.display = 'inline-block';
    resumeBtn.style.display = 'none';
    errorResumeBtn.style.display = 'none';
    resultResumeBtn.style.display = 'none';
}

function updateStats(data) {
    const totalBlocks = data.total_blocks || 0;
    const doneBlocks = data.done_blocks || 0;
    const totalChapters = data.total_chapters || 0;
    const doneChapters = data.done_chapters || 0;

    if (!totalBlocks && !totalChapters) {
        progressStats.textContent = '';
        return;
    }

    const unit = data.source_format === 'pdf' ? 'Seções' : 'Capítulos';
    progressStats.textContent =
        `${unit}: ${doneChapters}/${totalChapters} • Blocos: ${doneBlocks}/${totalBlocks}`;
}

function applyJobStatus(data) {
    progressBar.style.width = data.progress + '%';
    progressPercent.textContent = data.progress + '%';
    progressMessage.textContent = data.message || '';
    updateStats(data);

    if (data.status === 'pausing') {
        setPauseButton(true, 'Pausando...', true);
    } else if (PAUSABLE_STATUSES.includes(data.status)) {
        setPauseButton(true);
    } else {
        setPauseButton(false);
    }

    if (data.status === 'done') {
        clearInterval(pollInterval);
        pollInterval = null;
        setPanel('result');

        const total = data.total_blocks || 0;
        const done = data.done_blocks || 0;
        const pending = Math.max(total - done, 0);
        const isPdf = data.source_format === 'pdf';

        resultSummary.textContent = total
            ? `Blocos traduzidos: ${done}/${total}` +
              (pending ? ` • ${pending} pendente(s)` : '') +
              (isPdf ? ' • PDF convertido em EPUB' : '')
            : (isPdf ? 'PDF convertido em EPUB.' : '');
        resultResumeBtn.style.display = pending ? 'inline-block' : 'none';
        if (pending) {
            resultResumeBtn.textContent = `Retomar ${pending} bloco(s)`;
        }
        downloadLink.textContent = isPdf
            ? 'Baixar EPUB convertido do PDF'
            : 'Baixar EPUB traduzido';

        let downloadUrl = data.download_url || '';
        if (downloadUrl.startsWith('/api/')) {
            downloadUrl = downloadUrl.replace('/api', '');
        }
        downloadLink.href = `${API_URL}${downloadUrl}`;
    } else if (data.status === 'error') {
        clearInterval(pollInterval);
        pollInterval = null;
        showError(data.message, true, data.translator_errors);
    } else if (data.status === 'paused' || data.status === 'cancelled') {
        clearInterval(pollInterval);
        pollInterval = null;
        setPanel('progress');
        cancelBtn.style.display = 'none';
        resumeBtn.style.display = 'inline-block';
        progressMessage.textContent = data.message ||
            (data.status === 'cancelled'
                ? 'Tradução cancelada. Você pode retomar.'
                : 'Tradução pausada. Você pode retomar.');
    }

    if (['done', 'error', 'paused', 'cancelled'].includes(data.status)) {
        loadJobs();
    }
}

async function pollJobStatus() {
    if (!currentJobId) return;

    try {
        const response = await fetch(`${API_URL}/status/${currentJobId}`);
        const data = await response.json();
        applyJobStatus(data);
    } catch (error) {
        console.error('Polling error:', error);
    }
}

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    setRunningUI();

    pollJobStatus();
    pollInterval = setInterval(pollJobStatus, 1000);
}

async function cancelJob() {
    if (!currentJobId) return;

    cancelBtn.disabled = true;
    cancelBtn.textContent = 'Cancelando...';

    try {
        const response = await fetch(`${API_URL}/jobs/${currentJobId}/cancel`, {
            method: 'POST'
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Erro ao cancelar');
        }
        progressMessage.textContent =
            'Cancelamento solicitado. Aguardando o lote atual terminar...';
        loadJobs();
    } catch (error) {
        cancelBtn.disabled = false;
        cancelBtn.textContent = 'Cancelar';
        alert(error.message);
    }
}

async function pauseJob() {
    if (!currentJobId) return;

    setPauseButton(true, 'Pausando...', true);

    try {
        const response = await fetch(`${API_URL}/jobs/${currentJobId}/pause`, {
            method: 'POST'
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Erro ao pausar');
        }
        progressMessage.textContent =
            'Pausa solicitada. Aguardando o lote atual terminar...';
        loadJobs();
    } catch (error) {
        setPauseButton(true);
        alert(error.message);
    }
}

async function resumeJob(jobId = currentJobId) {
    if (!jobId) return;
    currentJobId = jobId;

    const formData = new FormData();
    formData.append('apiKey', document.getElementById('apiKey').value || '');

    resumeBtn.disabled = true;
    errorResumeBtn.disabled = true;
    resultResumeBtn.disabled = true;

    try {
        const response = await fetch(`${API_URL}/jobs/${jobId}/resume`, {
            method: 'POST',
            body: formData
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Erro ao retomar');
        }

        switchTab('translate');
        setPanel('progress');
        progressMessage.textContent = 'Retomando tradução...';
        startPolling();
    } catch (error) {
        alert(error.message);
    } finally {
        resumeBtn.disabled = false;
        errorResumeBtn.disabled = false;
        resultResumeBtn.disabled = false;
    }
}

function showError(message, canResume = false, details = null) {
    setPanel('error');

    let text = message || 'Erro inesperado';
    if (Array.isArray(details) && details.length) {
        text += '\n\n' + details.slice(0, 5).join('\n');
    }
    errorMessage.textContent = text;
    errorResumeBtn.style.display =
        canResume && currentJobId ? 'inline-block' : 'none';
    submitBtn.disabled = false;
    submitBtn.textContent = 'Traduzir livro';
}

function resetForm() {
    if (pollInterval) clearInterval(pollInterval);
    currentJobId = null;

    uploadForm.reset();
    removeFile();
    document.getElementById('provider').value = 'ollama';
    document.getElementById('model').value = 'qwen2.5:7b-instruct';
    document.getElementById('baseUrl').value = 'http://localhost:11434';

    switchTab('translate');
    setPanel('upload');
    progressStats.textContent = '';

    cancelBtn.style.display = 'inline-block';
    resumeBtn.style.display = 'none';
    errorResumeBtn.style.display = 'none';
    resultResumeBtn.style.display = 'none';

    submitBtn.disabled = false;
    submitBtn.textContent = 'Traduzir livro';
}

// ---------------------------------------------------------------------------
// Lista de traduções
// ---------------------------------------------------------------------------

function isJobInProgress(job) {
    return ACTIVE_STATUSES.includes(job.status) || job.status === 'paused';
}

function makeElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}

async function loadJobs() {
    try {
        const response = await fetch(`${API_URL}/jobs`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        const jobs = Array.isArray(data.jobs) ? data.jobs : [];

        updateJobsBadge(jobs);
        jobsError.style.display = 'none';

        if (currentTab === 'jobs') {
            renderJobs(jobs);
        }
    } catch (error) {
        console.error('Jobs error:', error);
        jobsBadge.style.display = 'none';

        if (currentTab === 'jobs') {
            jobsList.replaceChildren();
            jobsEmpty.style.display = 'none';
            jobsError.textContent =
                'Não foi possível carregar as traduções. Verifique se o backend está no ar.';
            jobsError.style.display = 'block';
        }
    }
}

function updateJobsBadge(jobs) {
    const activeCount = jobs.filter(isJobInProgress).length;
    jobsBadge.textContent = String(activeCount);
    jobsBadge.style.display = activeCount ? 'inline-block' : 'none';
}

function renderJobs(jobs) {
    const ordered = [...jobs].sort((a, b) => {
        return (isJobInProgress(a) ? 0 : 1) - (isJobInProgress(b) ? 0 : 1);
    });

    jobsList.replaceChildren();
    jobsEmpty.style.display = ordered.length ? 'none' : 'block';

    ordered.forEach(job => jobsList.appendChild(renderJob(job)));
}

function formatJobStats(job) {
    const totalChapters = Number(job.total_chapters) || 0;
    const doneChapters = Number(job.done_chapters) || 0;
    const totalBlocks = Number(job.total_blocks) || 0;
    const doneBlocks = Number(job.done_blocks) || 0;

    if (!totalChapters && !totalBlocks) return '';

    const unit = job.source_format === 'pdf' ? 'Seções' : 'Capítulos';
    return `${unit}: ${doneChapters}/${totalChapters} • Blocos: ${doneBlocks}/${totalBlocks}`;
}
}

function renderJob(job) {
    const status = job.status || 'queued';
    const card = makeElement('article', 'job');
    if (isJobInProgress(job)) card.classList.add('job-active');

    const header = makeElement('div', 'job-header');
    const titleBlock = makeElement('div', 'job-title-block');
    titleBlock.appendChild(
        makeElement('h3', 'job-title', job.filename || 'Arquivo sem nome')
    );
    titleBlock.appendChild(
        makeElement(
            'span',
            'job-format',
            job.source_format === 'pdf' ? 'PDF → EPUB' : 'EPUB'
        )
    );
    header.appendChild(titleBlock);

    const statusElement = makeElement(
        'span', 'job-status', STATUS_LABELS[status] || status
    );
    if (STATUS_LABELS[status]) statusElement.dataset.status = status;
    header.appendChild(statusElement);

    const progress = makeElement('div', 'job-progress');
    const progressBar = makeElement('div', 'job-progress-bar');
    const percent = Math.max(0, Math.min(100, Number(job.progress) || 0));
    progressBar.style.width = `${percent}%`;
    progress.appendChild(progressBar);

    const meta = makeElement('p', 'job-meta');
    meta.textContent = [job.message, formatJobStats(job)]
        .filter(Boolean)
        .join(' • ');

    const actions = makeElement('div', 'job-actions');

    if (status === 'done' && job.download_url) {
        let downloadUrl = job.download_url;
        if (downloadUrl.startsWith('/api/')) {
            downloadUrl = downloadUrl.replace('/api', '');
        }
        const download = makeElement('a', 'btn-secondary btn-small', 'Baixar EPUB');
        download.href = `${API_URL}${downloadUrl}`;
        download.download = '';
        actions.appendChild(download);
    }

    const openLabels = {
        done: 'Ver resultado',
        error: 'Ver detalhes'
    };
    const openButton = makeElement(
        'button',
        'btn-secondary btn-small',
        openLabels[status] || 'Acompanhar'
    );
    openButton.type = 'button';
    openButton.addEventListener('click', () => openJob(job.job_id));
    actions.appendChild(openButton);

    const pendingBlocks = Math.max(
        (Number(job.total_blocks) || 0) - (Number(job.done_blocks) || 0), 0
    );
    const canResume =
        RESUMABLE_STATUSES.includes(status) ||
        (status === 'done' && pendingBlocks > 0);

    if (PAUSABLE_STATUSES.includes(status)) {
        const pauseButton = makeElement('button', 'btn-secondary btn-small', 'Pausar');
        pauseButton.type = 'button';
        pauseButton.addEventListener('click', () => pauseJobFromList(job.job_id));
        actions.appendChild(pauseButton);
    }

    if (canResume) {
        const resumeButton = makeElement(
            'button',
            'btn-primary btn-small',
            status === 'done' ? `Retomar ${pendingBlocks} bloco(s)` : 'Retomar'
        );
        resumeButton.type = 'button';
        resumeButton.addEventListener('click', () => resumeJob(job.job_id));
        actions.appendChild(resumeButton);
    }

    if (ACTIVE_STATUSES.includes(status)) {
        const cancelButton = makeElement('button', 'btn-secondary btn-small', 'Cancelar');
        cancelButton.type = 'button';
        cancelButton.addEventListener('click', () => cancelJobFromList(job.job_id));
        actions.appendChild(cancelButton);
    }

    card.append(header, progress, meta);
    if (actions.childElementCount) card.appendChild(actions);
    return card;
}

function openJob(jobId) {
    currentJobId = jobId;
    switchTab('translate');
    setPanel('progress');
    startPolling();
}

async function pauseJobFromList(jobId) {
    try {
        const response = await fetch(`${API_URL}/jobs/${jobId}/pause`, {
            method: 'POST'
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Erro ao pausar');
        }

        await loadJobs();
        if (jobId === currentJobId) pollJobStatus();
    } catch (error) {
        alert(error.message);
    }
}

async function cancelJobFromList(jobId) {
    try {
        const response = await fetch(`${API_URL}/jobs/${jobId}/cancel`, {
            method: 'POST'
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Erro ao cancelar');
        }

        await loadJobs();
        if (jobId === currentJobId) pollJobStatus();
    } catch (error) {
        alert(error.message);
    }
}

switchTab('translate');
loadJobs();
jobsInterval = setInterval(loadJobs, 5000);
