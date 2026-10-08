# Matriz de controles

> Cada controle implementado, o tipo (preventivo, detectivo ou corretivo), as normas que ele atende e a **evidência** no repositório.
> Referências: ISO/IEC 27001:2022 (Anexo A), ISO/IEC 42001 (Anexo A), NIST CSF 2.0, OWASP Top 10 for LLM 2025, LGPD.

| # | Controle | Tipo | ISO 27001:2022 | ISO 42001 | NIST CSF 2.0 | OWASP LLM / LGPD | Evidência |
|---|---|---|---|---|---|---|---|
| C01 | Validação de entrada em 5 camadas (esquema estrito, documento, guardrail, regra, banco) | Preventivo | 8.28 Codificação segura | A.6 Ciclo de vida | PR.DS | LLM01, LLM05 | `src/validacao/esquemas.py`, `tests/validacao/` |
| C02 | Dígito verificador de CPF/CNPJ (alfanumérico) + consulta à Receita + aprovação do admin | Preventivo | 5.16 Gestão de identidade | — | PR.AA | — | `documentos.py`, `receita.py`, `test_receita.py` |
| C03 | Validade calculada pelo sistema | Preventivo | 8.28 | A.6 | PR.DS | — | `src/regras/validade.py` |
| C04 | Questionário + **Declaração assinada** (RSA-PSS), imutável e versionada | Preventivo + Detectivo | 8.24 Criptografia | A.8 Informação a partes interessadas | PR.DS | Lei 14.016 | `declaracao.py`, `test_declaracao.py` |
| C05 | Log completo em cobertura, mínimo em conteúdo, **cadeia HMAC** | Detectivo | 8.15 Registro de eventos · 8.11 Mascaramento | A.6 (registros de eventos) | PR.PS · DE.AE | LGPD art. 46 · LLM02 | `registro.py`, `test_registro.py` |
| C06 | Retenção (90 dias / 5 anos) com âncora selada | Corretivo | 8.10 Exclusão de informação | — | PR.DS | LGPD art. 15–16 | `registro.py::aplicar_retencao` |
| C07 | Pseudonimização (HMAC) de documentos e atores | Preventivo | 8.11 · 5.34 Privacidade e DP | A.7 Dados para IA | PR.DS | LGPD art. 12–13 | `minimizacao.py`, `entidades.py` |
| C08 | Observabilidade por linha de base (mediana/MAD por faixa) com 3 níveis | Detectivo | 8.16 Monitoramento | A.6 (operação e monitoramento) | DE.CM · DE.AE | LLM10 | `anomalias.py`, `test_anomalias.py` |
| C09 | Limite de requisições + **freio automático** reversível | Preventivo + Corretivo | 8.6 Gestão de capacidade | — | PR.PS · RS.MI | LLM10 | `freio.py` |
| C10 | Drift por PSI das entradas e saídas dos modelos | Detectivo | 8.16 | A.6 | DE.CM | LLM04 | `drift.py` |
| C11 | Camada única de controle da IA: saída validada, fallback, **piso de segurança** | Preventivo | 8.28 | A.9 Uso de sistemas de IA | PR.PS | LLM05, LLM06 | `controle.py`, `test_controle.py` |
| C12 | **Desligamento** por modelo, auditado | Corretivo | 5.26 Resposta a incidentes | A.6 | RS.MI | LLM06 | `Interruptores` |
| C13 | Artefato de modelo verificado por SHA-256 antes do load | Preventivo | 8.19 Instalação de software | A.6 | PR.PS | LLM03 | `artefatos.py`, `test_artefatos.py` |
| C14 | Modelos HF fixados por commit, só safetensors, sem `trust_remote_code` | Preventivo | 5.21 Cadeia de suprimentos de TIC | A.10 Terceiros | GV.SC | LLM03 | `nlp.py` |
| C15 | Feedback validado (conta verificada, limite, quarentena, cota) | Preventivo + Detectivo | 8.28 | A.7 Qualidade dos dados | DE.AE | LLM04 | `feedback.py`, `test_feedback.py` |
| C16 | Portão de promoção (teste fixo, metas, aprovador ≠ treinador) + rollback | Preventivo + Corretivo | 5.3 Segregação de funções · 8.32 Gestão de mudanças | A.6 | GV.RR | LLM04 | `portao_de_promocao`, `RegistroDeVersoes` |
| C17 | Catálogo de dados verificado por teste | Preventivo | 5.9 Inventário · 5.12 Classificação | A.7 | ID.AM | LGPD art. 37 | `catalogo.py`, `test_governanca.py` |
| C18 | Qualidade de dados no pipeline (15 checagens) | Detectivo | 8.29 Testes de segurança | A.7 Qualidade dos dados | ID.IM | — | `qualidade.py`, `reports/qualidade_dados.json` |
| C19 | Segregação de funções no caixa (quem pede não aprova) | Preventivo | 5.3 | — | GV.RR | — | `aprovacao_necessaria`, `test_regras.py` |
| C20 | Segredos fora do código; produção não sobe sem eles | Preventivo | 8.24 · 5.17 Informação de autenticação | — | PR.AA | LLM02 | `segredos.py` |
| C21 | Falha fechada em serviço externo | Preventivo | 5.23 Serviços em nuvem | A.10 | PR.PS | — | `receita.py` (PENDENTE) |
| C22 | SAST (Bandit) + varredura de imagem/dependências (Trivy) com gate | Detectivo + Preventivo | 8.8 Vulnerabilidades técnicas · 8.25 Desenvolvimento seguro | — | ID.RA · PR.PS | LLM03 | CP2 (GitHub Actions) |
