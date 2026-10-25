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

let currentJobId = null;
let pollInterval = null;

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
        if (!file.name.endsWith('.epub')) {
            alert('Apenas arquivos EPUB são permitidos');
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
        alert('Selecione um arquivo EPUB');
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
        
        uploadSection.style.display = 'none';
        progressSection.style.display = 'block';
        errorSection.style.display = 'none';
        resultSection.style.display = 'none';
        
        startPolling();
    } catch (error) {
        showError(error.message);
        submitBtn.disabled = false;
        submitBtn.textContent = 'Traduzir Livro';
    }
});

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    
    pollInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_URL}/status/${currentJobId}`);
            const data = await response.json();
            
            progressBar.style.width = data.progress + '%';
            progressPercent.textContent = data.progress + '%';
            progressMessage.textContent = data.message;
            
            if (data.status === 'done') {
                clearInterval(pollInterval);
                progressSection.style.display = 'none';
                resultSection.style.display = 'block';
                let downloadUrl = data.download_url || '';
                if (downloadUrl.startsWith('/api/')) {
                    downloadUrl = downloadUrl.replace('/api', '');
                }
                downloadLink.href = `${API_URL}${downloadUrl}`;
            } else if (data.status === 'error') {
                clearInterval(pollInterval);
                showError(data.message);
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 1000);
}

function showError(message) {
    progressSection.style.display = 'none';
    resultSection.style.display = 'none';
    uploadSection.style.display = 'none';
    errorSection.style.display = 'block';
    errorMessage.textContent = message;
    submitBtn.disabled = false;
    submitBtn.textContent = 'Traduzir Livro';
}

function resetForm() {
    if (pollInterval) clearInterval(pollInterval);
    
    uploadForm.reset();
    removeFile();
    document.getElementById('provider').value = 'ollama';
    document.getElementById('model').value = 'translategemma:4b';
    document.getElementById('baseUrl').value = 'http://localhost:11434';
    
    uploadSection.style.display = 'block';
    progressSection.style.display = 'none';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';
    
    submitBtn.disabled = false;
    submitBtn.textContent = 'Traduzir Livro';
}
