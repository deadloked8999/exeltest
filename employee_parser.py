"""Парсер списка сотрудников из текста"""
from typing import List, Dict, Optional, Tuple
import re


class EmployeeParser:
    """Парсер текстовых списков сотрудников"""

    # Паттерн для кода: буквы + цифры без пробелов
    CODE_PATTERN = re.compile(r'\b([A-Za-zА-Яа-яЁё]+\d+)\b')

    @staticmethod
    def normalize_name(name: str) -> str:
        """Приведение ФИО к виду «Фамилия Имя Отчество»"""
        if not name:
            return ''

        # Удаляем лишние символы и пробелы
        name = re.sub(r'[^\w\s]', ' ', name)
        parts = re.split(r'\s+', name.strip())
        normalized_parts = []

        for part in parts:
            if not part:
                continue
            normalized_parts.append(part.capitalize())

        return ' '.join(normalized_parts)

    def extract_code_and_name(self, text: str) -> Optional[Tuple[str, str]]:
        """
        Извлекает код и ФИО из одной строки или блока текста.
        Возвращает (code, full_name) или None
        """
        if not text or not text.strip():
            return None

        # Ищем все возможные коды в тексте
        codes = self.CODE_PATTERN.findall(text)
        
        if not codes:
            return None

        # Берём первый найденный код
        code = codes[0].upper()

        # Удаляем код из текста и получаем ФИО
        name_text = self.CODE_PATTERN.sub('', text)
        name_text = self.normalize_name(name_text)

        if not name_text:
            return None

        return (code, name_text)

    def parse(self, text: str) -> List[Dict[str, str]]:
        """
        Парсинг текста в список сотрудников.
        Поддерживает:
        - ФИО и код на одной строке (в любом порядке)
        - ФИО и код на разных строках
        - Любые разделители (дефис, тире, запятая, пробел)
        """
        if not text:
            return []

        employees: List[Dict[str, str]] = []
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        i = 0
        while i < len(lines):
            current_line = lines[i]

            # Пробуем извлечь код и имя из текущей строки
            result = self.extract_code_and_name(current_line)

            if result:
                code, name = result
                employees.append({
                    'employee_code': code,
                    'full_name': name
                })
                i += 1
            else:
                # Если не нашли код в текущей строке, пробуем объединить с следующей
                if i + 1 < len(lines):
                    combined = f"{current_line} {lines[i + 1]}"
                    result = self.extract_code_and_name(combined)
                    
                    if result:
                        code, name = result
                        employees.append({
                            'employee_code': code,
                            'full_name': name
                        })
                        i += 2  # Пропускаем следующую строку
                    else:
                        i += 1
                else:
                    i += 1

        return employees
