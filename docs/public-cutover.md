# Public Repo Cutover

Use this guide when you are splitting a reusable public Recall repo out of an older private notes repository. Create the public repo from a sanitized export instead of exposing the original git history.

## Private Content Boundary

Do not publish personal knowledge folders from this repo. The export script intentionally omits all note-library content and keeps only product code, deployment files, and documentation.

Examples of private content currently present in this workspace:

- `Inbox/`
- `KB/`
- `AKS_Udemy/`
- `AzureVPN/`
- `Csharp-Bangarraju/`
- `ExpressRoute Fastpath/`
- `HostNetworking/`
- `PacketcaptureScenarios/`
- `PrivateEndpoint/`
- `Quick Tips/`
- `RealIPFixMetadata/`
- `SQLServer/`
- `TCPIPBasics/`
- `attachments/`

## One-Time Cutover

1. Keep this repo private as the archive.
2. Run `./scripts/export-public-repo.ps1` from the repo root.
3. Create a new GitHub repository for the exported folder.
4. Initialize git in the exported folder and push it to the new public repository.
5. After the cutover, make future code and infrastructure changes only in the new public repo.

## What Ships In The Public Repo

The export keeps only:

- App code under `kb_app/`
- Azure deployment files under `infra/` and `azure.yaml`
- Utility scripts under `scripts/`
- Launch and deploy helper scripts
- Public documentation such as `README.md` and this cutover note

## Content Strategy After Cutover

- Hosted deployments start with an empty knowledge base.
- Production notes live under the app content root in Azure App Service.
- Keep a separate private backup of your own knowledge content. Do not rely on App Service storage as the only copy.

## AI Strategy

- The public repo supports Azure OpenAI as the first-class deployment path.
- Deployers can either reuse an existing Azure OpenAI resource or create a new one during `azd` provisioning.
- The website settings UI still supports manual configuration for other OpenAI-compatible providers after deployment.