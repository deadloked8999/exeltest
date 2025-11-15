"""
Модуль для работы с DeepSeek API
"""
import openai
import logging
import json
import base64
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DeepSeekAPI:
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com/v1"):
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
    
    def parse_misc_expenses_from_notes(self, notes_text: str) -> Dict[str, Any]:
        """
        Парсинг прочих расходов из текста примечаний с использованием DeepSeek Chat API
        
        Args:
            notes_text: Текст из блока примечаний
        
        Returns:
            Dict с результатом: {
                'success': bool,
                'expenses': [{'item': str, 'amount': Decimal}, ...],
                'total': Decimal,
                'error': str (optional)
            }
        """
        try:
            system_prompt = """Ты - эксперт по анализу финансовых документов.
Твоя задача - извлечь из текста прочие расходы, где каждая строка содержит статью расхода и сумму.

Правила:
1. Каждая строка содержит название статьи расхода и сумму
2. Формат может быть разным: "депозит т.Анар 8.000" или "9.250-закуп бар,такси К2"
3. Извлеки ВСЕ расходы из текста
4. Верни результат в формате JSON (массив объектов):
[
    {"item": "депозит т.Анар", "amount": "8000"},
    {"item": "депозит т.Руслан А", "amount": "8000"},
    {"item": "закуп бар,такси К2", "amount": "9250"}
]

ВАЖНО:
- Сумма должна быть числом БЕЗ пробелов и точек внутри (8000, а не 8.000)
- Если сумма с точкой как разделитель тысяч (8.000) - преобразуй в 8000
- Возвращай ТОЛЬКО JSON массив, без markdown и дополнительного текста"""

            user_prompt = f"""Извлеки все прочие расходы из этого текста:

{notes_text}

Верни результат в формате JSON массива."""
            
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            logger.info(f"DeepSeek misc expenses response: {content}")
            
            # Парсинг JSON ответа
            if content.startswith("```json"):
                content = content.split("```json")[1].split("```")[0].strip()
            elif content.startswith("```"):
                content = content.split("```")[1].split("```")[0].strip()
            
            expenses_list = json.loads(content)
            
            if not isinstance(expenses_list, list):
                return {
                    'success': False,
                    'error': 'Неверный формат ответа от DeepSeek'
                }
            
            # Преобразуем в нужный формат и считаем итого
            expenses = []
            total = Decimal('0')
            
            for exp in expenses_list:
                item = exp.get('item', '').strip()
                amount_str = exp.get('amount', '').strip()
                
                if not item or not amount_str:
                    continue
                
                # Очищаем сумму от пробелов, точек (как разделителей тысяч)
                amount_str = amount_str.replace(' ', '').replace('.', '').replace(',', '.')
                
                try:
                    amount = Decimal(amount_str)
                    expenses.append({
                        'item': item,
                        'amount': amount
                    })
                    total += amount
                except:
                    logger.warning(f"Could not parse amount: {amount_str}")
                    continue
            
            if not expenses:
                return {
                    'success': False,
                    'error': 'Не удалось извлечь расходы из текста'
                }
            
            logger.info(f"Successfully parsed {len(expenses)} misc expenses, total: {total}")
            
            return {
                'success': True,
                'expenses': expenses,
                'total': total
            }
        
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return {
                'success': False,
                'error': 'Ошибка парсинга ответа от DeepSeek'
            }
        except Exception as e:
            logger.error(f"Error in parse_misc_expenses_from_notes: {e}", exc_info=True)
            return {
                'success': False,
                'error': f'Ошибка обработки текста: {str(e)}'
            }
    
    def parse_receipt_from_text(self, text: str) -> Dict[str, Any]:
        """
        Парсинг чека/платежного поручения из текста с использованием DeepSeek Chat API
        
        Args:
            text: Текст из PDF документа
        
        Returns:
            Dict с результатом: {'success': bool, 'recipient': str, 'amount': Decimal, 'error': str}
        """
        try:
            system_prompt = """Ты - эксперт по анализу финансовых документов. 
Твоя задача - извлечь из текста чека или платежного поручения:
1. Получателя платежа (название организации/ИП)
2. Сумму платежа

Правила:
- Ищи получателя в полях: "Получатель", "Наименование получателя", "Контрагент", или после "ИНН"
- Сумма обычно указана в полях: "Сумма", "Сумма прописью", "Итого", "К оплате", "Списано"
- Если есть несколько сумм, выбирай ту, которая указана как основная сумма платежа
- Возвращай ТОЛЬКО JSON без дополнительного текста и markdown:
{
    "recipient": "Название организации",
    "amount": "1234.56"
}

Если не удалось найти данные, верни:
{
    "error": "Описание проблемы"
}"""

            user_prompt = f"""Извлеки из этого текста платежного документа получателя и сумму платежа:

{text}

Верни результат в формате JSON."""
            
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            content = response.choices[0].message.content.strip()
            logger.info(f"DeepSeek response: {content}")
            
            # Парсинг JSON ответа
            if content.startswith("```json"):
                content = content.split("```json")[1].split("```")[0].strip()
            elif content.startswith("```"):
                content = content.split("```")[1].split("```")[0].strip()
            
            result = json.loads(content)
            
            if 'error' in result:
                logger.warning(f"DeepSeek error: {result['error']}")
                return {
                    'success': False,
                    'error': result['error']
                }
            
            recipient = result.get('recipient', '').strip()
            amount_str = result.get('amount', '').strip()
            
            if not recipient or not amount_str:
                return {
                    'success': False,
                    'error': 'Не удалось извлечь получателя или сумму из документа'
                }
            
            # Конвертируем сумму в Decimal
            amount_str = amount_str.replace(',', '.').replace(' ', '')
            amount = Decimal(amount_str)
            
            logger.info(f"Successfully parsed: recipient={recipient}, amount={amount}")
            
            return {
                'success': True,
                'recipient': recipient,
                'amount': amount
            }
        
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}, content: {content}")
            return {
                'success': False,
                'error': 'Ошибка парсинга ответа от DeepSeek'
            }
        except Exception as e:
            logger.error(f"Error in parse_receipt_from_text: {e}", exc_info=True)
            return {
                'success': False,
                'error': f'Ошибка обработки текста: {str(e)}'
            }


