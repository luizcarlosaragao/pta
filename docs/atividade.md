# Enunciado da atividade

Tradução para português do enunciado original de
[glaucogoncalves/pta](https://github.com/glaucogoncalves/pta/blob/88c31ea43619fc68b65d02005a7a72cf2df5a983/README.md).
O original permanece no histórico Git. Esta página reúne as orientações da
atividade; as instruções de execução da implementação estão no [README](../README.md).

## Exercício prático

Faça um **fork** deste repositório e **desenvolva seu servidor** com base no
protocolo descrito no arquivo [pta.pdf](../pta.pdf), em português. Antes de
programar, leia cuidadosamente a especificação e compreenda o protocolo.
Experimente seu funcionamento com papel e lápis, desenhando exemplos de uso.

Desenvolva o código do servidor no diretório [pta-server](../pta-server).
A lista de usuários aceitos pelo protocolo deve ser lida do arquivo
[pta-server/users.txt](../pta-server/users.txt). Os arquivos que seu servidor
deve disponibilizar estão no diretório [pta-server/files](../pta-server/files).
Não altere esses arquivos e diretórios fornecidos.

Seu servidor será avaliado por uma ferramenta de testes automáticos. Para
experimentá-lo, utilize o arquivo [pta-client.py](../pta-client.py). Esse cliente
realiza alguns testes, mas a cobertura não é extensa: a avaliação real também
verificará outros aspectos da implementação do protocolo.

Você pode utilizar **qualquer linguagem de programação**, mas deve fornecer
instruções suficientes para executar o código com sucesso. Descreva os
requisitos de bibliotecas, interpretadores, versões e demais dependências.

Ao concluir o desenvolvimento, compartilhe o link do seu repositório GitHub
no ambiente de avaliação [SIGAA](https://sigaa.ufpa.br/).

## Idioma e referência normativa

O enunciado não exige inglês para o código ou para a documentação. O PDF do
PTA está em português e define os nomes e o formato das mensagens. Esses
identificadores e os bytes dos arquivos devem ser preservados exatamente;
traduções da documentação não modificam o protocolo.
