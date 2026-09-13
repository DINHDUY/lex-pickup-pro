targetScope = 'resourceGroup'

@description('Azure subscription ID that owns the target Cosmos account.')
param subscriptionId string = '41e5ce95-5e87-4679-bb44-babc02e5d6f6'

@description('Reuse the existing free-tier Cosmos account instead of creating a new one.')
param useExistingAccount bool = true
@description('Reuse the existing database and container instead of creating new Azure resources.')
param useExistingResources bool = true

@description('Globally unique Cosmos account name, lowercase letters, numbers and hyphens.')
param accountName string = 'dtranllc'
param location string = 'eastus2'
@description('Existing database name to reuse. If the database already exists, set this to its current name and do not force a rename.')
param databaseName string = 'clubs'
param containerName string = 'club_data'
@description('Object/principal ID of the backend managed identity; this is not its client ID.')
param backendPrincipalId string
@description('Optional principal ID allowed to initialize and migrate this container.')
param operatorPrincipalId string = ''
@description('Private endpoint subnet. Leave empty only when explicit firewall IPs are provided.')
param privateEndpointSubnetId string = ''
@description('VNet ID for private DNS linking when a private endpoint is selected.')
param privateDnsVnetId string = ''
@description('Explicit public IPv4 addresses/CIDRs. Empty disables public access.')
param allowedIpRanges array = []
@minValue(400)
param throughput int = 400
@description('Optional existing action-group resource ID for alert delivery.')
param actionGroupId string = ''

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = if (!useExistingAccount) {
  name: accountName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    consistencyPolicy: { defaultConsistencyLevel: 'Strong' }
    locations: [{ locationName: location, failoverPriority: 0, isZoneRedundant: false }]
    enableMultipleWriteLocations: false
    enableAutomaticFailover: false
    disableLocalAuth: true
    minimalTlsVersion: 'Tls12'
    publicNetworkAccess: empty(allowedIpRanges) ? 'Disabled' : 'Enabled'
    ipRules: [for ip in allowedIpRanges: { ipAddressOrRange: ip }]
    networkAclBypass: 'None'
    backupPolicy: {
      type: 'Continuous'
      continuousModeProperties: { tier: 'Continuous7Days' }
    }
  }
}
resource existingAccount 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = if (useExistingAccount) {
  name: accountName
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = if (!useExistingResources && !useExistingAccount) {
  parent: account
  name: databaseName
  properties: { resource: { id: databaseName } }
}
resource existingDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' existing = if (useExistingResources) {
  parent: existingAccount
  name: databaseName
}

resource container 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = if (!useExistingResources && !useExistingAccount) {
  parent: database
  name: containerName
  properties: {
    resource: {
      id: containerName
      partitionKey: { paths: ['/club_id'], kind: 'Hash', version: 2 }
      uniqueKeyPolicy: { uniqueKeys: [{ paths: ['/identity_key'] }] }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [{ path: '/*' }]
        excludedPaths: [
          { path: '/data/password_hash/?' }
          { path: '/data/body/?' }
          { path: '/data/result/*' }
          { path: '/_etag/?' }
        ]
        // The current adapter issues partition-scoped kind queries. These support future targeted reads.
        compositeIndexes: [
          [{ path: '/kind', order: 'ascending' }, { path: '/data/name', order: 'ascending' }]
          [{ path: '/kind', order: 'ascending' }, { path: '/data/starts_at', order: 'descending' }]
          [{ path: '/data/status', order: 'ascending' }, { path: '/data/starts_at', order: 'ascending' }]
          [{ path: '/data/season_id', order: 'ascending' }, { path: '/data/starts_at', order: 'descending' }]
        ]
      }
    }
    options: { throughput: throughput }
  }
}
resource existingContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' existing = if (useExistingResources) {
  parent: existingDatabase
  name: containerName
}

var dataContributor = '${useExistingAccount ? existingAccount.id : account.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
resource appAccess 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = if (useExistingAccount) {
  parent: existingAccount
  name: guid(existingAccount.id, existingContainer.id, backendPrincipalId)
  properties: {
    principalId: backendPrincipalId
    roleDefinitionId: dataContributor
    scope: '${existingAccount.id}/dbs/${databaseName}/colls/${containerName}'
  }
}
resource appAccessNew 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = if (!useExistingAccount) {
  parent: account
  name: guid(account.id, container.id, backendPrincipalId)
  properties: {
    principalId: backendPrincipalId
    roleDefinitionId: dataContributor
    scope: '${account.id}/dbs/${databaseName}/colls/${containerName}'
  }
}
resource operatorAccess 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = if (!empty(operatorPrincipalId) && useExistingAccount) {
  parent: existingAccount
  name: guid(existingAccount.id, existingContainer.id, operatorPrincipalId)
  properties: {
    principalId: operatorPrincipalId
    roleDefinitionId: dataContributor
    scope: '${existingAccount.id}/dbs/${databaseName}/colls/${containerName}'
  }
}
resource operatorAccessNew 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = if (!empty(operatorPrincipalId) && !useExistingAccount) {
  parent: account
  name: guid(account.id, container.id, operatorPrincipalId)
  properties: {
    principalId: operatorPrincipalId
    roleDefinitionId: dataContributor
    scope: '${account.id}/dbs/${databaseName}/colls/${containerName}'
  }
}
resource endpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = if (!empty(privateEndpointSubnetId)) {
  name: '${accountName}-private'
  location: location
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [{
      name: '${accountName}-sql'
      properties: { privateLinkServiceId: useExistingAccount ? existingAccount.id : account.id, groupIds: ['Sql'] }
    }]
  }
}
resource dns 'Microsoft.Network/privateDnsZones@2020-06-01' = if (!empty(privateEndpointSubnetId)) {
  name: 'privatelink.documents.azure.com'
  location: 'global'
}
resource dnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (!empty(privateEndpointSubnetId) && !empty(privateDnsVnetId)) {
  parent: dns
  name: '${accountName}-vnet'
  location: 'global'
  properties: { registrationEnabled: false, virtualNetwork: { id: privateDnsVnetId } }
}
resource dnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (!empty(privateEndpointSubnetId)) {
  parent: endpoint
  name: 'cosmos'
  properties: { privateDnsZoneConfigs: [{ name: 'cosmos', properties: { privateDnsZoneId: dns.id } }] }
}
var alerts = [
  { name: 'throttled', metric: 'TotalRequests', aggregation: 'Total', threshold: 10, dimensions: [{ name: 'StatusCode', operator: 'Include', values: ['429'] }] }
  { name: 'server-errors', metric: 'TotalRequests', aggregation: 'Total', threshold: 1, dimensions: [{ name: 'StatusCode', operator: 'Include', values: ['500', '503'] }] }
  { name: 'latency', metric: 'ServerSideLatency', aggregation: 'Average', threshold: 100, dimensions: [] }
  { name: 'storage', metric: 'DataUsage', aggregation: 'Maximum', threshold: 20000000, dimensions: [] }
  { name: 'ru-pressure', metric: 'NormalizedRUConsumption', aggregation: 'Maximum', threshold: 80, dimensions: [] }
]
resource metricAlerts 'Microsoft.Insights/metricAlerts@2018-03-01' = [for alert in alerts: {
  name: '${accountName}-${alert.name}'
  location: 'global'
  properties: {
    description: 'Lex Pickup Cosmos ${alert.name}; thresholds are initial guardrails, tune from measured workload.'
    severity: 2
    enabled: true
    scopes: [useExistingAccount ? existingAccount.id : account.id]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [{
        name: alert.name
        metricNamespace: 'Microsoft.DocumentDB/databaseAccounts'
        metricName: alert.metric
        timeAggregation: alert.aggregation
        operator: 'GreaterThan'
        threshold: alert.threshold
        dimensions: alert.dimensions
        criterionType: 'StaticThresholdCriterion'
      }]
    }
    actions: empty(actionGroupId) ? [] : [{ actionGroupId: actionGroupId }]
  }
}]

output endpoint string = useExistingAccount ? existingAccount.properties.documentEndpoint : account.properties.documentEndpoint
output database string = databaseName
output container string = containerName
output accountResourceId string = useExistingAccount ? existingAccount.id : account.id
output subscriptionId string = subscriptionId
