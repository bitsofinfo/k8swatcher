# k8swatcher <!-- omit in toc -->

![GitHub Actions status](https://github.com/bitsofinfo/k8swatcher/actions/workflows/pypi.yml/badge.svg) [![PyPI version](https://badge.fury.io/py/k8swatcher.svg)](https://badge.fury.io/py/k8swatcher) 

Python module that simplifies watching anything on a kubernetes cluster. You can utilize this module in your own python application to fulfill the typical *"list then watch"* functionality as described in the "[Efficient detection of changes](https://kubernetes.io/docs/reference/using-api/api-concepts/#efficient-detection-of-changes)" section of the kubernetes API documentation. (without having to write that code yourself!). This module utilizes the [Python Kubernetes Client](https://github.com/kubernetes-client) under the covers. 

- [Install](#install)
- [Using in your python code](#using-in-your-python-code)
  - [kubernetes configuration](#kubernetes-configuration)
  - [Direct](#direct)
  - [Queuing via K8sWatcherService](#queuing-via-k8swatcherservice)
  - [Asyncio via K8sWatcherService and a K8sEventHandler](#asyncio-via-k8swatcherservice-and-a-k8seventhandler)
- [run locally w/ the built in CLI](#run-locally-w-the-built-in-cli)
- [example CLI output](#example-cli-output)
- [local dev](#local-dev)
- [todo](#todo)

## Install

```
pip install k8swatcher
```
## Using in your python code

There are a few different ways you can utilize this module in your code. Note that the underlying [Python Kubernetes Client](https://github.com/kubernetes-client) does not support asyncio, so in real-world applications, you generally will be dealing w/ python `Threads` to handle events that come from the underlying library. The `K8sWatcherService` provides some convienence methods for this.

### kubernetes configuration

Currently the module determines the kubernetes connection configuration via the `kubernetes.config.load_kube_config()` method which relies on the excuting processes's `~/.kube/config` current context (by default), unless you specify a specific file/context to use via the `K8sWatcher` and `K8sWatcherService` constructors.
### Direct

The direct mode gives you more control on how process each `K8sWatchEvent` that is `yielded` from the `K8sWatcher`. 

For each type of kubernetes object you want to watch... wire up a separate `K8sWatcher` then call its `watcher()` method which returns a long-lived `Generator` that returns `K8sWatchEvent` objects as things happen.

A typical usage pattern would be to wire up separate `Threads`, one per thing you wish to watch, bind to `Queues` etc and then go from there...

```python
import json
from k8swatcher import K8sWatchConfig, K8sWatcher, K8sWatchEvent

watch_config = K8sWatchConfig(**{ \
                    "namespace": "my-namespace", \
                    "kind": "Pod", \
                    "sdk_client_class_name": "CoreV1Api", \
                    "sdk_list_function_name": "list_namespaced_pod", \
                    "field_selector": None, \
                    "label_selector": "mylabel=x,myotherlabel=y",
                    "include_k8s_objects": True
                })

k8s_watcher = K8sWatcher(watch_config).watcher()

for event in k8s_watcher:
    print(json.dumps(event.dict(),default=str,indent=2))
    
```

### Queuing via K8sWatcherService

If you are not interested in writing your own consumer `Thread` code and would like each `K8sWatchEvent` to be delivered via python `Queues` you can use the `K8sWatcherService.queuing_watch(K8sWatchConfig, unified_queue=True|False)` method. Each time you call `queuing_watch`, `K8sWatcherService` creates a new `Thread` bound to a unique `K8sWatcher` instance to automatically capture all events emitted from it. Each event will be placed on a `Queue` that is returned to you. If you pass `unified_queue=True`, the same `Queue` instance will be returned for every call to `queuing_watch()` so you only have to monitor a single `Queue` that will contains different `K8sWatchEvents` across all the different `K8sWatchConfigs` you define.

```python
import json
from k8swatcher import K8sWatchConfig, K8sWatchService, K8sWatchEvent
from threading import Thread

class MyConsumerThread(Thread):

    def __init__(self, event_queue_to_monitor, *args, **kwargs):
        kwargs.setdefault('daemon', True)
        super().__init__(*args, **kwargs)

    def run(self):
        while True:
            watch_event:K8sWatchEvent = self.watch_event_queue.get()
            print(json.dumps(watch_event.dict(),default=str,indent=2))

pod_watch_config = K8sWatchConfig(**{ \
                    "id": k8s_kind,
                    "namespace": k8s_namespace, \
                    "kind": "Pod", \
                  ...})

ingress_watch_config = K8sWatchConfig(**{ \
                    "id": k8s_kind,
                    "namespace": k8s_namespace, \
                    "kind": "Ingress", \
                  ...})

watch_service = K8sWatcherService()

"""
With `unified_queue=False` (the default):

... each distinct call to queuing_watch() returns
a dedicated Queue per K8sWatchConfig
"""
pod_event_queue:Queue = watch_service.queuing_watch(pod_watch_config)
ingress_event_queue:Queue = watch_service.queuing_watch(ingress_watch_config)

pod_consumer = MyConsumerThread(pod_event_queue)
pod_consumer.start()

ingress_consumer = MyConsumerThread(ingress_event_queue)
ingress_consumer.start()

pod_consumer.join()
ingress_consuner.join()
watch_service.join()


"""
However with `unified_queue=True`:

... each distinct call to queuing_watch() returns
a the same Queue that will get events for all K8sWatchConfigs 
"""
global_event_queue:Queue = watch_service.queuing_watch(pod_watch_config,unified_queue=True)
watch_service.queuing_watch(ingress_watch_config,unified_queue=True)

all_events_consumer = MyConsumerThread(global_event_queue)
all_events_consumer.start()
all_events_consumer.join()

watch_service.join()
...

```

### Asyncio via K8sWatcherService and a K8sEventHandler

If you don't want to manage any `Threads` at all, you can utilize the `K8sEventHandler` method. In this usage pattern you simply provide a class instance that implements the `K8sEventHandler` method `async def handle_k8s_watch_event(self, k8s_watch_event:K8sWatchEvent)` and your handler class will be called every time a new `K8sWatchEvent` is created. Internally `K8sWatcherService` manages a consumer thread automatically for you that captures all events and calls your `async` handler and then `awaits` it's finish.

```python
import json
from k8swatcher import K8sWatchConfig, K8sWatchService, K8sWatchEvent

class MyCustomHandler(K8sEventHandler):
    async def handle_k8s_watch_event(self, k8s_watch_event:K8sWatchEvent):
        watch_event:K8sWatchEvent = self.watch_event_queue.get()
        print(json.dumps(watch_event.dict(),default=str,indent=2))
        await doMyCustomStuff(k8s_watch_event)


pod_watch_config = K8sWatchConfig(**{ \
                    "id": k8s_kind,
                    "namespace": k8s_namespace, \
                    "kind": "Pod", \
                  ...})

ingress_watch_config = K8sWatchConfig(**{ \
                    "id": k8s_kind,
                    "namespace": k8s_namespace, \
                    "kind": "Ingress", \
                  ...})

watch_service = K8sWatcherService()

watch_service.asyncio_watch([pod_watch_config,ingress_watch_config],MyCustomHandler())

watch_service.join()
```

## run locally w/ the built in CLI

In addition to being able to utilize this module inline in your code, this module also includes a simple CLI you can use for testing out the functionality. The CLI is not intended for any production use.

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
  --exec-mode [asyncio_watch|queuing_watch]
                                  The preferred execution mode  [default:
                                  ExecMode.queuing_watch]
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
    "k8s_object": {
      "metadata": {
        "creationTimestamp": "2022-05-04T14:22:21+00:00",
        "generateName": "csi-azurefile-node-",
        "labels": {
          "app": "csi-azurefile-node",
          "controller-revision-hash": "56dd69698c",
          "pod-template-generation": "8"
        },
        "managedFields": [
            ...
        ]
        ...
      }
    }
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
    "k8s_object": {
      "metadata": {
        "creationTimestamp": "2022-05-04T14:22:21+00:00",
        "generateName": "csi-azurefile-node-",
        "labels": {
          "app": "csi-azurefile-node",
          "controller-revision-hash": "56dd69698c",
          "pod-template-generation": "8"
        },
        "managedFields": [
            ...
        ]
        ...
      }
    }
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
    "k8s_object": {
      "metadata": {
        "creationTimestamp": "2022-05-04T14:22:21+00:00",
        "generateName": "csi-azurefile-node-",
        "labels": {
          "app": "csi-azurefile-node",
          "controller-revision-hash": "56dd69698c",
          "pod-template-generation": "8"
        },
        "managedFields": [
            ...
        ]
        ...
      }
    }
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
    "k8s_object": {
      "metadata": {
        "creationTimestamp": "2022-05-04T14:22:21+00:00",
        "generateName": "csi-azurefile-node-",
        "labels": {
          "app": "csi-azurefile-node",
          "controller-revision-hash": "56dd69698c",
          "pod-template-generation": "8"
        },
        "managedFields": [
            ...
        ]
        ...
      }
    }
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
    "k8s_object": {
      "metadata": {
        "creationTimestamp": "2022-05-04T14:22:21+00:00",
        "generateName": "csi-azurefile-node-",
        "labels": {
          "app": "csi-azurefile-node",
          "controller-revision-hash": "56dd69698c",
          "pod-template-generation": "8"
        },
        "managedFields": [
            ...
        ]
        ...
      }
    }
  }
}
```

## local dev

```
python3 -m venv k8swatcher.ve
source k8swatcher.ve/bin/activate
pip install -r requirements-dev.txt
```

## todo

a few tests, using `kind` etc