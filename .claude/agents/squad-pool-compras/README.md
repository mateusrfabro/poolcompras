# Squad Pool Compras

8 agentes especializados pro projeto Aggron.

## Quem e quem

| Agente | Uso tipico |
|---|---|
| **product-manager** | Recebeu feedback do Ademar? Passa pro PM pra destilar spec |
| **backend-dev** | Implementar feature Flask nova (rotas, models, services) |
| **tester** | Escrever/atualizar testes pytest |
| **database** | Mudanca de schema, migration, performance de query |
| **code-quality** | Auditoria de qualidade de codigo (antes de PRs ou release) |
| **ux-review** | Revisao frontend (acessibilidade, responsivo, consistencia — sem alterar paleta) |
| **security** | OWASP Top 10: IDOR, CSRF, CSP, upload, auth |
| **devops** | Deploy, Docker, Nginx, CI/CD (ativa no Bloco D, aguardando VM Ademar) |

## Como invocar
Use a ferramenta `Task` com `subagent_type` igual ao nome do agente.

Exemplo:
```
Task(subagent_type="backend-dev", prompt="Implementar rota /admin/X que...")
Task(subagent_type="product-manager", prompt="Feedback do Ademar: [print]...")
```

## Fluxo tipico de nova feature
1. **product-manager** destila spec do feedback bruto
2. **database** avalia impacto no schema (se houver)
3. **backend-dev** implementa rota + service + template
4. **tester** escreve testes
5. **ux-review** + **security** revisam (opcional se mudanca pequena)
6. Push

## Regras inviolaveis dos agentes
- Nao alterar paleta/identidade visual (laranja #f57c00, cards claros)
- Nao trocar Flask por outro framework
- Nao commitar credenciais
- Nao deploy force
- Nao spawn de outros agentes dentro de agente (evitar recursao)

Detalhes completos estao no `CLAUDE.md` do projeto.