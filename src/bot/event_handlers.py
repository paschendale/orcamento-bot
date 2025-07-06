"""
Handlers de eventos do Discord
"""
import logging
from typing import Optional

import discord

from ..models.data_models import UserContext, MessageIntent
from ..utils.state_manager import StateManager
from ..utils.validators import validate_image_extension
from ..services.openai_service import OpenAIService
from ..services.classification_service import ClassificationService
from ..services.transfer_service import TransferService
from ..services.expense_service import ExpenseService
from ..utils.formatters import format_classification_summary, format_transfer_summary, format_help_message, format_transfer_help_message
from .command_handlers import CommandHandlers

logger = logging.getLogger(__name__)


class EventHandlers:
    """Handlers de eventos do Discord"""
    
    def __init__(
        self,
        state_manager: StateManager,
        openai_service: OpenAIService,
        classification_service: ClassificationService,
        transfer_service: TransferService,
        expense_service: ExpenseService,
        command_handlers: CommandHandlers,
        target_channel_id: int,
        supported_image_extensions: list
    ):
        self.state_manager = state_manager
        self.openai_service = openai_service
        self.classification_service = classification_service
        self.transfer_service = transfer_service
        self.expense_service = expense_service
        self.command_handlers = command_handlers
        self.target_channel_id = target_channel_id
        self.supported_image_extensions = supported_image_extensions
    
    async def on_ready(self, client: discord.Client):
        """Evento de inicialização do bot"""
        logger.info(f'Bot conectado como {client.user}')
        
        try:
            # Verificar conexões silenciosamente
            openai_ok, openai_msg = await self.openai_service.check_connection()
            
            if not openai_ok:
                logger.error(f'Erro na OpenAI: {openai_msg}')
            
            logger.info('Bot inicializado com sucesso.')
            
        except Exception as e:
            logger.error(f'Erro na inicialização: {e}')
    
    async def on_message(self, message: discord.Message, db_manager, get_categories, insert_transfer, get_transfer_history):
        """Processa mensagens recebidas"""
        if message.author == message.guild.me:
            return

        try:
            # Processar comandos especiais no canal principal
            if message.channel.id == self.target_channel_id and message.content.startswith('/'):
                command = message.content[1:].lower().strip()
                await self.command_handlers.handle_command(message, command, db_manager, get_categories, get_transfer_history)
                return

            # Processar imagens no canal principal
            if message.channel.id == self.target_channel_id and message.attachments:
                for attachment in message.attachments:
                    if validate_image_extension(attachment.filename, self.supported_image_extensions):
                        await self._handle_image_attachment(message, attachment, get_categories)
                        return

            # Processar mensagens de texto no canal principal
            elif message.channel.id == self.target_channel_id and not message.attachments:
                await self._handle_text_message(message, db_manager, get_categories)

            # Processar respostas em threads
            elif self.state_manager.has_context(str(message.channel.id)):
                await self._handle_thread_response(message, db_manager, get_categories, insert_transfer)

        except Exception as e:
            logger.error(f"Erro ao processar mensagem: {e}")
            try:
                await message.channel.send("Desculpe, ocorreu um erro ao processar sua mensagem. Tente novamente.")
            except:
                pass
    
    async def _handle_image_attachment(self, message: discord.Message, attachment: discord.Attachment, get_categories):
        """Processa anexo de imagem"""
        try:
            thread = await message.create_thread(name=f"Classificação de {attachment.filename}")
            
            # Criar contexto para a thread
            context = UserContext(
                user_id=str(message.author.id),
                thread_id=str(thread.id),
                attachment_url=attachment.url
            )
            self.state_manager.set_context(str(thread.id), context)
            
            await thread.send("Olá! Recebi a sua imagem e vou analisá-la. Em breve, enviarei a classificação dos produtos.")
            await self._process_image(thread, attachment.url, get_categories)
            
        except Exception as e:
            logger.error(f"Erro ao processar anexo de imagem: {e}")
            await message.channel.send("Erro ao processar imagem. Tente novamente.")
    
    async def _handle_text_message(self, message: discord.Message, db_manager, get_categories):
        """Processa mensagem de texto no canal principal"""
        try:
            # Detectar intenção da mensagem com OpenAI
            intent_result = await self.openai_service.detect_message_intent(message.content)
            
            if intent_result.intent == "transfer":
                await self._handle_transfer_intent(message, db_manager)
                
            elif intent_result.intent == "expense":
                await self._handle_expense_intent(message, get_categories)
                
        except Exception as e:
            logger.error(f"Erro ao processar mensagem de texto: {e}")
            await message.channel.send("Erro ao processar mensagem. Tente novamente.")
    
    async def _handle_transfer_intent(self, message: discord.Message, db_manager):
        """Processa intenção de transferência"""
        try:
            # Buscar contas disponíveis
            available_accounts = await db_manager.get_available_accounts()
            if not available_accounts:
                await message.channel.send("Erro: Não foi possível obter a lista de contas disponíveis.")
                return

            # Processar transferência
            transfer_data = await self.transfer_service.process_transfer(message.content, available_accounts)
            
            # Criar thread para a transferência
            thread_name = f"Transferência de R$ {transfer_data.valor:.2f}" if transfer_data.valor > 0 else "Transferência"
            thread = await message.create_thread(name=thread_name)
            
            # Criar contexto para a thread
            context = UserContext(
                user_id=str(message.author.id),
                thread_id=str(thread.id),
                message_content=message.content,
                transfer_data=transfer_data
            )
            self.state_manager.set_context(str(thread.id), context)
            
            await thread.send("Olá! Identifiquei uma transferência na sua mensagem. Vou analisá-la e processar.")
            
            # Mostrar resumo da transferência
            summary = format_transfer_summary(transfer_data)
            await thread.send(summary)
            
        except Exception as e:
            logger.error(f"Erro ao processar transferência: {e}")
            await message.channel.send(f"Erro ao processar transferência: {e}")
    
    async def _handle_expense_intent(self, message: discord.Message, get_categories):
        """Processa intenção de gasto"""
        try:
            # Buscar categorias disponíveis
            categories, error_msg = await get_categories()
            if error_msg:
                await message.channel.send(f"Ocorreu um erro ao buscar as categorias: {error_msg}")
                return

            # Processar gasto
            classification_data = await self.expense_service.process_text_expense(message.content, categories)
            
            # Criar thread para o gasto
            total_valor = sum(item.valor for item in classification_data.itens)
            thread_name = f"Gasto de R$ {total_valor:.2f}" if total_valor > 0 else "Gasto"
            thread = await message.create_thread(name=thread_name)
            
            # Criar contexto para a thread
            context = UserContext(
                user_id=str(message.author.id),
                thread_id=str(thread.id),
                message_content=message.content,
                classification_data=classification_data
            )
            self.state_manager.set_context(str(thread.id), context)
            
            await thread.send(f"Olá! Identifiquei um gasto na sua mensagem. Vou analisá-lo e gerar uma classificação.")
            
            # Mostrar resumo da classificação
            summary = format_classification_summary(classification_data)
            summary += "\n\nPor favor, verifique a classificação. Se estiver tudo certo, digite 'sim' ou 'ok'. Se precisar de alguma alteração, me diga o que devo mudar."
            await thread.send(summary)
            
        except Exception as e:
            logger.error(f"Erro ao processar gasto: {e}")
            await message.channel.send(f"Erro ao processar gasto: {e}")
    
    async def _handle_thread_response(self, message: discord.Message, db_manager, get_categories, insert_transfer):
        """Processa resposta em thread"""
        try:
            thread_id = str(message.channel.id)
            context = self.state_manager.get_context(thread_id)
            
            if not context:
                return
            
            user_input = message.content
            
            if context.classification_data:
                await self._handle_classification_response(message, context, db_manager, get_categories)
            elif context.transfer_data:
                await self._handle_transfer_response(message, context, insert_transfer)
                
        except Exception as e:
            logger.error(f"Erro ao processar resposta em thread: {e}")
            await message.channel.send("Desculpe, ocorreu um erro. Tente novamente.")
    
    async def _handle_classification_response(self, message: discord.Message, context: UserContext, db_manager, get_categories):
        """Processa resposta para classificação"""
        try:
            # Processar comando com OpenAI
            context_dict = context.to_dict()
            ai_response = await self.openai_service.process_user_input(message.content, context_dict)
            
            if ai_response.action == "confirm":
                await message.channel.send("Ótimo! Por favor, me informe a **conta** para que eu possa salvar as transações.")
                self.state_manager.update_context(str(message.channel.id), waiting_for_account=True)
                
            elif ai_response.action == "edit":
                # Editar classificação
                updated_data = await self.classification_service.edit_classification(
                    context.classification_data, message.content
                )
                self.state_manager.update_context(str(message.channel.id), classification_data=updated_data)
                
                # Mostrar resumo atualizado
                summary = format_classification_summary(updated_data)
                summary += "\n\nEstá correto agora? Se sim, digite 'sim' ou 'ok'."
                await message.channel.send(summary)
                
            elif ai_response.action == "account":
                # Salvar transações
                await self._save_transactions(message, context, db_manager)
                
            elif ai_response.action == "help":
                help_message = format_help_message()
                await message.channel.send(help_message)
                
            else:
                await message.channel.send(ai_response.message)
                
        except Exception as e:
            logger.error(f"Erro ao processar resposta de classificação: {e}")
            await message.channel.send("Desculpe, não consegui entender. Tente ser mais específico.")
    
    async def _handle_transfer_response(self, message: discord.Message, context: UserContext, insert_transfer):
        """Processa resposta para transferência"""
        try:
            # Processar comando com OpenAI
            context_dict = context.to_dict()
            ai_response = await self.openai_service.process_user_input(message.content, context_dict)
            
            if ai_response.action == "confirm":
                # Salvar transferência
                await self._save_transfer(message, context, insert_transfer)
                
            elif ai_response.action == "edit":
                # Editar transferência
                updated_data = await self.transfer_service.edit_transfer(
                    context.transfer_data, message.content
                )
                self.state_manager.update_context(str(message.channel.id), transfer_data=updated_data)
                
                # Mostrar resumo atualizado
                summary = format_transfer_summary(updated_data)
                summary += "\n\nEstá correto agora? Se sim, digite 'sim' ou 'ok'."
                await message.channel.send(summary)
                
            elif ai_response.action == "help":
                help_message = format_transfer_help_message()
                await message.channel.send(help_message)
                
            else:
                await message.channel.send(ai_response.message)
                
        except Exception as e:
            logger.error(f"Erro ao processar resposta de transferência: {e}")
            await message.channel.send("Desculpe, não consegui entender. Tente ser mais específico.")
    
    async def _process_image(self, thread: discord.Thread, image_url: str, get_categories):
        """Processa imagem com OpenAI"""
        try:
            # Buscar categorias disponíveis
            categories, error_msg = await get_categories()
            if error_msg:
                await thread.send(f"Ocorreu um erro ao buscar as categorias: {error_msg}")
                return

            # Classificar imagem
            classification_data = await self.classification_service.classify_image(image_url, categories)
            
            # Atualizar contexto
            self.state_manager.update_context(str(thread.id), classification_data=classification_data)
            
            # Mostrar resumo
            summary = format_classification_summary(classification_data)
            summary += "\n\nPor favor, verifique a classificação. Se estiver tudo certo, digite 'sim' ou 'ok'. Se precisar de alguma alteração, me diga o que devo mudar."
            await thread.send(summary)
            
        except Exception as e:
            logger.error(f"Erro ao processar imagem: {e}")
            await thread.send(f"Ocorreu um erro ao processar a imagem: {e}")
    
    async def _save_transactions(self, message: discord.Message, context: UserContext, db_manager):
        """Salva transações no banco de dados"""
        try:
            user_input = message.content
            classification_data = context.classification_data
            
            # Buscar contas disponíveis e identificar a conta
            available_accounts = await db_manager.get_available_accounts()
            conta = await self.openai_service.identify_account(user_input, available_accounts)
            
            # Validar se a conta existe
            if available_accounts and conta not in available_accounts:
                await message.channel.send(f"⚠️ Conta '{conta}' não encontrada nas contas disponíveis: {', '.join(available_accounts)}")
                await message.channel.send("Por favor, informe uma conta válida ou confirme se deseja usar esta conta mesmo assim.")
                return
            
            # Converter para formato de dicionário para compatibilidade
            transactions = [item.to_dict() for item in classification_data.itens]
            
            # Agrupar transações por categoria
            from ..utils.formatters import group_transactions_by_category
            grouped_transactions = group_transactions_by_category(transactions)
            
            # Salvar transações agrupadas
            saved_count, error_count = await db_manager.insert_grouped_transactions(
                classification_data.data_compra, grouped_transactions, conta, classification_data.estabelecimento
            )
            
            if saved_count > 0:
                await message.channel.send(f"✅ {saved_count} categorias salvas com sucesso na conta '{conta}'!")
            if error_count > 0:
                await message.channel.send(f"❌ {error_count} categorias falharam ao salvar.")
            
            await message.channel.send("Este tópico será arquivado. Obrigado!")
            self.state_manager.remove_context(str(message.channel.id))
            
        except Exception as e:
            logger.error(f"Erro ao salvar transações: {e}")
            await message.channel.send("Erro ao salvar transações. Tente novamente.")
    
    async def _save_transfer(self, message: discord.Message, context: UserContext, insert_transfer):
        """Salva transferência no banco de dados"""
        try:
            transfer_data = context.transfer_data
            
            # Salvar transferência no banco
            success, message_result = await insert_transfer(
                transfer_data.data_transferencia,
                transfer_data.valor,
                transfer_data.conta_origem,
                transfer_data.conta_destino,
                transfer_data.descricao
            )
            
            if success:
                await message.channel.send(f"✅ Transferência de R$ {transfer_data.valor:.2f} de '{transfer_data.conta_origem}' para '{transfer_data.conta_destino}' realizada com sucesso!")
            else:
                await message.channel.send(f"❌ Erro ao salvar transferência: {message_result}")
                return
            
            await message.channel.send("Este tópico será arquivado. Obrigado!")
            self.state_manager.remove_context(str(message.channel.id))
            
        except Exception as e:
            logger.error(f"Erro ao salvar transferência: {e}")
            await message.channel.send("Erro ao salvar transferência. Tente novamente.") 