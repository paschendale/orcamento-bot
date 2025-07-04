import asyncpg
import logging
from typing import List, Tuple, Optional
from config import Config

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.pool = None
    
    async def initialize(self):
        """Inicializa o pool de conexões"""
        try:
            self.pool = await asyncpg.create_pool(
                Config.DATABASE_URL,
                min_size=Config.DB_POOL_MIN_SIZE,
                max_size=Config.DB_POOL_MAX_SIZE
            )
            logger.info("Pool de conexões do banco de dados inicializado")
        except Exception as e:
            logger.error(f"Erro ao inicializar pool de conexões: {e}")
            raise
    
    async def close(self):
        """Fecha o pool de conexões"""
        if self.pool:
            await self.pool.close()
            logger.info("Pool de conexões do banco de dados fechado")
    
    async def check_connection(self) -> Tuple[bool, str]:
        """Verifica a conexão com o banco de dados"""
        try:
            if not self.pool:
                return False, "Pool de conexões não inicializado"
            
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True, "Conexão com o banco de dados bem-sucedida."
        except Exception as e:
            logger.error(f"Erro ao verificar conexão com banco: {e}")
            return False, f"Erro ao conectar com o banco de dados: {e}"
    
    async def get_categories(self) -> Tuple[List[str], Optional[str]]:
        """Busca categorias disponíveis no banco"""
        try:
            if not self.pool:
                return [], "Pool de conexões não inicializado"
            
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("SELECT DISTINCT categoria FROM public.orcamento WHERE categoria IS NOT NULL")
                
                if not rows:
                    return [], "A tabela 'orcamento' não possui categorias. Por favor, popule a tabela."
                
                categories = [row['categoria'] for row in rows]
                logger.info(f"Carregadas {len(categories)} categorias do banco")
                return categories, None
                
        except Exception as e:
            logger.error(f"Erro ao buscar categorias: {e}")
            return [], f"Erro ao buscar categorias: {e}"
    
    async def validate_category(self, category: str) -> bool:
        """Valida se uma categoria existe no banco"""
        try:
            if not self.pool:
                return False
            
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(
                    "SELECT COUNT(*) FROM public.orcamento WHERE categoria = $1",
                    category
                )
                return result > 0
        except Exception as e:
            logger.error(f"Erro ao validar categoria {category}: {e}")
            return False
    
    async def insert_transaction(self, data, descricao: str, conta: str, categoria: str, 
                               centro_custo: str, valor: float) -> bool:
        """Insere uma transação no banco de dados"""
        try:
            if not self.pool:
                logger.error("Pool de conexões não inicializado")
                return False
            
            # Validações
            if not descricao or not conta or not categoria:
                logger.error("Dados obrigatórios não fornecidos")
                return False
            
            if valor <= 0:
                logger.error(f"Valor inválido: {valor}")
                return False
            
            # Validar se categoria existe
            if not await self.validate_category(categoria):
                logger.error(f"Categoria '{categoria}' não existe no banco")
                return False
            
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO public.transacoes (data, descricao, conta, categoria, centro_custo, valor)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, data, descricao, conta, categoria, centro_custo, valor)
                
            logger.info(f"Transação inserida: {descricao} - R$ {valor:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao inserir transação: {e}")
            return False
    
    async def get_available_accounts(self) -> List[str]:
        """Busca contas disponíveis no banco"""
        try:
            if not self.pool:
                return []
            
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT DISTINCT conta 
                    FROM public.transacoes 
                    WHERE conta IS NOT NULL AND conta != ''
                    ORDER BY conta
                """)
                
                accounts = [row['conta'] for row in rows]
                logger.info(f"Contas disponíveis: {accounts}")
                return accounts
                
        except Exception as e:
            logger.error(f"Erro ao buscar contas: {e}")
            return []
    
    async def validate_account(self, account: str) -> bool:
        """Valida se uma conta existe no banco"""
        try:
            if not self.pool:
                return False
            
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(
                    "SELECT COUNT(*) FROM public.transacoes WHERE conta = $1",
                    account
                )
                return result > 0
        except Exception as e:
            logger.error(f"Erro ao validar conta {account}: {e}")
            return False
    
    async def insert_grouped_transactions(self, data, transactions_by_category: dict, conta: str, estabelecimento: str = None) -> Tuple[int, int]:
        """Insere transações agrupadas por categoria"""
        try:
            if not self.pool:
                return 0, 0
            
            saved_count = 0
            error_count = 0
            
            for categoria, items in transactions_by_category.items():
                try:
                    # Criar descrição agrupada com estabelecimento
                    produtos = [item['descricao'] for item in items]
                    if estabelecimento and estabelecimento != "Estabelecimento não identificado":
                        descricao = f"[BOT] {estabelecimento} - {', '.join(produtos)}"
                    else:
                        descricao = f"[BOT] {', '.join(produtos)}"
                    
                    # Calcular valor total (negativo para despesa)
                    valor_total = -sum(float(item['valor']) for item in items)
                    
                    # Validar se categoria existe
                    if not await self.validate_category(categoria):
                        logger.error(f"Categoria '{categoria}' não existe no banco")
                        error_count += 1
                        continue
                    
                    async with self.pool.acquire() as conn:
                        await conn.execute("""
                            INSERT INTO public.transacoes (data, descricao, conta, categoria, centro_custo, valor)
                            VALUES ($1, $2, $3, $4, $5, $6)
                        """, data, descricao, conta, categoria, "custeio", valor_total)
                    
                    saved_count += 1
                    logger.info(f"Transação agrupada inserida: {categoria} - R$ {valor_total:.2f}")
                    
                except Exception as e:
                    error_count += 1
                    logger.error(f"Erro ao inserir transação agrupada para {categoria}: {e}")
            
            return saved_count, error_count
            
        except Exception as e:
            logger.error(f"Erro ao inserir transações agrupadas: {e}")
            return 0, 0

# Instância global do gerenciador de banco
db_manager = DatabaseManager()

# Funções de compatibilidade para manter a API existente
async def check_database_connection():
    return await db_manager.check_connection()

async def get_categories():
    return await db_manager.get_categories()

async def insert_transaction(data, descricao, conta, categoria, centro_custo, valor):
    success = await db_manager.insert_transaction(data, descricao, conta, categoria, centro_custo, valor)
    if not success:
        raise Exception("Falha ao inserir transação")