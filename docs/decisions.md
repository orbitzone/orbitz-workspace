# Decisões

- 2026-11-02: nome confirmado Orbitz Workspace, ID `io.orbitz.Workspace`.
- Extrair o domínio Python/GTK completo, sem painéis GJS e sem coletores da extensão.
- Armazenamento e configuração em `orbitz-workspace`, sem importação automática.
- Manter formato de backup `orbitz-workspace`; credenciais usam schemas exclusivos do Workspace.
- Empacotamento inicial via Makefile; Flatpak e publicação são etapas posteriores.
- Preferências de idioma locais ao aplicativo; sem dependência GSettings do GNOME Shell.

- Nome de repositório confirmado: `orbitz-workspace`. Não há remoto configurado neste checkout.

- 2026-11-03: concluir identidade própria também no editor auxiliar, autor do PDF e cofre.
  Credenciais do Widgets não são removidas ou modificadas; a migração requer reconexão.
- Lembretes locais e de eventos em cache passam a ser agendados pelo aplicativo GTK.
  Funcionam enquanto ele estiver aberto; não foi instalado serviço em segundo plano.
- Diretório local passa a `orbitz-workspace`, com link de compatibilidade no caminho
  anterior para manter referências existentes. Não há remoto a renomear.

- Widget de desktop é um processo GTK separado (`io.orbitz.Workspace.DesktopWidget`).
  Preferências em `planner-ui.json` preservam o escopo de backup existente. Cache de
  clima fica em `~/.cache/orbitz-workspace/weather`; nenhuma configuração do Widgets
  é compartilhada. O provedor Open-Meteo é reutilizado com validação e limites de rede.
- Preferir X11/XWayland para dicas DESKTOP/BELOW/STICKY, com fallback GTK Wayland.
  Instalação não cria extensão GNOME nem altera o shell. Não prometer “qualquer versão”
  sem empacotamento/runtime e matriz de testes correspondentes.
- Widget não é ativado automaticamente pela instalação. Autostart é configurado
  somente pelo checkbox explícito; desabilitar o widget remove sua própria entrada.
