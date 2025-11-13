"""
PDF парсер для извлечения данных из чеков с использованием DeepSeek Chat API
"""
import logging
from typing import Dict, Any
import pdfplumber
from deepseek_api import DeepSeekAPI

logger = logging.getLogger(__name__)


class PDFReceiptParser:
    """Парсер PDF чеков для извлечения получателя и суммы платежа с использованием DeepSeek Chat API"""
    
    def __init__(self, deepseek_api_key: str = "sk-7c638331eef3495d9ae00f39efba407d"):
        """
        Args:
            deepseek_api_key: API ключ DeepSeek
        """
        self.deepseek = DeepSeekAPI(api_key=deepseek_api_key)
    
    def parse_receipt(self, pdf_path: str) -> Dict[str, Any]:
        """
        Парсит PDF чек и извлекает информацию о платеже с помощью DeepSeek Chat API
        
        Args:
            pdf_path: путь к PDF файлу
        
        Returns:
            dict с ключами:
            - recipient: получатель платежа
            - amount: сумма (Decimal)
            - success: True если успешно распарсилось
            - error: сообщение об ошибке если не успешно
        """
        try:
            logger.info(f"Extracting text from PDF: {pdf_path}")
            
            # Извлекаем текст из PDF
            full_text = ""
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        full_text += text + "\n"
            
            if not full_text.strip():
                return {
                    'success': False,
                    'error': 'Не удалось извлечь текст из PDF. Возможно, это отсканированное изображение.'
                }
            
            logger.info(f"Extracted text (first 500 chars): {full_text[:500]}")
            
            # Отправляем текст в DeepSeek для парсинга
            result = self.deepseek.parse_receipt_from_text(full_text)
            
            return result
        
        except Exception as e:
            logger.error(f"Error parsing PDF with DeepSeek: {e}", exc_info=True)
            return {
                'success': False,
                'error': f"Ошибка обработки PDF: {str(e)}"
            }


# Глобальный экземпляр парсера
pdf_parser = PDFReceiptParser()
