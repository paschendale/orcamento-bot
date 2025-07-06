"""
Utilitários de formatação para o bot
"""
from typing import Dict, List, Any
from datetime import date

from ..models.data_models import TransactionItem, ClassificationData, TransferData


def group_transactions_by_category(transactions: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Agrupa transações por categoria"""
    grouped = {}
    for item in transactions:
        categoria = item.get('categoria', 'a classificar')
        if categoria not in grouped:
            grouped[categoria] = []
        grouped[categoria].append(item)
    return grouped


def format_grouped_summary(grouped_transactions: Dict[str, List[Dict[str, Any]]], estabelecimento: str = None) -> str:
    """Formata resumo agrupado por categoria"""
    if not grouped_transactions:
        return "Nenhuma transação encontrada."
    
    summary = "**Resumo por Categoria:**\n\n"
    if estabelecimento:
        summary += f"🏪 **Estabelecimento:** {estabelecimento}\n\n"
    
    total_geral = 0.0
    
    for categoria, items in grouped_transactions.items():
        valor_categoria = sum(float(item.get('valor', 0)) for item in items)
        total_geral += valor_categoria
        
        produtos = [item['descricao'] for item in items]
        summary += f"**{categoria}** - R$ {valor_categoria:.2f}\n"
        summary += f"Produtos: {', '.join(produtos)}\n\n"
    
    summary += f"**Total Geral: R$ {total_geral:.2f}**"
    return summary


def format_classification_summary(classification_data: ClassificationData) -> str:
    """Formata resumo de classificação"""
    # Converter para formato de dicionário para compatibilidade
    transactions = [item.to_dict() for item in classification_data.itens]
    grouped_transactions = group_transactions_by_category(transactions)
    
    summary = format_grouped_summary(grouped_transactions, classification_data.estabelecimento)
    summary += f"\n\n📅 **Data da compra:** {classification_data.data_compra.strftime('%d/%m/%Y')}"
    
    return summary


def format_transfer_summary(transfer_data: TransferData) -> str:
    """Formata resumo de transferência"""
    summary = f"""**💸 Transferência Detectada**

💰 **Valor:** R$ {transfer_data.valor:.2f}
📤 **De:** {transfer_data.conta_origem}
📥 **Para:** {transfer_data.conta_destino}
📅 **Data:** {transfer_data.data_transferencia.strftime('%d/%m/%Y')}
📝 **Descrição:** {transfer_data.descricao or 'Transferência entre contas'}

Por favor, confirme se está correto. Digite 'sim' ou 'ok' para confirmar, ou me diga o que deve ser alterado."""
    
    return summary


def redistribute_values_for_total(items: List[Dict[str, Any]], target_total: float) -> List[Dict[str, Any]]:
    """Redistribui valores proporcionalmente para atingir o total desejado"""
    if not items:
        return items
    
    # Calcular total atual
    current_total = sum(float(item.get('valor', 0)) for item in items)
    
    if current_total == 0:
        return items
    
    # Calcular fator de multiplicação
    factor = target_total / current_total
    
    # Aplicar fator a todos os itens
    updated_items = []
    for item in items:
        new_item = item.copy()
        new_item['valor'] = round(float(item.get('valor', 0)) * factor, 2)
        updated_items.append(new_item)
    
    # Verificar se o total está correto (pode haver pequenas diferenças por arredondamento)
    actual_total = sum(float(item.get('valor', 0)) for item in updated_items)
    if abs(actual_total - target_total) > 0.01:
        # Ajustar o último item para compensar diferenças de arredondamento
        diff = target_total - actual_total
        if updated_items:
            updated_items[-1]['valor'] = round(updated_items[-1]['valor'] + diff, 2)
    
    return updated_items


def format_help_message() -> str:
    """Formata mensagem de ajuda"""
    return """**Comandos disponíveis:**
- `sim`, `ok`, `pode seguir` - Confirma a classificação
- `mude [item] para [categoria]` - Altera categoria de um item
- `troque [categoria] por [nova_categoria]` - Altera uma categoria
- `ajuda` - Mostra esta mensagem"""


def format_transfer_help_message() -> str:
    """Formata mensagem de ajuda para transferências"""
    return """**Comandos disponíveis para transferências:**
- `sim`, `ok`, `pode seguir` - Confirma a transferência
- `mude valor para [novo_valor]` - Altera o valor da transferência
- `troque conta origem para [nova_conta]` - Altera a conta de origem
- `troque conta destino para [nova_conta]` - Altera a conta de destino
- `mude descrição para [nova_descricao]` - Altera a descrição da transferência
- `ajuda` - Mostra esta mensagem""" 