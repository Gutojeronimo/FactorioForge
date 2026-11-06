# ForgePlan Area Bridge

Mod para Factorio 2.1. O atalho cria uma ferramenta de seleção; ao concluir a seleção, o mod grava tamanho, origem, superfície, jogador e tick em `script-output/forgeplan-area.json`.

ForgePlan lê esse arquivo, mede o retângulo real dos layouts candidatos, limita largura/altura e configura o encaixe absoluto do blueprint para coincidir com a grade da área selecionada. O app continua exportando uma string de blueprint; a colocação final é feita com a ferramenta de blueprint do jogo.

O limite é 512 tiles por lado. Instale `outputs/forgeplan-area-bridge_0.1.0.zip` na pasta `mods` do perfil usado pelo jogo, ative o mod e reinicie o Factorio. No jogo, clique no atalho **Exportar área para ForgePlan**, arraste sobre o terreno e solte. O mod limpa a captura anterior ao iniciar um mundo novo ou mudar sua configuração; selecione uma nova área em cada mundo/superfície que for usar. Depois clique em **Importar área do jogo** na aba Layout do app; a restrição da área será ativada automaticamente. Se o layout não couber, o app tenta outra geometria automática e, se nenhuma couber, informa o motivo.
