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


def get_intel_folder(root):
    '''
    Return full path to the intel folder
    '''
    folder = os.path.join(root, '.phpintel')
    if not os.path.exists(folder):
        os.mkdir(folder)
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
    Return the index object
    '''
    global _index
    _index = {}
    folder = get_intel_folder(root)
    index_filename = os.path.join(folder, 'index')
    if folder and os.path.exists(index_filename):
        with open(index_filename, 'rb') as f:
            _index = pickle.load(f)


def save_index(root):
    '''
    Save the index object
    '''
    folder = get_intel_folder(root)
    index_filename = os.path.join(folder, 'index')
    if folder:
        with open(index_filename, 'wb') as f:
            pickle.dump(_index, f, pickle.HIGHEST_PROTOCOL)
    

def save(declarations, filename):
    with open(filename, 'wb') as f:
        pickle.dump(declarations, f, pickle.HIGHEST_PROTOCOL)


def load(filename):
    declarations = []
    
    if os.path.exists(filename):
        with open(filename, 'rb') as f:
            declarations = pickle.load(f)

    return declarations
