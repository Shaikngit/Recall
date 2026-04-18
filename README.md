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

## Source Of Truth

Treat the public repo as the product repository that downstream users clone and deploy.

- Make product changes in the public repo and push them there.
- Use the public repo as the only deployment source for the production website.
- Do not keep a parallel app-development workflow in the private repo once you have moved to the public repo.

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
- The default hosted content root is `/home/mykb-content` to stay compatible with older MyKB App Service deployments

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
azd env set AZURE_OPENAI_ASSIGN_ROLE true
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
azd env set AZURE_OPENAI_ASSIGN_ROLE true
azd provision --preview
azd up
```

The Bicep template will create:

- App Service plan
- Linux App Service
- System-assigned managed identity on the web app
- Azure OpenAI account and deployment when `AZURE_OPENAI_MODE` is `new`
- Azure OpenAI RBAC assignment for the web app identity

If your identity cannot create role assignments on the Azure OpenAI resource, set `AZURE_OPENAI_ASSIGN_ROLE=false` before `azd provision --preview`. The app will still deploy, but Azure OpenAI access must then be completed separately by either:

- having someone with `User Access Administrator` or `Owner` grant the web app's managed identity the `Cognitive Services OpenAI User` role on the Azure OpenAI account
- or configuring another supported provider in the app settings UI after deployment

### Deployment Helper Script

There is also a local deployment helper:

```powershell
.\deploy-local.ps1 -Login -OpenAiMode existing -OpenAiResourceId <resource-id> -OpenAiDeployment <deployment-name>
.\deploy-local.ps1 -Login -OpenAiMode new -OpenAiDeployment <deployment-name> -OpenAiModelName gpt-4.1-mini
.\deploy-local.ps1 -Login -OpenAiMode existing -OpenAiResourceId <resource-id> -OpenAiDeployment <deployment-name> -AssignOpenAiRole $false
```

Pass `-BaseUrl` if you want the script to run the post-deploy health check and smoke test.

### Deploy To An Existing App Service

If you already have an App Service that was created from an earlier private repo, use the code-only deploy script instead of reprovisioning infrastructure. This preserves the existing app settings, Azure OpenAI wiring, and hosted content root.

```powershell
.\scripts\deploy-existing-appservice.ps1 -ResourceGroup <resource-group> -AppName <app-name> -BaseUrl https://<your-app>.azurewebsites.net
```

This path is the safest way to move day-to-day product development to the public repo while keeping an older production website stable.

### GitHub Push Deploy

The public repo also includes a GitHub Actions workflow for deploying to the existing production App Service on pushes to `main` or by manual dispatch.

Before using it, add this repository secret in GitHub:

- `AZURE_CLIENT_ID`: Entra app registration client ID for the GitHub Actions deploy identity
- `AZURE_TENANT_ID`: `16b3c013-d300-468d-ac64-7eda0820b6d3`
- `AZURE_SUBSCRIPTION_ID`: `58400668-ed03-47a3-a7f8-fb03677bdffb`

After that, pushing to `main` in the public repo can deploy the app automatically.

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
