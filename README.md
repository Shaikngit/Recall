# Recall

Recall is a small Flask app for capturing, organizing, and recalling internal knowledge through a web UI.

If you are adapting Recall from an existing private notes repository, create a fresh public repo from a sanitized export instead of publishing old git history that may contain personal content.

## What The App Does

- Saves quick notes into `Inbox/YYYY-MM-DD.md`
- Organizes clear-topic captures into `KB/AKS/`, `KB/Networking/`, `KB/SQL/`, `KB/PrivateEndpoint/`, and `KB/Copilot/`
- Lets users ask questions against the managed knowledge base
- Supports Azure OpenAI, GitHub Models, and other OpenAI-compatible providers through the settings UI
- Runs locally or on Azure App Service

## Public Repo Cutover

If you are starting from an older private repository, create a new public repo from a sanitized export instead of exposing the original git history.

From the repo root:

```powershell
.\scripts\export-public-repo.ps1
```

That export keeps only the product files needed for the public repo and omits private knowledge folders. The detailed cutover note is in [docs/public-cutover.md](docs/public-cutover.md).

## Local Run

From the repository root in PowerShell:

```powershell
.\launch-kb.ps1
```

The launcher will:

- Create `.venv` if needed
- Install dependencies from `requirements-local.txt`
- Start the local dashboard on `http://127.0.0.1:8765`
- Start the tray app and global capture hotkey

## AI Settings

AI is required for recall. New deployments start with an empty knowledge base and users must connect a provider before they can ask questions.

Supported providers in the UI:

- Azure OpenAI
- GitHub Models
- OpenAI-compatible endpoints

Settings are stored locally in `.recall/model-settings.json`, which is ignored by git.

## Azure Hosting

The app is prepared for Azure App Service with `azd`.

Key behavior:

- Hosted notes are stored under App Service persistent `/home` storage through `MYKB_CONTENT_ROOT`
- Fresh hosted deployments start empty
- The app no longer imports packaged markdown folders into hosted storage
- Azure OpenAI is the first-class infrastructure path for deployment

### Deployment Modes

#### Reuse an existing Azure OpenAI resource

Set these azd environment values:

```powershell
azd env new <environment-name>
azd env set AZURE_LOCATION <azure-region>
azd env set AZURE_OPENAI_MODE existing
azd env set AZURE_OPENAI_RESOURCE_ID <existing-openai-resource-id>
azd env set AZURE_OPENAI_DEPLOYMENT <existing-deployment-name>
azd env set AZURE_OPENAI_MODEL_NAME gpt-4.1-mini
azd env set AZURE_OPENAI_DEPLOYMENT_CAPACITY 1
azd env set AZURE_OPENAI_ACCOUNT_NAME ""
azd provision --preview
azd up
```

#### Create a new Azure OpenAI resource during deployment

Set these azd environment values:

```powershell
azd env new <environment-name>
azd env set AZURE_LOCATION <azure-region>
azd env set AZURE_OPENAI_MODE new
azd env set AZURE_OPENAI_RESOURCE_ID ""
azd env set AZURE_OPENAI_DEPLOYMENT <new-deployment-name>
azd env set AZURE_OPENAI_MODEL_NAME gpt-4.1-mini
azd env set AZURE_OPENAI_DEPLOYMENT_CAPACITY 1
azd env set AZURE_OPENAI_ACCOUNT_NAME ""
azd provision --preview
azd up
```

The Bicep template will create:

- App Service plan
- Linux App Service
- System-assigned managed identity on the web app
- Azure OpenAI account and deployment when `AZURE_OPENAI_MODE` is `new`
- Azure OpenAI RBAC assignment for the web app identity

### Deployment Helper Script

There is also a local deployment helper:

```powershell
.\deploy-local.ps1 -Login -OpenAiMode existing -OpenAiResourceId <resource-id> -OpenAiDeployment <deployment-name>
.\deploy-local.ps1 -Login -OpenAiMode new -OpenAiDeployment <deployment-name> -OpenAiModelName gpt-4.1-mini
```

Pass `-BaseUrl` if you want the script to run the post-deploy health check and smoke test.

## Smoke Test

```powershell
.\scripts\smoke-test.ps1
.\scripts\smoke-test.ps1 -BaseUrl https://<your-app>.azurewebsites.net
```

The script checks `/`, `/healthz`, `/api/recent`, then performs a capture and ask flow.

## Files

- `kb_app/app.py`: Flask routes
- `kb_app/core.py`: capture, search, and organization logic
- `kb_app/ai.py`: provider integration and token handling
- `kb_app/templates/index.html`: browser UI
- `infra/main.bicep`: Azure infrastructure
- `scripts/export-public-repo.ps1`: one-time public repo export
