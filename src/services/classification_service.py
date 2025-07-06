"""
Serviço de classificação para o bot
"""
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import date, datetime

from ..models.data_models import ClassificationData, TransactionItem
from ..utils.formatters import redistribute_values_for_total

logger = logging.getLogger(__name__)


class ClassificationService:
    """Serviço para classificação de transações"""
    
    def __init__(self, openai_service):
        self.openai_service = openai_service
    
    async def classify_image(self, image_url: str, categories: List[str]) -> ClassificationData:
        """Classifica imagem de cupom fiscal"""
        try:
            system_prompt = f"""Analise esta imagem de um cupom fiscal brasileiro. Extraia cada item, seu valor e classifique-o em uma das seguintes categorias: {categories}. Também identifique o nome do estabelecimento onde a compra foi feita (ex: Supermercado, Farmácia, etc) e a data da compra. Retorne um JSON com a seguinte estrutura: {{"estabelecimento": "nome do estabelecimento", "data": "YYYY-MM-DD", "itens": [{{'descricao': 'item', 'valor': valor, 'categoria': 'categoria'}}]}}. Se não conseguir identificar o estabelecimento, use "Estabelecimento não identificado". Se não conseguir identificar a data, use a data atual. Se não tiver certeza sobre a categoria de um item, use 'a classificar'."""

            response = self.openai_service.client.chat.completions.create(
                model=self.openai_service.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": system_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url}
                            }
                        ]
                    }
                ],
                max_tokens=self.openai_service.max_tokens,
            )
            
            response_json = response.choices[0].message.content
            clean_response_json = response_json.strip().replace("```json", "").replace("```", "")
            parsed_data = json.loads(clean_response_json)
            
            return self._parse_classification_response(parsed_data, categories)
            
        except Exception as e:
            logger.error(f"Erro ao classificar imagem: {e}")
            raise
    
    async def classify_text_expense(self, message_content: str, categories: List[str]) -> ClassificationData:
        """Classifica gasto informado em texto"""
        try:
            # Obter data atual
            data_atual = date.today()
            
            system_prompt = f"""Você é um assistente que ajuda a classificar gastos em categorias.

Analise a mensagem do usuário e extraia:
1. O valor do gasto
2. O estabelecimento ou tipo de local
3. A categoria mais apropriada

Categorias disponíveis: {categories}

IMPORTANTE: Use SEMPRE a data atual ({data_atual.strftime('%Y-%m-%d')}) para a data da compra, a menos que a mensagem especifique claramente uma data diferente.

Retorne um JSON com a seguinte estrutura:
{{
    "estabelecimento": "nome do estabelecimento ou tipo de local",
    "data": "{data_atual.strftime('%Y-%m-%d')}",
    "itens": [
        {{
            "descricao": "descrição do item ou tipo de gasto",
            "valor": valor_extraído_da_mensagem,
            "categoria": "categoria mais apropriada"
        }}
    ]
}}

Se não conseguir identificar o estabelecimento, use "Estabelecimento não identificado".
Use SEMPRE a data atual ({data_atual.strftime('%Y-%m-%d')}) para a data.
Se não tiver certeza sobre a categoria, use 'a classificar'.
Se a mensagem mencionar múltiplos itens, crie um item para cada um."""

            user_prompt = f"""
Mensagem do usuário: "{message_content}"

Extraia o valor do gasto e classifique nas categorias disponíveis."""

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
            
            return self._parse_classification_response(parsed_data, categories)
            
        except Exception as e:
            logger.error(f"Erro ao classificar gasto em texto: {e}")
            raise
    
    async def edit_classification(self, current_data: ClassificationData, user_command: str) -> ClassificationData:
        """Edita classificação existente"""
        try:
            # Primeiro, tentar extrair informações específicas do comando
            user_input = user_command.lower()
            target_total = None
            target_category = None
            
            # Extrair valor total mencionado
            import re
            total_match = re.search(r'total.*?r?\$?\s*([\d,]+\.?\d*)', user_input)
            if total_match:
                target_total = float(total_match.group(1).replace(',', '.'))
            
            # Extrair categoria mencionada
            if 'alimentação básica' in user_input or 'alimentacao basica' in user_input:
                target_category = 'Alimentação - Básica'
            elif 'alimentação supérflua' in user_input or 'alimentacao superflua' in user_input:
                target_category = 'Alimentação - Supérflua'
            elif 'casa' in user_input and 'manutenção' in user_input:
                target_category = 'Casa - Manutenção'
            elif 'higiene' in user_input:
                target_category = 'Higiene & Beleza - Básicos'
            
            # Se encontrou informações específicas, usar lógica programática
            if target_category or target_total:
                updated_items = current_data.itens.copy()
                
                # Aplicar mudança de categoria se especificada
                if target_category:
                    for item in updated_items:
                        item.categoria = target_category
                
                # Aplicar redistribuição de valores se especificada
                if target_total:
                    # Converter para formato de dicionário para compatibilidade
                    items_dict = [item.to_dict() for item in updated_items]
                    updated_items_dict = redistribute_values_for_total(items_dict, target_total)
                    updated_items = [TransactionItem.from_dict(item) for item in updated_items_dict]
                
                return ClassificationData(
                    estabelecimento=current_data.estabelecimento,
                    data_compra=current_data.data_compra,
                    itens=updated_items,
                    available_categories=current_data.available_categories
                )
            
            # Se não conseguiu extrair informações específicas, usar OpenAI
            system_prompt = """Você é um assistente que ajuda a reclassificar itens de uma lista de compras em formato JSON.

Analise o comando do usuário e faça as alterações solicitadas na lista de itens.
O usuário pode querer:
- Mudar categorias de itens específicos
- Mudar a categoria de todos os itens
- Corrigir valores de itens específicos
- Corrigir o valor total (distribuindo proporcionalmente)
- Fazer múltiplas alterações ao mesmo tempo

IMPORTANTE:
- Se o usuário pedir para "classificar tudo como [categoria]", mude a categoria de TODOS os itens para essa categoria
- Se o usuário mencionar um valor total diferente, redistribua os valores proporcionalmente para atingir esse total
- Mantenha a proporção relativa dos valores entre os itens quando possível
- Se não conseguir entender o comando, mantenha os valores originais

Retorne APENAS a lista JSON atualizada, sem texto adicional."""

            # Converter dados atuais para formato de dicionário
            current_items_dict = [item.to_dict() for item in current_data.itens]

            user_prompt = f"""
Lista atual: {json.dumps(current_items_dict)}
Categorias disponíveis: {current_data.available_categories}
Comando do usuário: '{user_command}'

Atualize a lista conforme solicitado e retorne APENAS o JSON."""

            response = self.openai_service.client.chat.completions.create(
                model=self.openai_service.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            logger.info(f"Resposta OpenAI (edição): {content}")
            
            # Limpar a resposta
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            if not content:
                raise ValueError("Resposta vazia da OpenAI")
            
            updated_items_dict = json.loads(content)
            
            # Validar dados atualizados
            for item in updated_items_dict:
                if not validate_transaction_item(item):
                    raise ValueError("Dados inválidos na edição")
            
            # Converter de volta para objetos TransactionItem
            updated_items = [TransactionItem.from_dict(item) for item in updated_items_dict]
            
            return ClassificationData(
                estabelecimento=current_data.estabelecimento,
                data_compra=current_data.data_compra,
                itens=updated_items,
                available_categories=current_data.available_categories
            )
            
        except Exception as e:
            logger.error(f"Erro ao editar classificação: {e}")
            raise
    
    def _parse_classification_response(self, parsed_data: Dict[str, Any], categories: List[str]) -> ClassificationData:
        """Converte resposta da OpenAI para ClassificationData"""
        # Extrair estabelecimento, data e itens
        estabelecimento = parsed_data.get('estabelecimento', 'Estabelecimento não identificado')
        
        # Extrair e validar data
        data_str = parsed_data.get('data', None)
        if data_str:
            try:
                # Tentar converter a data para datetime
                data_compra = datetime.strptime(data_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                # Se não conseguir converter, usar data atual
                data_compra = date.today()
        else:
            # Se não houver data, usar data atual
            data_compra = date.today()
        
        # Verificar se a resposta tem a estrutura esperada
        if 'itens' in parsed_data:
            items_data = parsed_data.get('itens', [])
        else:
            # Fallback para estrutura antiga (compatibilidade)
            items_data = parsed_data if isinstance(parsed_data, list) else []
            estabelecimento = 'Estabelecimento não identificado'
        
        # Validar dados recebidos
        for item in items_data:
            if not validate_transaction_item(item):
                raise ValueError("Dados inválidos recebidos da OpenAI")
        
        # Converter para objetos TransactionItem
        items = [TransactionItem.from_dict(item) for item in items_data]
        
        return ClassificationData(
            estabelecimento=estabelecimento,
            data_compra=data_compra,
            itens=items,
            available_categories=categories
        )


def validate_transaction_item(item: dict) -> bool:
    """Valida um item de transação"""
    if not item.get('descricao') or not item.get('categoria'):
        return False
    
    try:
        float(item.get('valor', 0))
    except (ValueError, TypeError):
        return False
    
    return True 