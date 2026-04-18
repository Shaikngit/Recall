targetScope = 'resourceGroup'

@description('Existing Azure OpenAI account name in the target resource group.')
param openAIAccountName string

@description('Principal ID that should receive the OpenAI role assignment.')
param principalId string

@description('Stable seed used to generate the role assignment resource name.')
param principalNameSeed string

@description('Fully qualified role definition ID to assign.')
param roleDefinitionId string

resource openAIAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: openAIAccountName
}

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAIAccount.id, principalNameSeed, roleDefinitionId)
  scope: openAIAccount
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleDefinitionId
  }
}
