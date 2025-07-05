import discord
import openai
import logging
import json
import datetime
import re
from typing import Dict, Any, Optional, List
from config import Config
from database import db_manager, get_categories, insert_transaction, check_database_connection, db_manager, insert_transfer, get_transfer_history

# Configurar logging estruturado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Validar configuração
try:
    Config.validate()
except ValueError as e:
    logger.error(f"Erro de configuração: {e}")
    exit(1)

# Inicializar OpenAI
openai_client = openai.OpenAI(api_key=Config.OPENAI_API_KEY)

# Configurar Discord
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

client = discord.Client(intents=intents)
user_classifications = {}

def save_state():
    """Salva o estado das conversas"""
    try:
        with open(Config.STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(user_classifications, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Estado salvo com {len(user_classifications)} conversas")
    except Exception as e:
        logger.error(f"Erro ao salvar estado: {e}")

def load_state():
    """Carrega o estado das conversas"""
    global user_classifications
    try:
        with open(Config.STATE_FILE, "r", encoding="utf-8") as f:
            user_classifications = json.load(f)
        logger.info(f"Estado carregado com {len(user_classifications)} conversas")
    except FileNotFoundError:
        logger.info("Arquivo de estado não encontrado, iniciando com estado vazio")
        user_classifications = {}
    except Exception as e:
        logger.error(f"Erro ao carregar estado: {e}")
        user_classifications = {}

async def check_openai_connection():
    """Verifica conexão com OpenAI"""
    try:
        openai_client.models.list()
        return True, "Conexão com a API da OpenAI bem-sucedida."
    except Exception as e:
        logger.error(f"Erro ao conectar com OpenAI: {e}")
        return False, f"Erro ao conectar com a API da OpenAI: {e}"

async def get_openai_usage():
    """Obtém informações de uso da OpenAI"""
    try:
        # Tentar obter informações de uso da API usando a nova API de billing
        try:
            # Usar a API de billing para obter informações de uso
            billing_response = openai_client.billing.usage.list()
            
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
            # Tentar usar a API de usage (método alternativo)
            usage_response = openai_client.usage.list()
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

def validate_image_extension(filename: str) -> bool:
    """Valida extensão de imagem"""
    if not filename:
        return False
    file_ext = filename.lower()
    return any(file_ext.endswith(ext) for ext in Config.SUPPORTED_IMAGE_EXTENSIONS)

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

async def identify_account_with_ai(user_input: str, available_accounts: List[str]) -> str:
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

        response = openai_client.chat.completions.create(
            model=Config.OPENAI_MODEL,
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

async def process_user_input_with_ai(user_input: str, context: Dict[str, Any]) -> Dict[str, Any]:
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
            if isinstance(obj, datetime.date):
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

        response = openai_client.chat.completions.create(
            model=Config.OPENAI_MODEL,
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
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"Erro JSON ao processar comando: {e}")
        # Fallback para comandos simples
        user_input_lower = user_input.lower()
        if any(keyword in user_input_lower for keyword in ["sim", "ok", "pode seguir", "confirmo", "correto", "manda bala", "confirma"]):
            return {"action": "confirm", "message": "Confirmação recebida"}
        elif any(keyword in user_input_lower for keyword in ["troque", "mude", "altere", "corrija"]):
            return {"action": "edit", "message": "Editando classificação"}
        elif any(keyword in user_input_lower for keyword in ["ajuda", "help", "comandos"]):
            return {"action": "help", "message": "Mostrando ajuda"}
        else:
            return {"action": "account", "message": "Processando como conta"}
            
    except Exception as e:
        logger.error(f"Erro ao processar comando com OpenAI: {e}")
        return {
            "action": "error",
            "message": "Desculpe, não consegui processar seu comando. Tente novamente.",
            "data": {}
        }

@client.event
async def on_ready():
    """Evento de inicialização do bot"""
    logger.info(f'Bot conectado como {client.user}')
    
    try:
        # Inicializar banco de dados
        await db_manager.initialize()
        load_state()
        
        # Verificar conexões silenciosamente
        db_ok, db_msg = await check_database_connection()
        openai_ok, openai_msg = await check_openai_connection()
        
        if not db_ok:
            logger.error(f'Erro no banco de dados: {db_msg}')
        if not openai_ok:
            logger.error(f'Erro na OpenAI: {openai_msg}')
        
        if db_ok:
            categories, cat_msg = await get_categories()
            if cat_msg:
                logger.error(f'Erro ao buscar categorias: {cat_msg}')
            else:
                logger.info(f'{len(categories)} categorias carregadas.')
        
        logger.info('Bot inicializado com sucesso.')
        
    except Exception as e:
        logger.error(f'Erro na inicialização: {e}')

@client.event
async def on_message(message):
    """Processa mensagens recebidas"""
    if message.author == client.user:
        return

    try:
        # Processar comandos especiais no canal principal
        if message.channel.id == Config.TARGET_CHANNEL_ID and message.content.startswith('/'):
            command = message.content[1:].lower().strip()
            await handle_command(message, command)
            return

        # Processar imagens no canal principal
        if message.channel.id == Config.TARGET_CHANNEL_ID and message.attachments:
            for attachment in message.attachments:
                if validate_image_extension(attachment.filename):
                    thread = await message.create_thread(name=f"Classificação de {attachment.filename}")
                    user_classifications[str(thread.id)] = {
                        "attachment_url": attachment.url,
                        "user_id": str(message.author.id)
                    }
                    save_state()
                    await thread.send("Olá! Recebi a sua imagem e vou analisá-la. Em breve, enviarei a classificação dos produtos.")
                    await process_image(thread, attachment.url)

        # Processar mensagens de texto no canal principal
        elif message.channel.id == Config.TARGET_CHANNEL_ID and not message.attachments:
            # Detectar intenção da mensagem com OpenAI
            intent_result = await detect_message_intent_with_ai(message.content)
            
            if intent_result["intent"] == "transfer":
                # Processar transferência
                extracted_data = intent_result.get("extracted_data", {})
                valor = extracted_data.get("valor", 0)
                thread_name = f"Transferência de R$ {valor:.2f}" if valor > 0 else "Transferência"
                
                thread = await message.create_thread(name=thread_name)
                user_classifications[str(thread.id)] = {
                    "message_content": message.content,
                    "user_id": str(message.author.id)
                }
                save_state()
                await thread.send("Olá! Identifiquei uma transferência na sua mensagem. Vou analisá-la e processar.")
                await process_transfer_with_ai(thread, message.content)
                
            elif intent_result["intent"] == "expense":
                # Processar gasto
                extracted_data = intent_result.get("extracted_data", {})
                valor = extracted_data.get("valor", 0)
                thread_name = f"Gasto de R$ {valor:.2f}" if valor > 0 else "Gasto"
                
                thread = await message.create_thread(name=thread_name)
                user_classifications[str(thread.id)] = {
                    "message_content": message.content,
                    "user_id": str(message.author.id)
                }
                save_state()
                await thread.send(f"Olá! Identifiquei um gasto na sua mensagem. Vou analisá-lo e gerar uma classificação.")
                await process_text_expense(thread, message.content)

        # Processar respostas em threads
        elif str(message.channel.id) in user_classifications:
            thread_id = str(message.channel.id)
            if "classification_data" in user_classifications[thread_id]:
                await handle_user_response(message)
            elif "transfer_data" in user_classifications[thread_id]:
                await handle_transfer_response(message)

    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")
        try:
            await message.channel.send("Desculpe, ocorreu um erro ao processar sua mensagem. Tente novamente.")
        except:
            pass

async def process_image(thread, attachment_url):
    """Processa imagem com OpenAI"""
    try:
        categories, error_msg = await get_categories()
        if error_msg:
            await thread.send(f"Ocorreu um erro ao buscar as categorias: {error_msg}")
            return

        response = openai_client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Analise esta imagem de um cupom fiscal brasileiro. Extraia cada item, seu valor e classifique-o em uma das seguintes categorias: {categories}. Também identifique o nome do estabelecimento onde a compra foi feita (ex: Supermercado, Farmácia, etc) e a data da compra. Retorne um JSON com a seguinte estrutura: {{\"estabelecimento\": \"nome do estabelecimento\", \"data\": \"YYYY-MM-DD\", \"itens\": [{{'descricao': 'item', 'valor': valor, 'categoria': 'categoria'}}]}}. Se não conseguir identificar o estabelecimento, use \"Estabelecimento não identificado\". Se não conseguir identificar a data, use a data atual. Se não tiver certeza sobre a categoria de um item, use 'a classificar'."},
                        {
                            "type": "image_url",
                            "image_url": {"url": attachment_url}
                        }
                    ]
                }
            ],
            max_tokens=Config.OPENAI_MAX_TOKENS,
        )
        
        response_json = response.choices[0].message.content
        clean_response_json = response_json.strip().replace("```json", "").replace("```", "")
        parsed_data = json.loads(clean_response_json)
        
        # Extrair estabelecimento, data e itens
        estabelecimento = parsed_data.get('estabelecimento', 'Estabelecimento não identificado')
        
        # Extrair e validar data
        data_str = parsed_data.get('data', None)
        if data_str:
            try:
                # Tentar converter a data para datetime
                data_compra = datetime.datetime.strptime(data_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                # Se não conseguir converter, usar data atual
                data_compra = datetime.date.today()
        else:
            # Se não houver data, usar data atual
            data_compra = datetime.date.today()
        
        # Verificar se a resposta tem a estrutura esperada
        if 'itens' in parsed_data:
            data = parsed_data.get('itens', [])
        else:
            # Fallback para estrutura antiga (compatibilidade)
            data = parsed_data if isinstance(parsed_data, list) else []
            estabelecimento = 'Estabelecimento não identificado'
        
        # Validar dados recebidos
        for item in data:
            if not item.get('descricao') or not item.get('categoria'):
                raise ValueError("Dados inválidos recebidos da OpenAI")
            try:
                float(item.get('valor', 0))
            except (ValueError, TypeError):
                raise ValueError("Valor inválido recebido da OpenAI")
        
        user_classifications[str(thread.id)]["classification_data"] = data
        user_classifications[str(thread.id)]["estabelecimento"] = estabelecimento
        user_classifications[str(thread.id)]["data_compra"] = data_compra
        user_classifications[str(thread.id)]["available_categories"] = categories
        save_state()
        
        # Agrupar e mostrar resumo por categoria
        grouped_transactions = group_transactions_by_category(data)
        summary = format_grouped_summary(grouped_transactions, estabelecimento)
        summary += f"\n\n📅 **Data da compra:** {data_compra.strftime('%d/%m/%Y')}"
        summary += "\n\nPor favor, verifique a classificação. Se estiver tudo certo, digite 'sim' ou 'ok'. Se precisar de alguma alteração, me diga o que devo mudar."
        
        await thread.send(summary)
        logger.info(f"Imagem processada com sucesso para thread {thread.id}")

    except Exception as e:
        logger.error(f"Erro ao processar imagem: {e}")
        await thread.send(f"Ocorreu um erro ao processar a imagem: {e}")

async def handle_user_response(message):
    """Processa resposta do usuário com OpenAI"""
    try:
        thread_id = str(message.channel.id)
        user_input = message.content
        context = user_classifications[thread_id].copy()
        
        # Processar comando com OpenAI
        ai_response = await process_user_input_with_ai(user_input, context)
        
        if ai_response["action"] == "confirm":
            await message.channel.send("Ótimo! Por favor, me informe a **conta** para que eu possa salvar as transações.")
            user_classifications[thread_id]["waiting_for_account"] = True
            save_state()
            
        elif ai_response["action"] == "edit":
            # Usar OpenAI para editar classificação
            await edit_classification_with_ai(message, context)
            
        elif ai_response["action"] == "account":
            # Usuário forneceu conta (pode ser na primeira mensagem ou após confirmação)
            await save_transactions(message, context)
            
        elif ai_response["action"] == "help":
            help_message = """**Comandos disponíveis:**
- `sim`, `ok`, `pode seguir` - Confirma a classificação
- `mude [item] para [categoria]` - Altera categoria de um item
- `troque [categoria] por [nova_categoria]` - Altera uma categoria
- `ajuda` - Mostra esta mensagem"""
            await message.channel.send(help_message)
            
        else:
            await message.channel.send(ai_response["message"])
            
    except Exception as e:
        logger.error(f"Erro ao processar resposta do usuário: {e}")
        await message.channel.send("Desculpe, ocorreu um erro. Tente novamente.")

async def edit_classification_with_ai(message, context):
    """Edita classificação usando OpenAI"""
    try:
        # Primeiro, tentar extrair informações específicas do comando
        user_input = message.content.lower()
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
            updated_data = context['classification_data'].copy()
            
            # Aplicar mudança de categoria se especificada
            if target_category:
                for item in updated_data:
                    item['categoria'] = target_category
            
            # Aplicar redistribuição de valores se especificada
            if target_total:
                updated_data = redistribute_values_for_total(updated_data, target_total)
            
            # Validar dados atualizados
            for item in updated_data:
                if not item.get('descricao') or not item.get('categoria'):
                    raise ValueError("Dados inválidos na edição")
                try:
                    float(item.get('valor', 0))
                except (ValueError, TypeError):
                    raise ValueError("Valor inválido na edição")
            
            user_classifications[str(message.channel.id)]["classification_data"] = updated_data
            save_state()
            
            # Agrupar e mostrar resumo por categoria
            grouped_transactions = group_transactions_by_category(updated_data)
            estabelecimento = context.get('estabelecimento', 'Estabelecimento não identificado')
            data_compra = context.get('data_compra', datetime.date.today())
            
            # Garantir que data_compra seja um objeto date
            if isinstance(data_compra, str):
                try:
                    data_compra = datetime.datetime.fromisoformat(data_compra).date()
                except:
                    data_compra = datetime.date.today()
            
            summary = format_grouped_summary(grouped_transactions, estabelecimento)
            summary += f"\n\n📅 **Data da compra:** {data_compra.strftime('%d/%m/%Y')}"
            summary += "\n\nEstá correto agora? Se sim, digite 'sim' ou 'ok'."
            await message.channel.send(summary)
            return
        
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

        user_prompt = f"""
Lista atual: {json.dumps(context['classification_data'])}
Categorias disponíveis: {context['available_categories']}
Comando do usuário: '{message.content}'

Atualize a lista conforme solicitado e retorne APENAS o JSON."""

        response = openai_client.chat.completions.create(
            model=Config.OPENAI_MODEL,
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
        
        updated_data = json.loads(content)
        
        # Validar dados atualizados
        for item in updated_data:
            if not item.get('descricao') or not item.get('categoria'):
                raise ValueError("Dados inválidos na edição")
            try:
                float(item.get('valor', 0))
            except (ValueError, TypeError):
                raise ValueError("Valor inválido na edição")
        
        user_classifications[str(message.channel.id)]["classification_data"] = updated_data
        save_state()
        
        # Agrupar e mostrar resumo por categoria
        grouped_transactions = group_transactions_by_category(updated_data)
        estabelecimento = context.get('estabelecimento', 'Estabelecimento não identificado')
        data_compra = context.get('data_compra', datetime.date.today())
        
        # Garantir que data_compra seja um objeto date
        if isinstance(data_compra, str):
            try:
                data_compra = datetime.datetime.fromisoformat(data_compra).date()
            except:
                data_compra = datetime.date.today()
        
        summary = format_grouped_summary(grouped_transactions, estabelecimento)
        summary += f"\n\n📅 **Data da compra:** {data_compra.strftime('%d/%m/%Y')}"
        summary += "\n\nEstá correto agora? Se sim, digite 'sim' ou 'ok'."
        await message.channel.send(summary)
        
    except json.JSONDecodeError as e:
        logger.error(f"Erro JSON ao editar classificação: {e}")
        await message.channel.send("Desculpe, não consegui entender a alteração. Tente ser mais específico, por exemplo: 'mude café para alimentação'")
    except Exception as e:
        logger.error(f"Erro ao editar classificação: {e}")
        await message.channel.send("Desculpe, não consegui fazer a alteração. Tente ser mais específico.")

async def save_transactions(message, context):
    """Salva transações no banco de dados"""
    try:
        user_input = message.content
        # Usar a data detectada pela OpenAI, ou data atual como fallback
        data_compra = context.get("data_compra", datetime.date.today())
        
        # Garantir que data_compra seja um objeto date
        if isinstance(data_compra, str):
            try:
                data_compra = datetime.datetime.fromisoformat(data_compra).date()
            except:
                data_compra = datetime.date.today()
        
        classification_data = context["classification_data"]
        
        # Buscar contas disponíveis e identificar a conta
        available_accounts = await db_manager.get_available_accounts()
        conta = await identify_account_with_ai(user_input, available_accounts)
        
        # Validar se a conta existe (se não existir, usar como está)
        if available_accounts and conta not in available_accounts:
            await message.channel.send(f"⚠️ Conta '{conta}' não encontrada nas contas disponíveis: {', '.join(available_accounts)}")
            await message.channel.send("Por favor, informe uma conta válida ou confirme se deseja usar esta conta mesmo assim.")
            return
        
        # Agrupar transações por categoria
        grouped_transactions = group_transactions_by_category(classification_data)
        
        # Salvar transações agrupadas
        estabelecimento = context.get('estabelecimento', 'Estabelecimento não identificado')
        saved_count, error_count = await db_manager.insert_grouped_transactions(
            data_compra, grouped_transactions, conta, estabelecimento
        )
        
        if saved_count > 0:
            await message.channel.send(f"✅ {saved_count} categorias salvas com sucesso na conta '{conta}'!")
        if error_count > 0:
            await message.channel.send(f"❌ {error_count} categorias falharam ao salvar.")
        
        await message.channel.send("Este tópico será arquivado. Obrigado!")
        del user_classifications[str(message.channel.id)]
        save_state()
        
    except Exception as e:
        logger.error(f"Erro ao salvar transações: {e}")
        await message.channel.send("Erro ao salvar transações. Tente novamente.")

async def save_transfer(message, context):
    """Salva transferência no banco de dados"""
    try:
        transfer_data = context["transfer_data"]
        
        # Extrair dados da transferência
        valor = transfer_data["valor"]
        conta_origem = transfer_data["conta_origem"]
        conta_destino = transfer_data["conta_destino"]
        data_transferencia = transfer_data["data_transferencia"]
        descricao = transfer_data["descricao"]
        
        # Garantir que data_transferencia seja um objeto date
        if isinstance(data_transferencia, str):
            try:
                data_transferencia = datetime.datetime.fromisoformat(data_transferencia).date()
            except:
                data_transferencia = datetime.date.today()
        
        # Salvar transferência no banco
        success, message_result = await insert_transfer(
            data_transferencia, valor, conta_origem, conta_destino, descricao
        )
        
        if success:
            await message.channel.send(f"✅ Transferência de R$ {valor:.2f} de '{conta_origem}' para '{conta_destino}' realizada com sucesso!")
        else:
            await message.channel.send(f"❌ Erro ao salvar transferência: {message_result}")
            return
        
        await message.channel.send("Este tópico será arquivado. Obrigado!")
        del user_classifications[str(message.channel.id)]
        save_state()
        
    except Exception as e:
        logger.error(f"Erro ao salvar transferência: {e}")
        await message.channel.send("Erro ao salvar transferência. Tente novamente.")

async def process_text_expense(thread, message_content: str):
    """Processa gasto informado em texto com OpenAI"""
    try:
        categories, error_msg = await get_categories()
        if error_msg:
            await thread.send(f"Ocorreu um erro ao buscar as categorias: {error_msg}")
            return

        # Obter data atual
        data_atual = datetime.date.today()
        
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

        response = openai_client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=Config.OPENAI_MAX_TOKENS,
        )
        
        response_json = response.choices[0].message.content
        clean_response_json = response_json.strip().replace("```json", "").replace("```", "")
        parsed_data = json.loads(clean_response_json)
        
        # Extrair estabelecimento, data e itens
        estabelecimento = parsed_data.get('estabelecimento', 'Estabelecimento não identificado')
        
        # Extrair e validar data
        data_str = parsed_data.get('data', None)
        if data_str:
            try:
                data_compra = datetime.datetime.strptime(data_str, '%Y-%m-%d').date()
                # Verificar se a data não é muito antiga (mais de 30 dias)
                data_limite = data_atual - datetime.timedelta(days=30)
                if data_compra < data_limite:
                    logger.warning(f"Data muito antiga retornada pela OpenAI: {data_compra}, usando data atual: {data_atual}")
                    data_compra = data_atual
            except (ValueError, TypeError):
                data_compra = data_atual
        else:
            data_compra = data_atual
        
        # Verificar se a resposta tem a estrutura esperada
        if 'itens' in parsed_data:
            data = parsed_data.get('itens', [])
        else:
            data = parsed_data if isinstance(parsed_data, list) else []
            estabelecimento = 'Estabelecimento não identificado'
        
        # Validar dados recebidos
        for item in data:
            if not item.get('descricao') or not item.get('categoria'):
                raise ValueError("Dados inválidos recebidos da OpenAI")
            try:
                float(item.get('valor', 0))
            except (ValueError, TypeError):
                raise ValueError("Valor inválido recebido da OpenAI")
        
        user_classifications[str(thread.id)]["classification_data"] = data
        user_classifications[str(thread.id)]["estabelecimento"] = estabelecimento
        user_classifications[str(thread.id)]["data_compra"] = data_compra
        user_classifications[str(thread.id)]["available_categories"] = categories
        save_state()
        
        # Agrupar e mostrar resumo por categoria
        grouped_transactions = group_transactions_by_category(data)
        summary = format_grouped_summary(grouped_transactions, estabelecimento)
        summary += f"\n\n📅 **Data da compra:** {data_compra.strftime('%d/%m/%Y')}"
        summary += "\n\nPor favor, verifique a classificação. Se estiver tudo certo, digite 'sim' ou 'ok'. Se precisar de alguma alteração, me diga o que devo mudar."
        
        await thread.send(summary)
        logger.info(f"Gasto em texto processado com sucesso para thread {thread.id}")

    except Exception as e:
        logger.error(f"Erro ao processar gasto em texto: {e}")
        await thread.send(f"Ocorreu um erro ao processar o gasto: {e}")

async def process_transfer_with_ai(thread, message_content: str):
    """Processa transferência informada em texto com OpenAI"""
    try:
        # Obter contas disponíveis
        available_accounts = await db_manager.get_available_accounts()
        if not available_accounts:
            await thread.send("Erro: Não foi possível obter a lista de contas disponíveis.")
            return

        # Obter data atual
        data_atual = datetime.date.today()
        
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

        response = openai_client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=Config.OPENAI_MAX_TOKENS,
        )
        
        response_json = response.choices[0].message.content
        clean_response_json = response_json.strip().replace("```json", "").replace("```", "")
        parsed_data = json.loads(clean_response_json)
        
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
                data_transferencia = datetime.datetime.strptime(data_str, '%Y-%m-%d').date()
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
        
        # Salvar dados da transferência no estado
        user_classifications[str(thread.id)]["transfer_data"] = {
            "valor": valor,
            "conta_origem": conta_origem,
            "conta_destino": conta_destino,
            "data_transferencia": data_transferencia,
            "descricao": descricao
        }
        save_state()
        
        # Mostrar resumo da transferência para confirmação
        summary = f"""**💸 Transferência Detectada**

💰 **Valor:** R$ {valor:.2f}
📤 **De:** {conta_origem}
📥 **Para:** {conta_destino}
📅 **Data:** {data_transferencia.strftime('%d/%m/%Y')}
📝 **Descrição:** {descricao}

Por favor, confirme se está correto. Digite 'sim' ou 'ok' para confirmar, ou me diga o que deve ser alterado."""
        
        await thread.send(summary)
        logger.info(f"Transferência processada com sucesso para thread {thread.id}")

    except Exception as e:
        logger.error(f"Erro ao processar transferência: {e}")
        await thread.send(f"Ocorreu um erro ao processar a transferência: {e}")

async def handle_transfer_response(message):
    """Processa resposta do usuário para transferências"""
    try:
        thread_id = str(message.channel.id)
        user_input = message.content
        context = user_classifications[thread_id].copy()
        
        # Processar comando com OpenAI
        ai_response = await process_user_input_with_ai(user_input, context)
        
        if ai_response["action"] == "confirm":
            # Salvar transferência
            await save_transfer(message, context)
            
        elif ai_response["action"] == "edit":
            # Usar OpenAI para editar transferência
            await edit_transfer_with_ai(message, context)
            
        elif ai_response["action"] == "help":
            help_message = """**Comandos disponíveis para transferências:**
- `sim`, `ok`, `pode seguir` - Confirma a transferência
- `mude valor para [novo_valor]` - Altera o valor da transferência
- `troque conta origem para [nova_conta]` - Altera a conta de origem
- `troque conta destino para [nova_conta]` - Altera a conta de destino
- `mude descrição para [nova_descricao]` - Altera a descrição da transferência
- `ajuda` - Mostra esta mensagem"""
            await message.channel.send(help_message)
            
        else:
            await message.channel.send(ai_response["message"])
            
    except Exception as e:
        logger.error(f"Erro ao processar resposta de transferência: {e}")
        await message.channel.send("Desculpe, ocorreu um erro. Tente novamente.")

async def handle_command(message, command):
    """Processa comandos especiais"""
    try:
        if command == "status":
            await handle_status_command(message)
        elif command == "usage":
            await handle_usage_command(message)
        elif command == "contas":
            await handle_contas_command(message)
        elif command == "categorias":
            await handle_categorias_command(message)
        elif command == "help":
            await handle_help_command(message)
        elif command == "ping":
            await handle_ping_command(message)
        elif command == "transferencias":
            await handle_transferencias_command(message)
        else:
            await message.channel.send("❌ Comando não reconhecido. Digite `/help` para ver os comandos disponíveis.")
    except Exception as e:
        logger.error(f"Erro ao processar comando {command}: {e}")
        await message.channel.send("❌ Erro ao processar comando. Tente novamente.")

async def handle_status_command(message):
    """Comando status - verifica se o bot está online"""
    try:
        db_ok, db_msg = await check_database_connection()
        openai_ok, openai_msg = await check_openai_connection()
        
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

async def handle_usage_command(message):
    """Comando usage - mostra uso de tokens da OpenAI"""
    try:
        usage_ok, usage_msg = await get_openai_usage()
        
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

async def handle_contas_command(message):
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

async def handle_categorias_command(message):
    """Comando categorias - lista todas as categorias disponíveis"""
    try:
        categories, error_msg = await get_categories()
        
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

async def handle_help_command(message):
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

async def handle_ping_command(message):
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

async def handle_transferencias_command(message):
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

async def detect_message_intent_with_ai(message_content: str) -> Dict[str, Any]:
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

        response = openai_client.chat.completions.create(
            model=Config.OPENAI_MODEL,
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
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"Erro JSON ao detectar intenção: {e}")
        # Fallback: assumir que é um gasto se contém palavras-chave
        message_lower = message_content.lower()
        if any(keyword in message_lower for keyword in ["transferi", "transf", "movi", "para", "pra"]):
            return {"intent": "transfer", "confidence": 0.7, "extracted_data": {}}
        elif any(keyword in message_lower for keyword in ["gastei", "comprei", "paguei", "mercado", "farmácia"]):
            return {"intent": "expense", "confidence": 0.7, "extracted_data": {}}
        else:
            return {"intent": "other", "confidence": 0.5, "extracted_data": {}}
            
    except Exception as e:
        logger.error(f"Erro ao detectar intenção com OpenAI: {e}")
        return {
            "intent": "other",
            "confidence": 0.0,
            "extracted_data": {},
            "error": str(e)
        }

async def edit_transfer_with_ai(message, context):
    """Edita transferência usando OpenAI"""
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
Transferência atual: {json.dumps(context['transfer_data'])}
Comando do usuário: '{message.content}'

Atualize a transferência conforme solicitado e retorne APENAS o JSON."""

        response = openai_client.chat.completions.create(
            model=Config.OPENAI_MODEL,
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
        
        user_classifications[str(message.channel.id)]["transfer_data"] = updated_data
        save_state()
        
        # Mostrar resumo da transferência atualizada
        valor = updated_data.get("valor", context["transfer_data"]["valor"])
        conta_origem = updated_data.get("conta_origem", context["transfer_data"]["conta_origem"])
        conta_destino = updated_data.get("conta_destino", context["transfer_data"]["conta_destino"])
        data_transferencia = updated_data.get("data_transferencia", context["transfer_data"]["data_transferencia"])
        descricao = updated_data.get("descricao", context["transfer_data"]["descricao"])
        
        # Garantir que data_transferencia seja um objeto date
        if isinstance(data_transferencia, str):
            try:
                data_transferencia = datetime.datetime.fromisoformat(data_transferencia).date()
            except:
                data_transferencia = datetime.date.today()
        
        summary = f"""**💸 Transferência Atualizada**

💰 **Valor:** R$ {valor:.2f}
📤 **De:** {conta_origem}
📥 **Para:** {conta_destino}
📅 **Data:** {data_transferencia.strftime('%d/%m/%Y')}
📝 **Descrição:** {descricao}

Está correto agora? Se sim, digite 'sim' ou 'ok'."""
        await message.channel.send(summary)
        
    except json.JSONDecodeError as e:
        logger.error(f"Erro JSON ao editar transferência: {e}")
        await message.channel.send("Desculpe, não consegui entender a alteração. Tente ser mais específico, por exemplo: 'mude valor para 3000'")
    except Exception as e:
        logger.error(f"Erro ao editar transferência: {e}")
        await message.channel.send("Desculpe, não consegui fazer a alteração. Tente ser mais específico.")

# Inicializar bot
try:
    client.run(Config.DISCORD_TOKEN)
except Exception as e:
    logger.error(f"Erro ao iniciar bot: {e}")
finally:
    # Limpar recursos
    try:
        db_manager.close()
    except:
        pass
