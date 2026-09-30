# JARVIS

Assistente de voz: hotword offline → Whisper → Claude (com ferramentas) → voz natural.

```
microfone → openWakeWord ("hey jarvis") → gravação até você parar de falar
          → faster-whisper (local) → Claude + tools → ElevenLabs → alto-falante
```

## Instalação

Requer Python 3.10+ e um microfone/alto-falante (rode na sua máquina, não em servidor).

```bash
cd jarvis
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # e preencha as chaves
python main.py
```

Na primeira execução o Whisper e o modelo da hotword são baixados automaticamente.

## Instalação no Mac (Apple Silicon)

```bash
cd jarvis
bash scripts/setup_mac.sh
```

O script instala Python 3.11 e PortAudio via Homebrew, cria o `.venv` e instala as dependências
(no M1 o Whisper roda via `mlx-whisper`, usando o chip). Depois edite o `.env`, coloque a música em
`assets/intro.mp3` e rode `source .venv/bin/activate && python main.py`.
Na primeira execução, autorize o **Microfone** para o Terminal quando o macOS pedir
(ou em Ajustes do Sistema > Privacidade e Segurança > Microfone).

## Configuração (.env)

| Variável | Para quê |
|---|---|
| `ANTHROPIC_API_KEY` | Cérebro (Claude). `JARVIS_MODEL` troca o modelo |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | Voz. Sem elas o Jarvis só imprime o texto |
| `WHISPER_MODEL` | `small` (padrão); no M1 `medium` também é rápido. `WHISPER_BACKEND=auto` escolhe mlx no Mac |
| `SPOTIPY_*` | Controle do Spotify (conta Premium) |

### Voz estilo JARVIS
Escolha em elevenlabs.io/voice-library uma voz masculina britânica, calma e formal, com suporte a português
(filtre por "British", "butler"/"narrator"), copie o *Voice ID* para o `.env`.
Se quiser clonar uma voz, use apenas uma que você tenha autorização para usar.

### Velocidade de resposta
- O Jarvis fala **frase a frase** enquanto o Claude ainda está escrevendo, então a voz começa antes de a resposta terminar.
- `SILENCE_SECONDS` (padrão 0.6) é quanto silêncio ele espera para saber que você terminou de falar. Menor = mais rápido, mas pode cortar pausas.
- Para respostas ainda mais rápidas, use um modelo menor em `JARVIS_MODEL` (por exemplo `claude-haiku-4-5`).

### Introdução do primeiro comando do dia
No primeiro comando de cada dia o Jarvis toca uma música por `INTRO_SECONDS` segundos (com fade-out) e
diz a saudação. Duas opções:
- **Arquivo local:** coloque seu áudio em `assets/intro.mp3` (ou aponte `INTRO_AUDIO_FILE`).
- **Spotify:** informe `INTRO_SPOTIFY_URI` (ex.: `spotify:track:...`).

Depois do bipe a música continua **baixinho ao fundo** (`INTRO_BED_LEVEL`, por `INTRO_AFTER_SECONDS` segundos)
e quase some enquanto você fala. O holograma pulsa com a batida da música (arquivo local; o Spotify não
permite analisar o áudio).

A data da última introdução fica em `~/.jarvis_state.json`; apague o arquivo para ouvir de novo.

## Tela HUD

Ao iniciar, o Jarvis abre uma tela futurista no navegador (`http://127.0.0.1:8765`) que reage em tempo real:
boot durante a música de abertura, e cores/animações para ouvindo, processando e respondendo.
Aperte `Ctrl+Cmd+F` no navegador para tela cheia.

### Widgets
| Widget | Fonte |
|---|---|
| Clima e previsão por hora | Open-Meteo (cidade em `JARVIS_CITY`) |
| Monitor do computador (CPU, memória, disco, bateria, rede) | psutil |
| Tocando agora | Spotify (se configurado) |
| Temporizadores | ferramenta `set_timer` |
| Relógios mundiais, comandos e tempo ativo | local |
| Agenda e e-mail | prontos para a fase do Google (`hud.publish("agenda", ...)`, `hud.publish("email", ...)`) |

**No tablet (Lenovo Tab):** no `.env` coloque `HUD_HOST=0.0.0.0`, rode o Jarvis e abra no navegador do tablet
o endereço que ele imprime ("No tablet, abra: ..."), com os dois aparelhos no mesmo Wi-Fi.
Nesse modo qualquer aparelho da rede consegue ver a tela; use só em rede de confiança.
Para desligar: `HUD=0`. Para não abrir o navegador sozinho: `HUD_AUTO_OPEN=0`.

## Ferramentas atuais

Data e hora, temporizador, Spotify (tocar, pausar, próxima, volume, o que está tocando).

Para criar uma nova, adicione um `Tool(...)` em `jarvis/tools/` e registre em `build_tools`.
O Claude decide sozinho quando chamá-la.

## Próximas fases

- Gmail (ler, resumir, buscar) e Google Agenda (listar/criar eventos) via OAuth
- Resposta do Claude em streaming, falando frase a frase (menos latência)
- Interface HUD

## Testes

```bash
pytest tests
```
