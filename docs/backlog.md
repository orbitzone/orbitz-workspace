# Próximas etapas

- Finalizar identidade visual de Orbitz Workspace (`orbitz-workspace`).
- Revisar UX das cinco áreas e eventual adoção de GTK/libadwaita.
- Configurar identidade OAuth própria e testar autenticação/sincronização com contas reais.
- Validar assinatura no portal gov.br e abertura no visualizador PDF do desktop real.
- Preparar Flatpak, metainfo, CI e publicação no repositório remoto a configurar.
- Avaliar lembretes com o aplicativo fechado, que exigem execução em segundo plano.

# Validado em 2026-11-03

128 testes passaram, sem skips fora do sandbox; 53 telas/estados GTK foram exercitados
com dados fictícios. Inclui tarefas, calendário em cache, timers, CSV, invoice PDF,
pagamento, arquivo de timesheets, idioma, exportação e restauração completa de backup.
Evidências em `qa/2026-11-03/` e limites em `validation.md`.

## Compatibilidade do widget

- Matriz Ubuntu 22.04/24.04/26.04, diferentes desktops, X11/XWayland e Wayland nativo.
- Empacotamento com runtime próprio para ampliar suporte a Ubuntu antigos.
- Avaliar integração de camada nativa por compositor, sem exigir extensão GNOME.
- Revisar plano/termos Open-Meteo antes de distribuição comercial.
