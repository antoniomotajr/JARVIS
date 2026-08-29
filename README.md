# JARVIS — Fase 1: MVP de Voz

Pipeline:

Microfone -> Wake Word -> Whisper -> Ollama -> Piper -> alto-falante

## Requisitos

- Windows 10/11
- Python 3.11 ou 3.12 recomendado
- Microfone e alto-falante/fone
- Ollama
- Modelo LLM
- Modelo de voz Piper

## Instalação

Crie o ambiente:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Copie `.env.example` para `.env`.

## Ollama

O modelo padrão do projeto (definido em `.env`) é `qwen2.5:1.5b`:

```powershell
ollama pull qwen2.5:1.5b
ollama run qwen2.5:1.5b
```

Para usar outro modelo, baixe-o com `ollama pull <modelo>` e ajuste `OLLAMA_MODEL` no `.env`.

Em outro terminal:

```powershell
python test_setup.py
```

## Piper

Este projeto já traz o executável `piper.exe` e o modelo de voz em
`models/piper/`, então normalmente nada precisa ser instalado — o `.env`
já aponta `PIPER_EXECUTABLE=models/piper/piper.exe`.

Se preferir usar uma instalação própria do Piper (ex.: via `pip install
piper-tts`), defina `PIPER_EXECUTABLE=piper` no `.env` para usar o
executável do PATH do sistema em vez do bundled.

Para trocar a voz, coloque o novo modelo `.onnx` em `models/piper/` e
ajuste `PIPER_MODEL` no `.env`. O arquivo `.onnx.json` correspondente
também deve estar junto do `.onnx`.

## Painel web (recomendado)

```powershell
python web_app.py
```

Sobe um servidor local em `http://127.0.0.1:5000` e já abre o painel
gráfico no navegador — não é mais preciso ficar de olho no terminal
pra saber o que o Jarvis está fazendo:

- O anel central mostra o status em tempo real (STANDBY / OUVINDO /
  PROCESSANDO / FALANDO) e o log embaixo mostra cada ação (wake word
  detectada, o que você disse, o que o Jarvis respondeu/executou).
- O botão **INICIAR/DESATIVAR J.A.R.V.I.S** liga e desliga a escuta
  por voz (wake word + conversa) sem precisar reiniciar o processo.
- Clicar num navegador ou aplicativo na lista **abre de verdade**
  (chama o mesmo `core/executor.py` usado pela voz); o "✕" ao lado de
  um app pede confirmação e fecha.
- **+ ADICIONAR NAVEGADOR / APLICATIVO / SITE** grava direto em
  `apps.json` (pelo mesmo mecanismo que a voz usa pra reconhecer
  comandos) — não precisa editar o arquivo na mão nem reiniciar o
  Jarvis pra usar o que acabou de cadastrar.
- Sites cadastrados dentro do accordion de um navegador abrem sempre
  como aba nova NAQUELE navegador específico.

Os modos de terminal (`python main.py` e `python main.py --text`)
continuam funcionando e são úteis pra depurar áudio/logs mais a fundo,
mas o painel web é a forma recomendada de usar o Jarvis no dia a dia.

## Teste sem voz (modo texto no terminal)

```powershell
python main.py --text
```

Esse modo testa o Ollama e o Piper sem Wake Word/Whisper.

## Modo completo (terminal)

```powershell
python main.py
```

Diga:

```text
Hey Jarvis
```

e depois fale o comando.

## Observação

O openWakeWord utiliza o modelo pré-treinado `hey_jarvis`; portanto a palavra de ativação nesta versão é "Hey Jarvis/Jarvis" conforme o comportamento do modelo.

## Próxima fase

Depois de validar o MVP:

1. MySQL
2. histórico de conversas
3. memória persistente
4. ChromaDB/RAG
5. ~~executor de comandos com permissões~~ ✅ implementado (ver abaixo)
6. automação do Windows
7. dashboard

## Executor de comandos (abrir/fechar aplicativos)

O Jarvis reconhece frases como "abra o Firefox" ou "feche o Chrome" e
executa a ação **antes** de passar qualquer coisa para o LLM — o
Ollama nunca decide sozinho o que rodar no seu PC.

- A lista de aplicativos permitidos fica em `apps.json`, na raiz do
  projeto. Cada entrada tem `nome`, `aliases` (formas de falar o nome),
  `exe` (nome do processo, usado para fechar) e `open_cmd` (comando
  para abrir). Dá pra editar esse arquivo na mão, mas o jeito mais
  fácil é usar os botões "+ ADICIONAR..." do painel web, que gravam
  ali direto.
- **Abrir** roda direto, sem confirmação — é uma ação de baixo risco.
- **Fechar** sempre pergunta "Tem certeza? Diga sim ou não" antes de
  executar, porque `taskkill /F` força o encerramento e pode perder
  trabalho não salvo. Para pular a confirmação em um app específico,
  adicione `"confirm_close": false` na entrada dele em `apps.json`.
- Só os apps listados em `apps.json` podem ser abertos/fechados; um
  pedido fora da lista cai na conversa normal com o LLM, que foi
  instruído a dizer que não tem essa capacidade em vez de fingir que
  executou algo.
- Esse recurso usa `taskkill`, então só funciona no Windows.
