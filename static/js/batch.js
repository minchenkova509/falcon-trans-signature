// Глобальные переменные
let selectedFiles = [];
let processedResults = [];

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    console.log('Инициализация пакетной обработки');
    
    initializeDragAndDrop();
    initializeFileInput();
    initializeButtons();
    updateSealPreview();
});

// Инициализация drag and drop
function initializeDragAndDrop() {
    const dropZone = document.getElementById('dropZone');
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });
    
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });
    
    dropZone.addEventListener('drop', handleDrop, false);
    dropZone.addEventListener('click', () => document.getElementById('fileInput').click());
}

// Инициализация input файла
function initializeFileInput() {
    const fileInput = document.getElementById('fileInput');
    fileInput.addEventListener('change', handleFileSelect);
}

// Инициализация кнопок
function initializeButtons() {
    // Кнопка применения стандартных координат
    document.getElementById('applyStandardCoords').addEventListener('click', applyStandardCoordinates);
    
    // Кнопка обработки файлов
    document.getElementById('processFiles').addEventListener('click', processFiles);
    
    // Кнопка скачивания всех файлов
    document.getElementById('downloadAllBtn').addEventListener('click', downloadAllFiles);
    
    // Обработчики изменения координат
    ['coordX', 'coordY', 'coordWidth', 'coordHeight'].forEach(id => {
        document.getElementById(id).addEventListener('input', updateSealPreview);
    });
    
    // Обработчики изменения настроек
    document.getElementById('sealType').addEventListener('change', updateSealPreview);
    document.getElementById('addSignature').addEventListener('change', updateSealPreview);
}

// Предотвращение стандартного поведения браузера
function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

// Подсветка области загрузки
function highlight(e) {
    document.getElementById('dropZone').classList.add('dragover');
}

// Убираем подсветку
function unhighlight(e) {
    document.getElementById('dropZone').classList.remove('dragover');
}

// Обработка сброса файлов
function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    
    if (files.length > 0) {
        handleFiles(Array.from(files));
    }
}

// Обработка выбора файлов
function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    handleFiles(files);
}

// Обработка файлов
function handleFiles(files) {
    const pdfFiles = files.filter(file => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'));
    
    if (pdfFiles.length === 0) {
        alert('Пожалуйста, выберите PDF файлы');
        return;
    }
    
    // Добавляем файлы к списку
    selectedFiles = selectedFiles.concat(pdfFiles);
    updateFileList();
    updateProcessButton();
}

// Обновление списка файлов
function updateFileList() {
    const fileList = document.getElementById('fileList');
    fileList.innerHTML = '';
    
    selectedFiles.forEach((file, index) => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <i class="fas fa-file-pdf text-danger me-2"></i>
                    <strong>${file.name}</strong>
                    <small class="text-muted ms-2">(${formatFileSize(file.size)})</small>
                </div>
                <button class="btn btn-outline-danger btn-sm" onclick="removeFile(${index})">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
        fileList.appendChild(fileItem);
    });
}

// Удаление файла из списка
function removeFile(index) {
    selectedFiles.splice(index, 1);
    updateFileList();
    updateProcessButton();
}

// Обновление кнопки обработки
function updateProcessButton() {
    const processBtn = document.getElementById('processFiles');
    processBtn.disabled = selectedFiles.length === 0;
}

// Применение стандартных координат
function applyStandardCoordinates() {
    const sealType = document.getElementById('sealType').value;
    const addSignature = document.getElementById('addSignature').checked;
    
    fetch(`/api/coordinates?seal_type=${sealType}&add_signature=${addSignature}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Ошибка получения координат:', data.error);
                return;
            }
            
            const coords = data.coordinates;
            const pageSize = data.page_size;
            
            // Конвертируем из пунктов в миллиметры
            const ptToMm = 0.352778; // 1 пункт = 0.352778 мм
            
            document.getElementById('coordX').value = (coords.x * ptToMm).toFixed(1);
            document.getElementById('coordY').value = (coords.y * ptToMm).toFixed(1);
            document.getElementById('coordWidth').value = (coords.width * ptToMm).toFixed(1);
            document.getElementById('coordHeight').value = (coords.height * ptToMm).toFixed(1);
            
            updateSealPreview();
        })
        .catch(error => {
            console.error('Ошибка при получении координат:', error);
        });
}

// Обновление предварительного просмотра печати
function updateSealPreview() {
    const preview = document.getElementById('sealPreview');
    const x = parseFloat(document.getElementById('coordX').value) || 0;
    const y = parseFloat(document.getElementById('coordY').value) || 0;
    const width = parseFloat(document.getElementById('coordWidth').value) || 17.6;
    const height = parseFloat(document.getElementById('coordHeight').value) || 13.6;
    
    // Конвертируем миллиметры в проценты (A4: 210x297 мм)
    const xPercent = (x / 210) * 100;
    const yPercent = (y / 297) * 100;
    const widthPercent = (width / 210) * 100;
    const heightPercent = (height / 297) * 100;
    
    preview.style.left = `${xPercent}%`;
    preview.style.bottom = `${yPercent}%`;
    preview.style.width = `${widthPercent}%`;
    preview.style.height = `${heightPercent}%`;
}

// Обработка файлов
async function processFiles() {
    if (selectedFiles.length === 0) {
        alert('Пожалуйста, выберите файлы для обработки');
        return;
    }
    
    const processBtn = document.getElementById('processFiles');
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    
    // Настройки обработки
    const sealType = document.getElementById('sealType').value;
    const addSignature = document.getElementById('addSignature').checked;
    
    // Координаты (конвертируем из мм в пункты)
    const mmToPt = 2.83465;
    const coordinates = {
        x: parseFloat(document.getElementById('coordX').value || 0) * mmToPt,
        y: parseFloat(document.getElementById('coordY').value || 0) * mmToPt,
        width: parseFloat(document.getElementById('coordWidth').value || 17.6) * mmToPt,
        height: parseFloat(document.getElementById('coordHeight').value || 13.6) * mmToPt
    };
    
    // Подготавливаем данные для отправки
    const filesData = [];
    
    for (let i = 0; i < selectedFiles.length; i++) {
        const file = selectedFiles[i];
        const base64 = await fileToBase64(file);
        filesData.push({
            filename: file.name,
            pdfData: base64
        });
    }
    
    const requestData = {
        files: filesData,
        seal_type: sealType,
        add_signature: addSignature,
        coordinates: coordinates
    };
    
    // Показываем прогресс
    processBtn.disabled = true;
    progressContainer.classList.remove('d-none');
    progressBar.style.width = '0%';
    progressText.textContent = 'Подготовка файлов...';
    
    try {
        const response = await fetch('/api/batch-process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            processedResults = result.results;
            showResults(result);
        } else {
            throw new Error(result.error || 'Ошибка обработки');
        }
        
    } catch (error) {
        console.error('Ошибка при обработке файлов:', error);
        alert(`Ошибка при обработке файлов: ${error.message}`);
    } finally {
        processBtn.disabled = false;
        progressContainer.classList.add('d-none');
    }
}

// Показ результатов
function showResults(result) {
    const resultsContainer = document.getElementById('resultsContainer');
    const processedCount = document.getElementById('processedCount');
    const totalCount = document.getElementById('totalCount');
    
    processedCount.textContent = result.processed_files;
    totalCount.textContent = result.total_files;
    
    resultsContainer.classList.remove('d-none');
    
    // Обновляем статус файлов в списке
    updateFileStatuses(result.results);
}

// Обновление статусов файлов
function updateFileStatuses(results) {
    const fileItems = document.querySelectorAll('.file-item');
    
    results.forEach((result, index) => {
        if (index < fileItems.length) {
            const fileItem = fileItems[index];
            fileItem.className = 'file-item';
            
            if (result.success) {
                fileItem.classList.add('success');
                fileItem.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <i class="fas fa-check-circle text-success me-2"></i>
                            <strong>${result.filename}</strong>
                            <small class="text-muted ms-2">(Обработан)</small>
                        </div>
                        <button class="btn btn-success btn-sm" onclick="downloadFile('${result.filename}', '${result.pdfData}')">
                            <i class="fas fa-download"></i>
                        </button>
                    </div>
                `;
            } else {
                fileItem.classList.add('error');
                fileItem.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <i class="fas fa-exclamation-circle text-danger me-2"></i>
                            <strong>${result.filename}</strong>
                            <small class="text-danger ms-2">(${result.error})</small>
                        </div>
                    </div>
                `;
            }
        }
    });
}

// Скачивание одного файла
function downloadFile(filename, pdfData) {
    const link = document.createElement('a');
    link.href = pdfData;
    link.download = filename.replace('.pdf', '_с_подписью.pdf');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Скачивание всех файлов
function downloadAllFiles() {
    processedResults.forEach(result => {
        if (result.success) {
            downloadFile(result.filename, result.pdfData);
        }
    });
}

// Конвертация файла в base64
function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve(reader.result);
        reader.onerror = error => reject(error);
    });
}

// Форматирование размера файла
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
} 