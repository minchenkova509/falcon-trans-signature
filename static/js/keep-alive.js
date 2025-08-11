// Keep Alive функциональность для Render Free плана
class KeepAlive {
    constructor(url, interval = 300000) { // 5 минут по умолчанию
        this.url = url;
        this.interval = interval;
        this.isRunning = false;
        this.timer = null;
    }

    start() {
        if (this.isRunning) return;
        
        this.isRunning = true;
        this.ping();
        this.timer = setInterval(() => this.ping(), this.interval);
        
        console.log(`Keep Alive запущен для ${this.url} каждые ${this.interval/1000} секунд`);
    }

    stop() {
        if (!this.isRunning) return;
        
        this.isRunning = false;
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
        
        console.log('Keep Alive остановлен');
    }

    async ping() {
        try {
            const response = await fetch(`${this.url}/ping`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                },
                cache: 'no-cache'
            });
            
            if (response.ok) {
                const data = await response.json();
                console.log(`Keep Alive: ${data.status} - ${data.timestamp}`);
            } else {
                console.warn(`Keep Alive: HTTP ${response.status}`);
            }
        } catch (error) {
            console.error('Keep Alive ошибка:', error);
        }
    }

    // Пинг каждые 2 минуты для более частого пробуждения
    startFrequent() {
        this.interval = 120000; // 2 минуты
        this.start();
    }

    // Пинг каждые 10 минут для экономии ресурсов
    startEconomy() {
        this.interval = 600000; // 10 минут
        this.start();
    }
}

// Автоматический запуск Keep Alive
document.addEventListener('DOMContentLoaded', function() {
    // Определяем URL приложения
    const baseUrl = window.location.origin;
    
    // Создаем экземпляр Keep Alive
    const keepAlive = new KeepAlive(baseUrl);
    
    // Запускаем частый пинг для Free плана Render
    keepAlive.startFrequent();
    
    // Сохраняем в глобальной области для доступа из консоли
    window.keepAlive = keepAlive;
    
    // Обработчик видимости страницы для оптимизации
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            // Страница скрыта - переключаемся на экономичный режим
            keepAlive.stop();
            keepAlive.startEconomy();
        } else {
            // Страница видна - возвращаемся к частому пингу
            keepAlive.stop();
            keepAlive.startFrequent();
        }
    });
});

// Функции для ручного управления (доступны в консоли браузера)
window.keepAliveControls = {
    start: () => window.keepAlive?.start(),
    stop: () => window.keepAlive?.stop(),
    startFrequent: () => window.keepAlive?.startFrequent(),
    startEconomy: () => window.keepAlive?.startEconomy(),
    status: () => {
        if (window.keepAlive) {
            console.log('Keep Alive статус:', {
                isRunning: window.keepAlive.isRunning,
                interval: window.keepAlive.interval,
                url: window.keepAlive.url
            });
        } else {
            console.log('Keep Alive не инициализирован');
        }
    }
}; 