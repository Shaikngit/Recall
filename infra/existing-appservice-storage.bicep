targetScope = 'resourceGroup'

@description('Existing Azure App Service name to receive the Azure Files mount.')
param appName string

@description('Region for the storage account. Use the same region as the App Service when possible.')
param location string = resourceGroup().location

@description('Globally unique storage account name for KB content.')
@minLength(3)
@maxLength(24)
param storageAccountName string

@description('Azure Files share name used for KB content.')
param shareName string = 'mykb-content'

@description('Custom mount identifier inside the App Service configuration.')
param mountName string = 'kbcontent'

@description('Linux mount path used by the App Service. Do not use / or /home.')
param mountPath string = '/mounts/mykb-content'

@minValue(1)
@maxValue(102400)
@description('Provisioned Azure Files share quota in GiB.')
param shareQuotaGiB int = 100

@allowed([
  'Standard_LRS'
  'Standard_ZRS'
])
@description('Storage account redundancy for KB content.')
param storageSkuName string = 'Standard_ZRS'

resource webApp 'Microsoft.Web/sites@2025-03-01' existing = {
  name: appName
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2025-06-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: storageSkuName
  }
  properties: {
    allowBlobPublicAccess: false
    allowCrossTenantReplication: false
    allowSharedKeyAccess: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
    largeFileSharesState: 'Enabled'
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2025-06-01' = {
  parent: storageAccount
  name: 'default'
}

resource fileShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2025-06-01' = {
  parent: fileService
  name: shareName
  properties: {
    accessTier: 'TransactionOptimized'
    enabledProtocols: 'SMB'
    shareQuota: shareQuotaGiB
  }
}

resource storageMountConfig 'Microsoft.Web/sites/config@2022-09-01' = {
  parent: webApp
  name: 'azurestorageaccounts'
  properties: {
    '${mountName}': {
      type: 'AzureFiles'
      accountName: storageAccount.name
      shareName: fileShare.name
      accessKey: storageAccount.listKeys().keys[0].value
      mountPath: mountPath
    }
  }
}

output fileShareName string = fileShare.name
output mountPath string = mountPath
output storageAccountResourceId string = storageAccount.id
