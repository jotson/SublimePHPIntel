'''
SublimePHPIntel for Sublime Text 2
Copyright 2012 John Watson <https://github.com/jotson>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

import os
import threading
import time
import sublime
import sublime_plugin
from os.path import realpath
import phpparser
import intel

'''
TODO Optimization
     Based on profiling, there are two big targets for optimization:

     1. Loading and decoding the entire completion file is very time consuming.
        It would be better if we only loaded the data we needed. I think this
        could be accomplished by saving data for each class in its own file.
        In contrast, scanning all of the completions once they are in memory
        takes almost no time at all (<100ms).

        Strategy:
            Completions stored per file
            Index of class => file

     2. phpparser.get_context() is slow (about 400ms). It's entirely because of
        the process call to the PHP executable. Writing and unlinking the tmp
        file takes almost no time at all.

TODO phparser.py: Scan method arguments and combine with param data
     The above may fix an issue with duplicate declarations appearing in Yii sites
     because of yiilite.php

TODO Document::model()-> doesn't seem to be working in Yii projects

TODO Detect variable assignment. e.g. $var = <code> where code returns an object

TODO Jump to definition

TODO Custom regex patterns for matching special cases, like factory methods.
     Mage::getModel('catalog/product'): e.g. {'Mage::getModel\('(.*?)/(.*?)'\)':
     'class': 'Mage_{1}_Model_{2}', 'cap_first': true}

TODO Detect when new files are added/removed and rescan

TODO Handle case when scan started while a scan is already in progress. Scan
queues, perhaps.
'''


class ScanProjectCommand(sublime_plugin.WindowCommand):
    def run(self):
        self.thread = ScanThread()
        self.thread.start()


class EventListener(sublime_plugin.EventListener):
    def on_post_save(self, view):
        self.thread = ScanThread(file=view.file_name())
        self.thread.start()

    def on_query_completions(self, view, prefix, locations):
        data = []
        found = []

        if self.has_intel():
            # Find context
            point = view.sel()[0].a
            source = view.substr(sublime.Region(0, view.size()))
            context = phpparser.get_context(source, point)
            operator = view.substr(sublime.Region(point - 2, point))

            # Iterate context and find completion at this point
            if context:
                for f in sublime.active_window().folders():
                    if realpath(view.file_name()).startswith(realpath(f)):
                        intel.load_index(f)

            print intel.index
            return False

            if not intel:
                return False

            def get_class(context):
                if len(context) == 0:
                    return None, None

                if len(context) == 1:
                    for i in intel:
                        if i['class'] == context[0]:
                            return context[0], ''

                    return '__global__', context[0]

                for i in intel:
                    if i['class'] == context[0] and (i['name'] == context[1] or i['name'] == '$' + context[1]):
                        context[1] = i['returns']
                        return get_class(context[1:])

                return context[0], context[1]

            context_class, context_partial = get_class(context)
            print '>>>', context_class, context_partial, str(time.time())
            if context_class:
                def find_completions(context_class, context_partial, found, parsed=[]):
                    for i in intel:
                        if i['class'] == context_class:
                            if i['class'] in parsed:
                                return
                            if i['name'] and i['name'].startswith(context_partial):
                                match_visibility = 'public'
                                match_static = 0
                                if context[0] == '$this' and len(context) == 2:
                                    match_visibility = 'all'
                                    match_static = 0
                                if operator == '::':
                                    match_visibility = 'public'
                                    match_static = 1
                                if int(i['static']) == int(match_static) and i['visibility'] == match_visibility:
                                    found.append(i)
                            if i['extends']:
                                find_completions(i['extends'], context_partial, found, parsed)
                    parsed.append(context_class)

                find_completions(context_class, context_partial, found)

        if found:
            for i in found:
                snippet = None
                argnames = []
                if i['kind'] == 'var':
                    snippet = i['name'].replace('$', '')
                    data.append(tuple([str(i['name']) + '\t' + str(i['returns']), str(snippet)]))
                if i['kind'] == 'func':
                    args = []
                    if len(i['args']):
                        args = i['args']
                        argnames = []
                        for j in range(0, len(args)):
                            argname, argtype = args[j]
                            argnames.append(argname)
                            args[j] = '${' + str(j + 1) + ':' + argname.replace('$', '\\$') + '}'
                    snippet = '{name}({args})'.format(name=i['name'], args=', '.join(args))
                    data.append(tuple([str(i['name']) + '(' + ', '.join(argnames) + ')\t' + str(i['returns']), str(snippet)]))

        if data:
            # Remove duplicates and sort
            data = sorted(list(set(data)))
            return data
            #return (data, sublime.INHIBIT_EXPLICIT_COMPLETIONS | sublime.INHIBIT_WORD_COMPLETIONS)
        else:
            return False

    def has_intel(self):
        for f in sublime.active_window().folders():
            if os.path.exists(os.path.join(f, '.phpintel')):
                return True


class ScanThread(threading.Thread):
    def __init__(self, file=None):
        self.file = file
        if file:
            msg = 'Scanning ' + file + '...'
        else:
            msg = 'Scanning project...'
        self.progress = ThreadProgress(self, msg, 'Scan complete')
        threading.Thread.__init__(self)

    def run(self):
        self.progress.start()

        if self.file:
            # Scan one file
            if os.path.splitext(self.file)[1] == '.php':
                path = realpath(self.file)
                for f in sublime.active_window().folders():
                    if path.startswith(realpath(f)):
                        d = phpparser.scan_file(path)
                        intel_filename = intel.get_intel_path(f, path)
                        intel.save(d, intel_filename)
                        intel.update_index(path, *set([x['class'] for x in d]))
                        intel.save_index(f)
                        break

        else:
            # Scan entire project
            for f in sublime.active_window().folders():
                for root, dirs, files in os.walk(f, followlinks=True):
                    for name in files:
                        if os.path.splitext(name)[1] == '.php':
                            path = os.path.join(root, name)
                            self.set_progress_message('Scanning ' + path)
                            d = phpparser.scan_file(path)
                            if d:
                                intel_filename = intel.get_intel_path(f, path)
                                intel.save(d, intel_filename)
                                intel.update_index(path, *set([x['class'] for x in d]))
                            time.sleep(0.010)
                intel.save_index(f)

    def set_progress_message(self, message):
        self.progress.message = message


class ThreadProgress(threading.Thread):
    '''
    Cribbed from Package Control and modified into a real Thread just for fun.
    '''
    def __init__(self, thread, message, success_message):
        self.thread = thread
        self.message = message
        self.success_message = success_message
        self.addend = 1
        self.size = 8
        self.i = 0
        threading.Thread.__init__(self)

    def run(self):
        while True:
            if not self.thread.is_alive():
                if hasattr(self.thread, 'result') and not self.thread.result:
                    self.update_status('')
                    break
                self.update_status(self.success_message)
                break

            before = self.i % self.size
            after = (self.size - 1) - before
            self.update_status('[{before}={after}] {message}'.format(message=self.message, before=' ' * before, after=' ' * after))
            if not after:
                self.addend = -1
            if not before:
                self.addend = 1
            self.i += self.addend
            time.sleep(0.100)

    def update_status(self, message):
        sublime.set_timeout(lambda: sublime.status_message(message), 0)
