"""
Gerenciador de estado para o bot
"""
import json
import logging
from typing import Dict, Optional
from pathlib import Path

from ..models.data_models import UserContext

logger = logging.getLogger(__name__)


class StateManager:
    """Gerencia o estado das conversas do bot"""
    
    def __init__(self, state_file: str):
        self.state_file = Path(state_file)
        self.user_contexts: Dict[str, UserContext] = {}
    
    def save_state(self) -> None:
        """Salva o estado das conversas"""
        try:
            # Verificar se o diretório pai existe
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Verificar se o arquivo é um diretório
            if self.state_file.exists() and self.state_file.is_dir():
                logger.error(f"Não é possível salvar estado: '{self.state_file}' é um diretório")
                return
            
            # Converter UserContext para dict
            state_data = {}
            for thread_id, context in self.user_contexts.items():
                state_data[thread_id] = context.to_dict()
            
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"Estado salvo com {len(self.user_contexts)} conversas")
        except Exception as e:
            logger.error(f"Erro ao salvar estado: {e}")
    
    def load_state(self) -> None:
        """Carrega o estado das conversas"""
        try:
            if not self.state_file.exists():
                logger.info("Arquivo de estado não encontrado, iniciando com estado vazio")
                self.user_contexts = {}
                return
            
            # Verificar se é um arquivo, não um diretório
            if self.state_file.is_dir():
                logger.error(f"'{self.state_file}' é um diretório, não um arquivo. Criando novo arquivo de estado.")
                self.user_contexts = {}
                return
            
            with open(self.state_file, "r", encoding="utf-8") as f:
                state_data = json.load(f)
            
            # Converter dict para UserContext
            self.user_contexts = {}
            for thread_id, context_data in state_data.items():
                try:
                    self.user_contexts[thread_id] = UserContext.from_dict(context_data)
                except Exception as e:
                    logger.warning(f"Erro ao carregar contexto para thread {thread_id}: {e}")
                    continue
            
            logger.info(f"Estado carregado com {len(self.user_contexts)} conversas")
        except Exception as e:
            logger.error(f"Erro ao carregar estado: {e}")
            self.user_contexts = {}
    
    def get_context(self, thread_id: str) -> Optional[UserContext]:
        """Obtém o contexto de uma thread"""
        return self.user_contexts.get(thread_id)
    
    def set_context(self, thread_id: str, context: UserContext) -> None:
        """Define o contexto de uma thread"""
        self.user_contexts[thread_id] = context
        self.save_state()
    
    def update_context(self, thread_id: str, **kwargs) -> None:
        """Atualiza campos específicos do contexto"""
        if thread_id in self.user_contexts:
            context = self.user_contexts[thread_id]
            for key, value in kwargs.items():
                if hasattr(context, key):
                    setattr(context, key, value)
            self.save_state()
    
    def remove_context(self, thread_id: str) -> None:
        """Remove o contexto de uma thread"""
        if thread_id in self.user_contexts:
            del self.user_contexts[thread_id]
            self.save_state()
    
    def has_context(self, thread_id: str) -> bool:
        """Verifica se existe contexto para uma thread"""
        return thread_id in self.user_contexts
    
    def get_all_contexts(self) -> Dict[str, UserContext]:
        """Obtém todos os contextos"""
        return self.user_contexts.copy()
    
    def clear_all(self) -> None:
        """Limpa todos os contextos"""
        self.user_contexts.clear()
        self.save_state() 