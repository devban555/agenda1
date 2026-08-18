Agenda1 - Marketing & Eventos

Módulo de campanhas e relacionamento integrado ao Agenda1.

FUNCIONALIDADES

1. Descontaço
- Seleção de público por segmento.
- Seleção manual de clientes.
- Mensagem personalizada.
- Envio pelo WhatsApp.
- Acompanhamento do progresso do envio.
- Confirmação ao concluir.
- Exibição de falhas quando existirem.
- Retorno automático do formulário ao estado inicial.

2. Sorteio
- Seleção de público.
- Sorteio realizado no servidor.
- Utiliza secrets.choice para escolha aleatória.

3. Fidelidade
- Ranking baseado no histórico de atendimentos.
- Cliente fidelizado a partir de 3 visitas realizadas.
- Ranking continua exibindo clientes com histórico abaixo do limite.

4. Oferta Flash
- Seleção de serviço ou produto.
- Seleção do público.
- Mensagem promocional pelo WhatsApp.
- Acompanhamento do progresso do envio.
- Confirmação ao concluir.
- Exibição de falhas quando existirem.
- Retorno automático do formulário ao estado inicial.

REGRAS DE PÚBLICO

Ativo:
- Possui agendamento futuro; ou
- Última visita ocorreu nos últimos 60 dias.

Inativo:
- Não possui agendamento futuro; e
- Não possui visita nos últimos 60 dias.

Fidelizado:
- 3 ou mais visitas realizadas.

ARQUIVOS PRINCIPAIS

- app/marketing_events.py
- app/templates/eventos.html
- app/templates/marketing_descontaco.html
- app/templates/marketing_sorteio.html
- app/templates/marketing_fidelidade.html
- app/templates/marketing_oferta_flash.html
- app/static/css/pages/eventos.css
- app/static/css/pages/marketing_eventos.css

INTEGRAÇÃO

O módulo reutiliza a função enviar_whatsapp() existente em app/routes.py.

O envio utiliza a integração WhatsApp/Baileys configurada no Agenda1.

BANCO DE DADOS

Esta versão não cria novas tabelas e não exige migração de banco.

São utilizados os dados já existentes de:
- Cliente
- Agendamento
- Servico
- Produto

OBSERVAÇÕES

- Descontaço e Oferta Flash enviam campanhas, mas não criam cupom ou baixa automática de estoque.
- Oferta Flash não reserva horário automaticamente.
- O envio de campanhas atualmente é executado pelo processo do Agenda1.
- Para campanhas maiores, uma futura evolução recomendada é uma fila persistente de envios.

STATUS

Testado localmente:
- Descontaço
- Sorteio
- Fidelidade
- Oferta Flash
- envio WhatsApp
- acompanhamento de envio
- confirmação de conclusão
