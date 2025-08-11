// Глобальные переменные
let currentFile = null;
let downloadFilename = null;

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    initializeDragAndDrop();
    initializeFileInput();
    initializeDownloadButton();
});

// Инициализация drag and drop
function initializeDragAndDrop() {
    const uploadArea = document.getElementById('uploadArea');
    
    // Предотвращаем стандартное поведение браузера
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });
    
    // Подсветка области при перетаскивании
    ['dragenter', 'dragover'].forEach(eventName => {
        uploadArea.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, unhighlight, false);
    });
    
    // Обработка сброса файла
    uploadArea.addEventListener('drop', handleDrop, false);
    
    // Клик по области загрузки
    uploadArea.addEventListener('click', () => {
        document.getElementById('fileInput').click();
    });
}

// Инициализация input файла
function initializeFileInput() {
    const fileInput = document.getElementById('fileInput');
    fileInput.addEventListener('change', handleFileSelect);
}

// Инициализация кнопки скачивания
function initializeDownloadButton() {
    const downloadBtn = document.getElementById('downloadBtn');
    downloadBtn.addEventListener('click', downloadFile);
}

// Предотвращение стандартного поведения браузера
function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

// Подсветка области загрузки
function highlight(e) {
    document.getElementById('uploadArea').classList.add('dragover');
}

// Убираем подсветку
function unhighlight(e) {
    document.getElementById('uploadArea').classList.remove('dragover');
}

// Обработка сброса файла
function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    
    if (files.length > 0) {
        handleFile(files[0]);
    }
}

// Обработка выбора файла
function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        handleFile(files[0]);
    }
}

// Обработка файла
function handleFile(file) {
    // Проверяем тип файла
    if (!file.type.includes('pdf')) {
        showError('Пожалуйста, выберите PDF файл');
        return;
    }
    
    // Проверяем размер файла (16MB)
    if (file.size > 16 * 1024 * 1024) {
        showError('Размер файла не должен превышать 16 МБ');
        return;
    }
    
    currentFile = file;
    uploadFile(file);
}

// Загрузка файла на сервер
async function uploadFile(file) {
    showProgress();
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        // Симуляция прогресса
        simulateProgress();
        
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            downloadFilename = result.filename;
            showSuccess(result.message);
        } else {
            showError(result.error || 'Произошла ошибка при обработке файла');
        }
        
    } catch (error) {
        console.error('Ошибка загрузки:', error);
        showError('Ошибка соединения с сервером');
    }
}

// Симуляция прогресса
function simulateProgress() {
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    let progress = 0;
    
    const interval = setInterval(() => {
        progress += Math.random() * 15;
        if (progress > 90) {
            progress = 90;
            clearInterval(interval);
        }
        
        progressBar.style.width = progress + '%';
        
        if (progress < 30) {
            progressText.textContent = 'Загрузка файла...';
        } else if (progress < 60) {
            progressText.textContent = 'Обработка документа...';
        } else {
            progressText.textContent = 'Добавление подписи...';
        }
    }, 200);
}

// Показать прогресс
function showProgress() {
    hideAllContainers();
    document.getElementById('progressContainer').classList.remove('d-none');
    document.getElementById('progressContainer').classList.add('fade-in');
}

// Показать успех
function showSuccess(message) {
    hideAllContainers();
    const resultContainer = document.getElementById('resultContainer');
    resultContainer.classList.remove('d-none');
    resultContainer.classList.add('fade-in');
    
    // Обновляем текст сообщения если нужно
    const messageElement = resultContainer.querySelector('h5');
    if (messageElement && message) {
        messageElement.textContent = message;
    }
}

// Показать ошибку
function showError(message) {
    hideAllContainers();
    const errorContainer = document.getElementById('errorContainer');
    const errorText = document.getElementById('errorText');
    
    errorContainer.classList.remove('d-none');
    errorContainer.classList.add('fade-in');
    errorText.textContent = message;
}

// Скрыть все контейнеры
function hideAllContainers() {
    const containers = [
        'progressContainer',
        'resultContainer', 
        'errorContainer'
    ];
    
    containers.forEach(id => {
        const container = document.getElementById(id);
        container.classList.add('d-none');
        container.classList.remove('fade-in');
    });
}

// Скачать файл
function downloadFile() {
    if (!downloadFilename) {
        showError('Файл для скачивания не найден');
        return;
    }
    
    // Создаем ссылку для скачивания
    const link = document.createElement('a');
    link.href = `/download/${downloadFilename}`;
    link.download = downloadFilename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    // Показываем уведомление
    showNotification('Файл начал скачиваться!', 'success');
}

// Сбросить форму
function resetForm() {
    hideAllContainers();
    currentFile = null;
    downloadFilename = null;
    document.getElementById('fileInput').value = '';
    
    // Сбрасываем прогресс бар
    const progressBar = document.getElementById('progressBar');
    progressBar.style.width = '0%';
}

// Показать уведомление
function showNotification(message, type = 'info') {
    // Создаем элемент уведомления
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    // Автоматически удаляем через 5 секунд
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

// Дополнительные утилиты
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Обработка ошибок сети
window.addEventListener('online', function() {
    showNotification('Соединение восстановлено', 'success');
});

window.addEventListener('offline', function() {
    showNotification('Потеряно соединение с интернетом', 'warning');
});

// Предотвращение закрытия страницы во время загрузки
window.addEventListener('beforeunload', function(e) {
    if (document.getElementById('progressContainer').classList.contains('d-none') === false) {
        e.preventDefault();
        e.returnValue = 'Файл загружается. Вы уверены, что хотите покинуть страницу?';
        return e.returnValue;
    }
}); 