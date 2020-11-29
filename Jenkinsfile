def environmentMap = [
  "master": "production",
  "development": "staging",
]

def namespaceMap = [
  "production": "kirppu",
  "staging": "kirppu-staging",
]

pipeline {
  agent any

  environment {
    PYTHONUNBUFFERED = "1"
    SKAFFOLD_DEFAULT_REPO = "harbor.con2.fi/con2"
  }

  stages {
    stage("Build") {
      steps {
        sh "emskaffolden -E ${environmentMap[env.BRANCH_NAME]} -- build --file-output build.json"
      }
    }

    stage("Deploy") {
      steps {
        sh "emskaffolden -E ${environmentMap[env.BRANCH_NAME]} -- deploy -n ${namespaceMap[environmentMap[env.BRANCH_NAME]]} -a=build.json"
      }
    }
  }

  post {
    always {
      archiveArtifacts "build.json"
      archiveArtifacts "kubernetes/template.compiled.yaml"
    }
  }
}
