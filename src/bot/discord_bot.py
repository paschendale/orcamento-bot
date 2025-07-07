"""
Cliente Discord principal
"""
import logging
import discord

from ..utils.state_manager import StateManager
from ..services.openai_service import OpenAIService
from ..services.classification_service import ClassificationService
from ..services.transfer_service import TransferService
from ..services.expense_service import ExpenseService
from .event_handlers import EventHandlers
from .command_handlers import CommandHandlers

logger = logging.getLogger(__name__)


class DiscordBot:
    """Cliente Discord principal"""
    
    def __init__(
        self,
        token: str,
        target_channel_id: int,
        supported_image_extensions: list,
        state_file: str,
        openai_api_key: str,
        openai_model: str,
        openai_max_tokens: int
    ):
        self.token = token
        self.target_channel_id = target_channel_id
        self.supported_image_extensions = supported_image_extensions
        
        # Configurar Discord
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        intents.guilds = True
        
        self.client = discord.Client(intents=intents)
        
        # Inicializar serviços
        self.state_manager = StateManager(state_file)
        self.openai_service = OpenAIService(openai_api_key, openai_model, openai_max_tokens)
        self.classification_service = ClassificationService(self.openai_service)
        self.transfer_service = TransferService(self.openai_service)
        self.expense_service = ExpenseService(self.classification_service)
        self.command_handlers = CommandHandlers(self.openai_service)
        
        # Inicializar handlers de eventos
        self.event_handlers = EventHandlers(
            state_manager=self.state_manager,
            openai_service=self.openai_service,
            classification_service=self.classification_service,
            transfer_service=self.transfer_service,
            expense_service=self.expense_service,
            command_handlers=self.command_handlers,
            target_channel_id=self.target_channel_id,
            supported_image_extensions=self.supported_image_extensions
        )
        
        # Configurar eventos
        self._setup_events()
    
    def _setup_events(self):
        """Configura os eventos do Discord"""
        
        @self.client.event
        async def on_ready():
            """Evento de inicialização do bot"""
            await self.event_handlers.on_ready(self.client)
        
        @self.client.event
        async def on_message(message):
            """Processa mensagens recebidas"""
            # Importar funções do banco de dados aqui para evitar dependência circular
            from database import db_manager, get_categories, insert_transfer, get_transfer_history
            
            await self.event_handlers.on_message(
                message, 
                db_manager, 
                get_categories, 
                insert_transfer, 
                get_transfer_history
            )
    
    async def start(self):
        """Inicia o bot"""
        try:
            # Carregar estado
            self.state_manager.load_state()
            
            # Inicializar banco de dados
            from database import db_manager
            await db_manager.initialize()
            
            logger.info("Iniciando bot Discord...")
            await self.client.start(self.token)
            
        except Exception as e:
            logger.error(f"Erro ao iniciar bot: {e}")
            raise
        finally:
            # Limpar recursos
            try:
                from database import db_manager
                await db_manager.close()
            except:
                pass
    
    async def stop(self):
        """Para o bot"""
        try:
            await self.client.close()
            logger.info("Bot Discord parado.")
        except Exception as e:
            logger.error(f"Erro ao parar bot: {e}")
    
    def get_client(self) -> discord.Client:
        """Retorna o cliente Discord"""
        return self.client 