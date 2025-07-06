"""
Utilitários de validação para o bot
"""
from typing import List


def validate_image_extension(filename: str, supported_extensions: List[str]) -> bool:
    """Valida extensão de imagem"""
    if not filename:
        return False
    
    file_ext = filename.lower()
    return any(file_ext.endswith(ext) for ext in supported_extensions)


def validate_transaction_item(item: dict) -> bool:
    """Valida um item de transação"""
    if not item.get('descricao') or not item.get('categoria'):
        return False
    
    try:
        float(item.get('valor', 0))
    except (ValueError, TypeError):
        return False
    
    return True


def validate_transfer_data(transfer_data: dict) -> bool:
    """Valida dados de transferência"""
    try:
        valor = float(transfer_data.get('valor', 0))
        if valor <= 0:
            return False
        
        conta_origem = transfer_data.get('conta_origem', '')
        conta_destino = transfer_data.get('conta_destino', '')
        
        if not conta_origem or not conta_destino:
            return False
        
        if conta_origem == conta_destino:
            return False
        
        return True
    except (ValueError, TypeError):
        return False


def validate_classification_data(data: dict) -> bool:
    """Valida dados de classificação"""
    if 'itens' not in data:
        return False
    
    itens = data.get('itens', [])
    if not itens:
        return False
    
    for item in itens:
        if not validate_transaction_item(item):
            return False
    
    return True 