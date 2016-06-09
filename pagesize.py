# Copyright 2015 Institute Of The Czech National Corpus
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This module provides a way how to measure page size with some predefined
page structure removals. E.g. if we want to watch for a page whose
content fluctuates too much due to some HTML element we can always
remove its contents to make results more "stable".

For more documentation please see watchdog.py
"""

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
import logging


class Query(object):
    def __init__(self, *items):
        self.items = items


class PageSize(object):

    def __init__(self, soup_document, ignores=None):
        self._ignores = ignores if ignores else []
        self._document = soup_document
        self._apply_ignores()

    def _apply_ignores(self):
        for ignore in self._ignores:
            elms = self.find_elem(ignore)
            for elm in elms:
                elm.clear()

    def find_elem(self, query):
        to_srch = [self._document.html]
        i = 0
        query_items = query.items[:]
        while i < len(query_items):
            query = query_items[i]
            to_srch_new = []
            for node in to_srch:
                to_srch_new.extend(node.find_all(query[0], query[1]))
            if len(to_srch_new) == 0:
                break
            to_srch = to_srch_new
            i += 1
        if i == len(query_items):
            return to_srch
        else:
            return []

    def get_size(self):
        return len(str(self._document))


def page_size(html_code, conf_ignore):
    if BeautifulSoup is not None:
        ignores = []
        if conf_ignore is None:
            conf_ignore = ()
        for single_ignore in conf_ignore:
            tmp = []
            for ignore_part in single_ignore:
                args = {}
                if 'class' in ignore_part:
                    args['class'] = ignore_part['class']
                if 'id' in ignore_part:
                    args['id'] = ignore_part['id']
                elm_name = ignore_part.get('name', None)
                tmp.append((elm_name, args))
            ignores.append(Query(*tmp))
        pd = PageSize(BeautifulSoup(html_code), ignores=ignores)
        return pd.get_size()
    else:
        logging.getLogger(__name__).warning('Module bs4 (BeautifulSoup ver4) not found. Returning raw page size.')
        return len(html_code)
