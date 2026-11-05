# Validação de Orbitz Workspace — 2026-11-03

## Resultado

- 128 testes Python aprovados, sem skips na execução com loopback permitido.
- 53 telas/estados de widgets GTK exercitados em ambiente gráfico isolado.
- Instalação em staging, compilação Python e arquivo desktop validados.
- Nenhuma instalação ativa, conta real ou dado pessoal foi alterado.

## Percurso

| Área | Fluxos exercitados |
| --- | --- |
| Hoje | Resumo, tarefas e navegação; PT/EN |
| Agenda | Evento fictício em cache, seleção de fonte e conversão em tarefa |
| Tarefas | Criar, editar, concluir, vincular horas e consultar registros |
| Horas | Nova timesheet, contexto, inclusão, edição inline, dia/semana/mês, cronômetro, exportar CSV, arquivar e consultar arquivo |
| Invoices | Formulário, prévia, salvar PDF pela interface, histórico, marcar pagamento, versões, importar PDF (cancelar), instruções de assinatura e confirmação de exclusão (cancelar) |
| Conexões | Formulários iCloud, Google, Calendly, ICS e gerenciamento; sem autenticar |
| Preferências | Área inicial e troca de idioma depois de fechar formulários |
| Backup | Exportação ZIP, escolha, prévia, cancelamento, restauração confirmada e fechamento do app |
| Lembretes | Limites de horário, deduplicação, persistência, criação da notificação e ação de abrir a tarefa; envio ao desktop simulado |

## Correções

- Confirmações de pagamento/exclusão referenciavam `localized`, que não existia no callback.
- Trocar o idioma podia acessar um ComboBox destruído após fechar o formulário de invoice.
- Diálogos de confirmação e preferências tinham dimensões insuficientes.
- O calendário usava cores fixas escuras mesmo no tema claro.
- Lembretes eram calculados pela extensão; agora o aplicativo tem agendador próprio.
- Editor auxiliar, PDF e schemas de credenciais usam a identidade Orbitz Workspace.

## Limites

O roteiro usa dados descartáveis e não testa login ou sincronização com contas reais,
assinatura no gov.br nem abertura por aplicativos externos do desktop. Os testes OAuth
usam callbacks locais sintéticos. O cliente Google ainda precisa de configuração própria
antes da publicação. Lembretes funcionam com o aplicativo aberto; nenhum serviço em
segundo plano foi instalado. A origem e os créditos do Widgets permanecem documentados.

Evidências: [capturas e relatório](qa/2026-11-03/README.md).

## Ampliação: widget de desktop

Regressão atual: 149 testes aprovados, sem skips fora do sandbox. O percurso de 53
estados do Workspace continua aprovado. O novo widget tem mais oito estados GTK,
validação de processo separado e teste de propriedades nativas no X11/XWayland.
[Documentação e limites](desktop-widget.md) · [Capturas](qa/desktop-widget-2026-11-03/README.md).
