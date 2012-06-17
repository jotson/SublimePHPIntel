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
        intel.reset()

        if self.has_intel():
            # Find context
            point = view.sel()[0].a
            source = view.substr(sublime.Region(0, view.size()))
            context = phpparser.get_context(source, point)
            operator = view.substr(sublime.Region(point - 2, point))
            if len(context) == 1 and operator != '->' and operator != '::':
                context = ['__global__']

            # Iterate context and find completion at this point
            if context:
                for f in sublime.active_window().folders():
                    if realpath(view.file_name()).startswith(realpath(f)):
                        intel.load_index(f)

            if not intel:
                return False

            context_class, context_partial = intel.get_class(context)
            print '>>>', context_class, context_partial, str(time.time())

            if context_class:
                intel.find_completions(context, operator, context_class, context_partial, found, [])

        if found:
            for i in found:
                snippet = None
                argnames = []
                if i['kind'] == 'var':
                    snippet = i['name'].replace('$', '')
                    data.append(tuple([str(i['name']) + '\t' + str(i['returns']), str(snippet)]))
                if i['kind'] == 'class':
                    snippet = i['name']
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
                        intel.save(d, f, path)
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
                                intel.save(d, f, path)
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
