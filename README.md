# Servidor PTA

Servidor do **Protocolo de Transferência de Arquivos (PTA)**, desenvolvido em
Python para a atividade de Sistemas Distribuídos. Utiliza sockets TCP,
implementa apresentação de usuários, listagem, download binário e encerramento
de sessão. Atende vários clientes com `asyncio` e usa apenas a biblioteca padrão.

Este repositório é um fork de [glaucogoncalves/pta](https://github.com/glaucogoncalves/pta).
A [especificação do protocolo](pta.pdf) define as mensagens e os estados.
O [enunciado da atividade em português](docs/atividade.md) fica separado desta
documentação de uso.

## Requisitos

- **Python 3.11 ou superior**.
- **Linux** como plataforma principal de execução e testes.
- Porta **TCP 11550** disponível para a configuração padrão.
- Nenhuma instalação por `pip`, frontend, API HTTP ou banco de dados.

## Como executar

```bash
git clone https://github.com/luizcarlosaragao/pta.git
cd pta
python3 pta-server/server.py
```

**Esta é a configuração recomendada para a atividade e para o cliente fornecido
pelo professor.** O comando já ativa `--framing auto`: aceita os pedidos sem
terminador do cliente original e detecta LF/CRLF quando utilizados. Nenhum
terminador adicional é exigido nas mensagens originais, e as respostas mantêm
o formato do PTA. Não é necessário passar opções extras para a avaliação.

Por padrão, o servidor escuta em `0.0.0.0:11550`, aceita conexões de rede e lê
os usuários de `pta-server/users.txt`. Os arquivos disponíveis ficam em
`pta-server/files/`. Esses caminhos são resolvidos a partir do script: é
possível iniciá-lo de outro diretório usando seu caminho absoluto.

Para escutar somente no computador local:

```bash
python3 pta-server/server.py --host 127.0.0.1 --port 11550
```

Para consultar as opções:

```bash
python3 pta-server/server.py --help
```

Os usuários originais são `user1`, `user2` e `user3`. A comparação diferencia
maiúsculas e minúsculas. A lista é carregada na inicialização; sua atualização
exige reinício. Falha de configuração ou porta ocupada encerra o processo com
diagnóstico em `stderr`. Ctrl+C (SIGINT) e SIGTERM encerram o servidor e as
conexões ativas. Os logs ficam em `stderr`, separados das mensagens TCP.

## Comandos e respostas

Os campos são separados por um espaço ASCII. Cada resposta repete exatamente
o número de sequência do pedido. O cliente é responsável por incrementar essa
sequência; o servidor aceita início diferente de zero e não exige contiguidade.

| Pedido | Resposta | Resultado |
| --- | --- | --- |
| `73 CUMP user1` | `73 OK` | Autentica a sessão |
| `73 CUMP desconhecido` | `73 NOK` | Fecha a conexão |
| Outro comando antes de apresentação válida | `SEQ NOK` | Fecha a conexão |
| `74 LIST` | `74 ARQS N nome1,nome2,...` | Lista os arquivos |
| `75 PEGA nome1` | `75 ARQ B ` seguido de B bytes | Envia o arquivo |
| Arquivo inexistente, inacessível ou caminho proibido | `SEQ NOK` | Mantém a sessão |
| Pedido inválido ou novo CUMP após autenticação | `SEQ NOK` | Mantém a sessão |
| `76 TERM` após autenticação | `76 OK` | Fecha a conexão |

LIST e TERM não recebem argumentos; CUMP recebe o usuário. PEGA atende um
arquivo por vez e ignora argumentos de arquivos adicionais, como determina
a especificação. Pedidos malformados são rejeitados. Se não for possível
recuperar uma sequência numérica ASCII, utiliza-se `0 NOK`; esse caso não é
definido pelo PDF.

LIST retorna nomes ordenados, separados por vírgulas, sem vírgula final.
Sem arquivos, retorna `SEQ ARQS 0 `, com o espaço final. Downloads são
binários, incluindo PNG e arquivos vazios: o cabeçalho informa o tamanho em
bytes, e o corpo contém exatamente os bytes do arquivo, sem conversão.
Um arquivo vazio produz `SEQ ARQ 0 `.

**Os identificadores do protocolo não são traduzidos ou alterados.** Eles
permanecem `CUMP`, `LIST`, `PEGA`, `TERM`, `OK`, `NOK`, `ARQS` e `ARQ`, com a
capitalização exata da especificação. O enunciado não exige inglês para a
documentação, comentários ou mensagens locais; esses textos estão em português.

## Delimitação das requisições TCP

TCP transmite um fluxo de bytes e não preserva os limites dos envios. O PDF não
especifica terminador ou tamanho para as requisições, e o cliente original
envia comandos sem terminador. O servidor oferece três modos:

| Opção `--framing` | Funcionamento |
| --- | --- |
| `auto` (padrão) | Compatível com o cliente original; ao receber o primeiro LF, fixa o modo por linhas para aquela conexão |
| `lines` | Exige LF ou CRLF desde o primeiro pedido, sem timeout de delimitação |
| `legacy` | Delimita pedidos sem terminador por silêncio; aceita também LF/CRLF sem fixar o modo por linhas |

No modo por linhas, fragmentos podem chegar em leituras distintas com pausas
maiores que 100 ms, incluindo CR e LF separados. Uma requisição sem terminador
permanece incompleta; o encerramento da entrada descarta sua parte pendente.
Depois da detecção de LF em `auto`, o cliente deve continuar usando LF/CRLF.

Para clientes que usam terminadores desde a primeira mensagem, inclusive
quando a apresentação pode chegar lentamente:

```bash
python3 pta-server/server.py --framing lines
```

No formato legado, o padrão é **100 ms sem novos bytes** para considerar o
pedido completo. É possível ajustar o intervalo:

```bash
python3 pta-server/server.py --framing legacy --legacy-idle-ms 250
```

Antes de detectar o primeiro LF no modo `auto`, aplica-se a mesma heurística
do formato legado. Uma pausa maior que o intervalo pode dividir uma mensagem,
especialmente na apresentação inicial. **Não há como eliminar universalmente
essa ambiguidade sem definir limites de mensagem no cliente.** Aumentar o
intervalo apenas altera o limite. Comandos concatenados sem terminadores não
são suportados; aguarde a resposta completa antes de enviar o próximo pedido.

Respostas não recebem terminadores adicionais. LIST/PEGA são operações
atômicas por sessão: pedidos recebidos durante uma operação são ignorados.
No modo por linhas, uma mensagem descartada continua sendo descartada até seu
terminador, mesmo se a transferência terminar entre os fragmentos. Não há
fila de operações por conexão. A conclusão do envio pelo servidor não exige
confirmação adicional de leitura pelo cliente.

O conteúdo de uma requisição é limitado a **64 KiB**, excluindo LF/CRLF.
O excesso recebe NOK quando possível e fecha a conexão. O tamanho é verificado
mesmo quando CR e LF chegam separadamente.

## Armazenamento e integridade

- Os materiais originais `pta.pdf`, `pta-client.py`, `pta-server/users.txt` e
  todos os arquivos de `pta-server/files/` permanecem intactos.
- Somente arquivos regulares diretamente na pasta são listados e servidos.
  Links simbólicos, subdiretórios, caminhos absolutos e travessia de diretórios
  são recusados.
- Nomes incompatíveis com os campos do protocolo, como nomes não ASCII,
  espaços ou vírgulas, não são listados nem servidos.
- No Linux, a abertura usa `O_NOFOLLOW` contra links simbólicos e `O_NONBLOCK`
  para evitar bloqueio em um FIFO substituído.
- O tamanho é obtido pelo descritor aberto. O envio usa blocos de até 64 KiB
  com controle de fluxo e sem carregar o arquivo inteiro em memória.
- Se a leitura falhar após o cabeçalho ARQ, a conexão é encerrada sem inserir
  NOK dentro do corpo. Os arquivos devem permanecer estáveis durante o envio;
  não há snapshot contra edição externa simultânea.

## Testes

Na raiz do projeto, sem precisar iniciar o servidor manualmente:

```bash
python3 -m unittest discover -s pta-server/tests -v
```

Os testes usam portas temporárias locais e diretórios temporários. O ambiente
precisa permitir sockets TCP. São verificados autenticação, estados,
sequências, comandos inválidos, listagens grandes, downloads dos 16 arquivos
originais por conteúdo e SHA-256, leitura lenta, desconexões, proteção de
caminhos, falhas de leitura, concorrência e encerramento por sinal.

As regressões cobrem fragmentos atravessando o fim de uma transferência,
limites de 64 KiB com LF/CRLF e CRLF separado, fragmentação lenta no modo por
linhas, apresentação lenta no modo explícito e compatibilidade legada.
O GitHub Actions executa a suíte no Ubuntu com Python **3.11 e 3.14**.

### Cliente fornecido pelo professor

Com o servidor iniciado, execute o cliente original em outra janela:

```bash
python3 pta-client.py 127.0.0.1 11550 user1
```

Esse cliente grava o download no diretório atual; se quiser evitar arquivos
extras na pasta do projeto, execute-o por caminho absoluto a partir de uma
pasta temporária. Ele escolhe um arquivo aleatório e trata o conteúdo como
texto UTF-8, portanto pode falhar ao selecionar o PNG. A contagem da listagem
também depende da fragmentação das leituras TCP.

Por isso, a suíte também usa um cliente próprio que lê bytes e respeita o
tamanho anunciado. O teste de compatibilidade executa o cliente original sem
modificá-lo, fixa externamente a seleção de um arquivo textual de 2048 bytes e
verifica a pontuação 6/6, TERM e o conteúdo baixado. Downloads binários e vazios
são verificados separadamente. O comportamento do servidor não depende de
corrigir ou substituir o cliente fornecido.

Há também um teste completo da execução pela linha de comando: o servidor é
iniciado sem selecionar `--framing`, e o cliente original se conecta a ele sem
terminadores, obtém 6/6 e baixa o arquivo textual corretamente. Esse teste usa
uma porta temporária para não conflitar com um servidor já em execução.

## Entrega da atividade

O repositório de entrega é o fork público
[luizcarlosaragao/pta](https://github.com/luizcarlosaragao/pta).
O professor pode cloná-lo e iniciar o servidor com os comandos desta página.
A submissão do link é feita no SIGAA. Os testes locais e o CI fornecem evidência
de correção, mas não garantem aprovação em testes ocultos ou em interpretações
diferentes das ambiguidades descritas na especificação.
