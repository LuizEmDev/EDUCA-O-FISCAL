# Missão Fiscal

Jogo 2D em Python/Pygame para ensinar educação fiscal com fases curtas, cartas de conteúdo e desafios de perguntas.

## Como jogar no Windows

```powershell
.\run_windows.ps1
```

## Gerar o arquivo .exe

```powershell
.\build_windows.ps1
```

O executável será criado em:

```text
dist\MissaoFiscal.exe
```

## Controles

- Setas ou WASD: mover
- Espaço, W ou seta para cima: pular
- 1, 2, 3, 4: responder perguntas
- Enter: avançar telas
- Esc: voltar/pausar

O jogo mostra um contador de FPS no canto inferior direito e limita a taxa máxima de quadros à taxa de atualização detectada no monitor.

## Conteúdo educativo

- Fase 1: impostos e serviços públicos
- Fase 2: nota fiscal e sonegação
- Fase 3: transparência e controle social

## Próximos ports

1. Windows: já preparado com PyInstaller.
2. Linux: usar `build_linux.sh` em uma máquina Linux.
3. Navegador: adaptar o loop para `pygbag`, mantendo Pygame.
4. Android: recomenda-se portar a interface para Kivy ou empacotar com Buildozer em Linux.
5. iOS: exige macOS/Xcode; o caminho mais viável em Python é Kivy-iOS, mas pode precisar de ajustes maiores.
