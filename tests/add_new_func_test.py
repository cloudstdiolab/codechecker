#!/usr/bin/env python
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
#                     The CodeChecker Infrastructure
#   This file is distributed under the University of Illinois Open Source
#   License. See LICENSE.TXT for details.
# -----------------------------------------------------------------------------
"""
Generate a new functional test directory and files
based on the template
"""
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

import os
import sys


def main():

    try:
        test_name = sys.argv[1]
    except IndexError:
        print("Please provide a function test name")
        sys.exit(1)

    current_dir = os.path.dirname(os.path.realpath(__file__))
    function_test_path = os.path.join(current_dir, 'functional')
    new_test_path = os.path.join(function_test_path, test_name)
    if os.path.exists(new_test_path):
        print("Functional test directory already exists.")
        sys.exit(1)

    test_skeleton_path = os.path.join(function_test_path, 'func_template')

    templ_init = os.path.join(test_skeleton_path, 'template__init__.py')
    templ_test = os.path.join(test_skeleton_path, 'template_test.py')

    with open(templ_init, 'r') as init:
        new_init_content = init.read()

    with open(templ_test, 'r') as test:
        new_test_content = test.read()

    string_to_replace = "$TEST_NAME$"
    new_init_content = new_init_content.replace(string_to_replace, test_name)
    new_test_content = new_test_content.replace(string_to_replace, test_name)

    print('Creating new funtional test directory: ' + test_name)
    os.makedirs(new_test_path)

    print('Generating new test files ...')
    new_init = os.path.join(new_test_path, "__init__.py")
    new_test = os.path.join(new_test_path, "test_"+test_name+".py")

    with open(new_init, 'w') as n_init:
        n_init.write(new_init_content)

    with open(new_test, 'w') as n_test:
        n_test.write(new_test_content)

    print('Done.')


if __name__ == "__main__":
    main()
