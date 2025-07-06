"""
Handlers de comandos do Discord
"""
import logging
import datetime

import discord

from ..services.openai_service import OpenAIService

logger = logging.getLogger(__name__)


class CommandHandlers:
    """Handlers de comandos do Discord"""
    
    def __init__(self, openai_service: OpenAIService):
        self.openai_service = openai_service
    
    async def handle_command(self, message: discord.Message, command: str, db_manager, get_categories, get_transfer_history):
        """Processa comandos especiais"""
        try:
            if command == "status":
                await self._handle_status_command(message, db_manager)
            elif command == "usage":
                await self._handle_usage_command(message)
            elif command == "contas":
                await self._handle_contas_command(message, db_manager)
            elif command == "categorias":
                await self._handle_categorias_command(message, get_categories)
            elif command == "help":
                await self._handle_help_command(message)
            elif command == "ping":
                await self._handle_ping_command(message)
            elif command == "transferencias":
                await self._handle_transferencias_command(message, get_transfer_history)
            else:
                await message.channel.send("❌ Comando não reconhecido. Digite `/help` para ver os comandos disponíveis.")
        except Exception as e:
            logger.error(f"Erro ao processar comando {command}: {e}")
            await message.channel.send("❌ Erro ao processar comando. Tente novamente.")
    
    async def _handle_status_command(self, message: discord.Message, db_manager):
        """Comando status - verifica se o bot está online"""
        try:
            # Verificar conexão com banco de dados
            db_ok = False
            db_msg = "Erro ao conectar"
            try:
                await db_manager.initialize()
                db_ok = True
                db_msg = "Conexão com banco de dados bem-sucedida."
            except Exception as e:
                db_msg = f"Erro no banco de dados: {e}"
            
            openai_ok, openai_msg = await self.openai_service.check_connection()
            
            status_embed = discord.Embed(
                title="🤖 Status do Bot",
                color=discord.Color.green() if (db_ok and openai_ok) else discord.Color.red(),
                timestamp=datetime.datetime.now()
            )
            
            status_embed.add_field(
                name="📊 Banco de Dados",
                value=f"{'✅ Online' if db_ok else '❌ Offline'}\n{db_msg}",
                inline=True
            )
            
            status_embed.add_field(
                name="🧠 OpenAI",
                value=f"{'✅ Online' if openai_ok else '❌ Offline'}\n{openai_msg}",
                inline=True
            )
            
            if db_ok and openai_ok:
                status_embed.add_field(
                    name="🎯 Status Geral",
                    value="✅ Bot online e funcionando!",
                    inline=False
                )
            else:
                status_embed.add_field(
                    name="🎯 Status Geral",
                    value="❌ Bot com problemas. Verifique os logs.",
                    inline=False
                )
            
            await message.channel.send(embed=status_embed)
            
        except Exception as e:
            logger.error(f"Erro no comando status: {e}")
            await message.channel.send("❌ Erro ao verificar status.")
    
    async def _handle_usage_command(self, message: discord.Message):
        """Comando usage - mostra uso de tokens da OpenAI"""
        try:
            usage_ok, usage_msg = await self.openai_service.get_usage_info()
            
            usage_embed = discord.Embed(
                title="💰 Uso da OpenAI",
                color=discord.Color.gold(),
                timestamp=datetime.datetime.now()
            )
            
            if usage_ok:
                usage_embed.add_field(
                    name="📈 Informações de Uso",
                    value=usage_msg,
                    inline=False
                )
                
                # Adicionar informações adicionais
                usage_embed.add_field(
                    name="💡 Dicas",
                    value="• Monitore seu uso regularmente\n• Configure alertas de gastos\n• Use modelos mais eficientes quando possível",
                    inline=False
                )
            else:
                usage_embed.add_field(
                    name="❌ Erro",
                    value=usage_msg,
                    inline=False
                )
            
            usage_embed.set_footer(text="💳 Para configurações de billing, acesse: https://platform.openai.com/account/billing")
            
            await message.channel.send(embed=usage_embed)
            
        except Exception as e:
            logger.error(f"Erro no comando usage: {e}")
            await message.channel.send("❌ Erro ao obter informações de uso.")
    
    async def _handle_contas_command(self, message: discord.Message, db_manager):
        """Comando contas - lista todas as contas disponíveis"""
        try:
            accounts = await db_manager.get_available_accounts()
            
            if not accounts:
                await message.channel.send("📋 **Contas disponíveis:**\nNenhuma conta encontrada no banco de dados.")
                return
            
            contas_embed = discord.Embed(
                title="🏦 Contas Disponíveis",
                color=discord.Color.gold(),
                timestamp=datetime.datetime.now()
            )
            
            accounts_text = "\n".join([f"• {account}" for account in accounts])
            contas_embed.add_field(
                name=f"📋 Total: {len(accounts)} conta(s)",
                value=accounts_text,
                inline=False
            )
            
            await message.channel.send(embed=contas_embed)
            
        except Exception as e:
            logger.error(f"Erro no comando contas: {e}")
            await message.channel.send("❌ Erro ao listar contas.")
    
    async def _handle_categorias_command(self, message: discord.Message, get_categories):
        """Comando categorias - lista todas as categorias disponíveis"""
        try:
            categories, error_msg = get_categories()
            
            if error_msg:
                await message.channel.send(f"❌ Erro ao buscar categorias: {error_msg}")
                return
            
            categorias_embed = discord.Embed(
                title="📂 Categorias Disponíveis",
                color=discord.Color.purple(),
                timestamp=datetime.datetime.now()
            )
            
            categories_text = "\n".join([f"• {category}" for category in categories])
            categorias_embed.add_field(
                name=f"📋 Total: {len(categories)} categoria(s)",
                value=categories_text,
                inline=False
            )
            
            await message.channel.send(embed=categorias_embed)
            
        except Exception as e:
            logger.error(f"Erro no comando categorias: {e}")
            await message.channel.send("❌ Erro ao listar categorias.")
    
    async def _handle_help_command(self, message: discord.Message):
        """Comando help - mostra todos os comandos disponíveis"""
        try:
            help_embed = discord.Embed(
                title="❓ Comandos Disponíveis",
                description="Lista de todos os comandos que você pode usar:",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now()
            )
            
            commands = [
                ("/status", "Verifica se o bot está online e funcionando"),
                ("/usage", "Mostra informações de uso da OpenAI"),
                ("/contas", "Lista todas as contas disponíveis no banco"),
                ("/categorias", "Lista todas as categorias disponíveis"),
                ("/transferencias", "Lista transferências recentes"),
                ("/ping", "Testa a latência/resposta do bot"),
                ("/help", "Mostra esta mensagem de ajuda")
            ]
            
            for cmd, desc in commands:
                help_embed.add_field(
                    name=cmd,
                    value=desc,
                    inline=False
                )
            
            help_embed.add_field(
                name="📸 Como usar",
                value="• Envie uma imagem de cupom fiscal para classificação automática\n• Digite gastos em texto (ex: 'gastei R$ 50 no mercado')\n• Digite transferências (ex: 'transferi R$ 5000 da BB VI para Rico Ju' ou 'transf 3000 de nubank para itau para pagar conta')\n• Use os comandos acima para informações do sistema",
                inline=False
            )
            
            await message.channel.send(embed=help_embed)
            
        except Exception as e:
            logger.error(f"Erro no comando help: {e}")
            await message.channel.send("❌ Erro ao mostrar ajuda.")
    
    async def _handle_ping_command(self, message: discord.Message):
        """Comando ping - testa latência/resposta do bot"""
        try:
            start_time = datetime.datetime.now()
            
            # Calcular latência
            end_time = datetime.datetime.now()
            latency = (end_time - start_time).total_seconds() * 1000
            
            ping_embed = discord.Embed(
                title="🏓 Pong!",
                color=discord.Color.green(),
                timestamp=end_time
            )
            
            ping_embed.add_field(
                name="⏱️ Latência",
                value=f"{latency:.1f}ms",
                inline=True
            )
            
            ping_embed.add_field(
                name="🤖 Status",
                value="✅ Bot respondendo!",
                inline=True
            )
            
            await message.channel.send(embed=ping_embed)
            
        except Exception as e:
            logger.error(f"Erro no comando ping: {e}")
            await message.channel.send("❌ Erro no comando ping.")
    
    async def _handle_transferencias_command(self, message: discord.Message, get_transfer_history):
        """Comando transferencias - lista transferências recentes"""
        try:
            # Buscar histórico de transferências
            transfers = await get_transfer_history(limit=10)
            
            if not transfers:
                await message.channel.send("📋 **Transferências recentes:**\nNenhuma transferência encontrada.")
                return
            
            transferencias_embed = discord.Embed(
                title="💸 Transferências Recentes",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now()
            )
            
            # Agrupar transferências por data
            transfers_by_date = {}
            for transfer in transfers:
                data_str = transfer['data'].strftime('%d/%m/%Y')
                if data_str not in transfers_by_date:
                    transfers_by_date[data_str] = []
                transfers_by_date[data_str].append(transfer)
            
            # Mostrar transferências agrupadas por data
            for data_str, day_transfers in transfers_by_date.items():
                transfers_text = ""
                for transfer in day_transfers:
                    valor = transfer['valor']
                    if valor > 0:
                        # Entrada na conta
                        transfers_text += f"📥 **+R$ {valor:.2f}** em {transfer['conta']}\n"
                    else:
                        # Saída da conta
                        transfers_text += f"📤 **R$ {abs(valor):.2f}** de {transfer['conta']}\n"
                    transfers_text += f"   └ {transfer['descricao']}\n\n"
                
                transferencias_embed.add_field(
                    name=f"📅 {data_str}",
                    value=transfers_text.strip(),
                    inline=False
                )
            
            transferencias_embed.set_footer(text=f"📊 Mostrando as {len(transfers)} transferências mais recentes")
            
            await message.channel.send(embed=transferencias_embed)
            
        except Exception as e:
            logger.error(f"Erro no comando transferencias: {e}")
            await message.channel.send("❌ Erro ao listar transferências.") 