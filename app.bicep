extension radius

@description('Specifies the location for resources.')
param location string = 'local'

@description('Specifies the environment for resources.')
param environment string = 'default'

@description('Specifies the port for the container resource.')
param port int = 3000

@description('Specifies the image for the container resource.')
param magpieimage string = 'ghcr.io/image-registry/magpie:latest'

resource app 'Applications.Core/applications@2023-10-01-preview' = {
  name: 'simple-app'
  location: location
  properties: {
    environment: environment
  }
}

resource frontend 'Applications.Core/containers@2023-10-01-preview' = {
  name: 'frontend'
  location: location
  properties: {
    application: app.id
    container: {
      image: magpieimage
      ports: {
        web: {
          containerPort: port
        }
      }
      readinessProbe: {
        kind: 'httpGet'
        containerPort: port
        path: '/healthz'
      }
    }
    connections: {
      backend: {
        source: 'http://backend:3000'
      }
    }
  }
}


resource backend 'Applications.Core/containers@2023-10-01-preview' = {
  name: 'backend'
  location: location
  properties: {
    application: app.id
    container: {
      image: magpieimage
     
      ports: {
        web: {
          containerPort: port
        }
      }
      readinessProbe: {
        kind: 'httpGet'
        containerPort: port
        path: '/healthz'
      }}
      connections: {
      database: {
        source: database.id
      
      }
    }
  }
}




// Database - Redis used as a simple data store
resource database 'Applications.Datastores/redisCaches@2023-10-01-preview' = {
  name: 'database'
  properties: {
    application: app.id
    environment: environment
  }
}
