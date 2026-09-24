"""Exemplos escritos à mão para o classificador por similaridade (poucos exemplos por classe).

São a "configuração" do classificador: o texto do doador vai para a classe cujos exemplos
são mais parecidos (similaridade de cosseno entre embeddings). Escritos com estilo
DIFERENTE dos modelos de frase do dataset simulado (src/data/textos.py), para não
viciar a avaliação. Palavras genéricas de doação ("sobrou", "doação", "retirar") aparecem em
várias classes de propósito, para o modelo não associá-las a uma categoria só (ajuste feito
medindo no período de VALIDAÇÃO; o teste e o conjunto independente não foram usados).
"""

from src.regras.dominio import Armazenamento, Categoria

EXEMPLOS_CATEGORIA: dict[Categoria, list[str]] = {
    Categoria.PREPARADO: [
        "comida do almoço do restaurante, arroz feijão e carne",
        "quentinhas prontas para servir",
        "bandejas de lasanha que não vendemos hoje",
        "sopa pronta em panelão, dá umas 40 porções",
        "refeições do buffet do fim do dia",
        "pratos feitos embalados, frango com purê",
        "salgados assados e sanduíches da lanchonete",
        "marmitex de feijoada",
        "comida caseira pronta para comer",
        "escondidinho e arroz à grega do evento de ontem",
    ],
    Categoria.REFRIGERADO: [
        "caixas de iogurte perto do vencimento",
        "queijo prato e mussarela fatiados",
        "bandejas de presunto e peito de peru",
        "leite fermentado e bebida láctea",
        "requeijão cremoso em copo",
        "sobrou iogurte com validade próxima",
        "frios variados da delicatessen",
        "potes de coalhada e iogurte grego",
        "salsicha e mortadela embaladas",
        "creme de leite fresco e nata",
    ],
    Categoria.CONGELADO: [
        "carne bovina congelada em peças",
        "frango inteiro congelado",
        "sobrecoxa e asinha congeladas",
        "carne moída do freezer",
        "peixe congelado em filés",
        "hambúrguer congelado em caixa",
        "linguiça toscana congelada",
        "cortes de porco congelados",
        "nuggets e empanados congelados",
        "doação de carne congelada, retirar hoje",
    ],
    Categoria.HORTIFRUTI: [
        "banana e mamão maduros",
        "caixa de tomate e cebola",
        "alface, rúcula e couve",
        "batata, cenoura e beterraba",
        "laranja e limão para suco",
        "abobrinha, chuchu e pepino da feira",
        "sobrou fruta da estação, doação para retirar",
        "maçã e pera levemente amassadas",
        "sobrou verdura e legume da feira",
        "mandioca e abóbora",
    ],
    Categoria.PADARIA: [
        "pão francês do dia",
        "pão de forma fechado",
        "bolo de fubá e bolo de cenoura",
        "sonhos e roscas da padaria",
        "pão doce e pão de leite",
        "baguetes e pães de fermentação natural",
        "broas e biscoitos caseiros de padaria",
        "sobraram pães do dia, doação para retirar",
        "pão de queijo assado",
        "panetone e bolo inglês",
    ],
    Categoria.NAO_PERECIVEL: [
        "sacos de arroz e feijão",
        "macarrão espaguete e parafuso",
        "latas de atum, sardinha e milho",
        "óleo de soja e açúcar",
        "farinha de trigo e fubá",
        "doação de cestas básicas, retirar hoje",
        "caixas de leite longa vida",
        "biscoito recheado e bolacha água e sal",
        "café em pó e achocolatado",
        "sobrou estoque de mercearia, enlatados e grãos",
    ],
}

EXEMPLOS_ARMAZENAMENTO: dict[Armazenamento, list[str]] = {
    Armazenamento.REFRIGERADO: [
        "está na geladeira",
        "guardado refrigerado",
        "mantido na câmara fria",
        "conservado gelado a 4 graus",
        "saiu agora do refrigerador e voltou para a geladeira",
    ],
    Armazenamento.CONGELADO: [
        "está no freezer",
        "congelado",
        "armazenado em câmara de congelamento",
        "mantido congelado a -18 graus",
        "guardado na freezer horizontal",
    ],
    Armazenamento.AMBIENTE: [
        "está em cima do balcão",
        "fora da geladeira",
        "em temperatura ambiente",
        "acabou de sair do fogão, ainda quente",
        "no estoque seco, sem refrigeração",
    ],
}
