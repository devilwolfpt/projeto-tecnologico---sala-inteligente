# Controlo de presenças com Tapo C200

Aplicação local para registar entradas e saídas através do stream RTSP da Tapo
C200 e de reconhecimento facial executado no próprio PC. Os dados ficam em
SQLite e os snapshots são guardados localmente.

> **Privacidade:** rostos e encodings faciais são dados biométricos; idade e
> contactos também são dados pessoais. Antes de utilizar em contexto escolar,
> confirme a base legal, as autorizações necessárias, a informação aos
> encarregados de educação, o prazo de conservação e quem pode aceder aos dados.
> Esta aplicação não tem autenticação nos endpoints; mantenha-a numa rede
> controlada e não exponha a porta 8000 à Internet. Contactos e idade não são
> incluídos nos endpoints do dashboard.

## Requisitos

- Python 3.10 ou superior.
- Windows, Linux ou macOS; uma câmara Tapo C200 acessível na rede local.
- A aplicação Tapo e uma conta de câmara configurada para RTSP.
- Dependências Python de `requirements.txt`. Em Windows, a instalação de
  `dlib` pode exigir passos adicionais descritos abaixo.

## 1. Preparar a Tapo C200

1. Ligue a câmara à rede local e atualize a aplicação Tapo e o firmware.
2. Na aplicação Tapo, abra as definições da câmara e procure **Definições
   avançadas > Conta da câmara** (a designação pode variar conforme a versão).
3. Crie uma conta de câmara com nome de utilizador e palavra-passe próprios.
   Não use as credenciais da conta Tapo.
4. Reserve um endereço IP para a câmara no router, para que o `CAM_IP` não
   mude. Confirme que o PC e a câmara estão na mesma rede.
5. O stream principal usa normalmente a porta `554` e o caminho `stream1`.
   O URL usado pela aplicação é
   `rtsp://<CAM_USER>:<CAM_PASS>@<CAM_IP>:554/stream1`.

Não publique o URL RTSP: inclui credenciais da câmara.

## 2. Instalar

Na pasta do projeto, crie e ative um ambiente virtual:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Em Linux/macOS, a ativação é `source .venv/bin/activate`.

### Nota sobre `dlib` no Windows

O `dlib` é uma dependência nativa e o PyPI pode não disponibilizar um wheel
compatível com a versão de Python e arquitetura instaladas. Nesse caso,
`pip install -r requirements.txt` pode tentar compilar o código C++ e falhar.

Opções:

- Instale primeiro um wheel pré-compilado de `dlib` que corresponda exatamente
  à versão de CPython (por exemplo, CPython 3.11), arquitetura (x64) e versão
  `19.24.6`, obtido de uma fonte de terceiros em que confie; depois repita
  `pip install -r requirements.txt`. Verifique a origem e a integridade do
  ficheiro antes de o instalar.
- Em alternativa, use um ambiente Conda e instale `dlib` de um canal Conda
  fiável. Confirme que a versão instalada satisfaz o pin do projeto.
- Se não conseguir obter um binário compatível, use Linux/WSL ou compile com
  Visual Studio C++ Build Tools e CMake instalados.

`face_recognition_models` é instalado como dependência Python, mas não substitui
o `dlib`. A aplicação não descarrega nem envia imagens para serviços externos.

## 3. Configurar

Copie o ficheiro de exemplo:

```powershell
Copy-Item .env.example .env
```

Edite `.env` e substitua pelo endereço IP, utilizador e palavra-passe da conta
de câmara criada na aplicação Tapo. As restantes definições são:

| Variável | Valor inicial | Descrição |
|---|---:|---|
| `CAM_RTSP_PORT` | `554` | Porta RTSP da câmara |
| `CAM_STREAM` | `stream1` | Caminho do stream |
| `FACE_TOLERANCE` | `0.5` | Distância máxima para aceitar uma correspondência |
| `DEBOUNCE_SECONDS` | `30` | Intervalo mínimo entre registos consecutivos |
| `MIN_INTERVAL_MINUTES` | `10` | Tempo mínimo entre entrada e saída |
| `PROCESS_EVERY_N_FRAMES` | `5` | Processa um em cada N frames recebidos |
| `DB_PATH` | `data/presencas.db` | Caminho da base de dados SQLite |
| `ENCODINGS_PATH` | `data/encodings.pkl` | Cópia local dos encodings faciais |
| `SNAPSHOTS_PATH` | `snapshots` | Pasta dos snapshots de auditoria |
| `CAMERA_RECONNECT_SECONDS` | `5` | Espera entre tentativas RTSP |
| `PC_CAMERA_INDEX` | `0` | Índice da webcam predefinida do PC |

Com `PROCESS_EVERY_N_FRAMES=5`, o processamento será aproximadamente 3 vezes
por segundo se o stream fornecer 15 frames por segundo. O valor efetivo depende
da taxa de frames da câmara.

## 4. Registar um aluno ou professor

Ligue uma webcam local ao computador e execute:

```powershell
python scripts/enroll.py
```

Introduza nome, cargo e os dados pedidos. Para alunos, ano e curso são
obrigatórios; para professores, esses campos não se aplicam. Idade, telefone,
email e horário previsto são opcionais. As horas reais de entrada e saída são
registadas automaticamente nos eventos de presença. A janela de captura mostra
a webcam: enquadre apenas a pessoa, prima **Espaço** para recolher cada amostra
e **Q** para cancelar. Por omissão são recolhidas cinco amostras. Também pode
passar argumentos:

```powershell
python scripts/enroll.py --nome "Nome do aluno" --cargo Aluno --ano "1.º" --curso "TPI" --idade 16 --hora-entrada 08:00 --hora-saida 17:00 --imagens 5
python scripts/enroll.py --nome "Nome do professor" --cargo Professor --telefone "912345678" --email "professor@example.org"
```

O perfil e os encodings são guardados na BD. O ficheiro `data/encodings.pkl` é
gerado/sincronizado a partir dos encodings ativos na BD. Os campos antigos de
turma são preservados. A migração acrescenta os novos campos sem apagar os
alunos ou registos já existentes; os perfis anteriores são classificados como
`Aluno`. Para preencher os dados dos perfis existentes sem duplicar encodings:

```powershell
python scripts/update_pessoa.py --id 1
```

Para listar alunos e professores:

```powershell
python scripts/list_alunos.py
```

O script de listagem mostra cargo, ano, curso/turma, idade e horário previsto,
mas omite telefone e email.
Depois de registar uma nova pessoa com o servidor já em execução, reinicie-o
para que o motor facial carregue os novos encodings.

## 5. Arrancar o dashboard

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Abra `http://localhost:8000` no PC. A câmara inicia em segundo plano; se o
stream estiver indisponível, a aplicação continua a funcionar e tenta
reconectar a cada cinco segundos. Para aceder a partir de outro equipamento,
use o IP local do PC e restrinja o acesso na firewall à rede autorizada.

Endpoints disponíveis:

- `GET /` — dashboard HTML com vídeo MJPEG, últimos 20 registos e presentes.
- `GET /video_feed` — stream MJPEG.
- `GET /api/registos?data=YYYY-MM-DD` — registos do dia (UTC); aceita também
  `limit` para limitar a lista.
- `GET /api/presentes` — alunos e professores cujo último registo é uma entrada;
  telefone, email e idade não são incluídos.
- `GET /api/camera/status` — fonte ativa, estado de ligação e erro seguro.
- `POST /api/camera/source` — altera a fonte; corpo JSON
  `{"source":"tapo"}` ou `{"source":"webcam"}`.

O arranque utiliza sempre a Câmara Tapo. A origem pode ser alterada em
execução no painel “Câmara em direto”, sem reiniciar o servidor. Quando a
Tapo está selecionada, a aplicação mantém a reconexão RTSP e usa o backend
FFmpeg do OpenCV. A webcam do PC usa o backend próprio do sistema operativo
e o índice definido por `PC_CAMERA_INDEX`. Os endpoints de estado não incluem
credenciais RTSP.

## Organização

```text
tapo_facial/
├── app/
│   ├── camera.py
│   ├── config.py
│   ├── database.py
│   ├── face_engine.py
│   ├── logic.py
│   ├── main.py
│   └── templates/index.html
├── data/
├── scripts/
│   ├── enroll.py
│   ├── list_alunos.py
│   └── update_pessoa.py
├── snapshots/
├── requirements.txt
└── .env.example
```

## Trocar o motor facial

O motor atual está isolado em `app/face_engine.py`, que fornece resultados no
formato `FaceMatch`. Se o `dlib` não for viável no ambiente, uma alternativa é
substituir essa implementação por DeepFace com backend `opencv`, mantendo a
interface `recognize()` e o formato de resultado consumido por `main.py`.
Essa troca requer adaptar a extração e armazenamento dos encodings e validar a
precisão com imagens adequadas; não é ativada automaticamente nesta versão.
