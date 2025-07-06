"""
Serviço de transferências para o bot
"""
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import date, datetime

from ..models.data_models import TransferData
from ..utils.validators import validate_transfer_data

logger = logging.getLogger(__name__)


class TransferService:
    """Serviço para processamento de transferências"""
    
    def __init__(self, openai_service):
        self.openai_service = openai_service
    
    async def process_transfer(self, message_content: str, available_accounts: List[str]) -> TransferData:
        """Processa transferência informada em texto"""
        try:
            # Obter data atual
            data_atual = date.today()
            
            system_prompt = f"""Você é um assistente que ajuda a processar transferências entre contas bancárias.

Analise a mensagem do usuário e identifique:
1. O valor da transferência
2. A conta de origem (de onde o dinheiro sai)
3. A conta de destino (para onde o dinheiro vai)
4. A data da transferência (use a data atual se não especificada)
5. Uma descrição personalizada (se o usuário forneceu uma)

Contas disponíveis: {available_accounts}

IMPORTANTE: 
- Use SEMPRE a data atual ({data_atual.strftime('%Y-%m-%d')}) para a data da transferência, a menos que a mensagem especifique claramente uma data diferente
- Identifique a conta mais próxima do nome mencionado pelo usuário
- Se não conseguir identificar uma conta específica, use o nome exato mencionado pelo usuário
- Se o usuário forneceu uma descrição ou motivo para a transferência, inclua na descrição
- Se não houver descrição específica, deixe o campo "descricao" vazio ou null

Retorne um JSON com a seguinte estrutura:
{{
    "valor": valor_extraído_da_mensagem,
    "conta_origem": "nome da conta de origem",
    "conta_destino": "nome da conta de destino", 
    "data": "{data_atual.strftime('%Y-%m-%d')}",
    "descricao": "descrição personalizada ou null"
}}

Se não conseguir identificar uma das contas, use o nome exato mencionado pelo usuário."""

            user_prompt = f"""
Mensagem do usuário: "{message_content}"

Contas disponíveis: {available_accounts}

Processe esta transferência e retorne o JSON."""

            response = self.openai_service.client.chat.completions.create(
                model=self.openai_service.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=self.openai_service.max_tokens,
            )
            
            response_json = response.choices[0].message.content
            clean_response_json = response_json.strip().replace("```json", "").replace("```", "")
            parsed_data = json.loads(clean_response_json)
            
            return self._parse_transfer_response(parsed_data, data_atual)
            
        except Exception as e:
            logger.error(f"Erro ao processar transferência: {e}")
            raise
    
    async def edit_transfer(self, current_data: TransferData, user_command: str) -> TransferData:
        """Edita transferência existente"""
        try:
            system_prompt = """Você é um assistente que ajuda a editar dados de transferências.

Analise o comando do usuário e faça as alterações solicitadas na transferência.
O usuário pode querer:
- Mudar o valor da transferência
- Mudar a conta de origem
- Mudar a conta de destino
- Mudar a descrição
- Fazer múltiplas alterações ao mesmo tempo

IMPORTANTE:
- Se o usuário pedir para "mude valor para [novo_valor]", atualize o valor
- Se o usuário pedir para "troque conta origem para [nova_conta]", atualize a conta de origem
- Se o usuário pedir para "troque conta destino para [nova_conta]", atualize a conta de destino
- Se o usuário pedir para "mude descrição para [nova_descricao]", atualize a descrição
- Se o usuário pedir para "descrição [nova_descricao]", atualize a descrição
- Mantenha os valores originais se não conseguir entender o comando

Retorne APENAS um JSON com a estrutura atualizada, sem texto adicional."""

            user_prompt = f"""
Transferência atual: {json.dumps(current_data.to_dict())}
Comando do usuário: '{user_command}'

Atualize a transferência conforme solicitado e retorne APENAS o JSON."""

            response = self.openai_service.client.chat.completions.create(
                model=self.openai_service.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            logger.info(f"Resposta OpenAI (edição de transferência): {content}")
            
            # Limpar a resposta
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            if not content:
                raise ValueError("Resposta vazia da OpenAI")
            
            updated_data = json.loads(content)
            
            # Validar dados atualizados
            if "valor" in updated_data and updated_data["valor"] <= 0:
                raise ValueError("Valor da transferência deve ser maior que zero")
            
            if "conta_origem" in updated_data and "conta_destino" in updated_data:
                if updated_data["conta_origem"] == updated_data["conta_destino"]:
                    raise ValueError("Conta de origem e destino não podem ser iguais")
            
            # Mesclar dados atualizados com dados atuais
            merged_data = current_data.to_dict()
            merged_data.update(updated_data)
            
            return TransferData.from_dict(merged_data)
            
        except Exception as e:
            logger.error(f"Erro ao editar transferência: {e}")
            raise
    
    def _parse_transfer_response(self, parsed_data: Dict[str, Any], data_atual: date) -> TransferData:
        """Converte resposta da OpenAI para TransferData"""
        # Extrair dados da resposta
        valor = float(parsed_data.get('valor', 0))
        conta_origem = parsed_data.get('conta_origem', '')
        conta_destino = parsed_data.get('conta_destino', '')
        descricao = parsed_data.get('descricao', None)
        
        # Se não há descrição personalizada, usar None para que o banco crie a descrição padrão
        if descricao is None or descricao == "" or descricao == "null":
            descricao = None
        
        # Extrair e validar data
        data_str = parsed_data.get('data', None)
        if data_str:
            try:
                data_transferencia = datetime.strptime(data_str, '%Y-%m-%d').date()
                # Verificar se a data não é muito antiga (mais de 30 dias)
                data_limite = data_atual - datetime.timedelta(days=30)
                if data_transferencia < data_limite:
                    logger.warning(f"Data muito antiga retornada pela OpenAI: {data_transferencia}, usando data atual: {data_atual}")
                    data_transferencia = data_atual
            except (ValueError, TypeError):
                data_transferencia = data_atual
        else:
            data_transferencia = data_atual
        
        # Validar dados
        if valor <= 0:
            raise ValueError("Valor da transferência deve ser maior que zero")
        
        if not conta_origem or not conta_destino:
            raise ValueError("Conta de origem e destino são obrigatórias")
        
        if conta_origem == conta_destino:
            raise ValueError("Conta de origem e destino não podem ser iguais")
        
        return TransferData(
            valor=valor,
            conta_origem=conta_origem,
            conta_destino=conta_destino,
            data_transferencia=data_transferencia,
            descricao=descricao
        ) 