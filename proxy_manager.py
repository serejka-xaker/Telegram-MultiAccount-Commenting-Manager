import os
from typing import List, Dict, Optional
import aiohttp
import asyncio
from loguru import logger
from itertools import cycle

class ProxyManager:
    def __init__(self, proxy_file: str = "proxies.txt"):
        self.proxy_file = proxy_file
        self.proxies: List[Dict] = []
        self.proxy_cycle = None
        self.load_proxies()
        self._initialize_cycle()
    
    def _initialize_cycle(self) -> None:
        """Инициализация цикла прокси"""
        if self.proxies:
            self.proxy_cycle = cycle(self.proxies)
            logger.info(f"Инициализирован цикл из {len(self.proxies)} прокси")
        else:
            self.proxy_cycle = None
            logger.warning("Нет доступных прокси для создания цикла")

    def load_proxies(self) -> None:
        """Загрузка прокси из файла"""
        if not os.path.exists(self.proxy_file):
            logger.warning(f"Файл с прокси {self.proxy_file} не найден")
            return
        
        try:
            with open(self.proxy_file, 'r') as f:
                proxy_lines = f.read().splitlines()
            
            self.proxies = []
            for line in proxy_lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                proxy_dict = self._parse_proxy(line)
                if proxy_dict:
                    self.proxies.append(proxy_dict)
            
            self._initialize_cycle()
                
        except Exception as e:
            logger.error(f"Ошибка при загрузке прокси: {str(e)}")
            self.proxies = []
            self.proxy_cycle = None
    
    def _parse_proxy(self, proxy_str: str) -> Optional[Dict]:
        """Парсинг строки прокси в словарь с поддержкой форматов:
        - USER:PASS@IP:PORT
        - IP:PORT"""
        try:
            proxy_dict = {}
            
            # Удаляем пробелы и проверяем базовый формат
            proxy_str = proxy_str.strip()
            if not proxy_str or proxy_str.count(':') < 1:
                logger.error(f"Неверный формат прокси: {proxy_str}")
                return None
            
            if '@' in proxy_str:
                # Формат USER:PASS@IP:PORT
                try:
                    auth, addr = proxy_str.split('@')
                    if ':' not in auth or ':' not in addr:
                        logger.error(f"Неверный формат авторизации прокси: {proxy_str}")
                        return None
                    
                    user, password = auth.split(':')
                    ip, port = addr.split(':')
                    
                    # Проверка корректности данных
                    if not all([user, password, ip, port]):
                        logger.error(f"Пустые поля в данных прокси: {proxy_str}")
                        return None
                    
                    proxy_dict.update({
                        'addr': ip.strip(),
                        'port': int(port.strip()),
                        'username': user.strip(),
                        'password': password.strip(),
                        'proxy_str': proxy_str
                    })
                except ValueError as e:
                    logger.error(f"Ошибка парсинга прокси с авторизацией {proxy_str}: {str(e)}")
                    return None
            else:
                # Формат IP:PORT
                try:
                    ip, port = proxy_str.split(':')
                    
                    # Проверка корректности данных
                    if not all([ip.strip(), port.strip()]):
                        logger.error(f"Пустые поля в данных прокси: {proxy_str}")
                        return None
                    
                    proxy_dict.update({
                        'addr': ip.strip(),
                        'port': int(port.strip()),
                        'proxy_str': proxy_str
                    })
                except ValueError as e:
                    logger.error(f"Ошибка парсинга прокси без авторизации {proxy_str}: {str(e)}")
                    return None
            
            # Базовая валидация IP и порта
            try:
                port = int(proxy_dict['port'])
                if not (0 < port < 65536):
                    logger.error(f"Неверный порт прокси {port} в {proxy_str}")
                    return None
                
                # Проверка формата IP
                ip_parts = proxy_dict['addr'].split('.')
                if len(ip_parts) != 4 or not all(0 <= int(p) <= 255 for p in ip_parts):
                    logger.error(f"Неверный формат IP адреса в {proxy_str}")
                    return None
                
            except (ValueError, IndexError) as e:
                logger.error(f"Ошибка валидации IP/порта для {proxy_str}: {str(e)}")
                return None
            
            return proxy_dict
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге прокси {proxy_str}: {str(e)}")
            return None

    async def _test_proxy_type(self, proxy: Dict, proxy_type: str) -> bool:
        """Тестирование прокси определенного типа"""
        proxy_url = f"{proxy_type}://"
        if proxy.get('username') and proxy.get('password'):
            proxy_url += f"{proxy['username']}:{proxy['password']}@"
        proxy_url += f"{proxy['addr']}:{proxy['port']}"

        try:
            timeout = aiohttp.ClientTimeout(total=5)  # Уменьшаем таймаут до 5 секунд
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get('https://api.telegram.org', proxy=proxy_url) as response:
                    if response.status == 200:
                        logger.info(f"Прокси {proxy['addr']}:{proxy['port']} работает как {proxy_type}")
                        return True
                    return False
        except Exception as e:
            logger.debug(f"Ошибка при проверке {proxy['addr']}:{proxy['port']} как {proxy_type}: {str(e)}")
            return False

    async def determine_proxy_type(self, proxy: Dict) -> Optional[Dict]:
        """Определение рабочего типа прокси"""
        proxy_types = ['socks5', 'http']  # Проверяем только socks5 и http
        
        for proxy_type in proxy_types:
            logger.info(f"Проверка прокси {proxy['addr']}:{proxy['port']} как {proxy_type}")
            if await self._test_proxy_type(proxy, proxy_type):
                proxy['proxy_type'] = proxy_type
                return proxy
            await asyncio.sleep(1)  # Пауза между проверками
        
        logger.warning(f"Прокси {proxy['addr']}:{proxy['port']} не работает ни с одним протоколом")
        return None

    async def check_proxy(self, proxy: Dict) -> Optional[Dict]:
        """Проверка работоспособности прокси и определение его типа"""
        try:
            working_proxy = await self.determine_proxy_type(proxy)
            if working_proxy:
                proxy_info = f"{working_proxy['addr']}:{working_proxy['port']}"
                if 'username' in working_proxy:
                    proxy_info = f"{working_proxy['username']}:***@{proxy_info}"
                logger.info(f"Рабочий прокси: {proxy_info} (тип: {working_proxy['proxy_type']})")
                return working_proxy
            return None
        except Exception as e:
            logger.error(f"Ошибка при проверке прокси {proxy['addr']}:{proxy['port']}: {str(e)}")
            return None

    async def check_all_proxies(self) -> None:
        """Проверка всех прокси"""
        if not self.proxies:
            logger.warning("Список прокси пуст")
            return
        
        logger.info(f"Начинаем проверку {len(self.proxies)} прокси")
        working_proxies = []
        
        for proxy in self.proxies:
            try:
                result = await self.check_proxy(proxy)
                if result:
                    working_proxies.append(result)
                    if len(working_proxies) >= 3:  # Останавливаемся после нахождения 3 рабочих прокси
                        break
            except Exception as e:
                logger.error(f"Ошибка при проверке прокси: {str(e)}")
                continue
            
            await asyncio.sleep(1)  # Пауза между проверками
        
        self.proxies = working_proxies
        self._initialize_cycle()
        
        if self.proxies:
            logger.success(f"Найдено рабочих прокси: {len(self.proxies)}")
            for proxy in self.proxies:
                proxy_info = f"{proxy['addr']}:{proxy['port']}"
                if 'username' in proxy:
                    proxy_info = f"{proxy['username']}:***@{proxy_info}"
                logger.info(f"Готов к использованию: {proxy_info} (тип: {proxy['proxy_type']})")
        else:
            logger.warning("Нет рабочих прокси")

    def format_proxy_for_telethon(self, proxy: Dict) -> Dict:
        """Форматирование прокси для Telethon клиента"""
        telethon_proxy = {
            'proxy_type': proxy['proxy_type'],
            'addr': proxy['addr'],
            'port': proxy['port']
        }
        
        if proxy.get('username') and proxy.get('password'):
            telethon_proxy.update({
                'username': proxy['username'],
                'password': proxy['password']
            })
            
        return telethon_proxy

    def get_next_proxy(self) -> Optional[Dict]:
        """Получение следующего прокси из цикла"""
        if not self.proxy_cycle:
            self._initialize_cycle()
            if not self.proxy_cycle:
                return None
                
        try:
            proxy = next(self.proxy_cycle)
            proxy_info = f"{proxy['addr']}:{proxy['port']}"
            if 'username' in proxy:
                proxy_info = f"{proxy['username']}:***@{proxy_info}"
            logger.info(f"Используется прокси: {proxy_info} (тип: {proxy['proxy_type']})")
            
            # Форматируем прокси для Telethon
            return self.format_proxy_for_telethon(proxy)
        except StopIteration:
            self._initialize_cycle()
            return self.get_next_proxy() if self.proxy_cycle else None 