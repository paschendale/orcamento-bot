"""
Modelos de dados para o bot de orçamento
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from datetime import date, datetime
import json


@dataclass
class TransactionItem:
    """Item de transação individual"""
    descricao: str
    valor: float
    categoria: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'descricao': self.descricao,
            'valor': self.valor,
            'categoria': self.categoria
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TransactionItem':
        return cls(
            descricao=data.get('descricao', ''),
            valor=float(data.get('valor', 0)),
            categoria=data.get('categoria', 'a classificar')
        )


@dataclass
class ClassificationData:
    """Dados de classificação de uma transação"""
    estabelecimento: str
    data_compra: date
    itens: List[TransactionItem]
    available_categories: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'estabelecimento': self.estabelecimento,
            'data_compra': self.data_compra.isoformat(),
            'itens': [item.to_dict() for item in self.itens],
            'available_categories': self.available_categories
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ClassificationData':
        # Converter data de string para date
        data_compra = date.today()
        if 'data_compra' in data:
            try:
                if isinstance(data['data_compra'], str):
                    data_compra = datetime.fromisoformat(data['data_compra']).date()
                elif isinstance(data['data_compra'], date):
                    data_compra = data['data_compra']
            except:
                data_compra = date.today()
        
        return cls(
            estabelecimento=data.get('estabelecimento', 'Estabelecimento não identificado'),
            data_compra=data_compra,
            itens=[TransactionItem.from_dict(item) for item in data.get('itens', [])],
            available_categories=data.get('available_categories', [])
        )


@dataclass
class TransferData:
    """Dados de uma transferência"""
    valor: float
    conta_origem: str
    conta_destino: str
    data_transferencia: date
    descricao: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'valor': self.valor,
            'conta_origem': self.conta_origem,
            'conta_destino': self.conta_destino,
            'data_transferencia': self.data_transferencia.isoformat(),
            'descricao': self.descricao
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TransferData':
        # Converter data de string para date
        data_transferencia = date.today()
        if 'data_transferencia' in data:
            try:
                if isinstance(data['data_transferencia'], str):
                    data_transferencia = datetime.fromisoformat(data['data_transferencia']).date()
                elif isinstance(data['data_transferencia'], date):
                    data_transferencia = data['data_transferencia']
            except:
                data_transferencia = date.today()
        
        return cls(
            valor=float(data.get('valor', 0)),
            conta_origem=data.get('conta_origem', ''),
            conta_destino=data.get('conta_destino', ''),
            data_transferencia=data_transferencia,
            descricao=data.get('descricao')
        )


@dataclass
class UserContext:
    """Contexto de uma conversa do usuário"""
    user_id: str
    thread_id: str
    attachment_url: Optional[str] = None
    message_content: Optional[str] = None
    classification_data: Optional[ClassificationData] = None
    transfer_data: Optional[TransferData] = None
    waiting_for_account: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        data = {
            'user_id': self.user_id,
            'thread_id': self.thread_id,
            'attachment_url': self.attachment_url,
            'message_content': self.message_content,
            'waiting_for_account': self.waiting_for_account
        }
        
        if self.classification_data:
            data['classification_data'] = self.classification_data.to_dict()
        
        if self.transfer_data:
            data['transfer_data'] = self.transfer_data.to_dict()
        
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserContext':
        context = cls(
            user_id=data.get('user_id', ''),
            thread_id=data.get('thread_id', ''),
            attachment_url=data.get('attachment_url'),
            message_content=data.get('message_content'),
            waiting_for_account=data.get('waiting_for_account', False)
        )
        
        if 'classification_data' in data:
            context.classification_data = ClassificationData.from_dict(data['classification_data'])
        
        if 'transfer_data' in data:
            context.transfer_data = TransferData.from_dict(data['transfer_data'])
        
        return context


@dataclass
class AIResponse:
    """Resposta processada pela IA"""
    action: str
    message: str
    data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'action': self.action,
            'message': self.message,
            'data': self.data
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AIResponse':
        return cls(
            action=data.get('action', 'error'),
            message=data.get('message', ''),
            data=data.get('data')
        )


@dataclass
class MessageIntent:
    """Intenção detectada em uma mensagem"""
    intent: str
    confidence: float
    extracted_data: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'intent': self.intent,
            'confidence': self.confidence,
            'extracted_data': self.extracted_data
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MessageIntent':
        return cls(
            intent=data.get('intent', 'other'),
            confidence=float(data.get('confidence', 0.0)),
            extracted_data=data.get('extracted_data', {})
        ) 