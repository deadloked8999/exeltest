"""Простой парсер текстовых команд для бота"""
import re
from typing import Dict


class SimpleQueryParser:
    """Находит базовые действия в текстовом запросе"""

    COLUMN_VALUE_PATTERN = re.compile(r'(?P<column>[A-Za-zА-Яа-яЁё0-9_\s]+)\s*=\s*(?P<value>.+)')

    def parse(self, text: str) -> Dict[str, str]:
        if not text:
            return {"action": "unknown"}

        lowered = text.lower()

        if 'сколько' in lowered and 'запис' in lowered:
            return {"action": "count_records"}

        if ('последн' in lowered and 'запис' in lowered) or ('покажи' in lowered and 'последн' in lowered):
            return {"action": "latest_records"}

        if 'покажи' in lowered and 'файл' in lowered:
            return {"action": "list_files"}

        match = self.COLUMN_VALUE_PATTERN.search(text)
        if match:
            column = match.group('column').strip()
            value = match.group('value').strip()
            return {
                "action": "search_by_column",
                "column": column,
                "value": value
            }

        if 'найди' in lowered or 'поиск' in lowered:
            return {"action": "request_search_input"}

        return {"action": "unknown"}
