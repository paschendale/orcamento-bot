import discord
import openai
import logging
import json
import datetime
import re
from typing import Dict, Any, Optional, List
from config import Config
from database import db_manager, get_categories, insert_transaction, check_database_connection, db_manager

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
        if 'data_compra' in context_for_json and isinstance(context_for_json['data_compra'], datetime.date):
            context_for_json['data_compra'] = context_for_json['data_compra'].isoformat()

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
        if any(keyword in user_input_lower for keyword in ["sim", "ok", "pode seguir", "confirmo", "correto"]):
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
        
        channel = client.get_channel(Config.TARGET_CHANNEL_ID)
        if not channel:
            logger.error('Canal não encontrado. Verifique o TARGET_CHANNEL_ID.')
            return
        
        # Verificar conexões
        db_ok, db_msg = await check_database_connection()
        openai_ok, openai_msg = await check_openai_connection()
        
        # Construir mensagem de status
        status_message = "**Status do Bot:**\n"
        status_message += f"- Banco de Dados: {'✅' if db_ok else '❌'} {db_msg}\n"
        status_message += f"- OpenAI: {'✅' if openai_ok else '❌'} {openai_msg}\n"
        
        cat_msg = None
        if db_ok:
            categories, cat_msg = await get_categories()
            if cat_msg:
                logger.error(f'Erro ao buscar categorias: {cat_msg}')
                status_message += f"- Categorias: ❌ {cat_msg}\n"
            else:
                logger.info(f'{len(categories)} categorias carregadas.')
                status_message += f"- Categorias: ✅ {len(categories)} categorias carregadas.\n"
        
        if db_ok and openai_ok and not cat_msg:
            status_message += "\nEstou online e pronto para receber imagens! 🤖"
        else:
            status_message += "\nO bot encontrou problemas na inicialização. Por favor, verifique os logs."
        
        await channel.send(status_message)
        logger.info('Mensagem de status enviada com sucesso.')
        
    except Exception as e:
        logger.error(f'Erro na inicialização: {e}')

@client.event
async def on_message(message):
    """Processa mensagens recebidas"""
    if message.author == client.user:
        return

    try:
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

        # Processar mensagens de texto com gastos no canal principal
        elif message.channel.id == Config.TARGET_CHANNEL_ID and not message.attachments:
            expense_info = detect_expense_in_message(message.content)
            if expense_info:
                thread = await message.create_thread(name=f"Gasto de R$ {expense_info['value']:.2f}")
                user_classifications[str(thread.id)] = {
                    "message_content": message.content,
                    "user_id": str(message.author.id)
                }
                save_state()
                await thread.send(f"Olá! Identifiquei um gasto de R$ {expense_info['value']:.2f} na sua mensagem. Vou analisá-lo e gerar uma classificação.")
                await process_text_expense(thread, message.content)

        # Processar respostas em threads
        elif str(message.channel.id) in user_classifications:
            thread_id = str(message.channel.id)
            if "classification_data" in user_classifications[thread_id]:
                await handle_user_response(message)

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

def detect_expense_in_message(message_content: str) -> Optional[Dict[str, Any]]:
    """Detecta se uma mensagem contém informações de gasto"""
    # Padrões para detectar gastos
    patterns = [
        # Padrão: "gastei R$ 50 no mercado" ou "comprei R$ 30 de comida"
        r'(?:gastei|comprei|paguei|gastei|compras?|mercado|farmácia|farmacia|restaurante|lanche|uber|99|ifood|rappi|delivery|alimentação|alimentacao)\s+(?:de\s+)?(?:r?\$?\s*)?([\d,]+\.?\d*)',
        # Padrão: "R$ 25,50 no supermercado" ou "$ 15.30 na farmácia"
        r'(?:r?\$?\s*)([\d,]+\.?\d*)\s+(?:no|na|em|para|com|de)\s+(?:mercado|supermercado|farmácia|farmacia|restaurante|lanche|uber|99|ifood|rappi|delivery|alimentação|alimentacao|compras?)',
        # Padrão: "compras: R$ 45,60" ou "gastos: $ 30"
        r'(?:compras?|gastos?|total|valor):\s*(?:r?\$?\s*)?([\d,]+\.?\d*)',
        # Padrão: "R$ 50" seguido de contexto de compra
        r'(?:r?\$?\s*)([\d,]+\.?\d*)(?:\s+(?:no|na|em|para|com|de|em|mercado|supermercado|farmácia|farmacia|restaurante|lanche|uber|99|ifood|rappi|delivery|alimentação|alimentacao|compras?))?'
    ]
    
    message_lower = message_content.lower()
    
    # Verificar se a mensagem contém palavras-chave de gasto
    expense_keywords = [
        'gastei', 'comprei', 'paguei', 'compras', 'mercado', 'farmácia', 'farmacia', 
        'restaurante', 'lanche', 'uber', '99', 'ifood', 'rappi', 'delivery', 
        'alimentação', 'alimentacao', 'gastos', 'total', 'valor'
    ]
    
    has_expense_keyword = any(keyword in message_lower for keyword in expense_keywords)
    
    if not has_expense_keyword:
        return None
    
    # Procurar por valores monetários
    for pattern in patterns:
        matches = re.findall(pattern, message_lower)
        if matches:
            # Pegar o primeiro valor encontrado
            value_str = matches[0].replace(',', '.')
            try:
                value = float(value_str)
                if value > 0:
                    return {
                        'value': value,
                        'message': message_content,
                        'detected_pattern': pattern
                    }
            except ValueError:
                continue
    
    return None

async def process_text_expense(thread, message_content: str):
    """Processa gasto informado em texto com OpenAI"""
    try:
        categories, error_msg = await get_categories()
        if error_msg:
            await thread.send(f"Ocorreu um erro ao buscar as categorias: {error_msg}")
            return

        # Detectar informações do gasto
        expense_info = detect_expense_in_message(message_content)
        if not expense_info:
            await thread.send("Não consegui identificar informações de gasto na sua mensagem. Por favor, seja mais específico (ex: 'gastei R$ 50 no mercado' ou 'comprei R$ 30 de comida').")
            return

        # Obter data atual
        data_atual = datetime.date.today()
        
        system_prompt = f"""Você é um assistente que ajuda a classificar gastos em categorias.

Analise a mensagem do usuário e classifique o gasto em uma das seguintes categorias: {categories}

A mensagem do usuário contém informações sobre um gasto de R$ {expense_info['value']:.2f}.

IMPORTANTE: Use SEMPRE a data atual ({data_atual.strftime('%Y-%m-%d')}) para a data da compra, a menos que a mensagem especifique claramente uma data diferente.

Retorne um JSON com a seguinte estrutura:
{{
    "estabelecimento": "nome do estabelecimento ou tipo de local",
    "data": "{data_atual.strftime('%Y-%m-%d')}",
    "itens": [
        {{
            "descricao": "descrição do item ou tipo de gasto",
            "valor": {expense_info['value']:.2f},
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

Classifique este gasto de R$ {expense_info['value']:.2f} nas categorias disponíveis."""

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
