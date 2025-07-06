### Post para o LinkedIn (Tom Informal)

E aí, pessoal! 👋

Sabe aquela tarefa chata de ficar lançando cada item do cupom fiscal numa planilha? Pois é, cansei disso e resolvi criar uma solução pra automatizar esse processo.

Criei o **Orçamento Bot**, um bot para Discord que usa IA para ler cupons fiscais e lançar tudo num banco de dados. O fluxo é bem simples:

1.  Eu tiro uma foto do cupom e mando no Discord.
2.  O bot abre uma conversa, lê a imagem usando a API da OpenAI (GPT-4o) e me mostra os itens que encontrou, já com uma sugestão de categoria.
3.  Aí eu posso simplesmente dizer "ok" ou, se precisar, falar algo como "muda o pão de queijo pra categoria lanche".
4.  Depois que eu aprovo, ele salva tudo direitinho num banco de dados PostgreSQL.

É um projeto que fiz pra resolver um problema meu, mas que pode ser útil pra mais gente. Foi bem legal de fazer e usei Python, `discord.py`, a API da OpenAI e `asyncpg`.

O código está todo aberto lá no meu GitHub. Se quiser dar uma olhada, o link é esse aqui:

**GitHub Repo:** https://github.com/paschendale/orcamento-bot

Valeu! 😉

#Python #Discord #Bot #OpenAI #PostgreSQL #Automacao #Desenvolvimento #InteligenciaArtificial #ProjetoPessoal