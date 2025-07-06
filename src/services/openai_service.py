"""
Serviço OpenAI para o bot
"""
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import date, datetime

import openai

from ..models.data_models import AIResponse, MessageIntent, ClassificationData, TransferData, TransactionItem
from ..utils.validators import validate_classification_data, validate_transfer_data

logger = logging.getLogger(__name__)


class OpenAIService:
    """Serviço para interação com a API da OpenAI"""
    
    def __init__(self, api_key: str, model: str, max_tokens: int):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
    
    async def check_connection(self) -> Tuple[bool, str]:
        """Verifica conexão com OpenAI"""
        try:
            self.client.models.list()
            return True, "Conexão com a API da OpenAI bem-sucedida."
        except Exception as e:
            logger.error(f"Erro ao conectar com OpenAI: {e}")
            return False, f"Erro ao conectar com a API da OpenAI: {e}"
    
    async def get_usage_info(self) -> Tuple[bool, str]:
        """Obtém informações de uso da OpenAI"""
        try:
            # Tentar obter informações de uso da API usando a nova API de billing
            try:
                billing_response = self.client.billing.usage.list()
                
                if billing_response and hasattr(billing_response, 'data'):
                    usage_data = billing_response.data[0] if billing_response.data else None
                    if usage_data:
                        # Calcular uso em dólares
                        total_usage = usage_data.total_usage / 100  # Convert from cents to dollars
                        
                        # Obter informações do período
                        start_date = usage_data.start_date
                        end_date = usage_data.end_date
                        
                        usage_info = f"**Período:** {start_date} a {end_date}\n"
                        usage_info += f"**Uso Total:** ${total_usage:.2f}\n"
                        
                        # Se houver limite de crédito
                        if hasattr(usage_data, 'granted') and usage_data.granted:
                            granted = usage_data.granted / 100
                            usage_info += f"**Crédito Disponível:** ${granted:.2f}\n"
                            usage_info += f"**Restante:** ${(granted - total_usage):.2f}"
                        
                        return True, usage_info
            except Exception as api_error:
                logger.warning(f"API de billing não disponível: {api_error}")
            
            # Fallback: tentar obter informações básicas de uso
            try:
                usage_response = self.client.usage.list()
                if usage_response and hasattr(usage_response, 'data'):
                    usage_data = usage_response.data[0] if usage_response.data else None
                    if usage_data:
                        return True, f"**Uso de Tokens:** {usage_data.usage.total_tokens:,} tokens\n**Limite:** {usage_data.usage.granted:,} tokens"
            except Exception as usage_error:
                logger.warning(f"API de usage não disponível: {usage_error}")
            
            # Fallback final: informações básicas
            return True, "**Informações de uso não estão disponíveis via API.**\n\nPara verificar seu uso detalhado, acesse:\n🔗 https://platform.openai.com/usage\n🔗 https://platform.openai.com/account/billing/usage"
        except Exception as e:
            logger.error(f"Erro ao obter uso da OpenAI: {e}")
            return False, f"Erro ao obter informações de uso: {e}"
    
    async def identify_account(self, user_input: str, available_accounts: List[str]) -> str:
        """Identifica conta usando OpenAI"""
        try:
            if not available_accounts:
                return user_input
            
            system_prompt = """Você é um assistente que ajuda a identificar contas bancárias.

Analise o texto do usuário e identifique qual conta bancária ele está se referindo.
Se não conseguir identificar uma conta específica, retorne "NÃO_IDENTIFICADA".

Responda APENAS com o nome da conta ou "NÃO_IDENTIFICADA"."""

            user_prompt = f"""
Texto do usuário: "{user_input}"

Contas disponíveis: {available_accounts}

Identifique a conta ou responda "NÃO_IDENTIFICADA"."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=50,
                temperature=0.1
            )
            
            identified_account = response.choices[0].message.content.strip()
            logger.info(f"Conta identificada: {identified_account}")
            
            if identified_account in available_accounts:
                return identified_account
            else:
                return user_input
                
        except Exception as e:
            logger.error(f"Erro ao identificar conta: {e}")
            return user_input
    
    async def process_user_input(self, user_input: str, context: Dict[str, Any]) -> AIResponse:
        """Processa entrada do usuário com OpenAI para determinar ação"""
        try:
            system_prompt = """Você é um assistente que ajuda a processar comandos de usuário em um bot de classificação de cupons fiscais.

Analise o comando do usuário e retorne APENAS um JSON válido com:
{
    "action": "confirm|edit|account|help|error",
    "message": "Mensagem para o usuário"
}

Ações possíveis:
- confirm: Usuário confirma classificação (sim, ok, pode seguir, etc) SEM mencionar conta OU correções
- edit: Usuário quer editar algo (mude, troque, altere, corrigir valores, etc) OU menciona que algo "é" diferente do que foi mostrado
- account: Usuário forneceu conta OU se a mensagem contém informações de conta (ex: "ok Cartão Rico", "sim, conta Nubank", etc)
- help: Usuário pediu ajuda
- error: Comando não reconhecido

IMPORTANTE: 
- Se a mensagem contém confirmação + conta, use action "account"
- Se a mensagem menciona erro de valor, correção, ou usa "é" para indicar que algo está diferente, use action "edit"
- Se a mensagem diz que "tudo é [categoria]" ou "o total é [valor]", isso é uma edição, não confirmação
- Se a mensagem contém "classifica tudo como" ou "tudo como", use action "edit"
- Se a mensagem contém "valor total é" ou "total é", use action "edit"
Responda APENAS com o JSON, sem texto adicional."""

            # Preparar contexto para serialização JSON (converter date para string)
            context_for_json = context.copy()
            
            # Função para converter objetos date para string
            def convert_dates_to_strings(obj):
                if isinstance(obj, date):
                    return obj.isoformat()
                elif isinstance(obj, dict):
                    return {k: convert_dates_to_strings(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_dates_to_strings(item) for item in obj]
                else:
                    return obj
            
            context_for_json = convert_dates_to_strings(context_for_json)

            user_prompt = f"""
Comando do usuário: "{user_input}"

Contexto: {json.dumps(context_for_json, ensure_ascii=False)}

Responda APENAS com o JSON da ação."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=200,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            logger.info(f"Resposta OpenAI: {content}")
            
            # Limpar a resposta
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            if not content:
                raise ValueError("Resposta vazia da OpenAI")
            
            result = json.loads(content)
            
            # Validar estrutura do resultado
            if "action" not in result:
                raise ValueError("Resposta não contém 'action'")
            
            logger.info(f"OpenAI processou comando: {result['action']}")
            return AIResponse.from_dict(result)
            
        except json.JSONDecodeError as e:
            logger.error(f"Erro JSON ao processar comando: {e}")
            # Fallback para comandos simples
            user_input_lower = user_input.lower()
            if any(keyword in user_input_lower for keyword in ["sim", "ok", "pode seguir", "confirmo", "correto", "manda bala", "confirma"]):
                return AIResponse(action="confirm", message="Confirmação recebida")
            elif any(keyword in user_input_lower for keyword in ["troque", "mude", "altere", "corrija"]):
                return AIResponse(action="edit", message="Editando classificação")
            elif any(keyword in user_input_lower for keyword in ["ajuda", "help", "comandos"]):
                return AIResponse(action="help", message="Mostrando ajuda")
            else:
                return AIResponse(action="account", message="Processando como conta")
                
        except Exception as e:
            logger.error(f"Erro ao processar comando com OpenAI: {e}")
            return AIResponse(
                action="error",
                message="Desculpe, não consegui processar seu comando. Tente novamente."
            )
    
    async def detect_message_intent(self, message_content: str) -> MessageIntent:
        """Detecta a intenção da mensagem usando OpenAI"""
        try:
            system_prompt = """Você é um assistente que analisa mensagens para identificar a intenção do usuário.

Analise a mensagem e retorne APENAS um JSON válido com:
{
    "intent": "transfer|expense|command|other",
    "confidence": 0.95,
    "extracted_data": {}
}

Intenções possíveis:
- transfer: Usuário está relatando uma transferência entre contas (ex: "transferi 5000 da bb vi pra rico Ju", "movi 3000 de nubank para itau")
- expense: Usuário está relatando um gasto/compra (ex: "gastei R$ 50 no mercado", "comprei R$ 30 de comida")
- command: Usuário está usando um comando (ex: "/status", "/help")
- other: Outra intenção não relacionada a finanças

Para transferências, inclua em extracted_data:
{
    "valor": 5000.0,
    "conta_origem": "BB VI",
    "conta_destino": "Rico Ju"
}

Para gastos, inclua em extracted_data:
{
    "valor": 50.0,
    "estabelecimento": "mercado"
}

Responda APENAS com o JSON, sem texto adicional."""

            user_prompt = f"""
Mensagem do usuário: "{message_content}"

Identifique a intenção e retorne o JSON."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=200,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            logger.info(f"Resposta OpenAI (detecção de intenção): {content}")
            
            # Limpar a resposta
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            if not content:
                raise ValueError("Resposta vazia da OpenAI")
            
            result = json.loads(content)
            
            # Validar estrutura do resultado
            if "intent" not in result:
                raise ValueError("Resposta não contém 'intent'")
            
            logger.info(f"OpenAI detectou intenção: {result['intent']}")
            return MessageIntent.from_dict(result)
            
        except json.JSONDecodeError as e:
            logger.error(f"Erro JSON ao detectar intenção: {e}")
            # Fallback: assumir que é um gasto se contém palavras-chave
            message_lower = message_content.lower()
            if any(keyword in message_lower for keyword in ["transferi", "transf", "movi", "para", "pra"]):
                return MessageIntent(intent="transfer", confidence=0.7, extracted_data={})
            elif any(keyword in message_lower for keyword in ["gastei", "comprei", "paguei", "mercado", "farmácia"]):
                return MessageIntent(intent="expense", confidence=0.7, extracted_data={})
            else:
                return MessageIntent(intent="other", confidence=0.5, extracted_data={})
                
        except Exception as e:
            logger.error(f"Erro ao detectar intenção com OpenAI: {e}")
            return MessageIntent(
                intent="other",
                confidence=0.0,
                extracted_data={}
            ) 