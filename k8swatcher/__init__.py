#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
"""


from pydantic import BaseModel
from typing import Generator, List, Optional, Dict, Any, Callable, Pattern

import enum
from kubernetes import client, config, kubernetes
import sys

from .logging import LogService

__author__ = "bitsofinfo"
class K8sWatchEventType(str, enum.Enum):
    LOADED:str = "LOADED"
    ADDED:str = "ADDED"
    MODIFIED:str = "MODIFIED"
    DELETED:str = "DELETED"
    BOOKMARK:str = "BOOKMARK"

    def __str__(self):
        return self.name

class K8sWatchConfig(BaseModel):
    suppress_bookmarks:bool = True
    include_k8s_objects:bool = False
    namespace: Optional[str]
    kind: str
    sdk_client_class_name:str
    sdk_list_function_name:str
    field_selector: Optional[str]
    label_selector: Optional[str]

    class Config:
        arbitrary_types_allowed = True

class K8sTrackedObject(BaseModel): 
    uid:str
    kind:str
    api_version:str
    name:str
    resource_version:str
    namespace:str
    k8s_object:Optional[Dict[Any,Any]]

class K8sWatchEvent(BaseModel):
    event_type:K8sWatchEventType
    resource_version:str
    k8s_tracked_object:Optional[K8sTrackedObject]

class K8sWatcher:

    def __init__(self, k8s_watch_config:K8sWatchConfig):
        
        config.load_kube_config()

        self.logger = LogService("K8sWatcher").logger

        self.k8s_api_client = client.ApiClient()
        
        self.sdk_clients = {}

        self.k8s_watch_config = k8s_watch_config

        api_client = getattr(kubernetes.client,self.k8s_watch_config.sdk_client_class_name)()
        api_client_function = getattr(api_client,self.k8s_watch_config.sdk_list_function_name)
        
        if k8s_watch_config.sdk_client_class_name not in self.sdk_clients:
            self.sdk_clients[k8s_watch_config.sdk_client_class_name] = {}

        self.sdk_clients[k8s_watch_config.sdk_client_class_name][k8s_watch_config.sdk_list_function_name] = api_client_function

        self.resource_version = None

        self.k8s_tracked_objects:Dict[str,K8sTrackedObject] = {}

    def watcher(self) -> Generator[K8sWatchEvent,None,None]:
        return iter(self)

    def get_k8s_list_function_args(self, watch_config:K8sWatchConfig, resource_version=None) -> dict:

        k8s_list_function_args = {
            "allow_watch_bookmarks": True,
            "field_selector": watch_config.field_selector,
            "label_selector": watch_config.label_selector,
            "timeout_seconds": 30,
            "resource_version": resource_version
        }

        # TODO: this is a bit of a hack...
        if "namespaced" in watch_config.sdk_list_function_name:
            k8s_list_function_args["namespace"] =  watch_config.namespace
        
        return k8s_list_function_args

    def to_k8s_tracked_object(self, k8s_object, k8s_kind, k8s_api_version) -> K8sTrackedObject:
        return K8sTrackedObject(**{
            "uid": k8s_object.metadata.uid,
            "kind": k8s_kind,
            "api_version": k8s_api_version,
            "name": k8s_object.metadata.name,
            "resource_version": k8s_object.metadata.resource_version,
            "namespace": k8s_object.metadata.namespace,
            "k8s_object": self.k8s_api_client.sanitize_for_serialization(k8s_object) if self.k8s_watch_config.include_k8s_objects else None
        })

    def get_sdk_list_function(self, k8s_watch_config:K8sWatchConfig):
        return self.sdk_clients[k8s_watch_config.sdk_client_class_name][k8s_watch_config.sdk_list_function_name]  

    def handle_k8s_object_list(self, k8s_watch_config:K8sWatchConfig) -> Generator[K8sWatchEvent,None,None]:

        self.logger.debug(f"handle_k8s_object_list() processing K8sWatchConfig[kind={k8s_watch_config.kind}]")

        k8s_list_function_args = self.get_k8s_list_function_args(k8s_watch_config)

        sdk_list_function = self.get_sdk_list_function(k8s_watch_config)

        k8s_object_list = sdk_list_function(**k8s_list_function_args)

        k8s_kind = k8s_object_list.kind.removesuffix('List')
        k8s_api_version = k8s_object_list.api_version

        for k8s_object in k8s_object_list.items:

            k8s_tracked_object = self.to_k8s_tracked_object(k8s_object,k8s_kind,k8s_api_version)
            
            self.k8s_tracked_objects[k8s_tracked_object.uid] = k8s_tracked_object
            
            yield K8sWatchEvent(**{
                "event_type": K8sWatchEventType.LOADED,
                "resource_version": k8s_object_list.metadata.resource_version,
                "k8s_tracked_object": k8s_tracked_object
            })

        self.resource_version = k8s_object_list.metadata.resource_version


    def handle_k8s_object_watch(self, k8s_watch_config:K8sWatchConfig) -> Generator[K8sWatchEvent,None,None]:

        self.logger.debug(f"handle_k8s_object_watch() processing K8sWatchConfig[kind={k8s_watch_config.kind}]")

        while True:
            k8s_list_function_args = self.get_k8s_list_function_args(k8s_watch_config, self.resource_version)
            k8s_watch = kubernetes.watch.Watch()

            sdk_list_function = self.get_sdk_list_function(k8s_watch_config)

            k8s_watch_generator = k8s_watch.stream(sdk_list_function, **k8s_list_function_args)

            while True:
                try:
                    k8s_watch_event = next(k8s_watch_generator)
                    k8s_watch_type = k8s_watch_event["type"]
                    k8s_object = k8s_watch_event["object"]
                    k8s_watch_type = K8sWatchEventType[k8s_watch_type]


                    if k8s_watch_type == K8sWatchEventType.BOOKMARK:
                        self.resource_version = k8s_object["metadata"]["resourceVersion"]
                        
                        if self.k8s_watch_config.suppress_bookmarks and k8s_watch_type == K8sWatchEventType.BOOKMARK:
                            continue
                        else:
                            yield K8sWatchEvent(**{
                                "event_type": K8sWatchEventType[k8s_watch_type],
                                "resource_version": self.resource_version,
                                "k8s_tracked_object": None
                            })
                    else:
                        k8s_tracked_object = self.to_k8s_tracked_object(k8s_object,k8s_object.kind,k8s_object.api_version)
                            
                        self.resource_version = k8s_tracked_object.resource_version

                        self.k8s_tracked_objects[k8s_tracked_object.uid] = k8s_tracked_object
                        
                        yield K8sWatchEvent(**{
                            "event_type": k8s_watch_type,
                            "resource_version": self.resource_version,
                            "k8s_tracked_object": k8s_tracked_object
                        })
                        

                except StopIteration as e:
                    break
                except Exception as e:
                    self.logger.exception(f"handle_k8s_object_watch() unexpected error: {str(sys.exc_info()[:2])}")
                

    def __iter__(self) -> Generator[K8sWatchEvent,None,None]:
        while True:
            try:
                self.logger.debug(f"__iter__() processing K8sWatchConfig[kind={self.k8s_watch_config.kind}]")

                if self.resource_version:
                    yield from self.handle_k8s_object_watch(self.k8s_watch_config)
                else:
                    yield from self.handle_k8s_object_list(self.k8s_watch_config)

                
            except Exception as e:
                self.logger.exception(f"_iter_() unexpected error: {str(sys.exc_info()[:2])}")

