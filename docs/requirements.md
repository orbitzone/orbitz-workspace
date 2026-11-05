# Requisitos e aceite da primeira etapa

Pedido: extrair calendário, tarefas, timesheets e invoices do Widgets for GNOME
para um aplicativo independente, seguindo o precedente Sticky Notes/YouTube.
Este será o aplicativo principal a publicar. Nome confirmado pelo usuário: **Orbitz Workspace**, repositório **orbitz-workspace**.

Aceite técnico: executar sem checkout ou extensão Widgets; manter funcionalidades
do Workspace; separar identidade, arquivos e preferências; preservar licenças;
permitir transferência explícita por backup; incluir launcher, instalação e testes.
A extração preserva a interface GTK existente. Redesign visual completo e publicação
não são considerados validados nesta etapa.

## Widget independente — 2026-11-03

Pedido confirmado: opção “Adicionar widget ao desktop” em Preferências e, quando
ativada, personalização integral do relógio/data/clima no mesmo lugar: localidade,
formato de data/hora e idioma PT/EN. Recriar a referência do Widgets for GNOME sem
utilizar a extensão ou depender da sessão GNOME. O usuário deseja ampla compatibilidade
com Ubuntu; compatibilidade universal permanece um objetivo, não uma validação feita.

Aceite implementado: prévia ao vivo, busca de cidade/manual, fuso, °C/°F, formatos
personalizados e predefinidos, seções/campos visíveis, fontes/tamanhos/cores/alpha,
fundo/borda/cantos, dimensões e posição, trava e autostart opt-in. Cancelar não aplica.
Processo separado persiste ao fechar a janela principal; desativar encerra o widget.

Limites explícitos: runtime Python 3.10+; alvo inicial Ubuntu 22.04+. X11/XWayland
permite dicas de desktop/posição; Wayland nativo não oferece as mesmas garantias.
Não se afirma suporte validado em todas as versões antigas ou ambientes de desktop.

## Cliques e transformação — complemento do usuário

Clique simples no relógio deve abrir o aplicativo principal e clique no clima deve
mostrar a previsão dos próximos dias. Super + clique/arraste move o widget. Ctrl+T
aciona redimensionamento; todos os elementos mantêm suas proporções.
Implementado como áreas de hit-test do renderer e escala uniforme do canvas; mudança
de escala pode ser confirmada ou cancelada e permanece independente dos dados locais.
