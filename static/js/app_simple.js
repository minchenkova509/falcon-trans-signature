// Упрощенная версия JavaScript для диагностики
console.log('Простой JavaScript загружен');

// Ждем загрузки DOM
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM загружен');
    
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');
    
    console.log('uploadArea:', uploadArea);
    console.log('fileInput:', fileInput);
    
    if (!uploadArea || !fileInput) {
        console.error('Элементы не найдены!');
        return;
    }
    
    // Простой обработчик для file input
    fileInput.addEventListener('change', function(e) {
        console.log('File input change:', e.target.files);
        if (e.target.files.length > 0) {
            const file = e.target.files[0];
            console.log('Выбран файл:', file.name, file.type, file.size);
            uploadFile(file);
        }
    });
    
    // Простой drag and drop
    uploadArea.addEventListener('dragover', function(e) {
        e.preventDefault();
        console.log('Drag over');
    });
    
    uploadArea.addEventListener('drop', function(e) {
        e.preventDefault();
        console.log('Drop event');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            console.log('Файл перетащен:', files[0].name);
            uploadFile(files[0]);
        }
    });
    
    // Клик по области загрузки
    uploadArea.addEventListener('click', function() {
        console.log('Клик по области загрузки');
        fileInput.click();
    });
    
    function uploadFile(file) {
        console.log('Начинаем загрузку файла:', file.name);
        
        // Проверка типа файла
        if (!file.type.includes('pdf') && !file.name.toLowerCase().endsWith('.pdf')) {
            alert('Пожалуйста, выберите PDF файл');
            return;
        }
        
        // Проверка размера
        if (file.size > 16 * 1024 * 1024) {
            alert('Файл слишком большой (максимум 16 МБ)');
            return;
        }
        
        // Создаем FormData
        const formData = new FormData();
        formData.append('file', file);
        
        // Отправляем запрос
        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            console.log('Ответ сервера:', response.status);
            return response.json();
        })
        .then(data => {
            console.log('Данные ответа:', data);
            if (data.success) {
                alert('Успех! Файл обработан: ' + data.filename);
                // Создаем ссылку для скачивания
                const link = document.createElement('a');
                link.href = '/download/' + data.filename;
                link.download = data.filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            } else {
                alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
            }
        })
        .catch(error => {
            console.error('Ошибка загрузки:', error);
            alert('Ошибка соединения с сервером');
        });
    }
    
    console.log('Инициализация завершена');
}); 