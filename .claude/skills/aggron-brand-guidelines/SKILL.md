---
name: aggron-brand-guidelines
description: Aplica a identidade visual e o tom de voz oficiais da Aggron (paleta verde+ouro, tipografia Sora+Inter, voz B2B inteligência operacional) em qualquer artefato que represente a marca — código, e-mails, comunicados, PDFs, planilhas, decks, posts sociais, banners, mockups, documentos. Use sempre que o output for público em nome da Aggron, mesmo que o usuário não cite a marca explicitamente.
license: Uso interno Aggron. Baseado no manual oficial "Aggron Identity System Official" (2026), fornecido pelo designer da marca.
---

# Aggron — Brand Guidelines

Fonte da verdade: [`docs/Aggron_Identity_System_Official.pdf`](../../../docs/Aggron_Identity_System_Official.pdf) (manual oficial 2026 do designer). Esta skill codifica o PDF em formato consumível por Claude.

## 1. O que é a Aggron

**Aggron é uma plataforma premium de inteligência operacional e compras estratégicas para food service.** Conecta fornecedores a hamburguerias, espetarias, lanchonetes e similares, gerando escala, reduzindo custos e elevando qualidade de insumos.

**Conceito da identidade visual:** conexão entre negócios, ganho de escala, eficiência operacional e negociação inteligente.

**Cliente-tipo:** dono(a) de lanchonete B2B no interior do Brasil (começou por Londrina-PR). Estilo de comunicação: WhatsApp, decisor pragmático, valoriza confiabilidade e simplicidade.

## 2. Paleta oficial (NUNCA improvisar cores)

| Token | Hex | Uso |
|---|---|---|
| Verde Aggron | `#0F2A1F` | Cor institucional principal, fundos escuros premium, identidade |
| Verde Claro | `#166B3D` | CTAs, links, indicadores positivos, glow discreto |
| Ouro Aggron | `#D4AF37` | Acento premium, valores em destaque, KPIs, badges, tagline |
| Grafite | `#111418` | Preto profundo — navbar, cards elevados, contraste |
| Cinza Claro | `#E6E6E6` | Texto principal sobre dark, wordmark "AGGRON" |
| Branco | `#FFFFFF` | Backgrounds claros (raros — Aggron é dark-first) |

### Tokens semânticos (CSS variables já mapeadas em `app/static/css/style.css`)
```css
--brand-verde:        #0F2A1F;
--brand-verde-claro:  #166B3D;
--brand-ouro:         #D4AF37;
--brand-grafite:      #111418;
--brand-cinza-claro:  #E6E6E6;
```

### Regras de uso de cor
- **Dominância:** Verde Aggron + Grafite formam o fundo. Verde Claro entra como CTA/positivo. Ouro entra como acento, **nunca dominante** — usar em <15% da composição.
- **Texto:** Cinza Claro `#E6E6E6` sobre fundos escuros (WCAG AA garantido). Grafite `#111418` sobre fundos claros/ouro.
- **Glow verde discreto:** `radial-gradient(ellipse at top, rgba(22, 107, 61, 0.12), transparent 70%)` — assina presença sem distrair.
- **Tints sutis (8-15% alpha):** usar para card-highlights, badges semânticos, focus states.

## 3. Tipografia

**Hierarquia obrigatória:**
- **Sora** (Google Fonts) — títulos, wordmark, branding, dashboards, KPIs numéricos. Pesos: 500/600/700.
- **Inter** (Google Fonts) — interface, corpo de texto, relatórios, formulários, leitura longa. Pesos: 400/500/600/700.

**CSS já configurado:**
```css
--font-heading: 'Sora', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
--font-body:    'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

**Letter-spacing:**
- Sora em headings: `letter-spacing: -0.01em` a `-0.03em` (números KPI gigantes).
- Sora em eyebrows/labels uppercase: `letter-spacing: 1.5px` a `2.5px`.
- Wordmark "AGGRON": `letter-spacing: 4px`.

**NUNCA usar:** Arial, Roboto, Open Sans, Lato, Montserrat, Space Grotesk, Poppins, Helvetica.

## 4. Logo

**Monograma A geométrico** — fonte da verdade é [`app/static/images/logo-aggron-symbol.png`](../../../app/static/images/logo-aggron-symbol.png) (extraído pixel-fiel do PDF oficial @ 600 DPI). Variante @2x disponível.

Construção do monograma (do PDF oficial):
- Estrutura técnica e moderna
- Elementos inspirados em fluxo e conexão
- Base dourada simbolizando geração de valor (faixa angular `#D4AF37`)

**Tagline oficial (do PDF):** "Conectamos quem fornece com quem faz acontecer."

**Tagline de produto/navbar (validada):** "INTELIGÊNCIA QUE GERA VALOR" — versão curta uppercase em ouro com traços laterais 1px, usada em headers de navegação.

**Regras de uso do logo:**
- **Sempre usar a versão PNG oficial** (`logo-aggron-symbol.png`). NUNCA recriar via SVG/CSS — não é fiel.
- Tamanho mínimo: 32×32px (favicon).
- Padding mínimo: metade da altura do logo ao redor.
- Glow ouro sutil aceitável sobre fundos escuros: `filter: drop-shadow(0 0 10px rgba(212, 175, 55, 0.35))`.
- NUNCA recolorir o logo. NUNCA esticar (preservar aspect ratio).

## 5. Voz e tom

Validada com base em referências B2B BR (Olist, Stone, Conta Azul, RD Station) + globais (Stripe, HubSpot, Square). Detalhes em `MEMORY.md` ([guia_tom_aggron.md](../../../C:/Users/NITRO/.claude/projects/c--Users-NITRO-Projects-poolcompras/memory/guia_tom_aggron.md)).

### Personalidade (do PDF oficial)
1. **Inteligente** — comunicação clara, baseada em dado, sem fluff.
2. **Confiável** — promessas honram-se. Linguagem firme, sem hype.
3. **Parceira** — fala "com" o cliente, não "para".
4. **Eficiente** — frases diretas, ações claras. Sem preâmbulo desnecessário.
5. **Ambiciosa** — visão grande, expressa com sobriedade B2B (sem entusiasmo de startup).

### Regras de redação
- Sempre tratar a empresa por **"Aggron"** ou **"a Aggron"**. NUNCA "a gente", "nós" (excesso de informalidade), "admin" (interno demais).
- Founders mencionados em 1 linha quando relevante: "Fundada por Mateus Fabro e Ademar [sobrenome]". Sem narrativa de vulnerabilidade pessoal.
- Acentos completos em PT-BR. NUNCA "ja", "voce" — sempre "já", "você".
- Frases curtas. Voz ativa. Imperativo direto em CTAs ("Criar rodada", "Ver detalhes", não "Clique aqui pra criar uma rodada").
- Números em destaque: usar Sora em ouro. Valores em R$: máscara `R$ X.XXX,XX` (PT-BR).
- Datas: PT-BR (`18/04/2026 às 23:59`) — filtros Jinja `data_br` e `datetime_br` no projeto.
- Termos do produto: "rodada" (não "ciclo"), "lanchonete" (não "cliente"), "fornecedor" (não "supplier"), "cotação" (não "quote"), "pedido" (não "order").

### O que evitar
- Emojis em comunicados formais (e-mails, contratos, decks, PDFs). Aceitáveis: WhatsApp interno entre sócios.
- Anglicismos desnecessários: "deadline" → "prazo"; "feedback" → "retorno"; "schedule" → "agenda".
- Linguagem genérica de SaaS: "soluções", "ecossistema", "jornada", "viva", "transforme".
- Hype: "revolucionário", "incrível", "amamos", "✨".

## 6. Layout e composição

### Princípios
- **Dark-first:** o produto é dark premium. Light theme é exceção (raros casos de exportação/impressão).
- **Assimetria deliberada:** grids 65/35 ou 60/40 superam 50/50 ou 4-cards-iguais. Hero-metric "Stripe-style" — UMA métrica dominante.
- **Atmosfera com gradient mesh:** elipses radiais sutis (verde 18% + ouro 10%) criam profundidade sem virar ruído.
- **8px grid:** spacing system já definido (`--space-1` = 8px até `--space-7` = 80px).
- **Densidade controlada:** info de apoio em `stat-mini` compacto; protagonistas com font-size `clamp(2.8rem, 6vw, 5rem)`.

### Componentes de referência (já no projeto)
- `.hero-metric` em [app/static/css/style.css](../../../app/static/css/style.css) — bloco de métrica dominante com gradient mesh.
- `.tag-success/.tag-danger/.tag-create/.tag-edit/.tag-info` — variantes semânticas de badge com tint 10% + borda 25%.
- `.btn-primary` / `.btn-outline` / `.btn-danger` — botões padrão com glow verde no hover.

## 7. Aplicação por tipo de artefato

### Código (Flask + Jinja + CSS)
- Usar variáveis CSS (`var(--brand-ouro)`), nunca hardcodar hex.
- Headings sempre Sora (já global em `style.css:210`).
- Numeric KPIs com `font-family: var(--font-heading)`, font-weight 700, color `--brand-ouro`.

### E-mails (SMTP, transacionais)
- HTML simples com inline CSS (clients quebram external).
- Header: fundo `#0F2A1F` com logo PNG ouro centralizado.
- Body: branco com Inter, headings Sora.
- CTA: botão `#166B3D` retangular com texto cinza-claro.
- Footer: cinza fino com link "Aggron — Londrina, PR | contato@aggron.com.br".

### PDFs (cotações, contratos, comprovantes)
- Capa: fundo grafite com logo ouro centralizado + tagline oficial em ouro.
- Cabeçalho de página: linha verde `#166B3D` 2pt + nome do documento em Sora.
- Tabelas: header verde escuro com texto cinza-claro; linhas alternadas grafite/grafite-escuro.
- Rodapé: paginação + "Aggron Central de Compras Cooperativa | Londrina-PR" em Inter 8pt cinza.

### Planilhas (xlsx)
- Header de planilha: fundo `#0F2A1F` com texto `#E6E6E6` em Calibri Bold 11pt (Excel não tem Sora nativa).
- Totais: linha de fundo ouro `#D4AF37` com texto grafite.
- Formatação numérica: `R$ #.##0,00` para valores; data `DD/MM/YYYY`.

### Decks/apresentações (pptx)
- Slide template dark com background `#0a0c0e` + gradient mesh top-right ouro 10%.
- Títulos em Sora bold 36pt ouro.
- Body em Inter regular 18pt cinza-claro.
- Acentos com ouro nas metrics. CTAs verde claro.

### Posts sociais (canvas-design)
- LinkedIn: 1200×627px com logo top-left + headline Sora bold + 1 KPI dominante em ouro + tagline rodapé.
- Instagram: 1080×1080 quadrado. Fundo grafite com glow verde top + ouro bottom. Logo + 1 frase curta.

## 8. Glossário de produto (vocabulário oficial)

- **Rodada** — ciclo de compra coletiva (preparando → aguardando_cotacao → aberta → em_negociacao → finalizada). Nunca "ciclo".
- **Lanchonete** — cliente comprador. Nunca "cliente" só.
- **Fornecedor** — vendedor B2B. Nunca "supplier".
- **Cotação** — proposta de preço do fornecedor. Pode ser "de partida" (inicial) ou "final" (com volumes reais).
- **Pedido** — solicitação da lanchonete num catálogo. Estados: rascunho, enviado, aprovado.
- **Catálogo** — lista de produtos cotados na rodada.
- **Sócio** — Mateus Fabro (tech) ou Ademar (infra/PO). Nunca "admin".
- **Yggdrasil** — servidor próprio do Ademar onde Aggron roda em prod.

## 9. Resumo executivo

Quando criar qualquer artefato em nome da Aggron:

1. **Dark-first.** Verde Aggron `#0F2A1F` + Grafite `#111418` formam a base. Ouro `#D4AF37` é acento (≤15%).
2. **Sora pra títulos, Inter pra corpo.** Nada de Arial/Roboto/Poppins.
3. **Logo PNG oficial** (`logo-aggron-symbol.png`), nunca recriado.
4. **Voz B2B sóbria** — direta, parceira, sem hype, sem emoji em formal.
5. **"Conectamos quem fornece com quem faz acontecer"** (tagline oficial) ou **"INTELIGÊNCIA QUE GERA VALOR"** (produto).
6. **Assimetria + 1 métrica dominante.** Não 4 cards iguais.

Quando dúvida, consultar `docs/Aggron_Identity_System_Official.pdf` (fonte da verdade).