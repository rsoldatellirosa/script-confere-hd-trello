# check_disk.py — Hapolo Server Disk Monitor

Script Python para monitoramento automatizado do uso de disco em servidores Linux, com integração ao Trello.

## Funcionalidades

- Conexão SSH em múltiplos servidores simultaneamente
- Coleta de uso de disco via `df -h`
- Relatório CSV com timestamp para histórico
- Atualização automática de checklists no Trello
- Saída colorida no terminal com alertas visuais

## Requisitos

- Python 3.7+
- Dependências:

```bash
pip install paramiko requests python-dotenv
```

## Configuração

### 1. Variáveis de ambiente

Copie o arquivo de exemplo e preencha com os valores reais:

```bash
cp .env.example .env
```

Edite o `.env` com suas credenciais (API Key e Token do Trello, porta SSH, etc).

> ⚠️ **Nunca suba o arquivo `.env` para o GitHub.**

### 2. Servidores

Copie e preencha com os dados dos seus servidores:

```bash
cp servers.json.example servers.json
```

Formato:
```json
[
  {"name": "NOME_SERVIDOR", "password": "senha", "ip": "000.000.000.000"}
]
```

> ⚠️ **Nunca suba o `servers.json` para o GitHub.**

### 3. Mapeamento Trello

Copie e preencha com os IDs dos checkItems do Trello:

```bash
cp checklist_items.json.example checklist_items.json
```

Formato:
```json
{
  "IP_DO_SERVIDOR": "ID_DO_CHECKITEM_TRELLO"
}
```

Para obter os IDs dos checkItems via API:
```bash
python -c "import requests; r = requests.get('https://api.trello.com/1/checklists/ID_DA_CHECKLIST/checkItems', params={'key': 'SUA_KEY', 'token': 'SEU_TOKEN', 'fields': 'name,id'}); print(r.text)"
```

> ⚠️ **Nunca suba o `checklist_items.json` para o GitHub.**

## Uso

```bash
python check_disk.py
```

Os relatórios CSV são salvos automaticamente na pasta `disk_reports/`.

## Estrutura do projeto

```
check_disk.py               # Script principal
.env.example                # Modelo de configuração (sem credenciais)
servers.json.example        # Modelo de lista de servidores (sem credenciais)
checklist_items.json.example# Modelo de mapeamento Trello (sem IDs reais)
.gitignore                  # Garante que arquivos sensíveis não sejam versionados
README.md                   # Este arquivo
disk_reports/               # Pasta gerada automaticamente com os CSVs
```

## Desenvolvido por

Hapolo Soluções Digitais — Infraestrutura & DevOps
