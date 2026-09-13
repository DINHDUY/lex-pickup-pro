targetScope = 'resourceGroup'

@description('Azure region for the deployment.')
param location string = resourceGroup().location

@description('Base name used for the Azure resources.')
param appName string = 'lex-pickup-pro'

@description('Globally unique Azure Container Registry name. Lowercase letters and numbers only.')
param acrName string = 'lexpickuppro${uniqueString(resourceGroup().id)}'

@description('Globally unique Cosmos DB account name. Lowercase letters and numbers only.')
param cosmosAccountName string = 'lexpickup${uniqueString(resourceGroup().id)}'

@description('Cosmos database name.')
param cosmosDatabaseName string = 'lex_pickup'

@description('Cosmos container name.')
param cosmosContainerName string = 'club_data'

@description('Cosmos partition key path for club-scoped docs.')
param cosmosPartitionKey string = '/club_id'

@description('Frontend hostname, without scheme. Example: lex-pickup.example.com')
param frontendHost string = 'lex-pickup.example.com'

@description('Explicit backend image reference. If empty, a registry-backed image is used.')
param backendImage string = ''

@description('Explicit frontend image reference. If empty, a registry-backed image is used.')
param frontendImage string = ''

@description('Backend image tag to deploy when not using an explicit image reference.')
param backendImageTag string = 'latest'

@description('Frontend image tag to deploy when not using an explicit image reference.')
param frontendImageTag string = 'latest'

@description('Production runtime environment value.')
param appEnvironment string = 'production'

@description('Minimum backend replicas in ACA.')
param backendMinReplicas int = 1

@description('Maximum backend replicas in ACA.')
param backendMaxReplicas int = 1

@description('Minimum frontend replicas in ACA.')
param frontendMinReplicas int = 1

@description('Maximum frontend replicas in ACA.')
param frontendMaxReplicas int = 1

@description('JWT secret used by the backend.')
@secure()
param jwtSecret string

@description('Invitation code used to onboard club members.')
param clubInviteCode string = 'LEX2026'

@description('Single cluster ID used within Cosmos data documents.')
param cosmosClubId string = 'lex-pickup'

var frontendOrigin = 'https://${frontendHost}'
var backendImageResolved = empty(backendImage) ? '${acr.outputs.loginServer}/backend:${backendImageTag}' : backendImage
var frontendImageResolved = empty(frontendImage) ? '${acr.outputs.loginServer}/frontend:${frontendImageTag}' : frontendImage

module logAnalytics 'modules/log-analytics.bicep' = {
  name: 'log-analytics'
  params: {
    name: '${appName}-logs'
    location: location
  }
}

module acr 'modules/acr.bicep' = {
  name: 'acr'
  params: {
    name: acrName
    location: location
  }
}

module cosmos 'modules/cosmos.bicep' = {
  name: 'cosmos'
  params: {
    accountName: cosmosAccountName
    databaseName: cosmosDatabaseName
    containerName: cosmosContainerName
    partitionKey: cosmosPartitionKey
    location: location
  }
}

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${appName}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.outputs.workspaceCustomerId
        sharedKey: logAnalytics.outputs.workspaceKey
      }
    }
  }
}

module backend 'modules/container-app.bicep' = {
  name: 'backend-app'
  params: {
    name: '${appName}-backend'
    location: location
    environmentId: managedEnvironment.id
    registryServer: empty(backendImage) ? acr.outputs.loginServer : ''
    registryUsername: empty(backendImage) ? acr.outputs.username : ''
    registryPassword: empty(backendImage) ? acr.outputs.password : ''
    image: backendImageResolved
    ingressExternal: true
    targetPort: 8000
    cpu: '0.5'
    memory: '1Gi'
    minReplicas: backendMinReplicas
    maxReplicas: backendMaxReplicas
    environmentVariables: [
      {
        name: 'APP_ENV'
        value: appEnvironment
      }
      {
        name: 'DATABASE_PROVIDER'
        value: 'cosmos'
      }
      {
        name: 'COSMOS_ENDPOINT'
        value: cosmos.outputs.endpoint
      }
      {
        name: 'COSMOS_DATABASE'
        value: cosmos.outputs.database
      }
      {
        name: 'COSMOS_CONTAINER'
        value: cosmos.outputs.container
      }
      {
        name: 'COSMOS_CLUB_ID'
        value: cosmosClubId
      }
      {
        name: 'COSMOS_KEY'
        value: cosmos.outputs.key
      }
      {
        name: 'COSMOS_AUTH_MODE'
        value: 'default_credential'
      }
      {
        name: 'JWT_SECRET'
        value: jwtSecret
      }
      {
        name: 'COOKIE_SECURE'
        value: 'true'
      }
      {
        name: 'FRONTEND_URL'
        value: frontendOrigin
      }
      {
        name: 'CORS_ORIGINS'
        value: '["${frontendOrigin}"]'
      }
      {
        name: 'CLUB_INVITE_CODE'
        value: clubInviteCode
      }
      {
        name: 'REGISTRATION_ENABLED'
        value: 'true'
      }
      {
        name: 'DEMO_ENABLED'
        value: 'false'
      }
    ]
  }
}

module frontend 'modules/container-app.bicep' = {
  name: 'frontend-app'
  params: {
    name: '${appName}-frontend'
    location: location
    environmentId: managedEnvironment.id
    registryServer: empty(frontendImage) ? acr.outputs.loginServer : ''
    registryUsername: empty(frontendImage) ? acr.outputs.username : ''
    registryPassword: empty(frontendImage) ? acr.outputs.password : ''
    image: frontendImageResolved
    ingressExternal: true
    targetPort: 8080
    cpu: '0.25'
    memory: '0.5Gi'
    minReplicas: frontendMinReplicas
    maxReplicas: frontendMaxReplicas
    environmentVariables: [
      {
        name: 'BACKEND_URL'
        value: 'https://${backend.outputs.fqdn}'
      }
    ]
  }
}

output backendFqdn string = backend.outputs.fqdn
output frontendFqdn string = frontend.outputs.fqdn
output cosmosEndpoint string = cosmos.outputs.endpoint
output cosmosDatabase string = cosmos.outputs.database
output cosmosContainer string = cosmos.outputs.container
output acrLoginServer string = acr.outputs.loginServer
