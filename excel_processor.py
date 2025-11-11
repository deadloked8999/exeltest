"""
Модуль для обработки Excel файлов
"""
import pandas as pd
import logging
from typing import List, Dict, Any, Tuple
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExcelProcessor:
    def __init__(self):
        """Инициализация процессора Excel"""
        self.supported_formats = ['.xlsx', '.xls', '.xlsm', '.csv']
    
    def process_file(self, file_content: bytes, file_name: str) -> Tuple[List[Dict[str, Any]], str]:
        """
        Обработка Excel файла
        
        Returns:
            Tuple[List[Dict], str]: (данные в виде списка словарей, краткая статистика)
        """
        try:
            # Определение типа файла
            if file_name.endswith('.csv'):
                df = pd.read_csv(io.BytesIO(file_content))
            else:
                df = pd.read_excel(io.BytesIO(file_content), engine='openpyxl')
            
            # Очистка данных
            df = self._clean_dataframe(df)
            
            # Преобразование в список словарей
            data = df.to_dict('records')
            
            # Генерация статистики
            stats = self._generate_statistics(df)
            
            logger.info(f"Processed file {file_name}: {len(data)} rows, {len(df.columns)} columns")
            
            return data, stats
        
        except Exception as e:
            logger.error(f"Error processing file {file_name}: {e}")
            raise ValueError(f"Не удалось обработать файл: {str(e)}")
    
    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Очистка DataFrame от пустых строк и нормализация имен колонок"""
        # Удаление пустых строк
        df = df.dropna(how='all')
        
        # Нормализация имен колонок
        df.columns = [str(col).strip().replace(' ', '_').lower() for col in df.columns]
        
        # Замена NaN на None для совместимости с SQL
        df = df.where(pd.notna(df), None)
        
        return df
    
    def _generate_statistics(self, df: pd.DataFrame) -> str:
        """Генерация статистики по данным"""
        stats_lines = [
            f"📊 **Статистика файла:**",
            f"",
            f"🔢 Количество строк: {len(df)}",
            f"📝 Количество колонок: {len(df.columns)}",
            f"",
            f"**Колонки:**"
        ]
        
        for col in df.columns:
            # Подсчет непустых значений
            non_null_count = df[col].notna().sum()
            
            # Определение типа данных
            if pd.api.types.is_numeric_dtype(df[col]):
                dtype = "Числовой"
                # Статистика для числовых данных
                try:
                    min_val = df[col].min()
                    max_val = df[col].max()
                    avg_val = df[col].mean()
                    stats_lines.append(
                        f"  • **{col}** ({dtype}): {non_null_count} значений | "
                        f"Мин: {min_val:.2f}, Макс: {max_val:.2f}, Среднее: {avg_val:.2f}"
                    )
                except:
                    stats_lines.append(f"  • **{col}** ({dtype}): {non_null_count} значений")
            else:
                dtype = "Текстовый"
                unique_count = df[col].nunique()
                stats_lines.append(
                    f"  • **{col}** ({dtype}): {non_null_count} значений | "
                    f"Уникальных: {unique_count}"
                )
        
        return "\n".join(stats_lines)
    
    def get_column_info(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Получение информации о колонках для AI"""
        if not data:
            return {}
        
        columns_info = {}
        sample_data = data[:5]  # Берем первые 5 строк как образец
        
        for col in data[0].keys():
            sample_values = [row[col] for row in sample_data if row.get(col) is not None]
            columns_info[col] = {
                'sample_values': sample_values[:3],  # Первые 3 значения
                'type': type(sample_values[0]).__name__ if sample_values else 'unknown'
            }
        
        return columns_info
    
    def validate_file(self, file_name: str) -> bool:
        """Проверка поддерживаемого формата файла"""
        return any(file_name.lower().endswith(fmt) for fmt in self.supported_formats)
    
    def export_to_excel(self, data: List[Dict[str, Any]], file_name: str = "export.xlsx") -> bytes:
        """Экспорт данных обратно в Excel"""
        try:
            df = pd.DataFrame(data)
            
            # Создание Excel файла в памяти
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Data')
            
            output.seek(0)
            return output.getvalue()
        
        except Exception as e:
            logger.error(f"Error exporting to Excel: {e}")
            raise ValueError(f"Не удалось экспортировать данные: {str(e)}")


