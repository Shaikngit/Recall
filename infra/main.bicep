targetScope = 'resourceGroup'

@description('Short environment name used to derive globally unique resource names.')
@minLength(1)
param environmentName string = 'mykb'

@description('Azure region for the deployment.')
param location string = resourceGroup().location

@allowed([
  'B1'
  'S1'
  'P0v3'
])
@description('App Service Plan SKU for the hosted Flask application.')
param appServiceSkuName string = 'B1'

@minValue(1)
@description('Instance count for the App Service Plan.')
param appServiceWorkerCount int = 1

@allowed([
  'existing'
  'new'
])
@description('Whether to reuse an existing Azure OpenAI resource or create a new one for this deployment.')
param openAIMode string = 'existing'

@description('Existing Azure OpenAI resource ID to reuse when openAIMode is existing.')
param openAIResourceId string = ''

@description('Azure OpenAI deployment name exposed to the application.')
param openAIDeploymentName string

@description('Azure OpenAI model name to deploy when openAIMode is new.')
param openAIModelName string = 'gpt-4.1-mini'

@minValue(1)
@description('Azure OpenAI deployment capacity when openAIMode is new.')
param openAIDeploymentCapacity int = 1

@description('Optional Azure OpenAI account name when openAIMode is new. Leave blank to derive a unique name.')
param openAINewAccountName string = ''

@description('Linux path under /home used for persistent knowledge storage in App Service.')
param contentMountPath string = '/home/mykb-content'

var normalizedEnvironmentName = toLower(replace(environmentName, '-', ''))
var uniqueSuffix = take(uniqueString(subscription().subscriptionId, resourceGroup().id, environmentName), 6)
var createNewOpenAI = openAIMode == 'new'

var appServicePlanName = take('asp-${normalizedEnvironmentName}-${uniqueSuffix}', 40)
var webAppName = take('app-${normalizedEnvironmentName}-${uniqueSuffix}', 60)
var derivedOpenAIAccountName = take('oai${normalizedEnvironmentName}${uniqueSuffix}', 64)
var effectiveOpenAIAccountName = createNewOpenAI
  ? (empty(openAINewAccountName) ? derivedOpenAIAccountName : openAINewAccountName)
  : split(openAIResourceId, '/')[8]
var effectiveOpenAIResourceGroupName = createNewOpenAI ? resourceGroup().name : split(openAIResourceId, '/')[4]
var openAIRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
)

resource appServicePlan 'Microsoft.Web/serverfarms@2025-03-01' = {
  name: appServicePlanName
  location: location
  kind: 'linux'
  sku: {
    name: appServiceSkuName
    capacity: appServiceWorkerCount
  }
  properties: {
    reserved: true
  }
}

resource newOpenAI 'Microsoft.CognitiveServices/accounts@2025-06-01' = if (createNewOpenAI) {
  name: effectiveOpenAIAccountName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: effectiveOpenAIAccountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource newOpenAIDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = if (createNewOpenAI) {
  parent: newOpenAI
  name: openAIDeploymentName
  sku: {
    name: 'Standard'
    capacity: openAIDeploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: openAIModelName
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

resource webApp 'Microsoft.Web/sites@2025-03-01' = {
  name: webAppName
  location: location
  kind: 'app,linux'
  identity: {
    type: 'SystemAssigned'
  }
  tags: {
    'azd-service-name': 'web'
  }
  properties: {
    serverFarmId: appServicePlan.id
    clientAffinityEnabled: false
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    siteConfig: {
      alwaysOn: true
      appCommandLine: 'gunicorn --bind=0.0.0.0 --timeout 600 kb_app.app:app'
      ftpsState: 'Disabled'
      healthCheckPath: '/healthz'
      http20Enabled: true
      linuxFxVersion: 'PYTHON|3.11'
      minTlsVersion: '1.2'
    }
  }
}

resource webAppAppSettingsExisting 'Microsoft.Web/sites/config@2024-04-01' = if (!createNewOpenAI) {
  parent: webApp
  name: 'appsettings'
  properties: {
    AZURE_OPENAI_DEPLOYMENT: openAIDeploymentName
    AZURE_OPENAI_ENDPOINT: reference(openAIResourceId, '2025-06-01').endpoint
    ENABLE_ORYX_BUILD: 'true'
    MYKB_CONTENT_ROOT: contentMountPath
    PYTHONUNBUFFERED: '1'
    SCM_DO_BUILD_DURING_DEPLOYMENT: 'true'
  }
}

resource webAppAppSettingsNew 'Microsoft.Web/sites/config@2024-04-01' = if (createNewOpenAI) {
  parent: webApp
  name: 'appsettings'
  properties: {
    AZURE_OPENAI_DEPLOYMENT: openAIDeploymentName
    #disable-next-line use-resource-symbol-reference
    AZURE_OPENAI_ENDPOINT: reference(newOpenAI.id, '2025-06-01').endpoint
    ENABLE_ORYX_BUILD: 'true'
    MYKB_CONTENT_ROOT: contentMountPath
    PYTHONUNBUFFERED: '1'
    SCM_DO_BUILD_DURING_DEPLOYMENT: 'true'
  }
}

resource ftpPublishingPolicy 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2025-03-01' = {
  parent: webApp
  name: 'ftp'
  properties: {
    allow: false
  }
}

resource scmPublishingPolicy 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2025-03-01' = {
  parent: webApp
  name: 'scm'
  properties: {
    allow: false
  }
}

module openAIRoleAssignment 'modules/openai-role-assignment.bicep' = {
  name: 'openai-role-assignment'
  scope: resourceGroup(effectiveOpenAIResourceGroupName)
  params: {
    openAIAccountName: effectiveOpenAIAccountName
    principalId: webApp.identity.principalId!
    principalNameSeed: webApp.name
    roleDefinitionId: openAIRoleDefinitionId
  }
}

output appServicePlanName string = appServicePlan.name
output openAIAccountName string = effectiveOpenAIAccountName
output openAIMode string = openAIMode
output webAppName string = webApp.name
output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
