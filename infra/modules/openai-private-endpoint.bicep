targetScope = 'resourceGroup'

param openaiPrivateDnsZoneName string
param openaiPrivateDnsZoneVnetLinkName string
param openaiPrivateDnsZoneConfigName string
param openaiPrivateEndpointName string
param openaiPrivateEndpointConnectionName string
param virtualNetworkName string
param location string
param openaiResourceId string
param subnetId string

resource virtualNetwork 'Microsoft.Network/virtualNetworks@2024-05-01' existing = {
  name: virtualNetworkName
}

resource openaiPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: openaiPrivateDnsZoneName
  location: 'global'
}

resource openaiPrivateDnsZoneVnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: openaiPrivateDnsZone
  name: openaiPrivateDnsZoneVnetLinkName
  location: 'global'
  properties: {
    registrationEnabled: false
    resolutionPolicy: 'Default'
    virtualNetwork: {
      id: virtualNetwork.id
    }
  }
}

resource openaiPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: openaiPrivateEndpointName
  location: location
  properties: {
    privateLinkServiceConnections: [
      {
        name: openaiPrivateEndpointConnectionName
        properties: {
          groupIds: [
            'account'
          ]
          privateLinkServiceId: openaiResourceId
        }
      }
    ]
    subnet: {
      id: subnetId
    }
  }
}

resource openaiPrivateEndpointDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: openaiPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: openaiPrivateDnsZoneConfigName
        properties: {
          privateDnsZoneId: openaiPrivateDnsZone.id
        }
      }
    ]
  }
}

output privateEndpointId string = openaiPrivateEndpoint.id
output privateEndpointName string = openaiPrivateEndpoint.name
output privateDnsZoneId string = openaiPrivateDnsZone.id
output privateDnsZoneName string = openaiPrivateDnsZone.name
