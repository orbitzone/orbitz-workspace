# Desktop widget — implementação e validação

Preferências reúne a ativação e as abas Conteúdo, Aparência e Posição e início.
O renderer Cairo/Pango é compartilhado pela prévia e pela janela transparente.
A prévia indica que o clima é fictício; a janela usa a localidade salva e o provedor real.
Formatos de data usam nomes PT/EN próprios, sem depender do locale instalado no Ubuntu.
Texto de usuário/provedor é desenhado como texto, nunca como markup ou comando.

## Processo e dados

- `app/widget_model.py`: defaults, validação, datas, condição e texto meteorológico.
- `app/widget_preferences.py`: formulário, prévia, busca de cidades em worker.
- `app/desktop_widget.py`: processo independente, janela, drag, menu e ciclo de vida.
- `app/widget_control.py`: lançamento e autostart explícito por usuário.
- `app/weather_backend.py`: núcleo validado do coletor original, com imports/identidade
  adaptados; não carrega o catálogo de localidades do Widgets nem seus arquivos privados.
- `app/widget_cache.py`: cache limitado/atômico exclusivamente do Workspace.

Preferências persistem na chave `desktop-widget` de `planner-ui.json`. A entrada de
login, quando solicitada, é `$XDG_CONFIG_HOME/autostart/io.orbitz.Workspace.DesktopWidget.desktop`.
Backups guardam preferências, mas não ativam automaticamente um autostart restaurado.
A janela verifica mudanças de configuração aproximadamente a cada segundo.

## Compatibilidade

O runtime atual exige Python 3.10+, GTK 3, PyGObject, Cairo/Pango e tzdata. Ubuntu
22.04+ é o alvo inicial. Não há promessa de funcionamento em toda versão histórica.
A janela prefere X11/XWayland quando DISPLAY está disponível. Em Wayland nativo,
posição absoluta, camada inferior e presença em todas as áreas de trabalho dependem
aprovação/suporte do compositor; a janela ainda funciona como superfície GTK.

Referências primárias: [GTK: posicionamento](https://docs.gtk.org/gtk3/method.Window.move.html),
[GTK: manter abaixo](https://docs.gtk.org/gtk3/method.Window.set_keep_below.html),
[Open-Meteo: clima](https://open-meteo.com/en/docs),
[Open-Meteo: localidades](https://open-meteo.com/en/docs/geocoding-api).

## Evidência

A regressão cobre modelo, formatos, fusos, PT/EN, visibilidade, cores, tipos inválidos,
configuração de login e persistência; os testes de previsão verificam schema, limites,
unidades, identidade de cache, cache stale e falhas de rede com respostas sintéticas.

O roteiro `tools/qa-widget-session.py` usa Broadway + D-Bus isolados e XDG temporário:
ativar/revelar, cancelar/preservar, buscar/selecionar cidade, estilos de hora/data,
prévia, aparência, autostart, falha de rede, trava, fechar Workspace mantendo widget
e processo real que encerra ao desabilitar. Capturas em `qa/desktop-widget-2026-11-03/`.

`tools/qa-widget-x11.py` confirmou no X11/XWayland deste computador a posição
[700,100], tipo `_NET_WM_WINDOW_TYPE_DESKTOP` e estados BELOW, STICKY, SKIP_PAGER e
SKIP_TASKBAR. Isso não equivale a uma matriz de teste de todos os compositores.

Uma busca de Brasília e a previsão real de sete dias foram consultadas com sucesso
na API pública, com cache temporário. Nenhum dado pessoal foi enviado nesses testes.

Para atualizar a instalação: `make install PREFIX="$HOME/.local"`. Fechar e reabrir
a janela principal para carregar o código novo. A ativação do widget é feita pelo usuário.

## Interações e escala proporcional

- Clique simples no relógio ou na data abre o Workspace; clique no bloco de clima
  abre a previsão de hoje e próximos dias, com mínima/máxima, condição, chuva e vento.
- A previsão reutiliza os mesmos dados/worker/cache, mantém o aviso de cache antigo
  e pode atualizar sem bloquear o relógio.
- Clique comum não arrasta mais o widget. Super + botão esquerdo inicia o movimento;
  a trava de posição bloqueia esse gesto. O monitor X11 acompanha o gesto mesmo
  quando o gerenciador de janelas captura o botão ou o ponteiro sai do widget.
- Ctrl+T com o ponteiro sobre o widget ativa um frame arredondado com oito alças
  sobre o próprio widget. Arraste uma alça para redimensionar proporcionalmente;
  Concluir, Esc ou Ctrl+T confirma. Não abre uma janela modal.
- O campo `scale` muda apenas a dimensão física; largura/altura lógicas, fontes,
  espaçamentos, bordas e raios continuam no mesmo canvas e recebem uma transformação
  Cairo uniforme. A escala persiste nas preferências e também pode ser definida ali.
- Áreas clicáveis são calculadas pelo mesmo renderer, acompanhando a escala.

O atalho sobre o widget usa `python3-xlib` em X11/XWayland. A captura passiva de
Ctrl+T é ativada somente quando o ponteiro está sobre a janela, e retirada ao sair;
não é um atalho global permanente. Há tratamento de repetição da tecla e Num/CapsLock.
Em outro backend o evento de teclado funciona quando a janela tem foco; o menu do
botão direito também permite redimensionar sem um atalho global.

O roteiro GTK valida os dois cliques, sete registros da previsão, Super + arraste,
ausência de arraste em clique simples, Ctrl+T, escala 150%, cancelamento e persistência.
Testes sem injetar entrada na sessão real verificam captura restrita ao hover,
repetição de tecla, movimento até a soltura e limpeza da conexão X11.
Referência: [Xlib: captura de teclas](https://www.x.org/releases/X11R7.6/doc/libX11/specs/libX11/libX11.html).

## Correção confirmada na sessão real

A combinação de janela de desktop/utility e estado BELOW deixava o widget visível,
mas os cliques físicos chegavam ao desktop nesta sessão. O clique injetado diretamente
no botão X11 funcionava, enquanto o contador do processo permanecia sem cliques físicos.
O usuário confirmou que a mudança para NORMAL sem BELOW fez os cliques funcionarem;
confirmou também Super + arraste e Ctrl+T nessa mesma janela.

A inicialização agora usa NORMAL, sem fixação abaixo/acima. Outras janelas podem
cobrir o widget normalmente. A aparência transparente permanece; não se afirma uma
integração forçada na camada de fundo do compositor. O relógio, a data e o clima usam
botões GTK transparentes com janelas de entrada X11 nativas. A previsão e o ajuste
não herdam a camada do widget. A abertura do Workspace utiliza o launcher do desktop
com o contexto de ativação do evento, e a entrada desktop possui StartupNotify.

A regressão de GUI agora envia eventos pelo dispatcher GTK às janelas de eventos dos
botões, em vez de apenas chamar os handlers Python. O teste nativo verifica NORMAL,
ausência de BELOW e mapeamento das janelas de entrada dos controles. O widget expõe
uma ação de diagnóstico somente-leitura (`widget-status`) com contadores, backend e
mapeamento dos controles; ela não inclui localidade, conteúdo de tarefas ou credenciais.

O teste de reinicialização em janela NORMAL usa uma posição inteiramente dentro do
monitor. Posições pedidas que deixam parte da janela fora da área útil podem ser
contidas pelo gerenciador (por exemplo, X=700 para 440 px em monitor de 1080 px).
Isso não é tratado como garantia de posicionamento fora dos limites da tela.

## Temas do widget

A aba Aparência oferece Light (padrão para novos widgets) e Dark. Light usa texto
e bordas escuros e fundo branco translúcido; Dark usa texto e bordas brancos e
fundo preto translúcido. A seleção aplica a paleta à prévia, mantendo tamanhos e
conteúdo; os controles de cor permitem ajustes posteriores. Widgets existentes
com texto branco são reconhecidos como Dark, preservando suas cores salvas.

## Rodapé Orbitz

`orbit.zone` aparece no canto inferior direito. Hover ou clique abre um painel
para cima, dentro do widget, com PayPal (desativado até definir o endereço),
GitHub (`https://github.com/orbitzone`) e site (`https://www.orbit.zone/`).
A saída do ponteiro fecha com pequeno atraso para permitir entrar no painel;
Esc também fecha. Light/Dark alteram as cores. Durante o redimensionamento,
o rodapé fica oculto; a área de conteúdo reserva espaço para a marca.

## Dashboard de previsão

A previsão usa um cartão principal com condição diária, temperatura atual, local
e horário dos dados. Sensação térmica e mínima/máxima ficam na faixa interna.
Chuva diária, umidade atual e vento máximo diário aparecem acima de sete cartões
numa linha (Hoje destacado). Ícones vetoriais desenhados por Cairo mantêm
a proporção. Temas Light/Dark e PT/EN são suportados; cache antigo continua
identificado. Não são exibidos horários solares sem dados do serviço.
