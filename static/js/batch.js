// Глобальные переменные
let filesQueue = [];

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    console.log('Инициализация пакетной обработки');
    
    initializeReliableUpload();
    initializeButtons();
    updateSealPreview();
});

// Надежная инициализация загрузки файлов
function initializeReliableUpload() {
    const dropzone = document.getElementById('dropzone');
    const input    = document.getElementById('fileInput');
    const pickBtn  = document.getElementById('pickBtn');
    const list     = document.getElementById('fileList');
    const runBtn   = document.getElementById('runBatch');

    function renderList() {
        list.innerHTML = '';
        filesQueue.forEach(f => {
            const li = document.createElement('li');
            li.className = 'file-item';
            li.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <span><i class="fas fa-file-pdf me-2"></i>${f.name} (${Math.round(f.size/1024)} KB)</span>
                    <button class="btn btn-sm btn-outline-danger" onclick="removeFile('${f.name}')">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            `;
            list.appendChild(li);
        });
        runBtn.disabled = filesQueue.length === 0;
    }

    function addFiles(fileList) {
        for (const f of fileList) {
            if (f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')) {
                // Проверяем, не добавлен ли уже этот файл
                if (!filesQueue.find(existing => existing.name === f.name && existing.size === f.size)) {
                    filesQueue.push(f);
                }
            }
        }
        renderList();
    }

    function removeFile(fileName) {
        filesQueue = filesQueue.filter(f => f.name !== fileName);
        renderList();
    }

    // Экспортируем функцию удаления в глобальную область
    window.removeFile = removeFile;

    // DnD: Safari требует preventDefault на dragover/dragenter/dragleave/drop
    ['dragenter','dragover','dragleave','drop'].forEach(ev =>
        dropzone.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); }, {passive:false})
    );
    dropzone.addEventListener('drop', e => addFiles(e.dataTransfer.files));
    pickBtn.addEventListener('click', () => input.click());
    input.addEventListener('change', e => addFiles(e.target.files));
}

// Инициализация кнопок
function initializeButtons() {
    // Кнопка применения стандартных координат
    document.getElementById('applyStandardCoords').addEventListener('click', applyStandardCoordinates);
    
    // Кнопка обработки файлов (новая надежная версия)
    document.getElementById('runBatch').addEventListener('click', processFilesReliable);
    
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

// Надежная обработка файлов
function processFilesReliable() {
    if (!filesQueue.length) return;
    
    const runBtn = document.getElementById('runBatch');
    runBtn.disabled = true;
    runBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>ОБРАБОТКА...';

    // координаты из UI (мм) — подставляем наши значения
    const mmToPt = 2.83465;
    const coordinates = {
        x: parseFloat(document.getElementById('coordX').value || 17.6) * mmToPt,
        y: parseFloat(document.getElementById('coordY').value || 67.6) * mmToPt,  // 17.6 + 50 (SHIFT_MM)
        width: parseFloat(document.getElementById('coordWidth').value || 46.4) * mmToPt,  // 17.6 * 2.64 (SCALE)
        height: parseFloat(document.getElementById('coordHeight').value || 35.9) * mmToPt  // 13.6 * 2.64 (SCALE)
    };

    const fd = new FormData();
    for (const f of filesQueue) fd.append('files', f); // КЛЮЧ ДОЛЖЕН БЫТЬ 'files'
    fd.append('config', JSON.stringify(coordinates));

    // Показываем прогресс
    showProgress('Отправка файлов на сервер...');

    fetch('/batch-stamp', { method: 'POST', body: fd })
        .then(r => {
            if (!r.ok) {
                return r.json().then(errorData => {
                    throw new Error('Ошибка сервера: ' + (errorData.error || r.statusText));
                });
            }
            return r.json(); // ждём JSON
        })
        .then(res => {
            if (!res.success) {
                throw new Error('Ошибка обработки на сервере');
            }
            
            // Скачиваем только успешные файлы
            const okItems = res.items.filter(it => it.ok);
            if (!okItems.length) {
                showError('Ни один файл не обработан');
                return;
            }
            
            // Скачиваем файлы по одному с паузами
            downloadFilesSequentially(okItems);
            
            // Показываем ошибки по неудачным
            const bad = res.items.filter(it => !it.ok);
            if (bad.length) {
                console.warn('Ошибки обработки:', bad);
                showWarning(`Обработано ${okItems.length} из ${res.count} файлов. ${bad.length} файлов с ошибками.`);
            } else {
                showSuccess(`Обработано ${okItems.length} файлов. Все файлы скачаны.`);
            }
        })
        .catch(e => {
            console.error(e);
            showError('Ошибка: ' + e.message);
        })
        .finally(() => {
            runBtn.disabled = false;
            runBtn.innerHTML = '<i class="fas fa-cogs me-2"></i>ОБРАБОТАТЬ ФАЙЛЫ';
        });
}

function showProgress(message) {
    const progressContainer = document.getElementById('progressContainer');
    const progressText = document.getElementById('progressText');
    progressContainer.classList.remove('d-none');
    progressText.textContent = message;
}

function showSuccess(message) {
    const resultsContainer = document.getElementById('resultsContainer');
    const processedCount = document.getElementById('processedCount');
    const totalCount = document.getElementById('totalCount');
    
    processedCount.textContent = filesQueue.length;
    totalCount.textContent = filesQueue.length;
    
    resultsContainer.classList.remove('d-none');
    resultsContainer.querySelector('.alert-success h6').innerHTML = 
        '<i class="fas fa-check-circle me-2"></i>' + message;
}

function showError(message) {
    const resultsContainer = document.getElementById('resultsContainer');
    resultsContainer.classList.remove('d-none');
    resultsContainer.innerHTML = `
        <div class="alert alert-danger">
            <h6><i class="fas fa-exclamation-triangle me-2"></i>Ошибка обработки</h6>
            <p>${message}</p>
        </div>
    `;
}

function showWarning(message) {
    const resultsContainer = document.getElementById('resultsContainer');
    resultsContainer.classList.remove('d-none');
    resultsContainer.innerHTML = `
        <div class="alert alert-warning">
            <h6><i class="fas fa-exclamation-triangle me-2"></i>Обработка завершена с предупреждениями</h6>
            <p>${message}</p>
        </div>
    `;
}

// Скачиваем файлы по одному с паузами
async function downloadFilesSequentially(items) {
    for (let i = 0; i < items.length; i++) {
        const item = items[i];
        const a = document.createElement('a');
        a.href = item.pdfData;
        a.download = item.filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        
        // Пауза между скачиваниями (чтобы браузер не заблокировал)
        if (i < items.length - 1) {
            await new Promise(resolve => setTimeout(resolve, 250));
        }
    }
}

// Удаление файла из списка (обновленная версия)
function removeFile(fileName) {
    filesQueue = filesQueue.filter(f => f.name !== fileName);
    const list = document.getElementById('fileList');
    const runBtn = document.getElementById('runBatch');
    
    // Обновляем список
    list.innerHTML = '';
    filesQueue.forEach(f => {
        const li = document.createElement('li');
        li.className = 'file-item';
        li.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <span><i class="fas fa-file-pdf me-2"></i>${f.name} (${Math.round(f.size/1024)} KB)</span>
                <button class="btn btn-sm btn-outline-danger" onclick="removeFile('${f.name}')">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
        list.appendChild(li);
    });
    
    runBtn.disabled = filesQueue.length === 0;
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
            
            console.log('Применены координаты:', {
                x: (coords.x * ptToMm).toFixed(1),
                y: (coords.y * ptToMm).toFixed(1),
                width: (coords.width * ptToMm).toFixed(1),
                height: (coords.height * ptToMm).toFixed(1)
            });
            
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
        x: parseFloat(document.getElementById('coordX').value || 17.6) * mmToPt,
        y: parseFloat(document.getElementById('coordY').value || 67.6) * mmToPt,  // 17.6 + 50 (SHIFT_MM)
        width: parseFloat(document.getElementById('coordWidth').value || 46.4) * mmToPt,  // 17.6 * 2.64 (SCALE)
        height: parseFloat(document.getElementById('coordHeight').value || 35.9) * mmToPt  // 13.6 * 2.64 (SCALE)
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