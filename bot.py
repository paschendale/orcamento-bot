import logging
import asyncio

from config import Config
from src.bot.discord_bot import DiscordBot

# Configurar logging estruturado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """Função principal"""
    try:
        # Validar configuração
        Config.validate()
        
        # Criar e iniciar bot
        bot = DiscordBot(
            token=Config.DISCORD_TOKEN,
            target_channel_id=Config.TARGET_CHANNEL_ID,
            supported_image_extensions=Config.SUPPORTED_IMAGE_EXTENSIONS,
            state_file=Config.STATE_FILE,
            openai_api_key=Config.OPENAI_API_KEY,
            openai_model=Config.OPENAI_MODEL,
            openai_max_tokens=Config.OPENAI_MAX_TOKENS
        )
        
        await bot.start()
        
    except ValueError as e:
        logger.error(f"Erro de configuração: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"Erro ao iniciar bot: {e}")
        exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot interrompido pelo usuário.")
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        exit(1) 