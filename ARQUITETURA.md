# Arquitetura do Bot de Orçamento

## Visão Geral

O bot de orçamento é uma aplicação Discord que processa transações financeiras através de imagens de cupons fiscais e mensagens de texto. Ele utiliza IA para classificar gastos e transferências, salvando os dados em um banco de dados estruturado.

## Arquitetura Geral

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Discord API   │◄──►│   Bot Discord   │◄──►│   OpenAI API    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │  Banco de Dados │
                       └─────────────────┘
```

## Componentes Principais

### 1. Cliente Discord (`src/bot/discord_bot.py`)

**Responsabilidade**: Orquestra todos os componentes e gerencia a conexão com o Discord.

**Funcionalidades**:

- Inicializa e configura o cliente Discord
- Coordena os diferentes serviços
- Gerencia o ciclo de vida da aplicação

**Fluxo**:

1. Recebe eventos do Discord
2. Roteia para handlers específicos
3. Coordena respostas entre serviços

### 2. Handlers de Eventos (`src/bot/event_handlers.py`)

**Responsabilidade**: Processa eventos específicos do Discord (mensagens, anexos, threads).

**Tipos de Eventos**:

- **Mensagens com imagens**: Cria thread e inicia classificação
- **Mensagens de texto**: Detecta intenção (gasto/transferência)
- **Respostas em threads**: Processa confirmações e edições

**Fluxo de Processamento**:

```
Mensagem → Detecção de Tipo → Criação de Thread → Processamento → Resposta
```

### 3. Handlers de Comandos (`src/bot/command_handlers.py`)

**Responsabilidade**: Processa comandos especiais (ex: `/status`, `/help`, `/usage`).

**Comandos Disponíveis**:

- `/status`: Verifica saúde do sistema
- `/usage`: Mostra uso da OpenAI
- `/contas`: Lista contas disponíveis
- `/categorias`: Lista categorias
- `/transferencias`: Histórico de transferências
- `/help`: Ajuda geral

## Camada de Serviços

### 4. OpenAI Service (`src/services/openai_service.py`)

**Responsabilidade**: Centraliza todas as interações com a API da OpenAI.

**Funcionalidades**:

- **Classificação de imagens**: Analisa cupons fiscais
- **Processamento de texto**: Extrai informações de gastos/transferências
- **Detecção de intenção**: Identifica o tipo de mensagem
- **Identificação de contas**: Mapeia nomes para contas válidas

**Prompts Especializados**:

- **Classificação**: Extrai itens, valores e categorias de cupons
- **Transferências**: Identifica origem, destino e valor
- **Gastos**: Classifica despesas em categorias

### 5. Classification Service (`src/services/classification_service.py`)

**Responsabilidade**: Gerencia o processo de classificação de transações.

**Funcionalidades**:

- **Classificação de imagens**: Processa cupons fiscais
- **Classificação de texto**: Processa gastos informados
- **Edição de classificações**: Permite correções via IA

**Fluxo de Classificação**:

```
Imagem/Texto → OpenAI → Validação → Estruturação → Resposta Formatada
```

### 6. Transfer Service (`src/services/transfer_service.py`)

**Responsabilidade**: Processa transferências entre contas bancárias.

**Funcionalidades**:

- **Detecção de transferências**: Identifica em mensagens de texto
- **Validação de dados**: Verifica contas e valores
- **Edição de transferências**: Permite correções

**Estrutura de Transferência**:

```python
TransferData:
  - valor: float
  - conta_origem: str
  - conta_destino: str
  - data_transferencia: date
  - descricao: Optional[str]
```

### 7. Expense Service (`src/services/expense_service.py`)

**Responsabilidade**: Processa gastos informados em texto.

**Funcionalidades**:

- **Extração de valores**: Identifica valores em mensagens
- **Classificação automática**: Categoriza gastos
- **Validação**: Verifica dados extraídos

## Camada de Utilitários

### 8. State Manager (`src/utils/state_manager.py`)

**Responsabilidade**: Gerencia o estado das conversas ativas.

**Funcionalidades**:

- **Persistência**: Salva/carrega estado em JSON
- **Contexto por thread**: Mantém dados de cada conversa
- **Limpeza automática**: Remove contextos finalizados

**Estrutura de Estado**:

```python
UserContext:
  - user_id: str
  - thread_id: str
  - classification_data: Optional[ClassificationData]
  - transfer_data: Optional[TransferData]
  - waiting_for_account: bool
```

### 9. Validators (`src/utils/validators.py`)

**Responsabilidade**: Valida dados em diferentes pontos do sistema.

**Validações**:

- **Extensões de imagem**: Verifica formatos suportados
- **Itens de transação**: Valida estrutura e valores
- **Dados de transferência**: Verifica contas e valores

### 10. Formatters (`src/utils/formatters.py`)

**Responsabilidade**: Formata dados para exibição ao usuário.

**Formatações**:

- **Resumos por categoria**: Agrupa transações
- **Resumos de transferência**: Formata dados de transferência
- **Mensagens de ajuda**: Textos padronizados

## Modelos de Dados

### 11. Data Models (`src/models/data_models.py`)

**Responsabilidade**: Define estruturas de dados consistentes.

**Modelos Principais**:

```python
TransactionItem:
  - descricao: str
  - valor: float
  - categoria: str

ClassificationData:
  - estabelecimento: str
  - data_compra: date
  - itens: List[TransactionItem]
  - available_categories: List[str]

TransferData:
  - valor: float
  - conta_origem: str
  - conta_destino: str
  - data_transferencia: date
  - descricao: Optional[str]
```

## Fluxo de Processamento

### Processamento de Imagem

```
1. Usuário envia imagem
2. Bot cria thread
3. OpenAI analisa imagem
4. ClassificationService estrutura dados
5. Bot mostra resumo
6. Usuário confirma/edita
7. Bot salva no banco
```

### Processamento de Transferência

```
1. Usuário envia mensagem
2. OpenAI detecta intenção
3. TransferService processa dados
4. Bot cria thread com resumo
5. Usuário confirma/edita
6. Bot salva transferência
```

### Processamento de Gasto

```
1. Usuário envia mensagem
2. OpenAI detecta intenção
3. ExpenseService processa dados
4. Bot cria thread com classificação
5. Usuário confirma/edita
6. Bot salva transações
```

## Integração com Banco de Dados

### Operações Principais

- **Inserção de transações**: Salva itens classificados
- **Inserção de transferências**: Registra movimentações entre contas
- **Consulta de categorias**: Lista categorias disponíveis
- **Consulta de contas**: Lista contas configuradas
- **Histórico de transferências**: Busca movimentações recentes

### Estrutura de Dados

- **Transações**: Agrupadas por categoria e data
- **Transferências**: Registradas com origem, destino e valor
- **Categorias**: Configuráveis via banco
- **Contas**: Configuráveis via banco

## Tratamento de Erros

### Estratégias de Fallback

1. **OpenAI indisponível**: Usa lógica programática simples
2. **Banco indisponível**: Logs de erro e retry
3. **Dados inválidos**: Validação e mensagens de erro
4. **Comandos não reconhecidos**: Sugestões de ajuda

### Logging

- **Estruturado**: Formato consistente
- **Níveis**: INFO, WARNING, ERROR
- **Arquivo**: `bot.log` para persistência
- **Console**: Output em tempo real

## Configuração

### Variáveis de Ambiente

- **DISCORD_TOKEN**: Token do bot Discord
- **OPENAI_API_KEY**: Chave da API OpenAI
- **TARGET_CHANNEL_ID**: Canal principal do bot
- **DATABASE_URL**: Conexão com banco de dados

### Configurações de OpenAI

- **Modelo**: GPT-4 Vision para imagens
- **Tokens máximos**: Configurável por operação
- **Temperatura**: Baixa para consistência

## Monitoramento e Saúde

### Comandos de Status

- **`/status`**: Verifica conectividade
- **`/usage`**: Monitora uso da OpenAI
- **`/ping`**: Testa latência

### Métricas

- **Conexões**: Discord, OpenAI, Banco
- **Uso de tokens**: Consumo da OpenAI
- **Transações processadas**: Volume de dados
- **Erros**: Taxa de falhas

## Segurança

### Validações

- **Entrada de usuário**: Sanitização e validação
- **Dados de API**: Verificação de estrutura
- **Permissões**: Controle de acesso por canal

### Dados Sensíveis

- **Tokens**: Armazenados em variáveis de ambiente
- **Dados financeiros**: Criptografados no banco
- **Logs**: Sem informações sensíveis

## Escalabilidade

### Pontos de Melhoria

- **Cache**: Para categorias e contas frequentes
- **Queue**: Para processamento assíncrono
- **Rate limiting**: Para APIs externas
- **Load balancing**: Para múltiplas instâncias

### Arquitetura Preparada

- **Modular**: Fácil adição de novos serviços
- **Desacoplada**: Baixa dependência entre componentes
- **Testável**: Estrutura preparada para testes
- **Configurável**: Parâmetros externalizados
