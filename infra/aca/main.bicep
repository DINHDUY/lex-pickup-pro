targetScope = 'resourceGroup'

@description('Azure region for the deployment.')
param location string = resourceGroup().location

@description('Base name used for the Azure resources.')
param appName string = 'lex-pickup-pro'

@description('Existing Cosmos DB account endpoint. Do not create a new account.')
param cosmosEndpoint string = 'https://dtranllc.documents.azure.com:443/'

@description('Primary or secondary key for the existing Cosmos DB account.')
@secure()
param cosmosKey string

@description('Existing Cosmos database name.')
param cosmosDatabaseName string = 'clubs'

@description('Existing Cosmos container name.')
param cosmosContainerName string = 'club_data'

@description('Frontend hostname, without scheme. Example: www.lex-pickup-pro.us')
param frontendHost string = 'www.lex-pickup-pro.us'

@description('Explicit backend image reference for the GHCR image.')
param backendImage string = 'ghcr.io/dinhduy/lex-pickup-pro/backend:latest'

@description('Explicit frontend image reference for the GHCR image.')
param frontendImage string = 'ghcr.io/dinhduy/lex-pickup-pro/frontend:latest'

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

@description('Invitation code used to onboard club members. Must not be LEX2026 when registration is enabled.')
param clubInviteCode string = 'LEX2026'

@description('Allow self-service registration with the club invitation code. Keep false in production unless clubInviteCode is unique.')
param registrationEnabled bool = false

@description('Allow Facebook users to immediately claim any active roster profile without an account.')
param facebookRosterClaimingEnabled bool = false

@description('Single cluster ID used within Cosmos data documents.')
param cosmosClubId string = 'lex-pickup'

var frontendOrigin = 'https://${frontendHost}'
var frontendAcaOrigin = 'https://${appName}-frontend.${managedEnvironment.properties.defaultDomain}'
var backendImageResolved = backendImage
var frontendImageResolved = frontendImage

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${appName}-env'
  location: location
  properties: {
    zoneRedundant: false
    appLogsConfiguration: {
      destination: 'azure-monitor'
    }
  }
}

module backend 'modules/container-app.bicep' = {
  name: 'backend-app'
  params: {
    name: '${appName}-backend'
    location: location
    environmentId: managedEnvironment.id
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
        value: cosmosEndpoint
      }
      {
        name: 'COSMOS_DATABASE'
        value: cosmosDatabaseName
      }
      {
        name: 'COSMOS_CONTAINER'
        value: cosmosContainerName
      }
      {
        name: 'COSMOS_CLUB_ID'
        value: cosmosClubId
      }
      {
        name: 'COSMOS_KEY'
        value: cosmosKey
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
        // Escape the leading '[' for the nested ARM deployment.
        value: '[["${frontendOrigin}","${frontendAcaOrigin}"]'
      }
      {
        name: 'CLUB_INVITE_CODE'
        value: clubInviteCode
      }
      {
        name: 'REGISTRATION_ENABLED'
        value: registrationEnabled ? 'true' : 'false'
      }
      {
        name: 'FACEBOOK_ROSTER_CLAIMING_ENABLED'
        value: facebookRosterClaimingEnabled ? 'true' : 'false'
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
    image: frontendImageResolved
    ingressExternal: true
    targetPort: 8080
    cpu: '0.25'
    memory: '0.5Gi'
    minReplicas: frontendMinReplicas
    maxReplicas: frontendMaxReplicas
    environmentVariables: [
      {
        name: 'NGINX_ENTRYPOINT_LOCAL_RESOLVERS'
        value: '1'
      }
      {
        name: 'BACKEND_URL'
        value: 'https://${backend.outputs.fqdn}'
      }
    ]
  }
}

output backendFqdn string = backend.outputs.fqdn
output frontendFqdn string = frontend.outputs.fqdn
output cosmosEndpoint string = cosmosEndpoint
output cosmosDatabase string = cosmosDatabaseName
output cosmosContainer string = cosmosContainerName
