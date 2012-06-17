'''
Code intelligence functions

Manages and provides functions for searching the code intelligence database.
'''

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
import hashlib
import pickle
from os.path import realpath

_index = {}
_roots = []


def reset():
    global _index
    global _roots
    _index = {}
    _roots = []


def get_intel_folder(root):
    '''
    Return full path to the intel folder
    '''
    folder = os.path.join(root, '.phpintel')
    if not os.path.exists(folder):
        os.makedirs(folder)

    return folder


def get_intel_path(root, filename):
    '''
    Return full path to an intel file
    '''
    folder = get_intel_folder(root)
    if folder:
        hashed_filename = hashlib.md5(realpath(filename)).hexdigest()
        return os.path.join(folder, hashed_filename)

    return None


def update_index(filename, *classes):
    global _index

    if _index == None:
        load_index()

    for key in _index.keys():
        if filename in _index[key]:
            _index[key].remove(filename)

    for classname in classes:
        if classname == None:
            classname = '__global__'
        if classname not in _index.keys():
            _index[classname] = [filename]
        elif filename not in _index[classname]:
            _index[classname].append(filename)


def load_index(root):
    '''
    Load the index located in root
    '''
    global _index, _roots

    folder = get_intel_folder(root)
    index_filename = os.path.join(folder, 'index')
    if folder and os.path.exists(index_filename):
        with open(index_filename, 'rb') as f:
            t = pickle.load(f)
            if '__global__' in _index:
                if '__global__' in t:
                    t['__global__'].extend(_index['__global__'])
                else:
                    t['__global__'] = _index['__global__']
                t['__global__'] = list(set(t['__global__']))
            _index.update(t)

            if root not in _roots:
                _roots.append(root)


def get_class(context):
    if len(context) == 0:
        return None, None

    if len(context) == 1:
        if context[0] in _index.keys():
            return context[0], ''

        return '__global__', context[0]

    intel = get_intel(context[0])

    for i in intel:
        if i['name'] == context[1] or i['name'] == '$' + context[1]:
            context[1] = i['returns']
            return get_class(context[1:])

    return context[0], context[1]


def get_intel(class_name):
    intel = []

    if class_name in _index:
        for filename in _index[class_name]:
            for root in _roots:
                intel.extend(load(root, filename))

    return intel


def find_completions(context, operator, context_class, context_partial, found, parsed=[]):
    if context_class in parsed:
        return
        
    # Match class names
    if context_class == '__global__':
        for i in _index:
            if i.lower().startswith(context_partial.lower()):
                found.append(
                    {
                        'class': i,
                        'name': i,
                        'kind': 'class',
                        'args': [],
                        'returns': i
                    }
                )

    # Match member names
    if context_class in _index:
        intel = get_intel(context_class)
        for i in intel:
            if not context_class in parsed:
                parsed.append(context_class)
                if i['extends']:
                    find_completions(context, operator, i['extends'], context_partial, found, parsed)
            if i['name'] and i['name'].lower().startswith(context_partial.lower()):
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


def save_index(root):
    '''
    Save the index to root
    '''
    folder = get_intel_folder(root)
    index_filename = os.path.join(folder, 'index')
    if folder:
        with open(index_filename, 'wb') as f:
            pickle.dump(_index, f, pickle.HIGHEST_PROTOCOL)
    

def save(declarations, root, filename):
    '''
    Save declarations for filename to root
    '''
    intel_filename = get_intel_path(root, filename)
    with open(intel_filename, 'wb') as f:
        pickle.dump(declarations, f, pickle.HIGHEST_PROTOCOL)


def load(root, filename):
    '''
    Load declarations for filename in root
    '''
    declarations = []
    
    intel_filename = get_intel_path(root, filename)
    if os.path.exists(intel_filename):
        with open(intel_filename, 'rb') as f:
            declarations = pickle.load(f)

    return declarations
