# Additional Notes

## Endpoints

- [OSCI - OpenShift Console](https://openshift-console.osci.io)

- https://dev.eightknot.io
- https://eightknot.io

## Note

If acme isn't working (SSL) make sure that the route
has been configured to expect its existence:

https://gitlab.com/osci/ansible-role-openshift/-/blob/main/route/templates/route.yml?ref_type=heads#L6

## Quick start

Choose your deployment

```
# development deployment
oc apply -k openshift/overlays/dev
```

```
# production deployment
oc apply -k openshift/overlays/prod
```

View the objects kustomize will create

```
# development
kustomize build openshift/overlays/dev

# production
kustomize build openshift/overlays/prod
```

NOTE: labels allow selection of similar objects

```
oc get all -l development=true
oc get all -l app=eightknot-app

oc get secrets -l app=eightknot-app
```

Cleanup

```
oc delete -k openshift/overlays/dev
```

## Secret management

You may need to update the following secrets with your account info:

- augur-config
- eightknot-redis

## DNS Records

See [Example](https://gitlab.com/osci/community-cage-infra-dns/-/merge_requests/49/diffs)

## Digital Certs

See https://github.com/tnozicka/openshift-acme/tree/master/deploy#single-namespace

TODO: use `cert-manager`

```
# setup lets encrypt certs for routes
oc apply -fhttps://raw.githubusercontent.com/tnozicka/openshift-acme/master/deploy/single-namespace/{role,serviceaccount,issuer-letsencrypt-live,deployment}.yaml

# we don't need more than one replica
oc scale deployment/openshift-acme --replicas=1

# setup rolebinding for lets encrypt / acme
oc create rolebinding openshift-acme \
  --role=openshift-acme \
  --serviceaccount="$( oc project -q ):openshift-acme" \
  --dry-run=client \
  -o yaml | oc apply -f -
```
