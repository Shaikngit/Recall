targetScope = 'resourceGroup'

@description('Name of the existing virtual network that will host the App Service integration subnet and storage private endpoint subnet.')
param virtualNetworkName string

@description('Name of the delegated subnet used for App Service regional VNet integration.')
param appServiceIntegrationSubnetName string

@description('CIDR prefix for the App Service integration subnet.')
param appServiceIntegrationSubnetPrefix string

@description('Name of the delegation on the App Service integration subnet.')
param appServiceDelegationName string = 'appServiceDelegation'

@allowed([
  'Enabled'
  'Disabled'
])
@description('Private endpoint network policies setting for the App Service integration subnet.')
param appServiceIntegrationPrivateEndpointNetworkPolicies string = 'Enabled'

@description('Name of the subnet used for the Blob private endpoint.')
param storagePrivateEndpointSubnetName string

@description('CIDR prefix for the storage private endpoint subnet.')
param storagePrivateEndpointSubnetPrefix string

@description('Optional network security group resource ID to preserve on the storage private endpoint subnet.')
param storagePrivateEndpointSubnetNetworkSecurityGroupResourceId string = ''

var storagePrivateEndpointSubnetProperties = union({
  addressPrefix: storagePrivateEndpointSubnetPrefix
  privateEndpointNetworkPolicies: 'Disabled'
  privateLinkServiceNetworkPolicies: 'Enabled'
}, empty(storagePrivateEndpointSubnetNetworkSecurityGroupResourceId) ? {} : {
  networkSecurityGroup: {
    id: storagePrivateEndpointSubnetNetworkSecurityGroupResourceId
  }
})

resource existingVirtualNetwork 'Microsoft.Network/virtualNetworks@2024-05-01' existing = {
  name: virtualNetworkName
}

resource appServiceIntegrationSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: existingVirtualNetwork
  name: appServiceIntegrationSubnetName
  properties: {
    addressPrefix: appServiceIntegrationSubnetPrefix
    delegations: [
      {
        name: appServiceDelegationName
        properties: {
          serviceName: 'Microsoft.Web/serverFarms'
        }
      }
    ]
    privateEndpointNetworkPolicies: appServiceIntegrationPrivateEndpointNetworkPolicies
    privateLinkServiceNetworkPolicies: 'Enabled'
  }
}

resource storagePrivateEndpointSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: existingVirtualNetwork
  name: storagePrivateEndpointSubnetName
  properties: storagePrivateEndpointSubnetProperties
}

output appServiceIntegrationSubnetId string = appServiceIntegrationSubnet.id
output storagePrivateEndpointSubnetId string = storagePrivateEndpointSubnet.id
output virtualNetworkId string = existingVirtualNetwork.id
