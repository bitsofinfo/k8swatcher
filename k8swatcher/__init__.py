#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
"""

from abc import abstractmethod
import asyncio
from queue import Queue
from threading import Thread
from pydantic import BaseModel
from typing import Generator, List, Optional, Dict, Any, Callable, Pattern
from abc import ABC
import enum
from kubernetes import client, config, kubernetes
import sys
from random import randint

from .logging import LogService

__author__ = "bitsofinfo"


class RestartRequiredException(Exception):
    def __init__(self,message):
        super().__init__(message)
        self.message = message

class K8sWatchEventType(str, enum.Enum):
    LOADED:str = "LOADED"
    ADDED:str = "ADDED"
    MODIFIED:str = "MODIFIED"
    DELETED:str = "DELETED"
    BOOKMARK:str = "BOOKMARK"

    def __str__(self):
        return self.name

class K8sWatchConfig(BaseModel):
    id:str
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

    def __init__(self, k8s_watch_config:K8sWatchConfig, \
                       k8s_config_file_path:str=None, \
                       k8s_config_context_name:str=None):
        
        self.logger = LogService("K8sWatcher").logger

        self.logger.debug(f"K8sWatcher() loading kube config: k8s_config_file_path={k8s_config_file_path} k8s_config_context_name={k8s_config_context_name} (Note: 'None' = using defaults)")

        try:
            config.load_kube_config(config_file=k8s_config_file_path, context=k8s_config_context_name)
        except Exception as e:
            self.logger.debug(f"K8sWatcher() load_kube_config() failed, attempting load_incluster_config()....")
            config.load_incluster_config()
            self.logger.debug(f"K8sWatcher() load_incluster_config() OK!")

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
                except client.ApiException as e:
                    if e.status == 410:
                        msg = f"handle_k8s_object_watch() k8s client 410 ApiException, setting local resource_version=None, raising RestartRequiredException... : {str(sys.exc_info()[:2])}"
                        self.logger.error(msg)
                        self.resource_version = None
                        raise RestartRequiredException(msg)
                    else:
                        raise e
                except Exception as e:
                    self.logger.exception(f"handle_k8s_object_watch() unexpected error: {str(sys.exc_info()[:2])}")
                    raise e
                

    def __iter__(self) -> Generator[K8sWatchEvent,None,None]:
        while True:
            try:
                self.logger.debug(f"__iter__() processing K8sWatchConfig[kind={self.k8s_watch_config.kind}]")

                if self.resource_version:
                    yield from self.handle_k8s_object_watch(self.k8s_watch_config)
                else:
                    yield from self.handle_k8s_object_list(self.k8s_watch_config)

                
            except RestartRequiredException as e:
                self.logger.warn(f"_iter_() caught RestartRequiredException, nullifying self.resource_version... : {e.message}")
                self.resource_version = None
                continue

            except Exception as e:
                self.logger.exception(f"_iter_() unexpected error: {str(sys.exc_info()[:2])}")

class K8sWatcherThread(Thread):
    
    def __init__(self, watch_event_queue:Queue, \
                       watch_config:K8sWatchConfig, \
                       k8s_config_file_path:str=None, \
                       k8s_config_context_name:str=None, \
                       *args, \
                       **kwargs):

        kwargs.setdefault('daemon', True)
        super().__init__(*args, **kwargs)
        self.watcher = K8sWatcher(watch_config,k8s_config_file_path,k8s_config_context_name).watcher()
        self.logger = LogService("K8sWatcherThread").logger
        self.watch_event_queue = watch_event_queue
        self.running = True

    def stop_running(self):
        self.running = False

    def run(self):
        try:
            while self.running:
                for k8s_watch_event in self.watcher:
                    self.watch_event_queue.put_nowait(k8s_watch_event)
            self.logger.debug("K8sWatcherThread.run() running=False, exiting...")
        except: 
            self.logger.exception(f"K8sWatcherThread().run() unexpected error: {str(sys.exc_info()[:2])}")
        finally:
            print("SHUTDOWN2")
            pass

class K8sEventHandler(ABC):
 
    @abstractmethod
    async def handle_k8s_watch_event(self, k8s_watch_event:K8sWatchEvent):
        pass

class K8sAsyncioConsumerThread(Thread):

    def __init__(self, watch_event_queue:Queue, event_handler:K8sEventHandler, *args, **kwargs):
        kwargs.setdefault('daemon', True)
        super().__init__(*args, **kwargs)
        self.logger = LogService("K8sAsyncioConsumerThread").logger
        self.watch_event_queue = watch_event_queue
        self.event_handler = event_handler
        self.running = True

    def stop_running(self):
        self.running = False

    async def consume_and_handle_watch_events(self):
        while self.running:
            try:
                watch_event:K8sWatchEvent = self.watch_event_queue.get()
                await self.event_handler.handle_k8s_watch_event(watch_event)
            except: 
                self.logger.exception(f"K8sAsyncioConsumerThread().run() unexpected error: {str(sys.exc_info()[:2])}")
            finally:
                pass
        self.logger.debug("K8sAsyncioConsumerThread.consume_and_handle_watch_events() running=False, exiting...")

    def run(self):
        try:
            asyncio.run(self.consume_and_handle_watch_events())
        except:
            print("SHUTDOWN")
        
class K8sWatcherService:

    def __init__(self, k8s_config_file_path:str=None, \
                       k8s_config_context_name:str=None):
        self.thread_map = {}
        self.threaded_watch_unified_event_queue = None
        self.logger = LogService("K8sWatcherService").logger

        self.k8s_config_file_path = k8s_config_file_path
        self.k8s_config_context_name = k8s_config_context_name

    def shutdown(self):

        # stop all in thread map
        if self.thread_map:
            for watch_id, watcher_thread in self.thread_map.items():
                self.logger.debug(f"shutdown() stopping thread: watch_id:{watch_id}")
                watcher_thread.stop_running()


    def queuing_watch(self, watch_config:K8sWatchConfig, unified_queue:bool = False) -> Queue:
        
        if unified_queue and not self.threaded_watch_unified_event_queue:
            self.threaded_watch_unified_event_queue = Queue()
            
        queue_to_use = self.threaded_watch_unified_event_queue

        if not queue_to_use:
            queue_to_use:Queue = Queue()

        thread = K8sWatcherThread(queue_to_use,watch_config,self.k8s_config_file_path,self.k8s_config_context_name)
        self.thread_map[watch_config.id] = thread
        thread.start()

        return queue_to_use

    def asyncio_watch(self, watch_configs:List[K8sWatchConfig], event_handler:K8sEventHandler):

        event_queue:Queue = None
        for wc in watch_configs:
             event_queue = self.queuing_watch(wc,unified_queue=True)

        asyncio_consumer_thread = K8sAsyncioConsumerThread(event_queue,event_handler)
        self.thread_map["asyncio_consumer_thread"] = asyncio_consumer_thread
        asyncio_consumer_thread.start()

    def join(self):
        for thread_id, thread in self.thread_map.items():
            self.logger.debug(f"join() joining thread: thread_id:{thread_id}")
            thread.join()