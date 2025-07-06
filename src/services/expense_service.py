"""
Serviço de gastos para o bot
"""
import logging
from typing import Dict, Any, List

from ..models.data_models import ClassificationData
from .classification_service import ClassificationService

logger = logging.getLogger(__name__)


class ExpenseService:
    """Serviço para processamento de gastos"""
    
    def __init__(self, classification_service: ClassificationService):
        self.classification_service = classification_service
    
    async def process_text_expense(self, message_content: str, categories: List[str]) -> ClassificationData:
        """Processa gasto informado em texto"""
        try:
            return await self.classification_service.classify_text_expense(message_content, categories)
        except Exception as e:
            logger.error(f"Erro ao processar gasto em texto: {e}")
            raise 