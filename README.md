# Orçamento Bot

O Orçamento Bot é um bot para Discord projetado para otimizar o lançamento de despesas a partir de cupons fiscais. Ele utiliza a API da OpenAI para analisar imagens de recibos, classificar os itens em categorias pré-definidas e, após a confirmação do usuário, salva as transações em um banco de dados PostgreSQL.

## Funcionalidades

- **Análise de Imagens:** Extrai itens e valores de imagens de cupons fiscais.
- **Classificação Inteligente:** Sugere categorias para cada item com base em uma lista personalizada.
- **Fluxo de Conversa Interativo:** Inicia uma thread no Discord para cada recibo, permitindo que o usuário revise e edite a classificação.
- **Processamento de Linguagem Natural:** Compreende os pedidos de edição do usuário em português.
- **Confirmação do Usuário:** Garante que os dados só sejam salvos no banco de dados após a aprovação explícita do usuário.
- **Comunicação em Português:** Toda a interação com o bot é em português brasileiro.

## Configuração e Instalação

Siga os passos abaixo para configurar e executar o bot.

### Pré-requisitos

- Python 3.8 ou superior
- Acesso a um banco de dados PostgreSQL

### 1. Clone o Repositório

```bash
git clone https://github.com/seu-usuario/orcamento-bot.git
cd orcamento-bot
```

### 2. Configure o Banco de Dados

Conecte-se ao seu banco de dados PostgreSQL e execute o script `db.sql` para criar as tabelas `orcamento` and `transacoes`.

```bash
psql -U seu_usuario -d seu_banco -f db.sql
```

Certifique-se de popular a tabela `orcamento` com as categorias que você deseja que o bot utilize para a classificação.

### 3. Instale as Dependências

Instale todas as bibliotecas Python necessárias com o seguinte comando:

```bash
pip install -r requirements.txt
```

### 4. Configure as Variáveis de Ambiente

Crie um arquivo chamado `.env` na raiz do projeto. Você pode renomear o arquivo `.env.example` se ele existir. Preencha o arquivo com as suas credenciais:

```
DISCORD_TOKEN=seu_token_do_discord
OPENAI_API_KEY=sua_chave_da_openai
POSTGRES_URL=postgres://usuario:senha@host:porta/banco_de_dados
TARGET_CHANNEL_ID=id_do_canal_do_discord
```

**Como obter as credenciais:**

- **`POSTGRES_URL`**: É a URL de conexão do seu banco de dados PostgreSQL.
- **`OPENAI_API_KEY`**: Sua chave de API da [plataforma OpenAI](https://platform.openai.com/account/api-keys).
- **`TARGET_CHANNEL_ID`**: O ID do canal do Discord onde o bot irá monitorar o envio de imagens.
    1. Ative o "Modo de Desenvolvedor" no Discord (Configurações > Avançado > Modo de Desenvolvedor).
    2. Clique com o botão direito no canal desejado e selecione "Copiar ID do Canal".
- **`DISCORD_TOKEN`**: O token secreto do seu bot.
    1. Vá para o [Portal de Desenvolvedores do Discord](https://discord.com/developers/applications).
    2. Crie uma "Nova Aplicação" e dê um nome a ela.
    3. Vá para a aba "Bot".
    4. Na seção "Privileged Gateway Intents", ative a **"MESSAGE CONTENT INTENT"**.
    5. No topo da página, clique em "Reset Token" para gerar e copiar seu token. **Trate este token como uma senha!**

### 5. Convide o Bot para o Servidor

Para que o bot funcione, ele precisa ser convidado para o seu servidor Discord.

1.  **Vá para o Portal de Desenvolvedores do Discord** e selecione a sua aplicação.
2.  No menu à esquerda, clique em **OAuth2** e depois em **URL Generator**.
3.  Na seção "Scopes", marque a caixa **`bot`**.
4.  Na seção "Bot Permissions" que aparecerá, marque as seguintes permissões:
    - **View Channel**
    - **Send Messages**
    - **Send Messages in Threads**
    - **Create Public Threads**
    - **Read Message History**
5.  Copie a URL gerada na parte inferior da página.
6.  Cole a URL em uma nova aba do seu navegador, selecione o servidor para o qual deseja convidar o bot e clique em **Autorizar**.

## Executando o Bot

Após concluir a configuração, inicie o bot com o seguinte comando:

```bash
python bot.py
```

## Como Usar

1.  **Envie uma Imagem:** Envie uma imagem de um cupom fiscal no canal do Discord que você definiu em `TARGET_CHANNEL_ID`.
2.  **Aguarde a Análise:** O bot criará uma nova thread e enviará uma mensagem com a análise inicial dos itens, valores e categorias sugeridas.
3.  **Revise e Edite:**
    - Se a classificação estiver correta, responda na thread com `sim`, `ok` ou `pode seguir`.
    - Se precisar de ajustes, diga ao bot o que mudar (ex: "mude café para a categoria alimentação"). O bot fará a alteração e pedirá uma nova confirmação.
4.  **Informe a Conta:** Após a aprovação, o bot pedirá que você informe a `conta` de onde o dinheiro saiu.
5.  **Confirmação Final:** Após você informar a conta, o bot salvará todas as transações no banco de dados e confirmará a operação.
