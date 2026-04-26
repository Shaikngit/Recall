targetScope = 'resourceGroup'

@description('Resource group containing the existing virtual network.')
param existingVirtualNetworkResourceGroupName string

@description('Existing virtual network name used for the Search private endpoint subnet.')
param existingVirtualNetworkName string

@description('Resource ID of the Azure AI Search service.')
param searchResourceId string

@description('CIDR prefix for the Search private endpoint subnet.')
param searchPrivateEndpointSubnetPrefix string = '10.0.4.0/24'

@description('Subnet name used for the Search private endpoint.')
param searchPrivateEndpointSubnetName string = 'search-private-endpoint-subnet'

@description('Private DNS zone used for Azure AI Search private endpoints.')
param searchPrivateDnsZoneName string = 'privatelink.search.windows.net'

@description('Private DNS zone VNet link name for Search private endpoint resolution.')
param searchPrivateDnsZoneVnetLinkName string = 'mykb-search-dns-link'

@description('Optional private endpoint name. Leave blank to derive a deterministic name.')
param searchPrivateEndpointName string = ''

@description('Optional private link service connection name for the Search private endpoint.')
param searchPrivateEndpointConnectionName string = ''

var normalizedEnvironmentName = toLower(replace(resourceGroup().name, '_', '-'))
var derivedSearchPrivateEndpointName = take('pe-${normalizedEnvironmentName}-search', 80)
var effectiveSearchPrivateEndpointName = empty(searchPrivateEndpointName)
  ? derivedSearchPrivateEndpointName
  : searchPrivateEndpointName
var effectiveSearchPrivateEndpointConnectionName = empty(searchPrivateEndpointConnectionName)
  ? '${effectiveSearchPrivateEndpointName}-search'
  : searchPrivateEndpointConnectionName

resource existingVirtualNetwork 'Microsoft.Network/virtualNetworks@2024-05-01' existing = {
  scope: resourceGroup(existingVirtualNetworkResourceGroupName)
  name: existingVirtualNetworkName
}

module searchNetworkSubnet 'modules/search-network-subnet.bicep' = {
  name: 'search-network-subnet-only'
  scope: resourceGroup(existingVirtualNetworkResourceGroupName)
  params: {
    virtualNetworkName: existingVirtualNetworkName
    subnetName: searchPrivateEndpointSubnetName
    subnetPrefix: searchPrivateEndpointSubnetPrefix
  }
}

module searchPrivateEndpointModule 'modules/search-private-endpoint.bicep' = {
  name: 'search-private-endpoint-only'
  scope: resourceGroup(existingVirtualNetworkResourceGroupName)
  params: {
    searchPrivateDnsZoneName: searchPrivateDnsZoneName
    searchPrivateDnsZoneVnetLinkName: searchPrivateDnsZoneVnetLinkName
    searchPrivateEndpointName: effectiveSearchPrivateEndpointName
    searchPrivateEndpointConnectionName: effectiveSearchPrivateEndpointConnectionName
    virtualNetworkName: existingVirtualNetworkName
    location: existingVirtualNetwork.location
    searchResourceId: searchResourceId
    subnetId: searchNetworkSubnet.outputs.subnetId
  }
}

output searchPrivateEndpointId string = searchPrivateEndpointModule.outputs.searchPrivateEndpointId
output searchPrivateEndpointName string = searchPrivateEndpointModule.outputs.searchPrivateEndpointName
output searchPrivateIp string = searchPrivateEndpointModule.outputs.searchPrivateIp
