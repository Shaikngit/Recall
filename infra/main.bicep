targetScope = 'resourceGroup'

@description('Short environment name used to derive globally unique resource names.')
@minLength(1)
param environmentName string = 'recall'

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

@description('Optional existing App Service Plan name to reuse instead of creating a new plan.')
param existingAppServicePlanName string = ''

@description('Optional existing App Service app name to reuse instead of creating a new web app.')
param existingWebAppName string = ''

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

@description('Whether the deployment should create the Azure OpenAI RBAC assignment for the web app managed identity. Set to false when you do not have permission to write role assignments on the target Azure OpenAI resource.')
param assignOpenAIRole bool = true

@description('Linux path under /home used for persistent knowledge storage in App Service.')
param contentMountPath string = '/home/mykb-content'

@description('Enable Blob-backed content mode for the hosted app.')
param enableBlobContent bool = false

@description('Existing storage account name used for Blob-backed content. Required when enableBlobContent is true.')
param blobStorageAccountName string = ''

@description('Resource group containing the existing storage account used for Blob-backed content.')
param blobStorageResourceGroupName string = resourceGroup().name

@description('Blob container name used for hosted knowledge content.')
param blobContainerName string = 'mykb-content'

@description('Local cache root used by the Blob sync layer inside App Service.')
param blobCacheRoot string = '/tmp/mykb-content-cache'

@minValue(5)
@description('Refresh interval in seconds for Blob cache synchronization.')
param blobRefreshSeconds int = 30

@description('Optional bootstrap root uploaded to Blob on first startup when the Blob container is empty.')
param blobBootstrapRoot string = ''

@description('Enable private networking between the App Service and the Blob storage account. Requires an existing VNet and storage account.')
param enableBlobPrivateNetworking bool = false

@description('Existing virtual network name used for App Service VNet integration and the storage private endpoint. Required when enableBlobPrivateNetworking is true.')
param existingVirtualNetworkName string = ''

@description('Resource group containing the existing virtual network used for Blob private networking.')
param existingVirtualNetworkResourceGroupName string = resourceGroup().name

@description('Name of the delegated subnet used for App Service regional VNet integration.')
param appServiceIntegrationSubnetName string = 'appsvc-integration-subnet'

@description('Delegation name to preserve on the App Service integration subnet when reusing an existing VNet.')
param appServiceDelegationName string = 'appServiceDelegation'

@allowed([
  'Enabled'
  'Disabled'
])
@description('Private endpoint network policies setting to preserve on the App Service integration subnet.')
param appServiceIntegrationPrivateEndpointNetworkPolicies string = 'Enabled'

@description('CIDR prefix for the App Service integration subnet.')
param appServiceIntegrationSubnetPrefix string = '10.0.1.0/24'

@description('Name of the subnet used for the Blob private endpoint.')
param storagePrivateEndpointSubnetName string = 'storage-private-endpoint-subnet'

@description('CIDR prefix for the storage private endpoint subnet.')
param storagePrivateEndpointSubnetPrefix string = '10.0.2.0/24'

@description('Optional network security group resource ID to preserve on the storage private endpoint subnet.')
param storagePrivateEndpointSubnetNetworkSecurityGroupResourceId string = ''

@description('Optional private endpoint name. Leave blank to derive a name from the environment.')
param blobPrivateEndpointName string = ''

@description('Private DNS zone used for Azure Blob private endpoints.')
param blobPrivateDnsZoneName string = 'privatelink.blob.${environment().suffixes.storage}'

@description('Private DNS zone config name attached to the Blob private endpoint DNS zone group.')
param blobPrivateDnsZoneConfigName string = 'blob'

@description('Virtual network link name for the Blob private DNS zone.')
param blobPrivateDnsZoneVnetLinkName string = 'mykb-blob-dns-link'

@description('Resolution policy to preserve on the Blob private DNS zone virtual network link.')
param blobPrivateDnsZoneResolutionPolicy string = 'Default'

@description('Private DNS zone group name attached to the Blob private endpoint.')
param blobPrivateDnsZoneGroupName string = 'default'

@description('Private link service connection name for the Blob private endpoint.')
param blobPrivateEndpointConnectionName string = ''

@description('Enable private networking between the App Service and Azure OpenAI. Optional - defaults to false.')
param enableOpenAIPrivateNetworking bool = false

@description('Name of the subnet used for the OpenAI private endpoint.')
param openaiPrivateEndpointSubnetName string = 'openai-private-endpoint-subnet'

@description('CIDR prefix for the OpenAI private endpoint subnet.')
param openaiPrivateEndpointSubnetPrefix string = '10.0.3.0/24'

@description('Private DNS zone used for Azure OpenAI private endpoints.')
param openaiPrivateDnsZoneName string = 'privatelink.openai.azure.com'

@description('Optional private endpoint name for OpenAI. Leave blank to derive a name.')
param openaiPrivateEndpointName string = ''

@description('Private DNS zone config name attached to the OpenAI private endpoint DNS zone group.')
param openaiPrivateDnsZoneConfigName string = 'openai'

@description('Virtual network link name for the OpenAI private DNS zone.')
param openaiPrivateDnsZoneVnetLinkName string = 'mykb-openai-dns-link'

@description('Private link service connection name for the OpenAI private endpoint.')
param openaiPrivateEndpointConnectionName string = ''

@description('Enable Azure AI Search private networking.')
param enableSearchPrivateNetworking bool = true

@description('CIDR prefix for the Azure AI Search private endpoint subnet.')
param searchPrivateEndpointSubnetPrefix string = '10.0.4.0/24'

@description('Private DNS zone used for Azure AI Search private endpoints.')
param searchPrivateDnsZoneName string = 'privatelink.search.windows.net'

@description('Optional private endpoint name for Azure AI Search. Leave blank to derive a name.')
param searchPrivateEndpointName string = ''

@description('Private DNS zone config name attached to the Azure AI Search private endpoint DNS zone group.')
param searchPrivateDnsZoneConfigName string = 'search'

@description('Virtual network link name for the Azure AI Search private DNS zone.')
param searchPrivateDnsZoneVnetLinkName string = 'mykb-search-dns-link'

@description('Private link service connection name for the Azure AI Search private endpoint.')
param searchPrivateEndpointConnectionName string = ''

@description('Resource ID of the Azure AI Search service.')
param searchResourceId string = ''

@description('API key for Azure AI Search.')
param searchApiKey string = ''

var normalizedEnvironmentName = toLower(replace(environmentName, '-', ''))
var uniqueSuffix = take(uniqueString(subscription().subscriptionId, resourceGroup().id, environmentName), 6)
var createNewOpenAI = openAIMode == 'new'
var useBlobContent = enableBlobContent
var useBlobPrivateNetworking = enableBlobPrivateNetworking
var useOpenAIPrivateNetworking = enableOpenAIPrivateNetworking
var useSearchPrivateNetworking = enableSearchPrivateNetworking && !empty(searchResourceId)
var useExistingAppServicePlan = !empty(existingAppServicePlanName)
var useExistingWebApp = !empty(existingWebAppName)

var appServicePlanName = useExistingAppServicePlan ? existingAppServicePlanName : take('asp-${normalizedEnvironmentName}-${uniqueSuffix}', 40)
var webAppName = useExistingWebApp ? existingWebAppName : take('app-${normalizedEnvironmentName}-${uniqueSuffix}', 60)
var derivedOpenAIAccountName = take('oai${normalizedEnvironmentName}${uniqueSuffix}', 64)
var derivedBlobPrivateEndpointName = take('pe-${normalizedEnvironmentName}-blob', 80)
var derivedOpenAIPrivateEndpointName = take('pe-${normalizedEnvironmentName}-openai', 80)
var derivedSearchPrivateEndpointName = take('pe-${normalizedEnvironmentName}-search', 80)
var effectiveBlobPrivateEndpointName = empty(blobPrivateEndpointName) ? derivedBlobPrivateEndpointName : blobPrivateEndpointName
var effectiveBlobPrivateEndpointConnectionName = empty(blobPrivateEndpointConnectionName) ? '${effectiveBlobPrivateEndpointName}-blob' : blobPrivateEndpointConnectionName
var effectiveOpenAIPrivateEndpointName = empty(openaiPrivateEndpointName) ? derivedOpenAIPrivateEndpointName : openaiPrivateEndpointName
var effectiveOpenAIPrivateEndpointConnectionName = empty(openaiPrivateEndpointConnectionName) ? '${effectiveOpenAIPrivateEndpointName}-openai' : openaiPrivateEndpointConnectionName
var effectiveSearchPrivateEndpointName = empty(searchPrivateEndpointName) ? derivedSearchPrivateEndpointName : searchPrivateEndpointName
var effectiveSearchPrivateEndpointConnectionName = empty(searchPrivateEndpointConnectionName) ? '${effectiveSearchPrivateEndpointName}-search' : searchPrivateEndpointConnectionName
var blobAccountUrl = 'https://${blobStorageAccountName}.blob.${environment().suffixes.storage}'
var effectiveOpenAIAccountName = createNewOpenAI
  ? (empty(openAINewAccountName) ? derivedOpenAIAccountName : openAINewAccountName)
  : (empty(openAIResourceId) ? 'oairecalltxudrn' : split(openAIResourceId, '/')[8])
var effectiveOpenAIResourceGroupName = createNewOpenAI ? resourceGroup().name : split(openAIResourceId, '/')[4]
var openAIRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
)
var webAppResourceId = resourceId('Microsoft.Web/sites', webAppName)
var webAppReference = reference(webAppResourceId, '2025-03-01', 'full')
var webAppPrincipalId = useExistingWebApp ? webAppReference.identity.principalId : webApp!.identity.principalId!
var webAppDefaultHostName = useExistingWebApp ? webAppReference.properties.defaultHostName : webApp!.properties.defaultHostName
var commonAppSettings = {
  ENABLE_ORYX_BUILD: 'true'
  PYTHONUNBUFFERED: '1'
  SCM_DO_BUILD_DURING_DEPLOYMENT: 'true'
}
var filesystemContentAppSettings = useBlobContent ? {} : {
  MYKB_CONTENT_ROOT: contentMountPath
}
var blobContentAppSettings = useBlobContent ? {
  MYKB_BLOB_ACCOUNT_URL: blobAccountUrl
  MYKB_BLOB_CACHE_ROOT: blobCacheRoot
  MYKB_BLOB_CONTAINER: blobContainerName
  MYKB_BLOB_REFRESH_SECONDS: string(blobRefreshSeconds)
} : {}
var blobBootstrapAppSettings = useBlobContent && !empty(blobBootstrapRoot) ? {
  MYKB_BLOB_BOOTSTRAP_ROOT: blobBootstrapRoot
} : {}
var blobNetworkingAppSettings = useBlobPrivateNetworking || useOpenAIPrivateNetworking || useSearchPrivateNetworking ? {
  WEBSITE_DNS_SERVER: '168.63.129.16'
  WEBSITE_VNET_ROUTE_ALL: '1'
} : {}
var searchEndpoint = !empty(searchResourceId) ? 'https://${split(searchResourceId, '/')[8]}.search.windows.net' : ''
var searchAppSettings = !empty(searchResourceId) ? union(
  {
    AZURE_SEARCH_ENDPOINT: searchEndpoint
    AZURE_SEARCH_INDEX_NAME: 'mykb-notes'
  },
  !empty(searchApiKey) ? { AZURE_SEARCH_API_KEY: searchApiKey } : {}
) : {}
var existingOpenAIAppSettings = union(commonAppSettings, filesystemContentAppSettings, blobContentAppSettings, blobBootstrapAppSettings, blobNetworkingAppSettings, searchAppSettings, {
  AZURE_OPENAI_DEPLOYMENT: openAIDeploymentName
  AZURE_OPENAI_ENDPOINT: reference(openAIResourceId, '2025-06-01').endpoint
})
var newOpenAIAppSettings = union(commonAppSettings, filesystemContentAppSettings, blobContentAppSettings, blobBootstrapAppSettings, blobNetworkingAppSettings, searchAppSettings, {
  AZURE_OPENAI_DEPLOYMENT: openAIDeploymentName
  #disable-next-line use-resource-symbol-reference
  AZURE_OPENAI_ENDPOINT: reference(newOpenAI.id, '2025-06-01').endpoint
})

resource blobStorageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = if (useBlobContent || useBlobPrivateNetworking) {
  scope: resourceGroup(blobStorageResourceGroupName)
  name: blobStorageAccountName
}

resource existingAppServicePlan 'Microsoft.Web/serverfarms@2025-03-01' existing = if (useExistingAppServicePlan) {
  name: appServicePlanName
}

resource existingWebApp 'Microsoft.Web/sites@2025-03-01' existing = if (useExistingWebApp) {
  name: webAppName
}

resource existingVirtualNetwork 'Microsoft.Network/virtualNetworks@2024-05-01' existing = if (useBlobPrivateNetworking || useOpenAIPrivateNetworking) {
  scope: resourceGroup(existingVirtualNetworkResourceGroupName)
  name: existingVirtualNetworkName
}

module blobNetworkSubnets 'modules/blob-network-subnets.bicep' = if (useBlobPrivateNetworking) {
  name: 'blob-network-subnets'
  scope: resourceGroup(existingVirtualNetworkResourceGroupName)
  params: {
    appServiceDelegationName: appServiceDelegationName
    appServiceIntegrationSubnetName: appServiceIntegrationSubnetName
    appServiceIntegrationPrivateEndpointNetworkPolicies: appServiceIntegrationPrivateEndpointNetworkPolicies
    appServiceIntegrationSubnetPrefix: appServiceIntegrationSubnetPrefix
    storagePrivateEndpointSubnetNetworkSecurityGroupResourceId: storagePrivateEndpointSubnetNetworkSecurityGroupResourceId
    storagePrivateEndpointSubnetName: storagePrivateEndpointSubnetName
    storagePrivateEndpointSubnetPrefix: storagePrivateEndpointSubnetPrefix
    virtualNetworkName: existingVirtualNetworkName
  }
}

module openaiNetworkSubnet 'modules/openai-network-subnet.bicep' = if (useOpenAIPrivateNetworking) {
  name: 'openai-network-subnet'
  scope: resourceGroup(existingVirtualNetworkResourceGroupName)
  params: {
    virtualNetworkName: existingVirtualNetworkName
    subnetName: openaiPrivateEndpointSubnetName
    subnetPrefix: openaiPrivateEndpointSubnetPrefix
  }
}

module searchNetworkSubnet 'modules/search-network-subnet.bicep' = if (useSearchPrivateNetworking) {
  name: 'search-network-subnet'
  scope: resourceGroup(existingVirtualNetworkResourceGroupName)
  params: {
    virtualNetworkName: existingVirtualNetworkName
    subnetName: 'search-private-endpoint-subnet'
    subnetPrefix: searchPrivateEndpointSubnetPrefix
  }
}

resource appServicePlan 'Microsoft.Web/serverfarms@2025-03-01' = if (!useExistingAppServicePlan) {
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
    publicNetworkAccess: useOpenAIPrivateNetworking ? 'Disabled' : 'Enabled'
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

resource webApp 'Microsoft.Web/sites@2025-03-01' = if (!useExistingWebApp) {
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
    serverFarmId: useExistingAppServicePlan ? existingAppServicePlan.id : appServicePlan.id
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

resource webAppAppSettingsExistingExistingWebApp 'Microsoft.Web/sites/config@2024-04-01' = if (!createNewOpenAI && useExistingWebApp) {
  parent: existingWebApp
  name: 'appsettings'
  properties: existingOpenAIAppSettings
}

resource webAppAppSettingsExistingNewWebApp 'Microsoft.Web/sites/config@2024-04-01' = if (!createNewOpenAI && !useExistingWebApp) {
  parent: webApp
  name: 'appsettings'
  properties: existingOpenAIAppSettings
}

resource webAppAppSettingsNewExistingWebApp 'Microsoft.Web/sites/config@2024-04-01' = if (createNewOpenAI && useExistingWebApp) {
  parent: existingWebApp
  name: 'appsettings'
  properties: newOpenAIAppSettings
}

resource webAppAppSettingsNewNewWebApp 'Microsoft.Web/sites/config@2024-04-01' = if (createNewOpenAI && !useExistingWebApp) {
  parent: webApp
  name: 'appsettings'
  properties: newOpenAIAppSettings
}

resource webAppVnetIntegrationExistingWebApp 'Microsoft.Web/sites/networkConfig@2024-04-01' = if (useBlobPrivateNetworking && useExistingWebApp) {
  parent: existingWebApp
  name: 'virtualNetwork'
  properties: {
    subnetResourceId: blobNetworkSubnets!.outputs.appServiceIntegrationSubnetId
    swiftSupported: true
  }
}

resource webAppVnetIntegrationNewWebApp 'Microsoft.Web/sites/networkConfig@2024-04-01' = if (useBlobPrivateNetworking && !useExistingWebApp) {
  parent: webApp
  name: 'virtualNetwork'
  properties: {
    subnetResourceId: blobNetworkSubnets!.outputs.appServiceIntegrationSubnetId
    swiftSupported: true
  }
}

resource blobPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = if (useBlobPrivateNetworking) {
  name: blobPrivateDnsZoneName
  location: 'global'
}

resource blobPrivateDnsZoneVnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = if (useBlobPrivateNetworking) {
  parent: blobPrivateDnsZone
  name: blobPrivateDnsZoneVnetLinkName
  location: 'global'
  properties: {
    registrationEnabled: false
    resolutionPolicy: blobPrivateDnsZoneResolutionPolicy
    virtualNetwork: {
      id: existingVirtualNetwork!.id
    }
  }
}

resource blobPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = if (useBlobPrivateNetworking) {
  name: effectiveBlobPrivateEndpointName
  location: location
  properties: {
    privateLinkServiceConnections: [
      {
        name: effectiveBlobPrivateEndpointConnectionName
        properties: {
          groupIds: [
            'blob'
          ]
          privateLinkServiceId: blobStorageAccount.id
        }
      }
    ]
    subnet: {
      id: blobNetworkSubnets!.outputs.storagePrivateEndpointSubnetId
    }
  }
}

resource blobPrivateEndpointDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (useBlobPrivateNetworking) {
  parent: blobPrivateEndpoint
  name: blobPrivateDnsZoneGroupName
  properties: {
    privateDnsZoneConfigs: [
      {
        name: blobPrivateDnsZoneConfigName
        properties: {
          privateDnsZoneId: blobPrivateDnsZone.id
        }
      }
    ]
  }
}

module openaiPrivateEndpointModule 'modules/openai-private-endpoint.bicep' = if (useOpenAIPrivateNetworking) {
  name: 'openai-private-endpoint'
  scope: resourceGroup(existingVirtualNetworkResourceGroupName)
  params: {
    openaiPrivateDnsZoneName: openaiPrivateDnsZoneName
    openaiPrivateDnsZoneVnetLinkName: openaiPrivateDnsZoneVnetLinkName
    openaiPrivateDnsZoneConfigName: openaiPrivateDnsZoneConfigName
    openaiPrivateEndpointName: effectiveOpenAIPrivateEndpointName
    openaiPrivateEndpointConnectionName: effectiveOpenAIPrivateEndpointConnectionName
    virtualNetworkName: existingVirtualNetworkName
    location: existingVirtualNetwork!.location
    openaiResourceId: createNewOpenAI ? newOpenAI.id : openAIResourceId
    subnetId: openaiNetworkSubnet!.outputs.subnetId
  }
}

module searchPrivateEndpointModule 'modules/search-private-endpoint.bicep' = if (useSearchPrivateNetworking) {
  name: 'search-private-endpoint'
  scope: resourceGroup(existingVirtualNetworkResourceGroupName)
  params: {
    searchPrivateDnsZoneName: searchPrivateDnsZoneName
    searchPrivateDnsZoneVnetLinkName: searchPrivateDnsZoneVnetLinkName
    searchPrivateEndpointName: effectiveSearchPrivateEndpointName
    searchPrivateEndpointConnectionName: effectiveSearchPrivateEndpointConnectionName
    virtualNetworkName: existingVirtualNetworkName
    location: existingVirtualNetwork!.location
    searchResourceId: searchResourceId
    subnetId: searchNetworkSubnet!.outputs.subnetId
  }
}

resource ftpPublishingPolicyExistingWebApp 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2025-03-01' = if (useExistingWebApp) {
  parent: existingWebApp
  name: 'ftp'
  properties: {
    allow: false
  }
}

resource ftpPublishingPolicyNewWebApp 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2025-03-01' = if (!useExistingWebApp) {
  parent: webApp
  name: 'ftp'
  properties: {
    allow: false
  }
}

resource scmPublishingPolicyExistingWebApp 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2025-03-01' = if (useExistingWebApp) {
  parent: existingWebApp
  name: 'scm'
  properties: {
    allow: false
  }
}

resource scmPublishingPolicyNewWebApp 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2025-03-01' = if (!useExistingWebApp) {
  parent: webApp
  name: 'scm'
  properties: {
    allow: false
  }
}

module openAIRoleAssignment 'modules/openai-role-assignment.bicep' = if (assignOpenAIRole) {
  name: 'openai-role-assignment'
  scope: resourceGroup(effectiveOpenAIResourceGroupName)
  params: {
    openAIAccountName: effectiveOpenAIAccountName
    principalId: webAppPrincipalId
    principalNameSeed: webAppName
    roleDefinitionId: openAIRoleDefinitionId
  }
}

output appServicePlanName string = appServicePlanName
output blobPrivateEndpointName string = useBlobPrivateNetworking ? blobPrivateEndpoint.name : ''
output blobPrivateDnsZoneName string = useBlobPrivateNetworking ? blobPrivateDnsZone.name : ''
  output openaiPrivateEndpointName string = useOpenAIPrivateNetworking ? openaiPrivateEndpointModule!.outputs.privateEndpointName : ''
  output openaiPrivateDnsZoneName string = useOpenAIPrivateNetworking ? openaiPrivateEndpointModule!.outputs.privateDnsZoneName : ''
output openAIAccountName string = effectiveOpenAIAccountName
output openAIMode string = openAIMode
output openAIRoleAssignmentEnabled bool = assignOpenAIRole
output webAppPrincipalId string = webAppPrincipalId
output webAppName string = webAppName
output webAppUrl string = 'https://${webAppDefaultHostName}'
