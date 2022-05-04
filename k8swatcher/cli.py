#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
"""

import argparse
import time
import sys
import os

import json

from .logging import LogService
from .k8swatcher import K8sWatchConfig, K8sWatcher

from typing import List

import typer

logger = LogService("k8swatcher.cli").logger

app = typer.Typer()

@app.command()
def watch(k8s_kind:str = typer.Option(..., help="k8s object kind to watch (i.e. Ingress, Pod etc)"), \
          k8s_namespace:str = typer.Option(None, help="k8s namespace to scope to (only applicable w/ a list_namespaced_* function name)"), \
          k8s_sdk_class_name:str = typer.Option(..., help="Python kubernetes-client class name to utilize"), \
          k8s_sdk_list_function_name:str = typer.Option(..., help="Python kubernetes-client class list function name to utilize"), \
          field_selector:str= typer.Option(None, help="--field-selector field.path=1,field2.path=3"), \
          label_selector:str = typer.Option(None, help="--label-selector label1=z,label2=v"), \
          suppress_bookmarks:bool = typer.Option(True, help="Suppress BOOKMARK events from the watcher"), \
          include_k8s_objects:bool = typer.Option(False, help="Include the full k8s object (as a dict) in each event")):

    watch_config = K8sWatchConfig(**{ \
                    "namespace": k8s_namespace, \
                    "kind": k8s_kind, \
                    "sdk_client_class_name": k8s_sdk_class_name, \
                    "sdk_list_function_name": k8s_sdk_list_function_name, \
                    "field_selector":field_selector, \
                    "label_selector":label_selector, \
                    "suppress_bookmarks": suppress_bookmarks, \
                    "include_k8s_objects":include_k8s_objects 
                })

    k8s_watcher = K8sWatcher(watch_config).watcher()

    for event in k8s_watcher:
        print(json.dumps(event.dict(),default=str,indent=2))



def main():
    app()