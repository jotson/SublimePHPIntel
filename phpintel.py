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
import re
import sublime
import sublime_plugin
import phpparser
import intel

'''
TODO Detect variable assignment. e.g. $var = <code> where code returns an object

TODO Custom regex patterns for matching special cases, like factory methods.
     Mage::getModel('catalog/product'): e.g. {'Mage::getModel\('(.*?)/(.*?)'\)':
     'class': 'Mage_{1}_Model_{2}', 'cap_first': true}

TODO Detect when new files are added/removed and rescan
'''


class ScanProjectCommand(sublime_plugin.WindowCommand):
    def run(self):
        start_scan()


class ScanAbortCommand(sublime_plugin.WindowCommand):
    def run(self):
        abort_scan()


class GotoDeclarationCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        intel.reset()

        view = self.view
        symbol = view.substr(expand_word(view, view.sel()[0]))
        path = None
        if symbol:
            for f in sublime.active_window().folders():
                intel.load_index(f)
            if symbol in intel._index:
                # Find class
                # TODO Show a quicklist when there is more than one choice
                path = intel._index[symbol].pop()
                self.view.window().open_file(path, sublime.TRANSIENT)
            # elif symbol in intel._symbol_index:
            #     # Find other symbol
            #     # TODO Build an index (with line numbers) of all declared symbols to make this faster
            #     # TODO Show a quicklist when there is more than one choice
            #     path = intel._symbol_index[symbol].pop()
            #     self.view.window().open_file(path, sublime.TRANSIENT)
            #     # Proof of concept implementation:
            #     # for class_name in intel._index.keys():
            #     #     i = intel.get_intel(class_name)
            #     #     for s in i:
            #     #         if s['name'] == symbol:
            #     #             path = intel._index[class_name].pop()
            #     #             view = self.view.window().open_file(path, sublime.TRANSIENT)
            #     #             break
            else:
                sublime.status_message('Not found')
        else:
            sublime.status_message('Put cursor on some text first')


def expand_word(view, region):
    '''
    Expand the region to hold the entire word it is within
    '''
    start = region.a
    end = region.b
    while re.match('[\w|_]', view.substr(start - 1)):
        start -= 1
    while re.match('[\w|_]', view.substr(end)):
        end += 1

    return sublime.Region(start, end)


class EventListener(sublime_plugin.EventListener):
    def on_post_save(self, view):
        start_scan(path=view.file_name())

    def on_query_completions(self, view, prefix, locations):
        data = []
        found = []
        intel.reset()

        point = view.sel()[0].a
        
        if view.score_selector(point, 'source.php') == 0 or view.score_selector(point, 'string.quoted') > 0:
            return False

        if self.has_intel():
            # Find context
            source = view.substr(sublime.Region(0, view.size()))
            context, visibility = phpparser.get_context(source, point)
            # print context, visibility
            operator = view.substr(sublime.Region(point - 2, point))
            if len(context) == 1 and operator != '->' and operator != '::':
                if len(context[0]) >= 2:
                    context = ['__global__', context[0]]
                else:
                    context = None

            # Iterate context and find completion at this point
            if context:
                for f in sublime.active_window().folders():
                    intel.load_index(f)
            else:
                return False

            if not intel:
                return False

            context_class, context_partial = intel.get_class(context)
            # print '>>>', context, visibility, context_class, context_partial, str(time.time())

            if context_class:
                intel.find_completions(context, operator, context_class, context_partial, found, visibility, [])

        if found:
            for i in found:
                snippet = None
                argnames = []
                if i['kind'] == 'var':
                    snippet = i['name'].replace('$', '')
                    returns = i['returns'] if i['returns'] else 'mixed'
                    data.append(tuple([str(i['name']) + '\t' + returns, str(snippet)]))
                if i['kind'] == 'class':
                    snippet = i['name']
                    returns = i['returns'] if i['returns'] else 'mixed'
                    data.append(tuple([str(i['name']) + '\t' + returns, str(snippet)]))
                if i['kind'] == 'func':
                    a = []
                    if len(i['args']):
                        args = i['args']
                        argnames = []
                        for j in range(0, len(args)):
                            argname, argtype = args[j]
                            argnames.append(argname)
                            a.append('${' + str(j + 1) + ':' + argname.replace('$', '\\$') + '}')
                    snippet = '{name}({args})'.format(name=i['name'], args=', '.join(a))
                    returns = i['returns'] if i['returns'] else 'mixed'
                    data.append(tuple([str(i['name']) + '(' + ', '.join(argnames) + ')' + '\t' + returns, str(snippet)]))

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


_scan_thread = None
_scan_lock = threading.RLock()


def start_scan(path='__all__'):
    global _scan_thread

    with _scan_lock:
        if _scan_thread:
            _scan_thread.queue(path)
        else:
            _scan_thread = ScanThread()
            _scan_thread.queue(path)
            _scan_thread.start()


def abort_scan():
    global _scan_thread

    if _scan_thread:
        _scan_thread.abort()


class ScanThread(threading.Thread):
    _scan_queue = []
    _abort = False

    def __init__(self):
        threading.Thread.__init__(self)

    def queue(self, path='__all__'):
        if not path in self._scan_queue:
            self._scan_queue.append(path)

    def abort(self):
        self._abort = True

    def run(self):
        self._abort = False
        self.progress = ThreadProgress(self, '', '')
        self.progress.start()
        start_time = time.time()
        scanned_something = False
        n = 0

        s = sublime.load_settings("SublimePHPIntel.sublime-settings")
        blacklist = s.get("scan_blacklist")

        def in_blacklist(path):
            for b in blacklist:
                if path.find(b) >= 0:
                    return True
            return False

        while True:
            with _scan_lock:
                if len(self._scan_queue) == 0:
                    global _scan_thread
                    _scan_thread = None
                    return

                filename = self._scan_queue.pop()

            if filename == '__all__':
                # Scan entire project
                for f in sublime.active_window().folders():
                    intel.reset()
                    if self._abort:
                        break
                    for root, dirs, files in os.walk(f, followlinks=True):
                        if self._abort:
                            break
                        for name in files:
                            if self._abort:
                                break
                            if os.path.splitext(name)[1] == '.php':
                                scanned_something = True
                                path = os.path.join(root, name)
                                if in_blacklist(path):
                                    continue
                                newpath, currentfile = os.path.split(path)
                                newpath, lastdir = os.path.split(newpath)
                                self.progress.message = 'Scanning .../' + lastdir + '/' + currentfile
                                d = phpparser.scan_file(path)
                                if d:
                                    intel.save(d, f, path)
                                    intel.update_index(path, *set([x['class'] for x in d]))
                                time.sleep(0.010)
                                n = n + 1
                                if n % 100 == 0:
                                    intel.save_index(f)
                    intel.save_index(f)
            elif filename:
                # Scan one file
                if os.path.splitext(filename)[1] == '.php':
                    path = filename
                    if in_blacklist(path):
                        return
                    for f in sublime.active_window().folders():
                        if path.startswith(f):
                            self.progress.message = 'Scanning ' + path
                            scanned_something = True
                            d = phpparser.scan_file(path)
                            intel.save(d, f, path)
                            intel.reset()
                            intel.load_index(f)
                            intel.update_index(path, *set([x['class'] for x in d]))
                            intel.save_index(f)
                            break

            if scanned_something:
                elapsed_s = time.time() - start_time
                if elapsed_s > 120:
                    elapsed = '{min:d}m{sec:d}s'.format(min=int(elapsed_s / 60), sec=int(elapsed_s % 60))
                else:
                    elapsed = '{sec:.2f}s'.format(sec=elapsed_s)
                self.progress.success_message = 'Scan completed in {elapsed}'.format(elapsed=elapsed)


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
                if self.success_message:
                    self.update_status(self.success_message)
                break

            before = self.i % self.size
            after = (self.size - 1) - before
            if self.message:
                self.update_status('[{before}={after}] {message}'.format(message=self.message, before=' ' * before, after=' ' * after))
            if not after:
                self.addend = -1
            if not before:
                self.addend = 1
            self.i += self.addend
            time.sleep(0.100)

    def update_status(self, message):
        sublime.set_timeout(lambda: sublime.status_message(message), 0)
