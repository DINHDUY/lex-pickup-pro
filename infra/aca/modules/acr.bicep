@description('Azure Container Registry name.')
param name string

@description('Azure region for the registry.')
param location string = resourceGroup().location

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

output loginServer string = registry.properties.loginServer
output username string = listCredentials(registry.id, registry.apiVersion).username
output password string = listCredentials(registry.id, registry.apiVersion).passwords[0].value
