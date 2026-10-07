#!/usr/bin/env python3
"""Typed owned GTK-only physical request contract; never PCManFM acceptance."""
import hashlib
import json
import re

TEXT='Arctic isolated GTK3 entry'


def require(value,message):
    if not value: raise RuntimeError(message)


def validate(value):
    require(type(value) is dict and value.get('schema')=='arctic-gtk-physical-request-v1'
            and value.get('arm')=='gtk-no-warmup' and value.get('virtual_status')=='own-entry-not-activated'
            and value.get('release_acceptance') is False and re.fullmatch('[0-9a-f]{32}',value.get('nonce',''))
            and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',value.get('boot_id',''))
            and re.fullmatch('[0-9a-f]{64}',value.get('widget_evidence_sha256','')), 'GTK physical envelope differs')
    process=value.get('process',{});client=value.get('client',{});widget=value.get('widget',{})
    require(all(type(process.get(k)) is int and process[k]>1 for k in ('pid','start_ticks'))
            and isinstance(process.get('executable'),str) and re.fullmatch(r'/usr/bin/python3(?:\.\d+)?',process['executable'])
            and re.fullmatch('[0-9a-f]{64}',process.get('executable_sha256',''))
            and process.get('is_xwayland') is False and isinstance(process.get('client_id'),str)
            and process['client_id'].isdigit(), 'GTK physical owned native ELF differs')
    appid=value.get('appid','')
    require(re.fullmatch(r'org\.arctic\.Diagnostic\.Entry\.a[0-9a-f]{16}',appid)
            and type(client.get('pid')) is int and client['pid']==process['pid']
            and type(client.get('id')) is int and str(client['id'])==process['client_id']
            and client.get('appid')==appid and client.get('title')=='Arctic Gtk3 diagnostic '+appid
            and isinstance(client.get('foreign_toplevel_id'),str) and 0<len(client['foreign_toplevel_id'])<=128
            and client.get('is_xwayland') is False and client.get('is_focused') is True
            and client.get('is_visible') is True
            and all(type(client.get(k)) is int for k in ('x','y','width','height'))
            and 0<client['width']<=16384 and 0<client['height']<=16384
            and isinstance(client.get('monitor'),str) and 0<len(client['monitor'])<=128, 'GTK physical current owned client/focus differs')
    require(widget.get('schema')=='arctic-gtk-widget-snapshot-v1' and widget.get('nonce')==value['nonce']
            and widget.get('appid')==appid and widget.get('title')==client['title']
            and all(type(widget.get(k)) is int and widget[k]==process[k] for k in ('pid','start_ticks'))
            and type(widget.get('uid')) is int and widget['uid']>0 and widget.get('boot_id')==value['boot_id']
            and widget.get('text')==TEXT and widget.get('has_focus') is True and widget.get('is_focus') is True
            and widget.get('window_active') is True and type(widget.get('activations')) is int and widget['activations']==0
            and type(value.get('monotonic_ns')) is int and value['monotonic_ns']>0
            and type(widget.get('monotonic_ns')) is int and widget['monotonic_ns']>0
            and 0<=value['monotonic_ns']-widget['monotonic_ns']<=1_000_000_000,
            'GTK physical fresh own widget state differs')
    return value


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
