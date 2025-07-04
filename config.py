import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Discord
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "0"))
    
    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
    OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1024"))
    
    # Database
    DATABASE_URL = os.getenv("POSTGRES_URL")
    DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "5"))
    DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "20"))
    
    # Bot Settings
    STATE_FILE = os.getenv("STATE_FILE", "state.json")
    SUPPORTED_IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
    DEFAULT_CENTRO_CUSTO = os.getenv("DEFAULT_CENTRO_CUSTO", "")
    
    @classmethod
    def validate(cls):
        missing_vars = []
        if not cls.DISCORD_TOKEN:
            missing_vars.append("DISCORD_TOKEN")
        if not cls.OPENAI_API_KEY:
            missing_vars.append("OPENAI_API_KEY")
        if not cls.DATABASE_URL:
            missing_vars.append("POSTGRES_URL")
        if cls.TARGET_CHANNEL_ID == 0:
            missing_vars.append("TARGET_CHANNEL_ID")
        
        if missing_vars:
            raise ValueError(f"Variáveis de ambiente obrigatórias não encontradas: {', '.join(missing_vars)}")
        
        return True 