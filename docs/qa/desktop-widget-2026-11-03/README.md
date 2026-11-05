# Widget — validação das interações

11 telas/estados; exceções capturadas: 0.

Dados fictícios e XDG/D-Bus isolados; sem injetar teclas na sessão real.

| Tela/estado | Captura |
| --- | --- |
| preferences-disabled | [PNG](preferences-disabled.png) |
| preferences-content | [PNG](preferences-content.png) |
| preferences-appearance | [PNG](preferences-appearance.png) |
| preferences-position | [PNG](preferences-position.png) |
| widget-english-12h | [PNG](widget-english-12h.png) |
| forecast-seven-days | [PNG](forecast-seven-days.png) |
| widget-scaled-150-percent | [PNG](widget-scaled-150-percent.png) |
| resize-frame-controls | [PNG](resize-frame-controls.png) |
| widget-portuguese-reference | [PNG](widget-portuguese-reference.png) |
| widget-custom-colors | [PNG](widget-custom-colors.png) |
| widget-weather-offline | [PNG](widget-weather-offline.png) |

[Detalhes dos testes](report.json) · [X11/XWayland nativo](x11-report.json)

[Implementação e limites](../../desktop-widget.md).

## Confirmação física na sessão do usuário

O usuário confirmou os cliques no relógio e no clima depois da mudança para janela
NORMAL sem BELOW, e confirmou Super + arraste e Ctrl+T. A região de entrada agora
usa botões GTK transparentes com janelas de eventos X11 nativas. O percurso sintético
permanece como regressão, sem substituir essa verificação de composição/entrada real.

## Frame de redimensionamento — 2026-11-03

A ferramenta modal foi substituída por um frame sobre o widget, com oito alças,
contorno pontilhado arredondado e botão Concluir. Esc e Ctrl+T também confirmam.
O arraste preserva a proporção de todos os elementos e a posição do lado oposto.
O item Open-Meteo · GeoNames foi removido do menu; os créditos continuam nas
preferências e na previsão.

Validação: 161 testes aprovados, percurso GTK sem exceções e arraste nativo X11
confirmando escala 1,2 e tamanho 528 × 492, com oito alças e sem modal.

[Relatório do arraste nativo](native-frame-report.json).
