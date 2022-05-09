#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
"""

import argparse
import asyncio
from enum import Enum
from queue import Queue
from threading import Thread
import time
import sys
import os

import time

import json

from .logging import LogService
from . import K8sEventHandler, K8sWatchConfig, K8sWatchEvent, K8sWatcher, K8sWatcherService

from typing import List

import typer

logger = LogService("k8swatcher.cli").logger

app = typer.Typer()


class ExecMode(str, Enum):
    asyncio_watch = "asyncio_watch"
    queuing_watch = "queuing_watch"

class PrintHandler(K8sEventHandler):
    async def handle_k8s_watch_event(self, k8s_watch_event:K8sWatchEvent):
        print(json.dumps(k8s_watch_event.dict(),default=str,indent=2))

class ExampleConsumerThread(Thread):

    def __init__(self, event_queue, *args, **kwargs):
        kwargs.setdefault('daemon', True)
        super().__init__(*args, **kwargs)
        self.event_queue = event_queue

    def run(self):
        while True:
            watch_event:K8sWatchEvent = self.event_queue.get()
            print(json.dumps(watch_event.dict(),default=str,indent=2))



@app.command()
def watch(k8s_kind:str = typer.Option(..., help="k8s object kind to watch (i.e. Ingress, Pod etc)"), \
          k8s_namespace:str = typer.Option(None, help="k8s namespace to scope to (only applicable w/ a list_namespaced_* function name)"), \
          k8s_sdk_class_name:str = typer.Option(..., help="Python kubernetes-client class name to utilize"), \
          k8s_sdk_list_function_name:str = typer.Option(..., help="Python kubernetes-client class list function name to utilize"), \
          field_selector:str= typer.Option(None, help="--field-selector field.path=1,field2.path=3"), \
          label_selector:str = typer.Option(None, help="--label-selector label1=z,label2=v"), \
          suppress_bookmarks:bool = typer.Option(True, help="Suppress BOOKMARK events from the watcher"), \
          include_k8s_objects:bool = typer.Option(False, help="Include the full k8s object (as a dict) in each event"), \
          exec_mode:ExecMode = typer.Option(ExecMode.queuing_watch, help="The preferred execution mode")):

    try:
        watch_config = K8sWatchConfig(**{ \
                        "id": k8s_kind,
                        "namespace": k8s_namespace, \
                        "kind": k8s_kind, \
                        "sdk_client_class_name": k8s_sdk_class_name, \
                        "sdk_list_function_name": k8s_sdk_list_function_name, \
                        "field_selector":field_selector, \
                        "label_selector":label_selector, \
                        "suppress_bookmarks": suppress_bookmarks, \
                        "include_k8s_objects":include_k8s_objects 
                    })

        watch_service = K8sWatcherService()

        if exec_mode == ExecMode.queuing_watch:
            watch_service.asyncio_watch([watch_config],PrintHandler())
        else:
            event_queue:Queue = watch_service.queuing_watch(watch_config)
            thread:ExampleConsumerThread = ExampleConsumerThread(event_queue)
            thread.start()
            thread.join()

        watch_service.join()

    except:
        print(str(sys.exc_info()[:2]))
        watch_service.shutdown()

def main():
    try:
        app()
    except Exception as e:
        print(str(sys.exc_info()[:2]))
        