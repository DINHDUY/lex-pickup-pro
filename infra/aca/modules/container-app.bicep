@description('Container App name.')
param name string

@description('Resource location.')
param location string = resourceGroup().location

@description('Azure Container Apps environment resource ID.')
param environmentId string

@description('Container registry login server. Leave empty when using a public registry such as GHCR.')
param registryServer string = ''

@description('Container registry username.')
param registryUsername string = ''

@description('Container registry password.')
@secure()
param registryPassword string = ''

@description('Container image to deploy.')
param image string

@description('Whether the ingress is public.')
param ingressExternal bool = true

@description('Target port for the container.')
param targetPort int = 8080

@description('CPU allocation for the app.')
param cpu string = '0.5'

@description('Memory allocation for the app.')
param memory string = '1Gi'

@description('Environment variables as name/value pairs.')
param environmentVariables array = []

@description('Minimum replica count.')
param minReplicas int = 1

@description('Maximum replica count.')
param maxReplicas int = 1

var registrySecrets = empty(registryPassword) ? [] : [
  {
    name: 'acr-password'
    value: registryPassword
  }
]

var registries = empty(registryServer) ? [] : [
  {
    server: registryServer
    username: registryUsername
    passwordSecretRef: 'acr-password'
  }
]

var envVars = [for item in environmentVariables: union({
    name: item.name
  }, empty(item.value) ? {} : {
    value: item.value
  }, empty(item.secretRef) ? {} : {
    secretRef: item.secretRef
  })]

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: ingressExternal
        targetPort: targetPort
        allowInsecure: false
        transport: 'auto'
      }
      registries: registries
      secrets: registrySecrets
    }
    template: {
      containers: [
        {
          name: 'main'
          image: image
          env: envVars
          resources: {
            cpu: json(cpu)
            memory: memory
          }
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output fqdn string = app.properties.configuration.ingress.fqdn
