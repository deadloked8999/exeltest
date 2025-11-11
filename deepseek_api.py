"""
Модуль для работы с DeepSeek API
"""
import openai
import logging
import json
from typing import Dict, Any, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DeepSeekAPI:
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        """
        Инициализация DeepSeek API клиента
        
        Args:
            api_key: API ключ DeepSeek
            base_url: Базовый URL API (по умолчанию DeepSeek)
        """
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        self.model = "deepseek-chat"
    
    def generate_sql_query(self, user_query: str, database_schema: str, 
                          column_info: Optional[str] = None) -> Tuple[str, str]:
        """
        Генерация SQL запроса из естественного языка
        
        Args:
            user_query: Запрос пользователя на естественном языке
            database_schema: Схема базы данных
            column_info: Дополнительная информация о колонках
        
        Returns:
            Tuple[str, str]: (SQL запрос, объяснение)
        """
        additional_info = ""
        if column_info:
            additional_info = f"Информация о данных в колонках:\n{column_info}"

        system_prompt = f"""Ты - эксперт по SQL и PostgreSQL. Твоя задача - преобразовать запрос пользователя на естественном языке в корректный SQL запрос.

{database_schema}

{additional_info}

Правила:
1. Генерируй ТОЛЬКО валидный PostgreSQL SQL запрос
2. Используй правильные имена таблиц и колонок из схемы
3. Для поиска по текстовым полям используй ILIKE для нечувствительности к регистру
4. Всегда ограничивай результаты (LIMIT) до разумного количества (100 по умолчанию)
5. Если нужно искать в excel_data, используй JOIN с uploaded_files
6. Возвращай результат в формате JSON:
{{
    "sql": "SQL запрос",
    "explanation": "Краткое объяснение что делает запрос"
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Парсинг JSON ответа
            try:
                # Удаление markdown форматирования если есть
                if content.startswith("```json"):
                    content = content.split("```json")[1].split("```")[0].strip()
                elif content.startswith("```"):
                    content = content.split("```")[1].split("```")[0].strip()
                
                result = json.loads(content)
                sql_query = result.get("sql", "")
                explanation = result.get("explanation", "")
                
                logger.info(f"Generated SQL: {sql_query}")
                return sql_query, explanation
            
            except json.JSONDecodeError:
                # Если не JSON, пытаемся извлечь SQL из текста
                logger.warning("Response is not JSON, trying to extract SQL")
                return self._extract_sql_from_text(content), content
        
        except Exception as e:
            logger.error(f"Error generating SQL query: {e}")
            raise ValueError(f"Ошибка при генерации SQL запроса: {str(e)}")
    
    def _extract_sql_from_text(self, text: str) -> str:
        """Извлечение SQL из текста"""
        # Поиск SQL между ```sql или просто SQL keywords
        if "SELECT" in text.upper() or "INSERT" in text.upper() or "UPDATE" in text.upper():
            lines = text.split('\n')
            sql_lines = []
            in_sql = False
            
            for line in lines:
                if 'SELECT' in line.upper() or 'INSERT' in line.upper() or 'UPDATE' in line.upper():
                    in_sql = True
                if in_sql:
                    sql_lines.append(line)
                if ';' in line:
                    break
            
            return '\n'.join(sql_lines).strip()
        
        return text
    
    def generate_insert_query(self, user_message: str, database_schema: str) -> Tuple[str, Dict[str, Any]]:
        """
        Генерация INSERT запроса из сообщения пользователя
        
        Args:
            user_message: Сообщение пользователя с данными для вставки
            database_schema: Схема базы данных
        
        Returns:
            Tuple[str, Dict]: (SQL INSERT запрос, извлеченные данные)
        """
        system_prompt = f"""Ты - эксперт по извлечению структурированных данных и SQL.
Твоя задача - извлечь данные из сообщения пользователя и создать INSERT запрос в PostgreSQL.

{database_schema}

Правила:
1. Извлеки все данные из сообщения пользователя
2. Определи подходящую таблицу для вставки (обычно user_custom_data)
3. Создай валидный INSERT запрос
4. Возвращай результат в формате JSON:
{{
    "sql": "INSERT запрос с параметрами %s",
    "values": ["значение1", "значение2"],
    "extracted_data": {{"ключ1": "значение1", "ключ2": "значение2"}},
    "explanation": "Что будет записано"
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Удаление markdown форматирования
            if content.startswith("```json"):
                content = content.split("```json")[1].split("```")[0].strip()
            elif content.startswith("```"):
                content = content.split("```")[1].split("```")[0].strip()
            
            result = json.loads(content)
            
            logger.info(f"Generated INSERT query: {result.get('sql', '')}")
            return result.get("sql", ""), result
        
        except Exception as e:
            logger.error(f"Error generating INSERT query: {e}")
            raise ValueError(f"Ошибка при генерации INSERT запроса: {str(e)}")

    def generate_delete_query(self, user_message: str, database_schema: str) -> Tuple[str, Dict[str, Any]]:
        """Генерация DELETE запроса из сообщения пользователя"""
        system_prompt = f"""Ты - эксперт по SQL и PostgreSQL.
Твоя задача - преобразовать запрос пользователя в безопасный DELETE запрос.

{database_schema}

Правила безопасности:
1. Всегда используй оператор DELETE (или UPDATE ... SET archived=true, если удаление невозможно) с корректным WHERE.
2. Если пользователь явно не просит удалить всё, обязательно добавляй точное условие фильтрации.
3. Возвращай список параметров для подстановки (%s) в JSON поле values.
4. Добавляй RETURNING id, чтобы можно было понять количество удалённых записей.
5. Если данных для удаления недостаточно, попроси пользователя уточнить запрос (поле "needs_confirmation": true).
6. Формат ответа (JSON):
{{
    "sql": "DELETE FROM ... WHERE ... RETURNING id",
    "values": ["значение1", 2],
    "explanation": "Что будет удалено",
    "needs_confirmation": false
}}
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.2,
                max_tokens=1000
            )

            content = response.choices[0].message.content.strip()

            if content.startswith("```json"):
                content = content.split("```json")[1].split("```")[0].strip()
            elif content.startswith("```"):
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)

            sql_query = result.get("sql", "")
            if "delete" not in sql_query.lower():
                raise ValueError("Сгенерированный запрос не является DELETE")

            return sql_query, result

        except Exception as e:
            logger.error(f"Error generating DELETE query: {e}")
            raise ValueError(f"Ошибка при генерации DELETE запроса: {str(e)}")
    
    def interpret_query_results(self, user_query: str, results: list, 
                               max_results_to_show: int = 10) -> str:
        """
        Интерпретация результатов запроса для пользователя
        
        Args:
            user_query: Оригинальный запрос пользователя
            results: Результаты SQL запроса
            max_results_to_show: Максимум результатов для показа
        
        Returns:
            str: Форматированный ответ для пользователя
        """
        if not results:
            return "По вашему запросу ничего не найдено 😔"
        
        system_prompt = """Ты - помощник, который форматирует результаты запросов к базе данных для пользователя.
Твоя задача - представить данные в понятном и структурированном виде.

Правила:
1. Используй эмодзи для лучшей читаемости
2. Группируй связанные данные
3. Выделяй ключевую информацию
4. Если результатов много, покажи первые и укажи общее количество
5. Форматируй числа и даты в удобочитаемом виде"""

        results_sample = results[:max_results_to_show]
        total_count = len(results)
        
        user_message = f"""Запрос пользователя: {user_query}

Результаты (показано {len(results_sample)} из {total_count}):
{json.dumps(results_sample, ensure_ascii=False, indent=2, default=str)}

Отформатируй это в понятный текст для пользователя на русском языке."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.5,
                max_tokens=2000
            )
            
            formatted_response = response.choices[0].message.content.strip()
            
            # Добавляем информацию о количестве результатов
            if total_count > max_results_to_show:
                formatted_response += f"\n\n📊 Всего найдено записей: {total_count}"
            
            return formatted_response
        
        except Exception as e:
            logger.error(f"Error interpreting results: {e}")
            # Fallback к простому форматированию
            return self._simple_format_results(results_sample, total_count)
    
    def _simple_format_results(self, results: list, total_count: int) -> str:
        """Простое форматирование результатов без AI"""
        formatted = "📊 **Результаты:**\n\n"
        
        for i, row in enumerate(results, 1):
            formatted += f"**Запись {i}:**\n"
            for key, value in row.items():
                formatted += f"  • {key}: {value}\n"
            formatted += "\n"
        
        if total_count > len(results):
            formatted += f"📝 Показано {len(results)} из {total_count} записей\n"
        
        return formatted


