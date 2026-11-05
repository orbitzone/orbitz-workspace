# Extração inicial — 2026-11-02

Origem: `/home/felipe/Documents/Codex/projects/orbitz-widgets-for-gnome/extension/planner`.
Foram copiados os módulos Python do domínio e UI, dependências vendorizadas com
licenças, runtime PT/EN e testes pertinentes. Não foram copiados dados de usuário,
credenciais, coletores ou código GJS da extensão. Os projetos Sticky Notes e
YouTube foram consultados como referência de separação de aplicativo e packaging.

Alterações: caminhos XDG próprios, Application ID `io.orbitz.Workspace`, launcher
portável, instalação via Makefile e idioma salvo nas preferências locais.
Formato de backup preservado. Na consolidação do nome, o cofre passou a usar
schemas exclusivos de Orbitz Workspace; contas migradas devem ser reconectadas.

Validação: suíte `make test`; instalação com `DESTDIR=/tmp/orbitz-workspace-stage`
e `PREFIX=/usr`; `desktop-file-validate data/io.orbitz.Workspace.desktop`.
A execução gráfica de teste falhou com `Gtk-WARNING: cannot open display: :0`.
Portanto, navegação e revisão visual em sessão real permanecem pendentes.
Não houve instalação ativa, importação de dados reais ou publicação remota.

Os testes herdados exercitam persistência atômica, concorrência, períodos de
faturamento, histórico, assinaturas, backups e provedores com dados sintéticos.
Os testes standalone verificam isolamento dos caminhos e independência do launcher.

Executar localmente: `./data/orbitz-workspace`. Para transferência de dados,
usar o fluxo de backup descrito no README, nunca copiar credenciais para o checkout.

## Validação posterior — 2026-11-03

A limitação gráfica inicial foi resolvida usando Broadway em sessão descartável,
restrita a localhost. O percurso real dos widgets GTK está em `tools/qa-workspace.py`,
com execução auxiliar em `tools/qa-session.py`. Capturas e relatório estão em
`docs/qa/2026-11-03/`.

Verificações finais: 128 testes passaram sem skips em execução com sockets locais
permitidos; a execução no sandbox passa com dois testes de loopback ignorados.
Instalação em staging e `desktop-file-validate` também passaram.
A autenticação real e os serviços externos não foram acionados pelo roteiro GTK.

Falhas corrigidas: variável inexistente nas confirmações de pagamento/exclusão,
callback de idioma acessando um ComboBox já destruído, tamanhos de diálogos,
contraste do calendário claro/escuro e ausência do agendamento independente de lembretes.
Notificações foram construídas e sua ação de navegação exercitada com envio ao desktop
substituído por um mock; o sistema de notificações real ainda depende da sessão do usuário.

## Ícone e instalação local — 2026-11-03

A ilustração fornecida pelo usuário foi refeita via ImageGen com fundo transparente.
O PNG original foi preservado em `data/io.orbitz.Workspace.png`, com oito tamanhos
para o tema hicolor. O SVG provisório foi substituído; a janela GTK também carrega o PNG.
Prompt e origem estão em `assets/branding/icon-prompt.md`.

O aplicativo agora foi instalado para o usuário em `~/.local/share/orbitz-workspace`,
com comando `~/.local/bin/orbitz-workspace` e entrada de menu
`~/.local/share/applications/io.orbitz.Workspace.desktop`.
Caches do menu/ícones atualizados. A instalação do Widgets e os dados do usuário
não foram alterados. A instalação local é uma cópia: alterações posteriores no
checkout precisam de `make install PREFIX="$HOME/.local"` para chegar ao aplicativo.

Verificações: alpha real no original e em todos os tamanhos, instalação em staging,
validação do desktop e smoke test em GTK isolado carregando o ícone da instalação real.

## Widget de desktop — 2026-11-03

Novo widget separado da extensão, habilitado e personalizado em Preferências.
149 testes passaram sem skips na execução com sockets locais permitidos. O percurso
anterior do Workspace manteve 53 telas/estados aprovados; o novo roteiro cobre oito
capturas e os fluxos de cancelamento, cidade, PT/EN, formatos, aparência, autostart,
falha de rede, trava, processo independente e remoção. O teste nativo deste Ubuntu
22.04.5 LTS confirmou X11/XWayland, posição e os estados desktop/below/sticky.
A busca de Brasília e a previsão de sete dias responderam pela API real.

A implementação e as limitações estão em `docs/desktop-widget.md`. Evidências em
`docs/qa/desktop-widget-2026-11-03/`. Bibliotecas de runtime adicionais documentadas
no README: Cairo, ponte GI/Cairo e Pango. Não foi instalada extensão do GNOME.

Atualização aplicada na instalação do usuário com `make install PREFIX="$HOME/.local"`.
Nenhum widget foi habilitado automaticamente e nenhuma entrada de autostart foi
criada na sessão real. A janela principal precisa ser fechada e reaberta para usar
os módulos novos já instalados; não se encerrou a janela do usuário com rascunhos.

## Cliques e redimensionamento do widget — 2026-11-03

Corrigidos os cliques por área: relógio/data abre o Workspace e clima abre a previsão
validada dos próximos sete dias. Movimentação exige Super + botão esquerdo; Ctrl+T
sobre o widget abre o ajuste proporcional, com confirmar/cancelar e persistência.
`scale` altera o canvas inteiro por transformação Cairo, sem mudar fontes individuais.
Há escala equivalente em Preferências e ações no menu contextual.

157 testes aprovados sem skips na execução com sockets locais permitidos. O roteiro
GTK tem onze capturas, incluindo previsão e escala 150%; valida cliques, modificador,
Ctrl+T, cancelamento e salvamento. O teste nativo confirmou o monitor de atalhos vivo
no X11/XWayland. Testes de atalhos usam mocks para não simular entrada na sessão real.
O runtime X11 de atalhos requer python3-xlib, já disponível nesta instalação.

Instalação atualizada e processo do widget reiniciado quando previamente habilitado,
sem mudar a ativação, localidade, aparência ou dados da janela principal. Reabrir o
Workspace carrega também o novo campo de escala em Preferências.

## Correção de interação física — confirmação do usuário

Os testes anteriores de handlers não cobriam a entrada física/composição da janela.
Na sessão real, a janela era visível mas passava os cliques ao desktop. A mudança
NORMAL sem BELOW foi aplicada e confirmada pelo usuário para relógio, clima,
Super + arraste e Ctrl+T. Essa mudança está na inicialização persistente do app.

Controles de clique agora são botões GTK transparentes com janelas X11 nativas;
previsão/escala têm janelas próprias. O launcher recebe o contexto de ativação.
Teste GTK atualizado para passar pelo dispatcher e pelos event windows dos botões.
A instalação definitiva é atualizada sem reiniciar a janela já corrigida, preservando
um eventual ajuste de escala aberto. Configurações e dados do usuário permanecem intactos.

Validação final desta correção: 159 testes aprovados sem skips fora do sandbox,
percurso GTK com entrada pelos botões nativos aprovado e teste X11 confirmando NORMAL,
ausência de BELOW, controles mapeados e restauração da posição salva após o mapeamento.
A confirmação de funcionamento dos dois cliques e dos dois gestos veio do usuário na
sessão real, não apenas dos testes sintéticos.

## Frame de redimensionamento — 2026-11-03

A ferramenta modal foi substituída por um frame sobre o widget, com oito alças,
contorno pontilhado arredondado e botão Concluir. Esc e Ctrl+T também confirmam.
O arraste preserva a proporção de todos os elementos e a posição do lado oposto.
O item Open-Meteo · GeoNames foi removido do menu; os créditos continuam nas
preferências e na previsão.

Validação: 161 testes aprovados, percurso GTK sem exceções e arraste nativo X11
confirmando escala 1,2 e tamanho 528 × 492, com oito alças e sem modal.

## Seletores de data e hora — 2026-11-03

`date_time_fields.py` centraliza calendário modal em campos de data e `TimeField`
com dropdowns separados de hora/minuto (00–59). Aplicado às tarefas, importação
de evento como tarefa, lançamentos e edição inline de horas, registro de tarefa
concluída, exportação CSV e data de emissão de invoice. O calendário de períodos
de invoices permanece disponível. Cancelar não altera a data; campos opcionais
podem ficar vazios; fim de atividade permite 24:00. Os valores persistidos
continuam ISO/HH:MM e preservam sinais de alteração e rascunhos.

Validação: 162 testes (2 skips do ambiente), 54 telas/estados GTK sem erros e
`tools/qa-date-time-fields.py` cobrindo calendário, ano bissexto, cancelamento,
horas/minutos, 24:00 e rascunhos.

## Recuperação de pintura do relógio — 2026-11-05

Na sessão afetada, os contadores de tick continuavam avançando, mas os pixels
da janela não mudavam, inclusive após enviar Expose. A verificação agora mede
o tempo desde a última pintura, independentemente do tick. Após 3 segundos sem
pintar, invalida a janela nativa e solicita fases do frame clock; após 5 segundos,
se continuar sem pintura, remapeia a janela sem ativá-la. O remapeamento fica
limitado a uma tentativa a cada 10 segundos. O status inclui draw_count, idade
da pintura e contagem de recuperações.

`tools/qa-clock-watchdog.py` simula perda de queue_draw e falha de process_updates,
verificando invalidação, fallback e retomada dos quadros. A sessão real foi
verificada por contadores de pintura e hashes da imagem da janela. Isso cobre
o congelamento visual observado; não garante ausência de falhas externas do
compositor ou de todo o processo.
