# RIPD: Relatório de Impacto à Proteção de Dados Pessoais

> LGPD art. 5º, XVII e art. 38. Versão 2.0 (2026-10-05). Escopo: plataforma Rede Alimenta IA (cadastro, matching, transporte, caixa solidário, IA, logs).

## 1. Descrição do tratamento

A plataforma conecta doadores de alimentos (PJ e PF) a ONGs. Ela trata dados de identificação e contato das partes, dados operacionais das doações e registros de auditoria. **Não trata dados sensíveis** (art. 5º, II) **nem dados de crianças** (art. 14). Os beneficiários finais das ONGs **não são cadastrados**.

## 2. Necessidade e proporcionalidade

| Dado | Necessário para | Alternativa menos invasiva adotada |
|---|---|---|
| Documento (CPF/CNPJ) | Verificar a entidade, evitar fraude | Guardado só como HMAC; verificação feita na hora |
| Endereço | Coleta e entrega | PF: centroide do setor até o aceite; exato só para a contraparte, depois do aceite |
| Contato | Coordenar a coleta | Visível só para a contraparte da doação |
| Texto livre | Sugerir a categoria | Guardrail + 90 dias + nunca nos logs + mascarado na declaração |
| Histórico de doações | Auditoria, KPIs, modelos | Modelos só com features sem dado pessoal; KPIs agregados |

## 3. Riscos ao titular e medidas

| Risco | P | I | Medidas | Residual |
|---|:-:|:-:|---|:-:|
| Vazamento do cadastro (nome, documento, endereço) | 3 | 4 | HMAC, RLS no Supabase, segredos no cofre, menor privilégio | Médio (6) |
| Exposição do endereço de PF | 2 | 4 | Centroide até o aceite; hub como opção preferencial | Baixo (4) |
| Dado pessoal em log | 3 | 3 | Minimização no código (chaves proibidas + máscaras), verificada por teste | Baixo (3) |
| Dado pessoal digitado no texto livre | 3 | 2 | Guardrail, mascaramento, 90 dias | Baixo (3) |
| Reidentificação via logs de auditoria | 2 | 3 | Pseudônimos HMAC; chave separada da chave de documentos | Baixo (3) |
| Decisão automatizada afetando o titular (art. 20) | 2 | 3 | A IA só recomenda; decisões têm humano (doador, ONG, gestor, admin); revisão disponível | Baixo (3) |
| Retenção excessiva | 2 | 2 | Prazos definidos e rotina de retenção | Baixo (2) |

P × I de 1 a 5 (mesma escala da Matriz STRIDE).

## 4. Direitos do titular (art. 18)

| Direito | Como atender |
|---|---|
| Acesso / confirmação | Exportar o cadastro e o histórico de doações do titular |
| Correção | Edição do cadastro (gera evento de auditoria) |
| Eliminação | Apagar os dados diretos; pseudonimizar o que precisa ficar na trilha de auditoria (sem quebrar a cadeia HMAC) |
| Revisão de decisão automatizada (art. 20) | Contestação ao admin, com o registro da recomendação e da regra usada |

## 5. Conclusão

Com as medidas acima, o tratamento é **proporcional à finalidade social** da plataforma. Não há risco residual alto. Revisar este relatório a cada nova versão das regras de negócio ou quando um dado novo entrar no catálogo.
