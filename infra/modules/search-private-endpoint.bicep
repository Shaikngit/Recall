targetScope = 'resourceGroup'

param searchPrivateDnsZoneName string
param searchPrivateDnsZoneVnetLinkName string
param searchPrivateEndpointName string
param searchPrivateEndpointConnectionName string
param virtualNetworkName string
param location string
param searchResourceId string
param subnetId string

var searchServiceName = split(searchResourceId, '/')[8]

resource virtualNetwork 'Microsoft.Network/virtualNetworks@2024-05-01' existing = {
  name: virtualNetworkName
}

resource searchPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: searchPrivateDnsZoneName
  location: 'global'
}

resource searchPrivateDnsZoneVnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: searchPrivateDnsZone
  name: searchPrivateDnsZoneVnetLinkName
  location: 'global'
  properties: {
    registrationEnabled: false
    resolutionPolicy: 'Default'
    virtualNetwork: {
      id: virtualNetwork.id
    }
  }
}

resource searchPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: searchPrivateEndpointName
  location: location
  properties: {
    privateLinkServiceConnections: [
      {
        name: searchPrivateEndpointConnectionName
        properties: {
          groupIds: [
            'searchService'
          ]
          privateLinkServiceId: searchResourceId
        }
      }
    ]
    subnet: {
      id: subnetId
    }
  }
}

resource searchPrivateDnsZoneConfig 'Microsoft.Network/privateDnsZones/A@2024-06-01' = {
  parent: searchPrivateDnsZone
  name: searchServiceName
  properties: {
    ttl: 3600
    aRecords: [
      {
        ipv4Address: searchPrivateEndpoint.properties.customDnsConfigs[0].ipAddresses[0]
      }
    ]
  }
}

output searchPrivateEndpointId string = searchPrivateEndpoint.id
output searchPrivateEndpointName string = searchPrivateEndpoint.name
output searchPrivateIp string = searchPrivateEndpoint.properties.customDnsConfigs[0].ipAddresses[0]
