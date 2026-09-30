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

## Configuração (.env)

| Variável | Para quê |
|---|---|
| `ANTHROPIC_API_KEY` | Cérebro (Claude). `JARVIS_MODEL` troca o modelo |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | Voz. Sem elas o Jarvis só imprime o texto |
| `WHISPER_MODEL` | `small` sem GPU; `medium`/`large-v3` com GPU NVIDIA |
| `SPOTIPY_*` | Controle do Spotify (conta Premium) |

### Voz estilo JARVIS
Escolha em elevenlabs.io/voice-library uma voz masculina britânica, calma e formal, com suporte a português
(filtre por "British", "butler"/"narrator"), copie o *Voice ID* para o `.env`.
Se quiser clonar uma voz, use apenas uma que você tenha autorização para usar.

### Introdução do primeiro comando do dia
No primeiro comando de cada dia o Jarvis toca uma música por `INTRO_SECONDS` segundos (com fade-out) e
diz a saudação. Duas opções:
- **Arquivo local:** coloque seu áudio em `assets/intro.mp3` (ou aponte `INTRO_AUDIO_FILE`).
- **Spotify:** informe `INTRO_SPOTIFY_URI` (ex.: `spotify:track:...`).

A data da última introdução fica em `~/.jarvis_state.json`; apague o arquivo para ouvir de novo.

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
