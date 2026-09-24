# Conjunto de avaliação independente do NLP

**Por que existe:** as descrições do dataset simulado e os exemplos do classificador foram escritos pela mesma fonte. Avaliar só com eles é como fazer a prova sabendo as respostas. Este conjunto precisa ser escrito **por outra pessoa**, do jeito que um doador real escreveria, e **nunca** pode ser usado para ajustar o classificador (só para medir).

## Como preencher `avaliacao_independente_nlp.csv`

- **~10 frases por categoria** (~60 no total), uma por linha.
- **Não olhe** `src/data/textos.py` nem `src/models/exemplos_nlp.py` antes de escrever.
- Escreva como no WhatsApp: abreviações, erros de digitação, gírias, frases curtas e longas, com e sem quantidade.
- Pode editar no **Excel** (uma frase por linha, colunas A/B/C) ou no **VS Code / Bloco de Notas**. O leitor aceita os dois formatos.
- No VS Code / Bloco de Notas, se a frase tiver vírgula, coloque entre aspas: `"sobrou arroz, feijão e bife",preparado,ambiente`

| Coluna | Valores permitidos |
|---|---|
| `descricao` | o texto livre |
| `categoria` | `preparado`, `refrigerado`, `congelado`, `hortifruti`, `padaria`, `nao_perecivel` |
| `armazenamento` | `refrigerado`, `congelado`, `ambiente` (para hortifruti, padaria e não perecível, use `ambiente`) |

**Definições das categorias:** preparado = comida pronta (marmita, buffet, salgado); refrigerado = laticínios e frios; congelado = carnes e congelados; hortifruti = frutas, verduras e legumes; padaria = pães e bolos; não perecível = mercearia seca e enlatados.

Depois de preencher, rode `python -m src.models.avaliar_nlp`. O resultado entra em `reports/avaliacao_nlp.json`.
