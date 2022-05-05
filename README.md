# k8swatcher <!-- omit in toc -->

![GitHub Actions status](https://github.com/bitsofinfo/k8swatcher/actions/workflows/pypi.yml/badge.svg) [![PyPI version](https://badge.fury.io/py/k8swatcher.svg)](https://badge.fury.io/py/k8swatcher) 

Python module that simplifies watching anything on a kubernetes cluster. You can utilize this module in your own python application to implement the typical *"list then watch"* functionality as described in the "[Efficient detection of changes](https://kubernetes.io/docs/reference/using-api/api-concepts/#efficient-detection-of-changes)" section of the kubernetes API documentation.

- [local dev](#local-dev)
- [build local wheel](#build-local-wheel)
- [using in your python code](#using-in-your-python-code)
- [run locally w/ the built in CLI](#run-locally-w-the-built-in-cli)
- [example CLI output](#example-cli-output)

## local dev

```
python3 -m venv k8swatcher.ve
source k8swatcher.ve/bin/activate
pip install -r requirements-dev.txt
```
## build local wheel

```
pip install .
```

## using in your python code


```python
import json
from k8swatcher import K8sWatchConfig, K8sWatcher

watch_config = K8sWatchConfig(**{ \
                    "namespace": "my-namespace", \
                    "kind": "Pod", \
                    "sdk_client_class_name": "CoreV1Api", \
                    "sdk_list_function_name": "list_namespaced_pod", \
                    "field_selector": None, \
                    "label_selector": "mylabel=x,myotherlabel=y"
                })

k8s_watcher = K8sWatcher(watch_config).watcher()

for event in k8s_watcher:
    print(json.dumps(event.dict(),default=str,indent=2))
    
```
## run locally w/ the built in CLI

In addition to being able to utilize this module inline in your code, this module also includes a simple CLI you can use for testing.

```
$ k8swatcher --help

Usage: k8swatcher [OPTIONS]

Options:
  --k8s-kind TEXT                 k8s object kind to watch (i.e. Ingress, Pod
                                  etc)  [required]
  --k8s-namespace TEXT            k8s namespace to scope to (only applicable
                                  w/ a list_namespaced_* function name)
  --k8s-sdk-class-name TEXT       Python kubernetes-client class name to
                                  utilize  [required]
  --k8s-sdk-list-function-name TEXT
                                  Python kubernetes-client class list function
                                  name to utilize  [required]
  --field-selector TEXT           --field-selector field.path=1,field2.path=3
  --label-selector TEXT           --label-selector label1=z,label2=v
  --suppress-bookmarks / --no-suppress-bookmarks
                                  Suppress BOOKMARK events from the watcher
                                  [default: suppress-bookmarks]
  --include-k8s-objects / --no-include-k8s-objects
                                  Include the full k8s object (as a dict) in
                                  each event  [default: no-
                                  include-k8s-objects]
  --install-completion [bash|zsh|fish|powershell|pwsh]
                                  Install completion for the specified shell.
  --show-completion [bash|zsh|fish|powershell|pwsh]
                                  Show completion for the specified shell, to
                                  copy it or customize the installation.
  --help                          Show this message and exit.
```

The arguments `--k8s-sdk-class-name` and `--k8s-sdk-list-function-name` are specifically referring to the [Python kubernetes-client](https://github.com/kubernetes-client/python/tree/master/kubernetes/docs) api's.

Watch `Ingress` objects across all namespaces...
```
k8swatcher \
    --k8s-kind Ingress \
    --k8s-sdk-class-name NetworkingV1Api \
    --k8s-sdk-list-function-name list_ingress_for_all_namespaces \
    --label-selector some-label=myvalue,other-label=true 
```

Watch `Pod` objects in a specific namespace...
```
k8swatcher \
    --k8s-kind Pod \
    --k8s-namespace my-apps \
    --k8s-sdk-class-name CoreV1Api \
    --k8s-sdk-list-function-name list_namespaced_pod \
    --include-k8s-objects
```

## example CLI output

Again the CLI is just for testing/demo purposes. The object emitted to STDOUT is the object you can utilize in your code when leveraging this module.

```
2022-05-05 06:56:19,587 - K8sWatcher - DEBUG - __iter__() processing K8sWatchConfig[kind=Pod]
2022-05-05 06:56:19,587 - K8sWatcher - DEBUG - handle_k8s_object_list() processing K8sWatchConfig[kind=Pod]
{
  "event_type": "LOADED",
  "resource_version": "24891356",
  "k8s_tracked_object": {
    "uid": "dc1321ba-4b4c-47a9-9d85-7b8a8d0ef2af",
    "kind": "Pod",
    "api_version": "v1",
    "name": "my-service-dev-0-0-3-886bf55d5-p7kpd",
    "resource_version": "24692787",
    "namespace": "my-apps",
    "k8s_object": null
  }
}
2022-05-05 06:56:21,319 - K8sWatcher - DEBUG - __iter__() processing K8sWatchConfig[kind=Pod]
2022-05-05 06:56:21,319 - K8sWatcher - DEBUG - handle_k8s_object_watch() processing K8sWatchConfig[kind=Pod]
{
  "event_type": "MODIFIED",
  "resource_version": "24891472",
  "k8s_tracked_object": {
    "uid": "dc1321ba-4b4c-47a9-9d85-7b8a8d0ef2af",
    "kind": "Pod",
    "api_version": "v1",
    "name": "my-service-dev-0-0-3-886bf55d5-p7kpd",
    "resource_version": "24891472",
    "namespace": "my-apps",
    "k8s_object": null
  }
}
{
  "event_type": "MODIFIED",
  "resource_version": "24891481",
  "k8s_tracked_object": {
    "uid": "dc1321ba-4b4c-47a9-9d85-7b8a8d0ef2af",
    "kind": "Pod",
    "api_version": "v1",
    "name": "my-service-dev-0-0-3-886bf55d5-p7kpd",
    "resource_version": "24891481",
    "namespace": "my-apps",
    "k8s_object": null
  }
}
{
  "event_type": "MODIFIED",
  "resource_version": "24891521",
  "k8s_tracked_object": {
    "uid": "dc1321ba-4b4c-47a9-9d85-7b8a8d0ef2af",
    "kind": "Pod",
    "api_version": "v1",
    "name": "my-service-dev-0-0-3-886bf55d5-p7kpd",
    "resource_version": "24891521",
    "namespace": "my-apps",
    "k8s_object": null
  }
}
{
  "event_type": "DELETED",
  "resource_version": "24891522",
  "k8s_tracked_object": {
    "uid": "dc1321ba-4b4c-47a9-9d85-7b8a8d0ef2af",
    "kind": "Pod",
    "api_version": "v1",
    "name": "my-service-dev-0-0-3-886bf55d5-p7kpd",
    "resource_version": "24891522",
    "namespace": "my-apps",
    "k8s_object": null
  }
}
```